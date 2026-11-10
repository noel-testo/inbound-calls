"""Notion database schemas: "Cody leads" (one row per call, for review) and "Call transcripts".

`scripts/provision_notion.py` adds any missing property to each database from these definitions;
n8n's post-call flow writes rows with the same property names. Each database keeps its default title
property, named "Name". "Review" is set to "To review" on create and never overwritten, so Noel's
triage survives a re-delivered webhook. "Line" (which number the call came in on) is on both
databases. On the RingCentral lines "Phone" stays empty, because the CLI is not the caller, and
"Callback number" holds the number the caller gave.
"""

from __future__ import annotations

from agent.extraction import FIELDS, INTENTS, PARTNERS
from agent.lines import load_line_map

OUTCOMES = (
    "discovery_booked",
    "qualified_not_booked",
    "transferred",
    "cold_call_declined",
    "message_taken",
    "support_message",
    "supplier_logged",
    "no_action",
    "abandoned",
    "max_duration",
    "error",
)
# One option per line in config/lines.yaml, named by the line key (the tag): noel-direct, sales,
# accounts, support, parking, general. "Line" is set on every row from the call's `line_key`.
LINE_OPTIONS = load_line_map().keys
REVIEW_OPTIONS = ("To review", "Reviewed", "Not a lead")


def _select(values) -> dict:
    return {"select": {"options": [{"name": v} for v in values]}}


def _multi(values) -> dict:
    return {"multi_select": {"options": [{"name": v} for v in values]}}


LEADS: dict[str, dict] = {
    "Name": {"title": {}},
    "Conversation ID": {"rich_text": {}},
    "Call time": {"date": {}},
    "Line": _select(LINE_OPTIONS),
    "Phone": {"phone_number": {}},
    "Callback number": {"phone_number": {}},
    "Email": {"email": {}},
    "Organisation": {"rich_text": {}},
    "Partner": _select(PARTNERS),
    "Role": _select(FIELDS["caller_role"].values),
    "Intent": _select(INTENTS),
    "Outcome": _select(OUTCOMES),
    "Lead score": {"number": {"format": "number"}},
    "Qualified": {"checkbox": {}},
    "Known caller": {"checkbox": {}},
    "Assets": _multi(FIELDS["asset_type"].values),
    "Estate size": {"number": {"format": "number"}},
    "Estate unit": _select(FIELDS["estate_size_unit"].values),
    "Connectivity": _select(FIELDS["current_connectivity"].values),
    "Driver": _select(FIELDS["driver"].values),
    "Timeline": _select(FIELDS["timeline"].values),
    "Decision authority": _select(FIELDS["decision_authority"].values),
    "Duration (s)": {"number": {"format": "number"}},
    "Summary": {"rich_text": {}},
    "Review": _select(REVIEW_OPTIONS),
    "Apollo contact": {"url": {}},
    "Apollo account": {"url": {}},
    "Apollo deal": {"url": {}},
    "Transcript": {"url": {}},
}

TRANSCRIPTS: dict[str, dict] = {
    "Name": {"title": {}},
    "Conversation ID": {"rich_text": {}},
    "Call time": {"date": {}},
    "Line": _select(LINE_OPTIONS),
    "Caller": {"rich_text": {}},
    "Company": {"rich_text": {}},
    "Partner": _select(PARTNERS),
    "Outcome": _select(OUTCOMES),
    "Summary": {"rich_text": {}},
}

SCHEMAS = {"leads": LEADS, "transcripts": TRANSCRIPTS}
