#!/usr/bin/env python
"""Idempotently provision the ElevenLabs agent and import the Telnyx DID (SPEC §7, Phase 3).

Creates the "Cody" inbound-receptionist agent (British voice, no audio recording, 30-day
transcript retention) if ELEVENLABS_AGENT_ID is unset; otherwise patches the existing agent with
the Phase 3 settings this repo owns: the §6 data-collection fields n8n's post-call flow parses,
the dynamic-variable placeholders n8n's conversation-init webhook fills, and permission for that
webhook to override first_message and ASR keywords, the per-line dynamic variables
(config/lines.yaml) and, when NOEL_MOBILE_E164 is set, the transfer_to_number tool for Noel's
direct line. Voice, greeting and privacy are not changed on an existing agent, and the system prompt
only with --sync-prompt. Then imports the Telnyx DID (default +442045200783) and every other
number a line is matched on in config/lines.yaml (the parking line) as SIP-trunk numbers bound to
the agent. The trunk is authenticated by Telnyx's signalling source IPs.

    uv run python scripts/provision_elevenlabs.py --dry-run   # print the requests, no API calls
    uv run python scripts/provision_elevenlabs.py --apply     # apply (needs ELEVENLABS_API_KEY)
    ... --apply --sync-prompt   # also replace an existing agent's system prompt from config/

The agent's first_message and base prompt are read from config/ (never invented here); the
per-call caller variables and keywords are supplied by n8n's conversation-init webhook. Run
scripts/provision_telnyx.py first so the DID already routes to ElevenLabs.

ElevenLabs API (https://api.elevenlabs.io, header xi-api-key):
  POST  /v1/convai/agents/create     create the agent
  PATCH /v1/convai/agents/{id}       Phase 3 settings on an existing agent
  GET  /v1/convai/phone-numbers     list imported numbers (idempotency)
  POST /v1/convai/phone-numbers     import the DID as a sip_trunk number

Other numbers still bound to the agent (the old 0330 DID, +443301900784) are reported, never
deleted: remove them in the ElevenLabs dashboard once the 020 number is live.

The conversation-init and post-call webhook URLs (n8n) and the three webhook tools are set in
the ElevenLabs dashboard (see infra/elevenlabs/README.md).

Noel's mobile (NOEL_MOBILE_E164) is read from the environment, sent to ElevenLabs as the transfer
destination and never printed: --dry-run shows a placeholder. The tool is the conference type, so
it needs outbound calling on the SIP trunk, which this script does not set up (see
infra/elevenlabs/README.md). Without NOEL_MOBILE_E164 the transfer tool is skipped. Applying it
rewrites the agent's whole transfer_to_number slot.

No secrets are printed: only resource IDs and request bodies (which carry no keys).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import lines as line_config  # noqa: E402
from agent.extraction import data_collection_config  # noqa: E402
from agent.phone import to_e164  # noqa: E402
from agent.prompt import render_prompt  # noqa: E402


def _default_line_variables() -> dict[str, str]:
    """Placeholders for the default line, used if the conversation-init call fails or times out."""
    greeting = line_config.load_greeting()
    line_map = line_config.load_line_map()
    return line_config.dynamic_variables(
        line_map.default, greeting, line_config.load_prompt_sections()
    )


# n8n's conversation-init must return every one of these (ElevenLabs requirement). The line_*
# variables and caller_id_is_caller come from POST /lines/resolve; caller_phone is blank there on
# the RingCentral lines because the CLI is not the caller.
DYNAMIC_VARIABLES = {
    "caller_known": "false",
    "caller_name": "",
    "caller_first_name": "",
    "caller_company": "",
    "caller_relationship": "",
    **_default_line_variables(),
}
REDACTED_DESTINATION = "<NOEL_MOBILE_E164 from the environment>"

BASE_URL = "https://api.elevenlabs.io"

AGENT_NAME = "ControlFreq receptionist (Cody)"
VOICE_ID = "jRAAK67SEFE9m7ci5DhD"  # British English (DECISIONS 2026-10-09)
LANGUAGE = "en"
RETENTION_DAYS = 30
LABEL = "ControlFreq inbound (Telnyx)"
DEFAULT_DID = "+442045200783"  # London 020 DID (replaces +443301900784); TELNYX_DID overrides

# Telnyx EU signalling source IPs — verified against sip.telnyx.com (sip.telnyx.eu).
# ElevenLabs accepts the inbound trunk from these alone; Telnyx inbound uses no digest auth.
TELNYX_SIGNALLING_IPS = ["185.246.41.140/32", "185.246.41.141/32"]


def _first_message() -> str:
    data = yaml.safe_load((ROOT / "config" / "greeting.yaml").read_text())
    return " ".join(str(data["greeting"]).split())


def _base_prompt() -> str:
    # Host name and deflections come from greeting.yaml. Per-call {{variables}} stay.
    greeting = yaml.safe_load((ROOT / "config" / "greeting.yaml").read_text())
    return render_prompt((ROOT / "config" / "prompt.md").read_text(), greeting)


def _transfer_tool(destination: str) -> dict:
    """The transfer_to_number slot, from the line that screens and transfers (config/lines.yaml)."""
    line = next(ln for ln in line_config.load_line_map().lines if ln.screen_and_transfer)
    return {
        "type": "system",
        "name": "transfer_to_number",
        "params": {
            "system_tool_type": "transfer_to_number",
            "transfers": [
                {
                    "transfer_destination": {"type": "phone", "phone_number": destination},
                    "condition": line.transfer.condition,
                    "transfer_type": line.transfer.type,
                }
            ],
            "enable_client_message": True,
        },
    }


def _phase3_settings(noel_mobile: str | None = None, sync_prompt: bool = False) -> dict:
    agent: dict = {"dynamic_variables": {"dynamic_variable_placeholders": DYNAMIC_VARIABLES}}
    prompt: dict = {}
    if sync_prompt:
        prompt["prompt"] = _base_prompt()
    if noel_mobile:
        prompt["built_in_tools"] = {"transfer_to_number": _transfer_tool(noel_mobile)}
    if prompt:
        agent["prompt"] = prompt
    return {
        "conversation_config": {"agent": agent},
        "platform_settings": {
            "data_collection": data_collection_config(),
            "overrides": {
                "enable_conversation_initiation_client_data_from_webhook": True,
                "conversation_config_override": {
                    "agent": {"first_message": True},
                    "asr": {"keywords": True},
                },
            },
        },
    }


def _noel_mobile(raw: str | None) -> str | None:
    """Noel's mobile in E.164 from NOEL_MOBILE_E164, or None if unset; exits if it is invalid."""
    raw = (raw or "").strip()
    if not raw:
        return None
    e164 = to_e164(raw)
    if e164 is None:
        raise SystemExit("NOEL_MOBILE_E164 is not a valid phone number (use E.164, +44...)")
    return e164


