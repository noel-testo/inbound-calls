"""Unit tests for the Cal.com client, against fixtures via httpx.MockTransport.

No network: a MockTransport routes each (method, path) to a canned response and
records the request so we can assert the payload and the cal-api-version header.
"""

from __future__ import annotations

import json

import httpx
import pytest

from agent.calcom import CalComClient, CalComError

EVENT_TYPE_ID = 7103844


class Recorder:
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


def make_client(recorder: Recorder) -> CalComClient:
    transport = httpx.MockTransport(recorder.handler)
    ac = httpx.AsyncClient(
        transport=transport,
        base_url="https://api.cal.com",
        headers={"Authorization": "Bearer test", "Content-Type": "application/json"},
    )
    return CalComClient("test", EVENT_TYPE_ID, client=ac)


async def test_get_availability_parses_filters_and_normalises_to_utc():
    rec = Recorder(
        {
            ("GET", "/v2/slots"): (
                200,
                {
                    "data": {
                        "2026-10-06": [
                            {"start": "2026-10-06T10:00:00.000+01:00"},  # 09:00Z, in-window
                            {"start": "2026-10-06T10:15:00.000+01:00"},  # 09:15Z, in-window
                        ],
                        "2026-10-07": [
                            {"start": "2026-10-07T09:00:00.000+01:00"},  # next day, out of window
                        ],
                    }
                },
            )
        }
    )
    client = make_client(rec)
    out = await client.get_availability("2026-10-06T00:00:00Z", "2026-10-06T23:59:59Z")
    assert out["slots"] == ["2026-10-06T09:00:00Z", "2026-10-06T09:15:00Z"]
    # Slots request carries the slots api version and the event type.
    req = rec.requests[0]
    assert req.headers["cal-api-version"] == "2024-09-04"
    assert req.url.params["eventTypeId"] == str(EVENT_TYPE_ID)
    await client.aclose()


async def test_get_availability_caps_at_limit():
    slots = [{"start": f"2026-10-06T{h:02d}:00:00.000Z"} for h in range(10)]
    rec = Recorder({("GET", "/v2/slots"): (200, {"data": {"2026-10-06": slots}})})
    client = make_client(rec)
    out = await client.get_availability("2026-10-06T00:00:00Z", "2026-10-06T23:59:59Z", limit=3)
    assert len(out["slots"]) == 3
    await client.aclose()


async def test_book_meeting_builds_payload_and_reads_back():
    rec = Recorder(
        {
            ("POST", "/v2/bookings"): (
                201,
                {"data": {"uid": "bk_123", "status": "accepted", "start": "2026-10-06T09:00:00Z"}},
            )
        }
    )
    client = make_client(rec)
    out = await client.book_meeting(
        "2026-10-06T10:00:00.000+01:00",
        "Sam Jones",
        "sam@example.com",
        "Acme Lifts",
        phone="+447700900123",
        notes="2 lifts, PSTN switch-off",
    )
    assert out == {
        "booking_id": "bk_123",
        "start_iso": "2026-10-06T09:00:00Z",
        "status": "accepted",
    }
    body = rec.body(-1)
    assert body["eventTypeId"] == EVENT_TYPE_ID
    assert body["start"] == "2026-10-06T09:00:00Z"  # normalised to UTC
    assert body["attendee"] == {
        "name": "Sam Jones",
        "email": "sam@example.com",
        "timeZone": "Europe/London",
        "language": "en",
        "phoneNumber": "+447700900123",
    }
    assert body["bookingFieldsResponses"] == {
        "Company": "Acme Lifts",
        "title": "Intro call – Acme Lifts",
        "notes": "2 lifts, PSTN switch-off",
    }
    assert rec.requests[-1].headers["cal-api-version"] == "2024-08-13"
    await client.aclose()


async def test_book_meeting_omits_optional_fields():
    rec = Recorder(
        {("POST", "/v2/bookings"): (201, {"data": {"uid": "bk_1", "status": "accepted"}})}
    )
    client = make_client(rec)
    await client.book_meeting("2026-10-06T09:00:00Z", "Sam", "sam@example.com", "Acme")
    body = rec.body(-1)
    assert "phoneNumber" not in body["attendee"]
    assert "notes" not in body["bookingFieldsResponses"]
    assert body["bookingFieldsResponses"]["title"] == "Intro call – Acme"
    await client.aclose()


async def test_error_raises_calcomerror():
    rec = Recorder({("POST", "/v2/bookings"): (422, {"error": {"message": "no availability"}})})
    client = make_client(rec)
    with pytest.raises(CalComError) as ei:
        await client.book_meeting("2026-10-06T09:00:00Z", "Sam", "sam@example.com", "Acme")
    assert ei.value.status == 422
    assert "no availability" in ei.value.message
    await client.aclose()
