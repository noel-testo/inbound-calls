"""Test doubles: an in-memory Store and stateful mock HTTP servers for Apollo, Notion and Slack.

The mock servers sit behind httpx.MockTransport, so the real clients' request code runs unchanged
and the tests assert on what actually went over the wire.
"""

from __future__ import annotations

import itertools
import json
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qsl

import httpx

from agent.apollo import ApolloClient
from agent.notion import NotionClient
from agent.post_call import Services
from agent.settings import Settings
from agent.slack import SlackNotifier
from agent.store.db import CALL_COLUMNS, CALLER_COLUMNS

SCORING = {
    "high_value_threshold": 50,
    "weights": {
        "caller_role": {"managing_agent": 30, "landlord_owner": 20},
        "asset_type": {"lifts": 15},
        "estate_size": {"bands": [{"min": 10, "points": 20}, {"min": 1, "points": 0}]},
        "current_connectivity": {"pstn_copper": 20},
    },
}


class FakeStore:
    def __init__(self):
        self.calls: dict[str, dict] = {}
        self.callers: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.events: list[tuple] = []
        self.transcripts: dict[str, list] = {}
        self.config = {
            "greeting": {"greeting": "Thanks for calling.\n  Hello."},
            "scoring": SCORING,
        }
        self.terms = ["ControlFreq", "EN81-28"]
        self.closed = False

    async def close(self):
        self.closed = True

    async def lookup_caller(self, phone):
        return self.callers.get(phone)

    async def load_config(self, key):
        return self.config.get(key)

    async def active_terms(self, limit=100):
        return self.terms[:limit]

    def _new_call(self, conversation_id):
        return {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "caller_e164": None,
            "called_number": None,
            "caller_id": None,
            "processed_at": None,
            "post_call_payload": None,
            "post_call_lock_until": None,
            **{c: None for c in CALL_COLUMNS},
        }

    async def start_call(self, conversation_id, caller_e164, called_number, caller_id=None):
        call = self.calls.setdefault(conversation_id, self._new_call(conversation_id))
        call["caller_e164"] = call["caller_e164"] or caller_e164
        call["called_number"] = call["called_number"] or called_number
        call["caller_id"] = call["caller_id"] or caller_id
        return call["id"]

    async def get_call(self, conversation_id):
        call = self.calls.get(conversation_id)
        return dict(call) if call else None

    async def ensure_call(self, conversation_id):
        self.calls.setdefault(conversation_id, self._new_call(conversation_id))
        return await self.get_call(conversation_id)

    async def add_message(self, call_id, category, summary, callback_number, urgency, site):
        mid = str(uuid.uuid4())
        self.messages.append(
            {
                "id": mid,
                "call_id": call_id,
                "category": category,
                "summary": summary,
                "callback_number": callback_number,
                "urgency": urgency,
                "site": site,
            }
        )
        return mid

    async def messages_for(self, call_id):
        return [m for m in self.messages if m["call_id"] == call_id]

    async def log_event(self, call_id, type_, payload=None):
        self.events.append((call_id, type_, payload or {}))

    async def record_post_call(self, conversation_id, payload):
        call = self.calls.setdefault(conversation_id, self._new_call(conversation_id))
        call["post_call_payload"] = payload
        return await self.get_call(conversation_id)

    async def ingest(
        self,
        conversation_id,
        *,
        caller_e164,
        called_number,
        started_at,
        ended_at,
        duration_s,
        turns,
    ):
        call = self.calls[conversation_id]
        call["caller_e164"] = call["caller_e164"] or caller_e164
        call["called_number"] = call["called_number"] or called_number
        call.update(started_at=started_at, ended_at=ended_at, duration_s=duration_s)
        self.transcripts[call["id"]] = list(turns)
        return await self.get_call(conversation_id)

    async def upsert_caller(self, phone, *, name, email, organisation, relationship, last_call_at):
        row = self.callers.get(phone)
        if not row:
            row = {
                "id": str(uuid.uuid4()),
                "phone_e164": phone,
                "name": None,
                "email": None,
                "organisation": None,
                "relationship": "lead",
                "apollo_contact_id": None,
                "apollo_account_id": None,
                "first_seen_at": datetime.now(UTC),
            }
            self.callers[phone] = row
        row["name"] = name or row["name"]
        row["email"] = email or row["email"]
        row["organisation"] = organisation or row["organisation"]
        if row["relationship"] != "customer":
            row["relationship"] = relationship
        row["last_call_at"] = last_call_at
        return dict(row)

    async def link_caller(self, conversation_id, caller_id):
        self.calls[conversation_id]["caller_id"] = caller_id

    async def claim(self, conversation_id, seconds=300):
        call = self.calls[conversation_id]
        if call["post_call_lock_until"]:
            return False
        call["post_call_lock_until"] = "locked"
        return True

    async def release(self, conversation_id):
        self.calls[conversation_id]["post_call_lock_until"] = None

    async def update_call(self, conversation_id, **cols):
        assert set(cols) <= CALL_COLUMNS, set(cols) - CALL_COLUMNS
        self.calls[conversation_id].update(cols)

    async def update_caller(self, caller_id, **cols):
        assert set(cols) <= CALLER_COLUMNS
        for row in self.callers.values():
            if row["id"] == caller_id:
                row.update(cols)

    async def get_caller(self, caller_id):
        return next((dict(r) for r in self.callers.values() if r["id"] == caller_id), None)

    async def unprocessed(self, limit=50):
        return [
            c for c, v in self.calls.items() if v["post_call_payload"] and not v["processed_at"]
        ]


