#!/usr/bin/env python
"""Idempotently provision the ElevenLabs agent and import the Telnyx DID (SPEC §7, Phase 3).

Creates the "Cody" inbound-receptionist agent (British voice, no audio recording, 30-day
transcript retention) if ELEVENLABS_AGENT_ID is unset; otherwise patches the existing agent with
the Phase 3 settings this repo owns: the §6 data-collection fields the post-call webhook parses,
the dynamic-variable placeholders the conversation-init webhook fills, and permission for that
webhook to override first_message and ASR keywords. Voice, greeting and privacy are not changed
on an existing agent. Then imports the Telnyx DID (default +442045200783) as a SIP-trunk number
bound to the agent. The trunk is authenticated by Telnyx's signalling source IPs.

    uv run python scripts/provision_elevenlabs.py --dry-run   # print the requests, no API calls
    uv run python scripts/provision_elevenlabs.py --apply     # apply (needs ELEVENLABS_API_KEY)

The agent's first_message and base prompt are read from config/ (never invented here); the
full per-call prompt, keywords and tools are supplied by the conversation-init webhook in
Phase 3. Run scripts/provision_telnyx.py first so the DID already routes to ElevenLabs.

ElevenLabs API (https://api.elevenlabs.io, header xi-api-key):
  POST  /v1/convai/agents/create     create the agent
  PATCH /v1/convai/agents/{id}       Phase 3 settings on an existing agent
  GET  /v1/convai/phone-numbers     list imported numbers (idempotency)
  POST /v1/convai/phone-numbers     import the DID as a sip_trunk number

Other numbers still bound to the agent (the old 0330 DID, +443301900784) are reported, never
deleted: remove them in the ElevenLabs dashboard once the 020 number is live.

The conversation-init webhook URL, the post-call webhook and the three webhook tools are set in
the ElevenLabs dashboard (see infra/elevenlabs/README.md), because they need WEBHOOK_DOMAIN live.

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

from agent.conversation_init import DYNAMIC_VARIABLES  # noqa: E402
from agent.extraction import data_collection_config  # noqa: E402

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
    # Drop the leading dev note (lines starting with "# "); keep the prompt body verbatim.
    lines = (ROOT / "config" / "prompt.md").read_text().splitlines()
    while lines and lines[0].startswith("# "):
        lines.pop(0)
    return "\n".join(lines).strip()


def _phase3_settings() -> dict:
    return {
        "conversation_config": {
            "agent": {"dynamic_variables": {"dynamic_variable_placeholders": DYNAMIC_VARIABLES}},
        },
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


def _agent_body() -> dict:
    phase3 = _phase3_settings()
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": _first_message(),
                "language": LANGUAGE,
                "prompt": {"prompt": _base_prompt()},
                **phase3["conversation_config"]["agent"],
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


def _print_plan(did: str, agent_id: str | None) -> None:
    print("ElevenLabs agent + number import (plan):")
    if agent_id:
        print(f"\n1. Agent {agent_id} exists — patch Phase 3 settings:")
        _show("PATCH", f"/v1/convai/agents/{agent_id}", _phase3_settings())
    else:
        print("\n1. Create agent:")
        _show("POST", "/v1/convai/agents/create", _agent_body())
    print(f"\n2. Import DID {did} as a SIP-trunk number:")
    _show("POST", "/v1/convai/phone-numbers", _number_body(did, agent_id or "<agent_id>"))


async def _create_agent(client: httpx.AsyncClient) -> str:
    r = await client.post("/v1/convai/agents/create", json=_agent_body())
    _check(r)
    aid = r.json()["agent_id"]
    print(f"agent '{AGENT_NAME}': created ({aid})")
    return aid


async def _patch_agent(client: httpx.AsyncClient, agent_id: str) -> None:
    r = await client.patch(f"/v1/convai/agents/{agent_id}", json=_phase3_settings())
    _check(r)
    print(f"agent {agent_id}: Phase 3 settings applied")


async def _import_number(client: httpx.AsyncClient, did: str, agent_id: str) -> None:
    r = await client.get("/v1/convai/phone-numbers")
    _check(r)
    numbers = r.json()
    for n in numbers:
        bound = (n.get("assigned_agent") or {}).get("agent_id")
        if n.get("phone_number") != did and bound == agent_id:
            print(
                f"note: {n.get('phone_number')} is still bound to this agent "
                f"({n.get('phone_number_id')}); remove it in the dashboard when {did} is live"
            )
    for n in numbers:
        if n.get("phone_number") == did:
            print(f"phone_number {did}: already imported ({n.get('phone_number_id')})")
            return
    r = await client.post("/v1/convai/phone-numbers", json=_number_body(did, agent_id))
    _check(r)
    print(f"phone_number {did}: imported ({r.json().get('phone_number_id')})")


async def main() -> int:
    load_dotenv(ROOT / ".env")
    args = sys.argv[1:]
    apply = "--apply" in args
    if not apply and "--dry-run" not in args:
        print("usage: provision_elevenlabs.py [--dry-run | --apply]", file=sys.stderr)
        return 2

    did = os.environ.get("TELNYX_DID", "").strip() or DEFAULT_DID
    agent_id = os.environ.get("ELEVENLABS_AGENT_ID", "").strip() or None

    if not apply:
        _print_plan(did, agent_id)
        return 0

    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        print("ELEVENLABS_API_KEY is not set (use --dry-run to preview)", file=sys.stderr)
        return 1

    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        if agent_id:
            await _patch_agent(client, agent_id)
        else:
            agent_id = await _create_agent(client)
            print(f"\nPut this in .env:  ELEVENLABS_AGENT_ID={agent_id}\n")
        await _import_number(client, did, agent_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
