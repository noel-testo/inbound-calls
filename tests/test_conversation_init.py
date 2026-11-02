"""conversation-init webhook: Neon caller lookup by E.164 within the timeout budget, fail soft."""

from __future__ import annotations

import asyncio

from agent.conversation_init import DYNAMIC_VARIABLES, handle
from tests.fakes import FakeStore, make_settings

BODY = {
    "caller_id": "+447400123456",
    "agent_id": "agent_x",
    "called_number": "+442045200783",
    "call_sid": "sip_1",
    "conversation_id": "conv_1",
}


async def test_known_caller_gets_name_company_and_greeting():
    store = FakeStore()
    store.callers["+447400123456"] = {
        "id": "c1",
        "name": "Jane Smith",
        "organisation": "Acme Estates",
        "relationship": "customer",
        "apollo_contact_id": "a" * 24,
    }
    resp = await handle(store, make_settings(), BODY)
    v = resp["dynamic_variables"]
    assert resp["type"] == "conversation_initiation_client_data"
    assert set(v) == set(DYNAMIC_VARIABLES)
    assert v["caller_known"] == "true" and v["caller_first_name"] == "Jane"
    assert v["caller_company"] == "Acme Estates" and v["caller_relationship"] == "customer"
    assert "a" * 24 not in str(resp)  # Apollo ids never reach the LLM
    override = resp["conversation_config_override"]
    assert override["agent"]["first_message"] == "Thanks for calling. Hello."
    assert override["asr"]["keywords"] == ["ControlFreq", "EN81-28"]
    assert store.calls["conv_1"]["caller_id"] == "c1"
    assert store.calls["conv_1"]["called_number"] == "+442045200783"


async def test_national_format_is_normalised_to_e164():
    store = FakeStore()
    store.callers["+447400123456"] = {
        "id": "c1",
        "name": "Jane",
        "organisation": None,
        "relationship": "lead",
    }
    resp = await handle(store, make_settings(), {**BODY, "caller_id": "07400 123456"})
    assert resp["dynamic_variables"]["caller_known"] == "true"
    assert resp["dynamic_variables"]["caller_phone"] == "+447400123456"


async def test_unknown_and_withheld_callers_get_defaults():
    store = FakeStore()
    resp = await handle(store, make_settings(), BODY)
    assert resp["dynamic_variables"]["caller_known"] == "false"
    resp = await handle(store, make_settings(), {**BODY, "caller_id": "anonymous"})
    assert resp["dynamic_variables"]["caller_phone"] == ""


async def test_todo_greeting_is_not_spoken():
    store = FakeStore()
    store.config["greeting"] = {"greeting": "TODO greeting"}
    resp = await handle(store, make_settings(), BODY)
    assert "agent" not in resp.get("conversation_config_override", {})


class SlowStore(FakeStore):
    async def lookup_caller(self, phone):
        await asyncio.sleep(1)
        return None


class BrokenStore(FakeStore):
    async def load_config(self, key):
        raise ConnectionError("neon down")


async def test_slow_lookup_times_out_to_generic_start():
    resp = await handle(SlowStore(), make_settings(init_lookup_timeout_s=0.05), BODY)
    assert resp == {
        "type": "conversation_initiation_client_data",
        "dynamic_variables": {**DYNAMIC_VARIABLES, "caller_phone": "+447400123456"},
    }


async def test_database_error_fails_soft():
    resp = await handle(BrokenStore(), make_settings(), BODY)
    assert resp["dynamic_variables"]["caller_known"] == "false"
    assert "conversation_config_override" not in resp
