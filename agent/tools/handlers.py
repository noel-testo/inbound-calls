"""Webhook tool handlers. Each returns compact JSON the agent can speak from, logs one JSON line,
and never raises to ElevenLabs: on failure the agent is told to take a message instead (SPEC §5.1).

Every tool receives `conversation_id` (the agent maps it from `system__conversation_id`). Nothing is
stored here: n8n's post-call flow logs the call to Notion and adds any message to the lead's
Summary.
"""

from __future__ import annotations

import time
import uuid

from agent import log
from agent.calcom import CalComError
from agent.phone import to_e164

CATEGORIES = {"enquiry", "support", "supplier", "other"}
URGENCIES = {"normal", "high"}
CALCOM_TIMEOUT_S = 8.0


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


async def check_availability(calcom, body: dict) -> dict:
    """Slots on Noel Sesto's discovery-call calendar (Cal.com event 7747197)."""
    conversation_id = body.get("conversation_id")
    start = time.monotonic()
    try:
        result = await calcom.get_availability(
            body["from_iso"], body["to_iso"], timeout=CALCOM_TIMEOUT_S
        )
    except (CalComError, KeyError) as e:
        log.event("tool_error", call_id=conversation_id, tool="check_availability", error=str(e))
        return {"slots": [], "error": "unavailable", "fallback": "take_message"}
    log.event(
        "tool_call",
        call_id=conversation_id,
        tool="check_availability",
        slots=len(result["slots"]),
        ms=_ms(start),
    )
    return result


async def book_meeting(calcom, body: dict) -> dict:
    """Book a 15-minute discovery call with Noel Sesto, Technical Director."""
    conversation_id = body.get("conversation_id")
    # Cal.com requires a phone; fall back to the CLI the agent maps from `system__caller_id`.
    phone = to_e164(body.get("phone")) or to_e164(body.get("caller_phone"))
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
        return {"status": "failed", "fallback": "take_message"}
    log.event(
        "tool_call",
        call_id=conversation_id,
        tool="book_meeting",
        booking_id=result["booking_id"],
        ms=_ms(start),
    )
    return result


def take_message(body: dict) -> dict:
    conversation_id = body.get("conversation_id")
    if not conversation_id or not body.get("summary"):
        return {"status": "failed", "error": "conversation_id and summary are required"}
    category = body.get("category") if body.get("category") in CATEGORIES else "other"
    urgency = body.get("urgency") if body.get("urgency") in URGENCIES else "normal"
    message_id = str(uuid.uuid4())
    log.event(
        "tool_call",
        call_id=conversation_id,
        tool="take_message",
        message_id=message_id,
        category=category,
        urgency=urgency,
    )
    return {"message_id": message_id}
