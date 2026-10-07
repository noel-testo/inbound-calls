"""Unit tests for the HubSpot CRM client, against fixtures via httpx.MockTransport.

No network: a MockTransport routes each (method, path) to a canned response and
records the request so we can assert the payload the client sends. Scheduling is
tested separately in test_calcom_client.py (booking moved to Cal.com).
"""

from __future__ import annotations

import json

import httpx
import pytest

from agent.hubspot import HubSpotClient, HubSpotError
from agent.hubspot.client import _phone_search_values


class Recorder:
    """Routes requests by (method, path) to canned (status, json), recording each."""

    def __init__(self, routes: dict[tuple[str, str], tuple[int, dict]]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        if key not in self.routes:
            return httpx.Response(404, json={"message": f"no route for {key}"})
        status, body = self.routes[key]
        return httpx.Response(status, json=body)

    def body(self, index: int = -1) -> dict:
        return json.loads(self.requests[index].content)


def make_client(recorder: Recorder, **kw) -> HubSpotClient:
    transport = httpx.MockTransport(recorder.handler)
    ac = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.hubapi.com",
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
    )
    return HubSpotClient("test", client=ac, **kw)


def test_phone_search_values():
    # UK +44 and 0-national both yield [national, e164-without-plus]; non-UK too.
    assert _phone_search_values("+44 7917 528642") == ["7917528642", "447917528642"]
    assert _phone_search_values("07769265959") == ["7769265959", "447769265959"]
    assert _phone_search_values("+386 40 414 559") == ["40414559", "38640414559"]


async def test_search_contact_by_phone_found():
    rec = Recorder(
        {
            ("POST", "/crm/v3/objects/contacts/search"): (
                200,
                {
                    "results": [
                        {
                            "id": "501",
                            "properties": {
                                "firstname": "Dawn",
                                "company": "Metropole FM",
                                "lifecyclestage": "customer",
                                "cf_ai_call_summary": "Prior lift fault logged.",
                            },
                        }
                    ]
                },
            ),
            ("GET", "/crm/v3/objects/contacts/501/associations/deals"): (
                200,
                {"results": [{"id": "1"}, {"id": "2"}]},
            ),
        }
    )
    client = make_client(rec)
    out = await client.search_contact_by_phone("+447917528642")
    assert out == {
        "found": True,
        "contact_id": "501",
        "first_name": "Dawn",
        "company": "Metropole FM",
        "lifecycle_stage": "customer",
        "open_deal_count": 2,
        "last_summary": "Prior lift fault logged.",
    }
    sent = rec.body(0)
    assert len(sent["filterGroups"]) == 2
    props = set()
    for g in sent["filterGroups"]:
        f = g["filters"][0]
        assert f["operator"] == "IN"
        assert f["values"] == ["7917528642", "447917528642"]
        props.add(f["propertyName"])
    assert props == {
        "hs_searchable_calculated_phone_number",
        "hs_searchable_calculated_mobile_number",
    }
    await client.aclose()


async def test_search_contact_by_phone_not_found():
    rec = Recorder({("POST", "/crm/v3/objects/contacts/search"): (200, {"results": []})})
    client = make_client(rec)
    assert await client.search_contact_by_phone("+447700900123") is None
    await client.aclose()


async def test_upsert_contact_creates_when_absent():
    rec = Recorder(
        {
            ("POST", "/crm/v3/objects/contacts/search"): (200, {"results": []}),
            ("POST", "/crm/v3/objects/contacts"): (201, {"id": "900"}),
        }
    )
    client = make_client(rec)
    out = await client.upsert_contact({"firstname": "Sam"}, email="sam@example.com")
    assert out == {"contact_id": "900", "created": True}
    assert rec.requests[-1].method == "POST"
    assert rec.body(-1) == {"properties": {"firstname": "Sam"}}
    await client.aclose()


async def test_upsert_contact_updates_when_found_by_email():
    rec = Recorder(
        {
            ("POST", "/crm/v3/objects/contacts/search"): (200, {"results": [{"id": "77"}]}),
            ("PATCH", "/crm/v3/objects/contacts/77"): (200, {"id": "77"}),
        }
    )
    client = make_client(rec)
    out = await client.upsert_contact({"cf_lead_score": "80"}, email="sam@example.com")
    assert out == {"contact_id": "77", "created": False}
    assert rec.requests[-1].method == "PATCH"
    await client.aclose()


async def test_create_deal_builds_associations():
    rec = Recorder({("POST", "/crm/v3/objects/deals"): (201, {"id": "d1"})})
    client = make_client(rec)
    out = await client.create_deal(
        {"dealname": "Metropole — lifts"}, contact_id="501", company_id="601"
    )
    assert out == {"deal_id": "d1"}
    body = rec.body(-1)
    assoc = {(a["to"]["id"], a["types"][0]["associationTypeId"]) for a in body["associations"]}
    assert assoc == {("501", 3), ("601", 5)}
    await client.aclose()


async def test_create_call_builds_associations():
    rec = Recorder({("POST", "/crm/v3/objects/calls"): (201, {"id": "c1"})})
    client = make_client(rec)
    out = await client.create_call(
        {"hs_call_title": "AI receptionist — new_enquiry"},
        contact_id="501",
        company_id="601",
        deal_id="d1",
    )
    assert out == {"call_id": "c1"}
    body = rec.body(-1)
    assoc = {(a["to"]["id"], a["types"][0]["associationTypeId"]) for a in body["associations"]}
    assert assoc == {("501", 194), ("601", 182), ("d1", 206)}
    await client.aclose()


async def test_error_raises_hubspoterror():
    rec = Recorder(
        {
            ("POST", "/crm/v3/objects/contacts/search"): (
                401,
                {"message": "unauthorized", "correlationId": "abc"},
            )
        }
    )
    client = make_client(rec)
    with pytest.raises(HubSpotError) as ei:
        await client.search_contact_by_phone("+447700900123")
    assert ei.value.status == 401
    assert ei.value.correlation_id == "abc"
    await client.aclose()
