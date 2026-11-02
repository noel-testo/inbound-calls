"""Wire-level checks for the Apollo and Notion clients."""

from __future__ import annotations

import json

import httpx
import pytest

from agent.apollo import ApolloClient, ApolloError
from agent.notion import client as n
from agent.slack import qualified_call_text
from tests.fakes import NotionServer


def recorder(status=200, body=None):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body if body is not None else {})

    return seen, handler


async def test_apollo_sends_api_key_header_and_dedupes_contacts():
    seen, handler = recorder(body={"contact": {"id": "c1"}})
    ac = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.apollo.io/api/v1"
    )
    client = ApolloClient("k", client=ac)
    await client.create_contact({"first_name": "Jane"})
    req = seen[0]
    assert req.url.path == "/api/v1/contacts" and req.headers["x-api-key"] == "k"
    assert json.loads(req.content) == {"first_name": "Jane", "run_dedupe": True}


async def test_apollo_log_call_uses_query_params_with_call_identifier():
    seen, handler = recorder(body={"phone_call": {"id": "p1"}})
    client = ApolloClient(
        "k",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.apollo.io/api/v1"
        ),
    )
    await client.log_call(
        call_identifier="conv_1",
        contact_id="c1",
        account_id=None,
        from_number="+447400123456",
        to_number="+442045200783",
        start_time=None,
        end_time=None,
        duration=95,
        note="n",
        user_id="u1",
    )
    params = seen[0].url.params
    assert params["call_identifier"] == "conv_1" and params["logged"] == "true"
    assert params["user_id[]"] == "u1" and params["duration"] == "95"
    assert "account_id" not in params


async def test_apollo_account_match_is_exact_and_errors_raise():
    seen, handler = recorder(
        body={
            "accounts": [
                {"id": "a1", "name": "Acme Estates Ltd"},
                {"id": "a2", "name": "acme estates"},
            ]
        }
    )
    client = ApolloClient(
        "k",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://api.apollo.io/api/v1"
        ),
    )
    assert (await client.find_account("Acme Estates"))["id"] == "a2"

    _, bad = recorder(status=422, body={"error": "invalid"})
    client = ApolloClient(
        "k",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(bad), base_url="https://api.apollo.io/api/v1"
        ),
    )
    with pytest.raises(ApolloError, match="422"):
        await client.create_task(user_id="u", contact_id="c", due_at="x", title="t", note="n")


async def test_notion_long_transcripts_are_chunked():
    server = NotionServer()
    client = server.client()
    blocks = [n.paragraph("x" * 4500)] + [n.paragraph(f"turn {i}") for i in range(149)]
    assert len(blocks[0]["paragraph"]["rich_text"]) == 3
    page = await client.create_page("db", {"Conversation ID": n.rich("c1")}, blocks)
    assert len(server.pages[page["id"]]["children"]) == 150
    first = json.loads(server.requests[0].content)
    assert len(first["children"]) == 100
    assert server.requests[0].headers["Notion-Version"] == "2022-06-28"
    assert await client.find_by_conversation("db", "c1") == page["id"]
    assert await client.find_by_conversation("db", "c2") is None
    assert n.rich("y" * 3000)["rich_text"][0]["text"]["content"] == "y" * 2000


def test_slack_text_is_plain_and_complete():
    text = qualified_call_text(
        name="Jane Smith",
        organisation="Acme",
        phone="+447400123456",
        email=None,
        score=85,
        outcome="qualified_not_booked",
        summary="Wants 4G units.",
        notion_url="https://www.notion.so/x",
        apollo_contact_url=None,
    )
    assert text.splitlines()[0] == "*Qualified call:* Jane Smith, Acme"
    assert "please call back" in text and "<https://www.notion.so/x|Notion>" in text
    assert "Apollo" not in text
