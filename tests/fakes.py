"""Test doubles: a stateful mock Notion server and data-collection fixtures.

The mock server sits behind httpx.MockTransport, so the real client's request code runs unchanged
and the tests assert on what actually went over the wire.
"""

from __future__ import annotations

import itertools
import json

import httpx

from agent.notion import NotionClient


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
