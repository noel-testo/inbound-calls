"""Real-SQL tests: migrations + Store + the full pipeline against a throwaway local Postgres.

Skipped unless TEST_DATABASE_URL points at a database whose name ends in `_test` (the schema is
dropped and rebuilt). Never point this at Neon production.

    TEST_DATABASE_URL=postgresql://cody:cody@localhost/cody_test uv run pytest -k integration
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import asyncpg
import pytest

from agent.post_call import Services, process
from agent.store import Store
from db.migrate import apply
from tests.fakes import ApolloServer, NotionServer, SlackServer, make_settings, payload

DSN = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not urlparse(DSN).path.endswith("_test"), reason="TEST_DATABASE_URL (…_test) not set"
)


@pytest.fixture
async def store():
    conn = await asyncpg.connect(DSN)
    try:
        await conn.execute("drop schema public cascade; create schema public;")
        assert await apply(conn) == ["0001_baseline.sql", "0002_callers_apollo_notion.sql"]
        assert await apply(conn) == []
        await conn.execute(
            "insert into config (key, value) values ('scoring', $1::jsonb)",
            '{"high_value_threshold": 50, "weights": {"caller_role": {"managing_agent": 60}}}',
        )
    finally:
        await conn.close()
    s = await Store.connect(DSN)
    yield s
    await s.close()


async def test_lookup_claim_and_updates(store):
    await store.upsert_caller(
        "+447400123456",
        name="Jane Smith",
        email=None,
        organisation="Acme",
        relationship="customer",
        last_call_at=None,
    )
    caller = await store.lookup_caller("+447400123456")
    assert caller["name"] == "Jane Smith"
    await store.upsert_caller(
        "+447400123456",
        name=None,
        email="j@a.example",
        organisation=None,
        relationship="lead",
        last_call_at=None,
    )
    caller = await store.lookup_caller("+447400123456")
    assert (caller["name"], caller["email"], caller["relationship"]) == (
        "Jane Smith",
        "j@a.example",
        "customer",
    )

    await store.start_call("conv_1", "+447400123456", "+442045200783", caller["id"])
    await store.start_call("conv_1", None, None)
    call = await store.get_call("conv_1")
    assert call["caller_id"] == caller["id"] and call["cli_present"] is True

    assert await store.claim("conv_1") is True
    assert await store.claim("conv_1") is False
    await store.release("conv_1")
    assert await store.claim("conv_1") is True

    await store.update_call("conv_1", booking_id="bk_1", extraction={"intent": "new_enquiry"})
    call = await store.get_call("conv_1")
    assert call["booking_id"] == "bk_1" and call["extraction"] == {"intent": "new_enquiry"}
    with pytest.raises(ValueError):
        await store.update_call("conv_1", caller_e164="+440000000000")


async def test_pipeline_end_to_end_on_real_sql(store):
    apollo, notion, slack = ApolloServer(), NotionServer(), SlackServer()
    svc = Services(
        store=store,
        settings=make_settings(apollo_create_deals=True),
        notion=notion.client(),
        apollo=apollo.client(),
        slack=slack.client(),
    )
    await store.start_call("conv_1", "+447400123456", "+442045200783")
    call = await store.ensure_call("conv_1")
    await store.add_message(call["id"], "enquiry", "Call back", None, "normal", None)

    body = payload()
    await store.record_post_call("conv_1", body)
    assert await store.unprocessed() == ["conv_1"]
    assert await process(svc, "conv_1") == "processed"
    assert await store.unprocessed() == []
    assert await process(svc, "conv_1") == "already_processed"

    call = await store.get_call("conv_1")
    assert call["high_value"] is True and call["intent"] == "new_enquiry"
    assert call["apollo_deal_id"] and call["apollo_task_id"] and call["notion_lead_page_id"]
    assert call["slack_alerted_at"] is not None and call["post_call_lock_until"] is None
    caller = await store.lookup_caller("+447400123456")
    assert caller["apollo_contact_id"] == call["apollo_contact_id"]
    rows = await store.pool.fetch(
        "select role, text from transcripts where call_id = $1 order by seq", call["id"]
    )
    assert [r["role"] for r in rows] == ["agent", "caller"]
    assert len(apollo.deals) == 1 and len(slack.posts) == 1
