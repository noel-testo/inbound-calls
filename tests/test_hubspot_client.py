"""Unit tests for the HubSpot client, against recorded fixtures via httpx.MockTransport.

No network: a MockTransport routes each (method, path) to a canned response and
records the request so we can assert the payload the client sends.
"""

from __future__ import annotations

import json

import httpx
import pytest

from agent.hubspot import HubSpotClient, HubSpotError, uk_phone_variants


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


def test_uk_phone_variants():
    assert uk_phone_variants("+447700900123") == [
        "+447700900123",
        "07700900123",
        "+44 7700 900123",
    ]
    assert uk_phone_variants("07700900123") == [
        "07700900123",
        "+447700900123",
        "+44 7700 900123",
    ]
    assert uk_phone_variants("+13105551234") == ["+13105551234"]
    assert uk_phone_variants(" 077 00900123 ") == [
        "07700900123",
        "+447700900123",
        "+44 7700 900123",
    ]


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
    out = await client.search_contact_by_phone("+447700900123")
    assert out == {
        "found": True,
        "contact_id": "501",
        "first_name": "Dawn",
        "company": "Metropole FM",
        "lifecycle_stage": "customer",
        "open_deal_count": 2,
        "last_summary": "Prior lift fault logged.",
    }
    # Searches both phone props across both number formats.
    sent = rec.body(0)
    pairs = {
        (g["filters"][0]["propertyName"], g["filters"][0]["value"]) for g in sent["filterGroups"]
    }
    assert pairs == {
        ("phone", "+447700900123"),
        ("phone", "07700900123"),
        ("phone", "+44 7700 900123"),
        ("mobilephone", "+447700900123"),
        ("mobilephone", "07700900123"),
        ("mobilephone", "+44 7700 900123"),
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


async def test_get_availability_parses_and_filters():
    rec = Recorder(
        {
            ("GET", "/scheduler/2026-03/meetings/meeting-links/book/disco"): (
                200,
                {
                    "linkAvailability": {
                        "linkAvailabilityByDuration": {
                            "1800000": {
                                "availabilities": [
                                    {"startMillisUtc": 1760000000000},  # in-window
                                    {"startMillisUtc": 1760003600000},  # in-window
                                    {"startMillisUtc": 1770000000000},  # out of window
                                ]
                            }
                        }
                    }
                },
            )
        }
    )
    client = make_client(rec, meeting_slug="disco")
    out = await client.get_availability("2025-10-09T00:00:00Z", "2025-10-09T23:59:59Z")
    assert out["slots"] == ["2025-10-09T08:53:20Z", "2025-10-09T09:53:20Z"]
    await client.aclose()


async def test_get_availability_requires_slug():
    rec = Recorder({})
    client = make_client(rec)  # no meeting_slug
    with pytest.raises(HubSpotError):
        await client.get_availability("2025-10-09T00:00:00Z", "2025-10-09T23:59:59Z")
    await client.aclose()


async def test_book_meeting_sends_epoch_ms_and_reads_back():
    rec = Recorder(
        {("POST", "/scheduler/2026-03/meetings/meeting-links/book"): (200, {"id": "mtg-1"})}
    )
    client = make_client(rec, meeting_slug="disco")
    out = await client.book_meeting(
        "2025-10-09T09:00:00Z",
        "Sam",
        "Jones",
        "sam@example.com",
        phone="+447700900123",
        organisation="Acme",
    )
    assert out == {
        "meeting_id": "mtg-1",
        "start_iso": "2025-10-09T09:00:00Z",
        "confirmation_sent": True,
    }
    body = rec.body(-1)
    assert body["slug"] == "disco"
    assert body["startTime"] == 1760000400000
    assert body["duration"] == 1800000
    names = {f["name"] for f in body["formFields"]}
    assert {"email", "firstName", "lastName", "phone", "company"} <= names
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
