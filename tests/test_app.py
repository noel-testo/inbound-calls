"""HTTP surface: secret header on init/tools, HMAC on post-call, background pipeline."""

from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient

from agent.app import create_app
from agent.security import sign
from tests.fakes import FakeStore, make_services, make_settings, payload


class FakeCalCom:
    def __init__(self):
        self.booked = []

    async def get_availability(self, from_iso, to_iso, **kw):
        return {"slots": ["2026-11-03T09:00:00Z"]}

    async def book_meeting(self, start_iso, name, email, organisation, **kw):
        self.booked.append((start_iso, name, email, organisation, kw))
        return {"booking_id": "bk_1", "start_iso": start_iso, "status": "accepted"}


def make_client():
    settings = make_settings()
    store = FakeStore()
    svc, apollo, notion, slack = make_services(settings, store)
    calcom = FakeCalCom()
    app = create_app(settings, store=store, calcom=calcom, services=svc)
    return TestClient(app), store, calcom, apollo, notion, slack


def signed(body: dict, secret: str = "hmac-secret", ts: int | None = None):
    raw = json.dumps(body).encode()
    return raw, {
        "ElevenLabs-Signature": sign(raw, secret, ts or int(time.time())),
        "Content-Type": "application/json",
    }


def test_init_and_tools_require_the_secret():
    client, *_ = make_client()
    with client:
        for path in (
            "/elevenlabs/conversation-init",
            "/tools/take_message",
            "/tools/check_availability",
            "/tools/book_meeting",
        ):
            assert client.post(path, json={}).status_code == 401
            assert client.post(path, json={}, headers={"X-Cody-Secret": "nope"}).status_code == 401


def test_conversation_init_over_http():
    client, store, *_ = make_client()
    with client:
        r = client.post(
            "/elevenlabs/conversation-init",
            headers={"X-Cody-Secret": "tool-secret"},
            json={"caller_id": "+447400123456", "conversation_id": "conv_1"},
        )
    assert r.status_code == 200
    assert r.json()["dynamic_variables"]["caller_known"] == "false"
    assert "conv_1" in store.calls


def test_tools_over_http():
    client, store, calcom, *_ = make_client()
    h = {"X-Cody-Secret": "tool-secret"}
    with client:
        client.post(
            "/elevenlabs/conversation-init",
            headers=h,
            json={"caller_id": "+447400123456", "conversation_id": "conv_1"},
        )
        slots = client.post(
            "/tools/check_availability",
            headers=h,
            json={
                "conversation_id": "conv_1",
                "from_iso": "2026-11-03T08:00:00Z",
                "to_iso": "2026-11-03T17:00:00Z",
            },
        ).json()
        booked = client.post(
            "/tools/book_meeting",
            headers=h,
            json={
                "conversation_id": "conv_1",
                "slot_iso": slots["slots"][0],
                "name": "Jane Smith",
                "email": "jane@acme.example",
                "organisation": "Acme",
            },
        ).json()
        msg = client.post(
            "/tools/take_message",
            headers=h,
            json={
                "conversation_id": "conv_1",
                "category": "enquiry",
                "summary": "Call back re lifts",
                "urgency": "urgent!",
            },
        ).json()
    assert booked["booking_id"] == "bk_1"
    assert calcom.booked[0][4]["phone"] == "+447400123456"  # CLI used as the attendee phone
    assert store.calls["conv_1"]["booking_id"] == "bk_1"
    assert msg["message_id"] and store.messages[0]["urgency"] == "normal"


def test_post_call_rejects_bad_or_stale_signatures():
    client, store, *_ = make_client()
    with client:
        raw, h = signed(payload(), secret="wrong")
        assert client.post("/elevenlabs/post-call", content=raw, headers=h).status_code == 401
        raw, h = signed(payload(), ts=int(time.time()) - 3600)
        assert client.post("/elevenlabs/post-call", content=raw, headers=h).status_code == 401
        raw = json.dumps(payload()).encode()
        assert client.post("/elevenlabs/post-call", content=raw).status_code == 401
    assert store.calls == {}


def test_post_call_accepts_signed_payload_and_runs_pipeline():
    client, store, _, apollo, notion, slack = make_client()
    raw, h = signed(payload())
    with client:
        r = client.post("/elevenlabs/post-call", content=raw, headers=h)
        assert r.status_code == 200
        assert store.calls["conv_1"]["processed_at"] is not None
        r2 = client.post("/elevenlabs/post-call", content=raw, headers=h)
        assert r2.status_code == 200
    assert len(apollo.contacts) == 1 and len(slack.posts) == 1 and len(notion.pages) == 2


def test_post_call_rejects_signed_but_malformed_bodies_with_400():
    client, store, *_ = make_client()
    bodies = [
        b"{not json",
        b"\xff\xfe",
        b"[]",
        b'"post_call_transcription"',
        json.dumps({"type": "post_call_transcription", "data": "conv_1"}).encode(),
        json.dumps({"type": "post_call_transcription", "data": {}}).encode(),
        json.dumps({"type": "post_call_transcription", "data": {"conversation_id": 7}}).encode(),
    ]
    with client:
        for raw in bodies:
            h = {"ElevenLabs-Signature": sign(raw, "hmac-secret", int(time.time()))}
            r = client.post("/elevenlabs/post-call", content=raw, headers=h)
            assert r.status_code == 400, raw
    assert store.calls == {}


def test_post_call_ignores_other_event_types():
    client, store, *_ = make_client()
    raw, h = signed({"type": "post_call_audio", "data": {"conversation_id": "c"}})
    with client:
        r = client.post("/elevenlabs/post-call", content=raw, headers=h)
    assert r.status_code == 200 and store.calls == {}
