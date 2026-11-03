"""HTTP surface: secret header on the three tools; no state, no conversation-init or post-call."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agent.app import create_app
from agent.settings import Settings


class FakeCalCom:
    def __init__(self):
        self.booked = []

    async def get_availability(self, from_iso, to_iso, **kw):
        return {"slots": ["2026-11-03T09:00:00Z"]}

    async def book_meeting(self, start_iso, name, email, organisation, **kw):
        self.booked.append((start_iso, name, email, organisation, kw))
        return {"booking_id": "bk_1", "start_iso": start_iso, "status": "accepted"}


def make_client():
    calcom = FakeCalCom()
    app = create_app(Settings(tool_secret="tool-secret"), calcom=calcom)
    return TestClient(app), calcom


H = {"X-Cody-Secret": "tool-secret"}


def test_tools_require_the_secret():
    client, _ = make_client()
    with client:
        for path in ("/tools/take_message", "/tools/check_availability", "/tools/book_meeting"):
            assert client.post(path, json={}).status_code == 401
            assert client.post(path, json={}, headers={"X-Cody-Secret": "nope"}).status_code == 401


def test_neon_era_endpoints_are_gone():
    client, _ = make_client()
    with client:
        for path in ("/elevenlabs/conversation-init", "/elevenlabs/post-call"):
            assert client.post(path, json={}, headers=H).status_code == 404


def test_tools_over_http():
    client, calcom = make_client()
    with client:
        slots = client.post(
            "/tools/check_availability",
            headers=H,
            json={
                "conversation_id": "conv_1",
                "from_iso": "2026-11-03T08:00:00Z",
                "to_iso": "2026-11-03T17:00:00Z",
            },
        ).json()
        booked = client.post(
            "/tools/book_meeting",
            headers=H,
            json={
                "conversation_id": "conv_1",
                "slot_iso": slots["slots"][0],
                "name": "Jane Smith",
                "email": "jane@acme.example",
                "organisation": "Acme",
                "caller_phone": "07400 123456",
            },
        ).json()
        msg = client.post(
            "/tools/take_message",
            headers=H,
            json={
                "conversation_id": "conv_1",
                "category": "enquiry",
                "summary": "Call back re lifts",
                "urgency": "urgent!",
            },
        ).json()
    assert booked["booking_id"] == "bk_1"
    assert calcom.booked[0][4]["phone"] == "+447400123456"  # CLI used as the attendee phone
    assert msg["message_id"]


def test_book_meeting_prefers_the_spoken_phone_over_the_cli():
    client, calcom = make_client()
    body = {
        "conversation_id": "conv_1",
        "slot_iso": "2026-11-03T09:00:00Z",
        "name": "Jane Smith",
        "email": "jane@acme.example",
        "organisation": "Acme",
        "phone": "+447700900123",
        "caller_phone": "+447400123456",
    }
    with client:
        client.post("/tools/book_meeting", headers=H, json=body)
    assert calcom.booked[0][4]["phone"] == "+447700900123"


def test_take_message_needs_conversation_and_summary():
    client, _ = make_client()
    with client:
        r = client.post("/tools/take_message", headers=H, json={"conversation_id": "c"}).json()
        ids = {
            client.post(
                "/tools/take_message", headers=H, json={"conversation_id": "c", "summary": "x"}
            ).json()["message_id"]
            for _ in range(2)
        }
    assert r["status"] == "failed"
    assert len(ids) == 2


def test_tool_bodies_must_be_json_objects():
    client, _ = make_client()
    with client:
        r = client.post("/tools/take_message", headers=H, content=b"{not json")
        assert r.status_code == 400
        assert client.post("/tools/take_message", headers=H, json=[]).status_code == 400
