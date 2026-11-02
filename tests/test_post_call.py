"""Post-call pipeline: Neon ingest, Notion rows, Apollo (qualified only), Slack, idempotency."""

from __future__ import annotations

from agent.post_call import process
from tests.fakes import UNQUALIFIED, FakeStore, make_services, make_settings, payload


async def run(svc, body):
    cid = body["data"]["conversation_id"]
    await svc.store.record_post_call(cid, body)
    return await process(svc, cid)


async def test_qualified_call_runs_every_step_once():
    svc, apollo, notion, slack = make_services()
    assert await run(svc, payload()) == "processed"

    call = svc.store.calls["conv_1"]
    assert call["high_value"] is True and call["outcome"] == "qualified_not_booked"
    assert call["lead_score"] == 85
    assert svc.store.transcripts[call["id"]][1][0] == "caller"
    assert len(svc.store.transcripts[call["id"]]) == 2  # the empty tool-call turn is dropped

    assert len(notion.in_db("transcripts-db")) == 1
    [lead] = notion.in_db("leads-db")
    assert lead["properties"]["Qualified"] == {"checkbox": True}
    assert lead["properties"]["Review"] == {"select": {"name": "To review"}}
    assert lead["properties"]["Apollo contact"]["url"].endswith(call["apollo_contact_id"])

    [account] = apollo.accounts.values()
    [contact] = apollo.contacts.values()
    assert account["name"] == "Acme Estates"
    assert contact["account_id"] == account["id"]
    assert contact["email"] == "jane@acme.example"
    assert contact["first_name"] == "Jane" and contact["last_name"] == "Smith"
    assert contact["mobile_phone"] == "+447400123456"
    [logged] = apollo.calls.values()
    assert logged["call_identifier"] == "conv_1"
    assert logged["contact_id"] == contact["id"] and logged["account_id"] == account["id"]
    assert "Wants 4G units." in logged["note"]
    assert logged["to_number"] == "+442045200783"
    [task] = apollo.tasks.values()
    assert task["contact_id"] == contact["id"] and task["status"] == "scheduled"

    caller = svc.store.callers["+447400123456"]
    assert caller["apollo_contact_id"] == contact["id"]
    assert caller["apollo_account_id"] == account["id"]
    assert call["apollo_call_id"] == logged["id"] and call["apollo_task_id"] == task["id"]

    assert len(slack.posts) == 1
    assert "Jane Smith, Acme Estates" in slack.posts[0]["text"]


async def test_deal_creation_is_off_by_default():
    svc, apollo, _, _ = make_services()
    await run(svc, payload())
    assert apollo.deals == {}
    assert not any("/opportunities" in p for p in apollo.paths())


async def test_deal_created_on_account_when_flag_on():
    svc, apollo, notion, _ = make_services(
        make_settings(apollo_create_deals=True, apollo_deal_stage_id="stage1")
    )
    await run(svc, payload())
    [deal] = apollo.deals.values()
    [account] = apollo.accounts.values()
    assert deal["account_id"] == account["id"]
    assert deal["opportunity_stage_id"] == "stage1"
    assert svc.store.calls["conv_1"]["apollo_deal_id"] == deal["id"]
    assert notion.in_db("leads-db")[0]["properties"]["Apollo deal"]["url"].endswith(deal["id"])


async def test_never_touches_sequences():
    svc, apollo, _, _ = make_services(make_settings(apollo_create_deals=True))
    await run(svc, payload())
    assert apollo.requests
    assert not any("emailer_campaigns" in p or "sequence" in p for p in apollo.paths())


async def test_redelivered_webhook_duplicates_nothing():
    svc, apollo, notion, slack = make_services(make_settings(apollo_create_deals=True))
    body = payload()
    await run(svc, body)
    assert await run(svc, body) == "already_processed"
    assert (len(apollo.accounts), len(apollo.contacts), len(apollo.calls)) == (1, 1, 1)
    assert (len(apollo.deals), len(apollo.tasks)) == (1, 1)
    assert len(notion.pages) == 2 and len(slack.posts) == 1


