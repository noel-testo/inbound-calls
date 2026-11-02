"""Webhook tool handlers. Each returns compact JSON the agent can speak from, logs an `events` row,
and never raises to ElevenLabs: on failure the agent is told to take a message instead (SPEC §5.1).

Every tool receives `conversation_id` (the agent maps it from `system__conversation_id`).
"""

from __future__ import annotations

import time

from agent import log
from agent.calcom import CalComError
from agent.phone import to_e164

CATEGORIES = {"enquiry", "support", "supplier", "other"}
URGENCIES = {"normal", "high"}
CALCOM_TIMEOUT_S = 8.0


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def check_availability(store, calcom, body: dict) -> dict:
    """Slots on Noel Sesto's discovery-call calendar (Cal.com event 7747197)."""
    conversation_id = body.get("conversation_id")
    call = await store.ensure_call(conversation_id) if conversation_id else None
    start = time.monotonic()
    try:
        result = await calcom.get_availability(
            body["from_iso"], body["to_iso"], timeout=CALCOM_TIMEOUT_S
        )
    except (CalComError, KeyError) as e:
        log.event("tool_error", call_id=conversation_id, tool="check_availability", error=str(e))
        if call:
            await store.log_event(
                call["id"], "tool_error", {"tool": "check_availability", "error": str(e)}
            )
        return {"slots": [], "error": "unavailable", "fallback": "take_message"}
    if call:
        await store.log_event(
            call["id"],
            "tool_call",
            {"tool": "check_availability", "slots": len(result["slots"]), "ms": _ms(start)},
        )
    return result


async def book_meeting(store, calcom, body: dict) -> dict:
    """Book a 15-minute discovery call with Noel Sesto, Technical Director."""
    conversation_id = body.get("conversation_id")
    call = await store.ensure_call(conversation_id) if conversation_id else None
    phone = to_e164(body.get("phone")) or (call or {}).get("caller_e164")
    start = time.monotonic()
    try:
        result = await calcom.book_meeting(
            body["slot_iso"],
            body["name"],
            body["email"],
            body["organisation"],
            phone=phone,
            notes=body.get("notes"),
            timeout=CALCOM_TIMEOUT_S,
        )
    except (CalComError, KeyError) as e:
        log.event("tool_error", call_id=conversation_id, tool="book_meeting", error=str(e))
        if call:
            await store.log_event(
                call["id"], "tool_error", {"tool": "book_meeting", "error": str(e)}
            )
        return {"status": "failed", "fallback": "take_message"}
    if call:
        await store.update_call(conversation_id, booking_id=str(result["booking_id"]))
        await store.log_event(
            call["id"],
            "tool_call",
            {"tool": "book_meeting", "booking_id": result["booking_id"], "ms": _ms(start)},
        )
    return result


async def take_message(store, body: dict) -> dict:
    conversation_id = body.get("conversation_id")
    if not conversation_id or not body.get("summary"):
        return {"status": "failed", "error": "conversation_id and summary are required"}
    call = await store.ensure_call(conversation_id)
    category = body.get("category") if body.get("category") in CATEGORIES else "other"
    urgency = body.get("urgency") if body.get("urgency") in URGENCIES else "normal"
    callback = to_e164(body.get("callback_number")) or body.get("callback_number")
    message_id = await store.add_message(
        call["id"], category, body["summary"], callback, urgency, body.get("site")
    )
    await store.log_event(
        call["id"], "tool_call", {"tool": "take_message", "category": category, "urgency": urgency}
    )
    return {"message_id": message_id}