def _agent_body(noel_mobile: str | None = None) -> dict:
    phase3 = _phase3_settings(noel_mobile)
    phase3_agent = phase3["conversation_config"]["agent"]
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": _first_message(),
                "language": LANGUAGE,
                **phase3_agent,
                "prompt": {"prompt": _base_prompt(), **phase3_agent.get("prompt", {})},
            },
            "tts": {"voice_id": VOICE_ID},
        },
        "platform_settings": {
            "privacy": {"record_voice": False, "retention_days": RETENTION_DAYS},
            **phase3["platform_settings"],
        },
    }


def _number_body(did: str, agent_id: str) -> dict:
    return {
        "phone_number": did,
        "label": LABEL,
        "provider": "sip_trunk",
        "agent_id": agent_id,
        "inbound_trunk_config": {
            "allowed_addresses": TELNYX_SIGNALLING_IPS,
            "media_encryption": "disabled",
        },
    }


def _check(r: httpx.Response) -> None:
    """Raise on HTTP error, surfacing the API's error body (no secrets in it)."""
    if r.is_error:
        print(
            f"  ElevenLabs API {r.status_code} on {r.request.method} {r.request.url.path}:",
            file=sys.stderr,
        )
        print(f"  {r.text}", file=sys.stderr)
        r.raise_for_status()


def _show(method: str, path: str, body: dict | None) -> None:
    print(f"  {method} {path}")
    if body is not None:
        for line in json.dumps(body, indent=2).splitlines():
            print(f"    {line}")


