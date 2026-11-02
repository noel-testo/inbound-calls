#!/usr/bin/env python
"""Idempotently create the ElevenLabs agent and import the Telnyx DID (SPEC §7, Phase 3 bootstrap).

Creates the "Cody" inbound-receptionist agent (British voice, no audio recording, 30-day
transcript retention) and imports the Telnyx DID as a SIP-trunk phone number bound to it.
The trunk is authenticated by Telnyx's signalling source IPs — no SIP credentials.

    uv run python scripts/provision_elevenlabs.py --dry-run   # print the requests, no API calls
    uv run python scripts/provision_elevenlabs.py --apply     # apply (needs ELEVENLABS_API_KEY)

The agent's first_message and base prompt are read from config/ (never invented here); the
full per-call prompt, keywords and tools are supplied by the conversation-init webhook in
Phase 3. Run scripts/provision_telnyx.py first so the DID already routes to ElevenLabs.

ElevenLabs API (https://api.elevenlabs.io, header xi-api-key):
  POST /v1/convai/agents/create     create the agent
  GET  /v1/convai/phone-numbers     list imported numbers (idempotency)
  POST /v1/convai/phone-numbers     import the DID as a sip_trunk number

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
BASE_URL = "https://api.elevenlabs.io"

AGENT_NAME = "ControlFreq receptionist (Cody)"
VOICE_ID = "jRAAK67SEFE9m7ci5DhD"  # British English (DECISIONS 2026-10-09)
LANGUAGE = "en"
RETENTION_DAYS = 30
LABEL = "ControlFreq inbound (Telnyx)"

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


def _agent_body() -> dict:
    return {
        "name": AGENT_NAME,
        "conversation_config": {
            "agent": {
                "first_message": _first_message(),
                "language": LANGUAGE,
                "prompt": {"prompt": _base_prompt()},
            },
            "tts": {"voice_id": VOICE_ID},
        },
        "platform_settings": {
            "privacy": {"record_voice": False, "retention_days": RETENTION_DAYS},
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
        print(f"  ElevenLabs API {r.status_code} on {r.request.method} {r.request.url.path}:",
              file=sys.stderr)
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
        print(f"\n1. Agent: ELEVENLABS_AGENT_ID already set ({agent_id}) — skip create.")
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


async def _import_number(client: httpx.AsyncClient, did: str, agent_id: str) -> None:
    r = await client.get("/v1/convai/phone-numbers")
    _check(r)
    for n in r.json():
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

    did = os.environ.get("TELNYX_DID", "").strip()
    if not did:
        print("TELNYX_DID is not set", file=sys.stderr)
        return 1
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
            print(f"agent: reusing ELEVENLABS_AGENT_ID ({agent_id})")
        else:
            agent_id = await _create_agent(client)
            print(f"\nPut this in .env:  ELEVENLABS_AGENT_ID={agent_id}\n")
        await _import_number(client, did, agent_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