async def test_failed_step_is_replayed_without_duplicates():
    svc, apollo, notion, slack = make_services(make_settings(apollo_create_deals=True))
    apollo.fail_paths.add("/tasks")
    assert await run(svc, payload()) == "incomplete"
    call = svc.store.calls["conv_1"]
    assert call["processed_at"] is None and call["apollo_deal_id"]
    assert "post_call_step_failed" in [e[1] for e in svc.store.events]

    apollo.fail_paths.clear()
    assert await process(svc, "conv_1") == "processed"
    assert (len(apollo.accounts), len(apollo.contacts), len(apollo.deals)) == (1, 1, 1)
    assert len(apollo.calls) == 1  # call_identifier upsert
    assert len(apollo.tasks) == 1
    assert len(notion.in_db("leads-db")) == 1 and len(notion.in_db("transcripts-db")) == 1
    assert len(slack.posts) == 1


async def test_returning_caller_reuses_stored_apollo_ids():
    store = FakeStore()
    svc, apollo, _, _ = make_services(store=store)
    await run(svc, payload("conv_1"))
    await run(svc, payload("conv_2"))
    assert len(apollo.accounts) == 1 and len(apollo.contacts) == 1
    assert len(apollo.calls) == 2 and len(apollo.tasks) == 2
    paths = apollo.paths()
    assert paths.count("POST /api/v1/contacts/search") == 1
    assert paths.count("POST /api/v1/accounts/search") == 1


async def test_existing_apollo_contact_found_by_email_is_updated_not_created():
    svc, apollo, _, _ = make_services()
    apollo.contacts["c" * 24] = {"id": "c" * 24, "email": "jane@acme.example", "first_name": "J"}
    await run(svc, payload())
    assert list(apollo.contacts) == ["c" * 24]
    assert apollo.contacts["c" * 24]["first_name"] == "Jane"


async def test_unqualified_call_gets_notion_row_only():
    svc, apollo, notion, slack = make_services()
    assert await run(svc, payload(results=UNQUALIFIED)) == "processed"
    assert apollo.requests == [] and slack.posts == []
    [lead] = notion.in_db("leads-db")
    assert lead["properties"]["Qualified"] == {"checkbox": False}
    assert svc.store.calls["conv_1"]["outcome"] == "no_action"


async def test_booking_and_messages_set_outcome():
    svc, *_ = make_services()
    await svc.store.ensure_call("conv_1")
    await svc.store.update_call("conv_1", booking_id="bk_1")
    await run(svc, payload())
    assert svc.store.calls["conv_1"]["outcome"] == "discovery_booked"

    svc, *_ = make_services()
    call = await svc.store.ensure_call("conv_9")
    await svc.store.add_message(call["id"], "support", "Lift alarm fault", None, "high", "Site A")
    await run(svc, payload("conv_9", results=UNQUALIFIED))
    assert svc.store.calls["conv_9"]["outcome"] == "support_message"


async def test_withheld_number_still_processed_without_caller_row():
    svc, _, notion, _ = make_services()
    assert await run(svc, payload(caller="anonymous", results=UNQUALIFIED)) == "processed"
    assert svc.store.callers == {}
    assert notion.in_db("leads-db")[0]["properties"]["Phone"] == {"phone_number": None}


async def test_missing_integrations_are_skipped():
    svc, *_ = make_services()
    svc.apollo = svc.notion = svc.slack = None
    assert await run(svc, payload()) == "processed"


async def test_existing_customer_relationship_is_never_downgraded():
    store = FakeStore()
    svc, *_ = make_services(store=store)
    await store.upsert_caller(
        "+447400123456",
        name="Jane Smith",
        email=None,
        organisation="Acme",
        relationship="customer",
        last_call_at=None,
    )
    await run(svc, payload())
    assert store.callers["+447400123456"]["relationship"] == "customer"