def _dids(did: str) -> list[str]:
    """The primary DID first, then every other number lines.yaml matches on."""
    return list(dict.fromkeys([did, *line_config.load_line_map().called_numbers]))


def _print_plan(did: str, agent_id: str | None, noel_mobile: str | None, sync_prompt: bool) -> None:
    shown = REDACTED_DESTINATION if noel_mobile else None
    print("ElevenLabs agent + number import (plan):")
    if agent_id:
        print(f"\n1. Agent {agent_id} exists — patch Phase 3 settings:")
        _show("PATCH", f"/v1/convai/agents/{agent_id}", _phase3_settings(shown, sync_prompt))
    else:
        print("\n1. Create agent:")
        _show("POST", "/v1/convai/agents/create", _agent_body(shown))
    if not noel_mobile:
        print("\n   NOEL_MOBILE_E164 is not set: the transfer_to_number tool is NOT included.")
    if agent_id and not sync_prompt:
        print(
            "   --sync-prompt is not set: the agent's system prompt is NOT updated, so the new "
            '"This line" section (config/prompt.md) will be missing until you pass it.'
        )
    for i, number in enumerate(_dids(did), start=2):
        print(f"\n{i}. Import DID {number} as a SIP-trunk number:")
        _show("POST", "/v1/convai/phone-numbers", _number_body(number, agent_id or "<agent_id>"))


async def _create_agent(client: httpx.AsyncClient, noel_mobile: str | None) -> str:
    r = await client.post("/v1/convai/agents/create", json=_agent_body(noel_mobile))
    _check(r)
    aid = r.json()["agent_id"]
    print(f"agent '{AGENT_NAME}': created ({aid})")
    return aid


async def _patch_agent(
    client: httpx.AsyncClient, agent_id: str, noel_mobile: str | None, sync_prompt: bool
) -> None:
    body = _phase3_settings(noel_mobile, sync_prompt)
    r = await client.patch(f"/v1/convai/agents/{agent_id}", json=body)
    _check(r)
    print(f"agent {agent_id}: Phase 3 settings applied")
    print("system prompt: " + ("replaced from config/" if sync_prompt else "left as it is"))
    print(
        "transfer_to_number: "
        + ("set for Noel's direct line" if noel_mobile else "skipped (NOEL_MOBILE_E164 not set)")
    )


async def _import_numbers(client: httpx.AsyncClient, dids: list[str], agent_id: str) -> None:
    r = await client.get("/v1/convai/phone-numbers")
    _check(r)
    numbers = r.json()
    for n in numbers:
        bound = (n.get("assigned_agent") or {}).get("agent_id")
        if n.get("phone_number") not in dids and bound == agent_id:
            print(
                f"note: {n.get('phone_number')} is still bound to this agent "
                f"({n.get('phone_number_id')}); remove it in the dashboard when {dids[0]} is live"
            )
    imported = {n.get("phone_number"): n.get("phone_number_id") for n in numbers}
    for did in dids:
        if did in imported:
            print(f"phone_number {did}: already imported ({imported[did]})")
            continue
        r = await client.post("/v1/convai/phone-numbers", json=_number_body(did, agent_id))
        _check(r)
        print(f"phone_number {did}: imported ({r.json().get('phone_number_id')})")


async def main() -> int:
    load_dotenv(ROOT / ".env")
    args = sys.argv[1:]
    apply = "--apply" in args
    sync_prompt = "--sync-prompt" in args
    if not apply and "--dry-run" not in args:
        print(
            "usage: provision_elevenlabs.py [--dry-run | --apply] [--sync-prompt]", file=sys.stderr
        )
        return 2

    did = os.environ.get("TELNYX_DID", "").strip() or DEFAULT_DID
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip() or None
    noel_mobile = _noel_mobile(os.environ.get("NOEL_MOBILE_E164"))

    if not apply:
        _print_plan(did, agent_id, noel_mobile, sync_prompt)
        return 0

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY is not set (use --dry-run to preview)", file=sys.stderr)
        return 1

    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        if agent_id:
            await _patch_agent(client, agent_id, noel_mobile, sync_prompt)
        else:
            agent_id = await _create_agent(client, noel_mobile)
            print(f"\nPut this in .env:  ELEVENLABS_AGENT_ID={agent_id}\n")
        await _import_numbers(client, _dids(did), agent_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
