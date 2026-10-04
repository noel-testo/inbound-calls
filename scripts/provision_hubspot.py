#!/usr/bin/env python
"""Idempotently provision HubSpot for the receptionist (SPEC §9).

Create-only: creates the contact property group and the 12 `cf_` properties if they
are missing; never renames or deletes. Safe to rerun.

    uv run python scripts/provision_hubspot.py --dry-run   # print the plan, no API calls
    uv run python scripts/provision_hubspot.py             # apply (needs HUBSPOT_PROVISION_KEY)

Auth: uses HUBSPOT_PROVISION_KEY (a HubSpot Service Key with properties write), kept
separate from the agent's runtime HUBSPOT_SERVICE_KEY.

Pipeline: the deal pipeline is the existing "Sales Pipeline" (id `default`) — no new
pipeline (the Starter plan allows two). The receptionist's two outcomes map onto
existing stages, configured in `.env` and only echoed here for confirmation:
  HUBSPOT_STAGE_QUALIFIED_NOT_BOOKED -> "Lead Identified"
  HUBSPOT_STAGE_DISCOVERY_BOOKED     -> "Initial Contact"

Endpoints follow HubSpot's dated properties API, per Noel:
  GET  /crm/properties/2026-09/contacts/groups
  GET  /crm/properties/2026-09/contacts/{name}
  POST /crm/properties/2026-09/contacts[/groups]
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.hubapi.com"
PROPS = "/crm/properties/2026-09/contacts"

GROUP_NAME = "controlfreq_ai_receptionist"
GROUP_LABEL = "ControlFreq AI Receptionist"

# Enum value sets, verbatim from SPEC §6.
CALLER_ROLE = [
    "facilities_manager",
    "managing_agent",
    "lift_contractor",
    "landlord_owner",
    "consultant",
    "installer",
    "other",
    "unknown",
]
ASSET_TYPE = ["lifts", "car_parks", "alarm_panels", "other"]
ESTATE_SIZE_UNIT = ["lifts", "sites"]
CONNECTIVITY = ["pstn_copper", "existing_4g", "mixed", "unknown"]
DRIVER = [
    "pstn_switch_off",
    "failures",
    "new_build",
    "contract_renewal",
    "cost",
    "other",
    "unknown",
]
TIMELINE = ["immediate", "1_3_months", "3_6_months", "6_plus", "unknown"]
DECISION = ["decision_maker", "influencer", "researcher", "unknown"]

_SPECIAL_LABELS = {
    "1_3_months": "1–3 months",
    "3_6_months": "3–6 months",
    "6_plus": "6+ months",
    "existing_4g": "Existing 4G",
    "pstn_copper": "PSTN copper",
    "pstn_switch_off": "PSTN switch-off",
}
_ACRONYMS = {"pstn": "PSTN", "4g": "4G"}


def humanize(value: str) -> str:
    """Readable British-English label for an enum value."""
    if value in _SPECIAL_LABELS:
        return _SPECIAL_LABELS[value]
    words = [_ACRONYMS.get(w, w) for w in value.split("_")]
    s = " ".join(words)
    return s[:1].upper() + s[1:]


def _options(values: list[str]) -> list[dict]:
    return [
        {"label": humanize(v), "value": v, "displayOrder": i, "hidden": False}
        for i, v in enumerate(values)
    ]


def _prop(
    name: str,
    label: str,
    type_: str,
    field_type: str,
    options: list[str] | None = None,
) -> dict:
    spec = {
        "name": name,
        "label": label,
        "type": type_,
        "fieldType": field_type,
        "groupName": GROUP_NAME,
    }
    if options is not None:
        spec["options"] = _options(options)
    return spec


_BOOL_OPTIONS = [
    {"label": "Yes", "value": "true", "displayOrder": 0, "hidden": False},
    {"label": "No", "value": "false", "displayOrder": 1, "hidden": False},
]

# The 12 cf_ contact properties, exactly per SPEC §9 / §6.
PROPERTIES: list[dict] = [
    _prop("cf_caller_role", "Caller role", "enumeration", "select", CALLER_ROLE),
    _prop("cf_asset_type", "Asset type", "enumeration", "checkbox", ASSET_TYPE),  # multi-select
    _prop("cf_estate_size", "Estate size", "number", "number"),
    _prop("cf_estate_size_unit", "Estate size unit", "enumeration", "select", ESTATE_SIZE_UNIT),
    _prop("cf_current_connectivity", "Current connectivity", "enumeration", "select", CONNECTIVITY),
    _prop("cf_driver", "Driver", "enumeration", "select", DRIVER),
    _prop("cf_timeline", "Timeline", "enumeration", "select", TIMELINE),
    _prop("cf_decision_authority", "Decision authority", "enumeration", "select", DECISION),
    _prop("cf_lead_score", "Lead score", "number", "number"),
    {
        "name": "cf_high_value",
        "label": "High value",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "groupName": GROUP_NAME,
        "options": _BOOL_OPTIONS,
    },
    _prop("cf_last_ai_call_id", "Last AI call id", "string", "text"),
    _prop("cf_ai_call_summary", "AI call summary", "string", "textarea"),
]


def _print_plan() -> None:
    print(f"Group: {GROUP_LABEL} ({GROUP_NAME})")
    print(f"Properties ({len(PROPERTIES)}):")
    for p in PROPERTIES:
        opts = f" [{len(p['options'])} options]" if "options" in p else ""
        print(f"  {p['name']:<24} {p['type']}/{p['fieldType']}{opts}")
    print("Pipeline: existing 'Sales Pipeline' (id 'default') — not modified.")
    qnb = os.environ.get("HUBSPOT_STAGE_QUALIFIED_NOT_BOOKED", "(unset)")
    dbk = os.environ.get("HUBSPOT_STAGE_DISCOVERY_BOOKED", "(unset)")
    print(f"  HUBSPOT_STAGE_QUALIFIED_NOT_BOOKED = {qnb}")
    print(f"  HUBSPOT_STAGE_DISCOVERY_BOOKED     = {dbk}")


async def _ensure_group(client: httpx.AsyncClient, dry_run: bool) -> None:
    resp = await client.get(f"{PROPS}/groups")
    resp.raise_for_status()
    existing = {g.get("name") for g in resp.json().get("results", [])}
    if GROUP_NAME in existing:
        print(f"group {GROUP_NAME}: exists")
        return
    if dry_run:
        print(f"group {GROUP_NAME}: would create")
        return
    r = await client.post(f"{PROPS}/groups", json={"name": GROUP_NAME, "label": GROUP_LABEL})
    r.raise_for_status()
    print(f"group {GROUP_NAME}: created")


async def _ensure_property(client: httpx.AsyncClient, spec: dict, dry_run: bool) -> str:
    resp = await client.get(f"{PROPS}/{spec['name']}")
    if resp.status_code == 200:
        return "exists"
    if resp.status_code != 404:
        resp.raise_for_status()
    if dry_run:
        return "would create"
    r = await client.post(PROPS, json=spec)
    r.raise_for_status()
    return "created"


async def main() -> int:
    load_dotenv(ROOT / ".env")
    dry_run = "--dry-run" in sys.argv[1:]

    if dry_run:
        _print_plan()
        return 0

    key = os.environ.get("HUBSPOT_PROVISION_KEY")
    if not key:
        print("HUBSPOT_PROVISION_KEY is not set (use --dry-run to preview)", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        await _ensure_group(client, dry_run)
        counts: dict[str, int] = {}
        for spec in PROPERTIES:
            outcome = await _ensure_property(client, spec, dry_run)
            counts[outcome] = counts.get(outcome, 0) + 1
            print(f"property {spec['name']}: {outcome}")
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    print(f"Done — {summary}")
    print("Pipeline left as existing 'Sales Pipeline' (id 'default'); stages mapped via .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