def _hexid(counter) -> str:
    return f"{next(counter):024x}"


class ApolloServer:
    """Stateful fake of the Apollo endpoints Cody uses; records every request."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.accounts: dict[str, dict] = {}
        self.contacts: dict[str, dict] = {}
        self.calls: dict[str, dict] = {}
        self.deals: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.fail_paths: set[str] = set()
        self._ids = itertools.count(1)

    def paths(self) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requests]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/v1")
        if path in self.fail_paths:
            return httpx.Response(500, json={"error": "boom"})
        body = json.loads(request.content) if request.content else {}
        if request.method == "POST" and path == "/accounts/search":
            name = body["q_organization_name"].casefold()
            hits = [a for a in self.accounts.values() if a["name"].casefold() == name]
            return httpx.Response(200, json={"accounts": hits})
        if request.method == "POST" and path == "/accounts":
            acc = {"id": _hexid(self._ids), **body}
            self.accounts[acc["id"]] = acc
            return httpx.Response(200, json={"account": acc})
        if request.method == "POST" and path == "/contacts/search":
            hits = [c for c in self.contacts.values() if c.get("email") == body["q_keywords"]]
            return httpx.Response(200, json={"contacts": hits})
        if request.method == "POST" and path == "/contacts":
            fields = {k: v for k, v in body.items() if k != "run_dedupe"}
            con = {"id": _hexid(self._ids), **fields}
            self.contacts[con["id"]] = con
            return httpx.Response(200, json={"contact": con})
        if request.method == "PATCH" and path.startswith("/contacts/"):
            con = self.contacts[path.rsplit("/", 1)[1]]
            con.update(body)
            return httpx.Response(200, json={"contact": con})
        if request.method == "POST" and path == "/phone_calls":
            params = dict(parse_qsl(request.url.query.decode()))
            ident = params["call_identifier"]
            existing = next((c for c in self.calls.values() if c["call_identifier"] == ident), None)
            rec = existing or {"id": _hexid(self._ids)}
            rec.update(params)
            self.calls[rec["id"]] = rec
            return httpx.Response(200, json={"phone_call": rec})
        if request.method == "POST" and path == "/opportunities":
            deal = {"id": _hexid(self._ids), **body}
            self.deals[deal["id"]] = deal
            return httpx.Response(200, json={"opportunity": deal})
        if request.method == "POST" and path == "/tasks":
            task = {"id": _hexid(self._ids), **body}
            self.tasks[task["id"]] = task
            return httpx.Response(200, json={"task": task})
        return httpx.Response(404, json={"error": f"no route {request.method} {path}"})

    def client(self) -> ApolloClient:
        ac = httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler), base_url="https://api.apollo.io/api/v1"
        )
        return ApolloClient("test", client=ac)


class NotionServer:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.pages: dict[str, dict] = {}
        self.databases: dict[str, dict] = {}
        self._ids = itertools.count(1)

    def in_db(self, db: str) -> list[dict]:
        return [p for p in self.pages.values() if p["parent"]["database_id"] == db]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if request.method == "POST" and path == "/v1/pages":
            pid = f"{next(self._ids):08d}-0000-0000-0000-000000000000"
            page = {
                "id": pid,
                "parent": body["parent"],
                "properties": body["properties"],
                "children": list(body.get("children") or []),
            }
            self.pages[pid] = page
            return httpx.Response(200, json={"id": pid, "url": f"https://www.notion.so/{pid}"})
        if request.method == "PATCH" and path.startswith("/v1/pages/"):
            page = self.pages[path.rsplit("/", 1)[1]]
            page["properties"].update(body["properties"])
            return httpx.Response(200, json={"id": page["id"]})
        if request.method == "PATCH" and path.startswith("/v1/blocks/"):
            self.pages[path.split("/")[3]]["children"] += body["children"]
            return httpx.Response(200, json={})
        if request.method == "POST" and path.endswith("/query"):
            db = path.split("/")[3]
            want = body["filter"]["rich_text"]["equals"]
            hits = [
                {"id": p["id"]}
                for p in self.in_db(db)
                if p["properties"]["Conversation ID"]["rich_text"][0]["text"]["content"] == want
            ]
            return httpx.Response(200, json={"results": hits[:1]})
        if path.startswith("/v1/databases/"):
            db = self.databases.setdefault(
                path.split("/")[3], {"properties": {"Name": {"type": "title"}}}
            )
            if request.method == "PATCH":
                db["properties"].update(body["properties"])
            return httpx.Response(200, json=db)
        return httpx.Response(404, json={"message": "no route"})

    def client(self) -> NotionClient:
        ac = httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler), base_url="https://api.notion.com"
        )
        return NotionClient("test", client=ac)


class SlackServer:
    def __init__(self):
        self.posts: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.posts.append(json.loads(request.content))
        return httpx.Response(200, text="ok")

    def client(self) -> SlackNotifier:
        ac = httpx.AsyncClient(transport=httpx.MockTransport(self.handler))
        return SlackNotifier("https://hooks.slack.test/services/T/B/X", client=ac)


def make_settings(**kw) -> Settings:
    base = dict(
        tool_secret="tool-secret",
        webhook_secret="hmac-secret",
        apollo_api_key="k",
        apollo_user_id="u" * 24,
        notion_api_key="n",
        notion_leads_db_id="leads-db",
        notion_transcripts_db_id="transcripts-db",
        slack_webhook_url="https://hooks.slack.test/x",
    )
    base.update(kw)
    return Settings(**base)


def make_services(settings: Settings | None = None, store: FakeStore | None = None):
    apollo, notion, slack = ApolloServer(), NotionServer(), SlackServer()
    svc = Services(
        store=store or FakeStore(),
        settings=settings or make_settings(),
        notion=notion.client(),
        apollo=apollo.client(),
        slack=slack.client(),
    )
    return svc, apollo, notion, slack


def dc(**values) -> dict:
    return {k: {"data_collection_id": k, "value": v, "rationale": ""} for k, v in values.items()}


QUALIFIED = dc(
    intent="new_enquiry",
    caller_name="Jane Smith",
    organisation="Acme Estates",
    caller_role="managing_agent",
    asset_type="lifts",
    estate_size=40,
    estate_size_unit="lifts",
    current_connectivity="pstn_copper",
    driver="pstn_switch_off",
    timeline="1_3_months",
    decision_authority="decision_maker",
    contact_email="jane@acme.example",
    notes="",
)
UNQUALIFIED = dc(
    intent="new_enquiry",
    caller_name="Bob Jones",
    organisation="",
    caller_role="landlord_owner",
    asset_type="lifts",
    estate_size=1,
    estate_size_unit="lifts",
    current_connectivity="unknown",
    driver="unknown",
    timeline="unknown",
    decision_authority="researcher",
    contact_email="",
)


def payload(
    conversation_id="conv_1", caller="+447400123456", results=None, summary="Wants 4G units."
):
    return {
        "type": "post_call_transcription",
        "event_timestamp": 1793000000,
        "data": {
            "agent_id": "agent_x",
            "conversation_id": conversation_id,
            "status": "done",
            "transcript": [
                {"role": "agent", "message": "Thanks for calling.", "time_in_call_secs": 0},
                {"role": "user", "message": "Hi, it's Jane from Acme.", "time_in_call_secs": 4},
                {"role": "agent", "message": None, "time_in_call_secs": 6},
            ],
            "metadata": {
                "start_time_unix_secs": 1793000000,
                "call_duration_secs": 95,
                "termination_reason": "end_call tool was called",
                "phone_call": {
                    "direction": "inbound",
                    "external_number": caller,
                    "agent_number": "+442045200783",
                    "type": "sip_trunking",
                },
            },
            "analysis": {
                "transcript_summary": summary,
                "data_collection_results": QUALIFIED if results is None else results,
            },
            "conversation_initiation_client_data": {"dynamic_variables": {}},
        },
    }
