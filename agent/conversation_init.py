"""ElevenLabs conversation-initiation webhook: caller lookup at call start (SPEC §5 step 2, §7).

ElevenLabs posts `{caller_id, agent_id, called_number, call_sid, conversation_id}` while the call is
still connecting. We look the caller up in Cody's own Neon caller directory by E.164 — never Apollo,
which cannot search by phone and is never called mid-call — and return dynamic variables plus the
greeting and STT keywords from Neon config. All Neon work shares one budget
(`INIT_LOOKUP_TIMEOUT_MS`); on timeout or error the call starts as an unknown caller with the
agent's own first message, so a slow database never delays the greeting.
"""

from __future__ import annotations

import asyncio
import time

from agent import log
from agent.phone import to_e164

# Every dynamic variable defined on the agent must be returned (ElevenLabs requirement).
DYNAMIC_VARIABLES = {
    "caller_known": "false",
    "caller_name": "",
    "caller_first_name": "",
    "caller_company": "",
    "caller_relationship": "",
    "caller_phone": "",
}


def _greeting_text(cfg: dict | None) -> str | None:
    if not cfg or not cfg.get("greeting"):
        return None
    text = " ".join(str(cfg["greeting"]).split())
    return None if "TODO" in text else text


async def _lookup(store, conversation_id: str | None, caller: str | None, called: str | None):
    caller_row, greeting, terms = await asyncio.gather(
        store.lookup_caller(caller) if caller else asyncio.sleep(0, result=None),
        store.load_config("greeting"),
        store.active_terms(),
    )
    if conversation_id:
        await store.start_call(
            conversation_id, caller, called, caller_row["id"] if caller_row else None
        )
    return caller_row, greeting, terms


async def handle(store, settings, body: dict) -> dict:
    conversation_id = body.get("conversation_id")
    caller = to_e164(body.get("caller_id"))
    called = to_e164(body.get("called_number"))

    variables = dict(DYNAMIC_VARIABLES, caller_phone=caller or "")
    response: dict = {"type": "conversation_initiation_client_data", "dynamic_variables": variables}

    start = time.monotonic()
    try:
        async with asyncio.timeout(settings.init_lookup_timeout_s):
            caller_row, greeting, terms = await _lookup(store, conversation_id, caller, called)
    except TimeoutError:
        log.event(
            "init_lookup_timeout", call_id=conversation_id, budget_s=settings.init_lookup_timeout_s
        )
        return response
    except Exception as e:  # fail soft: the caller must still be answered
        log.event("init_lookup_error", call_id=conversation_id, error=str(e))
        return response

    if caller_row:
        name = caller_row.get("name") or ""
        variables.update(
            caller_known="true",
            caller_name=name,
            caller_first_name=name.split()[0] if name else "",
            caller_company=caller_row.get("organisation") or "",
            caller_relationship=caller_row.get("relationship") or "",
        )

    override: dict = {}
    first_message = _greeting_text(greeting)
    if first_message:
        override["agent"] = {"first_message": first_message}
    if terms:
        override["asr"] = {"keywords": terms}
    if override:
        response["conversation_config_override"] = override

    log.event(
        "init_lookup",
        call_id=conversation_id,
        known=bool(caller_row),
        cli_present=bool(caller),
        ms=int((time.monotonic() - start) * 1000),
    )
    return response
