#!/usr/bin/env python
"""Idempotently wire the Telnyx DID to ElevenLabs over SIP (SPEC §4, Phase 2).

Creates (if missing) an FQDN SIP connection that routes the inbound PSTN call to
ElevenLabs' SIP FQDN, then assigns the existing Telnyx DID to it. ElevenLabs is
inbound-only, so there is no outbound voice profile and no SIP credentials — the
trunk is authenticated on the ElevenLabs side by Telnyx's signalling source IPs
(see scripts/provision_elevenlabs.py).

    uv run python scripts/provision_telnyx.py --dry-run   # print the exact requests, no API calls
    uv run python scripts/provision_telnyx.py --apply     # apply (needs TELNYX_API_KEY)

Telnyx v2 API (https://developers.telnyx.com/api):
  GET/POST  /v2/fqdn_connections       create the FQDN connection (inbound DNIS +E.164, TCP)
  GET/POST  /v2/fqdns                  point the connection at sip.rtc.elevenlabs.io:5060
  GET/PATCH /v2/phone_numbers          assign the DID to the connection

No secrets are printed: only resource IDs and request bodies (which carry no keys).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.telnyx.com"

CONNECTION_NAME = "elevenlabs-inbound"
ELEVENLABS_FQDN = "sip.rtc.elevenlabs.io"
ELEVENLABS_PORT = 5060
TRANSPORT = "TCP"  # TCP signalling (UDP media); TLS (5061) is the alternative


def _check(r: httpx.Response) -> None:
    """Raise on HTTP error, surfacing the API's error body (no secrets in it)."""
    if r.is_error:
        print(f"  Telnyx API {r.status_code} on {r.request.method} {r.request.url.path}:",
              file=sys.stderr)
        print(f"  {r.text}", file=sys.stderr)
        r.raise_for_status()


def _show(method: str, path: str, body: dict | None) -> None:
    """Print one intended request (no network, no secrets)."""
    print(f"  {method} {path}")
    if body is not None:
        for line in json.dumps(body, indent=2).splitlines():
            print(f"    {line}")


def _connection_body() -> dict:
    # connection_name is the only required field; inbound.dnis_number_format delivers the
    # dialled DID to ElevenLabs in +E.164 so the agent sees the real number.
    return {
        "connection_name": CONNECTION_NAME,
        "transport_protocol": TRANSPORT,
        "inbound": {"dnis_number_format": "+e164"},
    }


def _fqdn_body(connection_id: str) -> dict:
    return {
        "connection_id": connection_id,
        "fqdn": ELEVENLABS_FQDN,
        "port": ELEVENLABS_PORT,
        "dns_record_type": "a",
    }


def _print_plan(did: str) -> None:
    print("Telnyx → ElevenLabs SIP wiring (plan):")
    print(f"\n1. Ensure FQDN connection '{CONNECTION_NAME}':")
    _show("POST", "/v2/fqdn_connections", _connection_body())
    print(f"\n2. Ensure FQDN {ELEVENLABS_FQDN}:{ELEVENLABS_PORT} on the connection:")
    _show("POST", "/v2/fqdns", _fqdn_body("<connection_id>"))
    print(f"\n3. Assign DID {did} to the connection:")
    _show("GET", f"/v2/phone_numbers?filter[phone_number]={did}", None)
    _show("PATCH", "/v2/phone_numbers/<id>", {"connection_id": "<connection_id>"})
    print("\nInbound-only: no outbound voice profile, no SIP credentials "
          "(ElevenLabs authenticates by Telnyx signalling IPs).")


async def _ensure_connection(client: httpx.AsyncClient) -> str:
    r = await client.get(
        "/v2/fqdn_connections", params={"filter[connection_name]": CONNECTION_NAME}
    )
    _check(r)
    data = r.json().get("data", [])
    if data:
        cid = data[0]["id"]
        print(f"fqdn_connection '{CONNECTION_NAME}': exists ({cid})")
        return cid
    r = await client.post("/v2/fqdn_connections", json=_connection_body())
    _check(r)
    cid = r.json()["data"]["id"]
    print(f"fqdn_connection '{CONNECTION_NAME}': created ({cid})")
    return cid


async def _ensure_fqdn(client: httpx.AsyncClient, connection_id: str) -> None:
    r = await client.get("/v2/fqdns", params={"filter[connection_id]": connection_id})
    _check(r)
    for fq in r.json().get("data", []):
        if fq.get("fqdn") == ELEVENLABS_FQDN:
            print(f"fqdn {ELEVENLABS_FQDN}: exists ({fq['id']})")
            return
    r = await client.post("/v2/fqdns", json=_fqdn_body(connection_id))
    _check(r)
    print(f"fqdn {ELEVENLABS_FQDN}: created ({r.json()['data']['id']})")


async def _assign_number(client: httpx.AsyncClient, did: str, connection_id: str) -> None:
    r = await client.get("/v2/phone_numbers", params={"filter[phone_number]": did})
    _check(r)
    data = r.json().get("data", [])
    if not data:
        print(f"phone_number {did}: NOT FOUND in this Telnyx account — purchase/port it first",
              file=sys.stderr)
        raise SystemExit(1)
    num = data[0]
    if num.get("connection_id") == connection_id:
        print(f"phone_number {did}: already on '{CONNECTION_NAME}'")
        return
    r = await client.patch(f"/v2/phone_numbers/{num['id']}", json={"connection_id": connection_id})
    _check(r)
    print(f"phone_number {did}: assigned to '{CONNECTION_NAME}'")


async def main() -> int:
    load_dotenv(ROOT / ".env")
    args = sys.argv[1:]
    apply = "--apply" in args
    if not apply and "--dry-run" not in args:
        print("usage: provision_telnyx.py [--dry-run | --apply]", file=sys.stderr)
        return 2

    did = os.environ.get("TELNYX_DID", "").strip()
    if not did:
        print("TELNYX_DID is not set", file=sys.stderr)
        return 1

    if not apply:
        _print_plan(did)
        return 0

    key = os.environ.get("TELNYX_API_KEY")
    if not key:
        print("TELNYX_API_KEY is not set (use --dry-run to preview)", file=sys.stderr)
        return 1

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=30.0) as client:
        connection_id = await _ensure_connection(client)
        await _ensure_fqdn(client, connection_id)
        await _assign_number(client, did, connection_id)
    print(f"\nDone. Put this in .env:  TELNYX_SIP_CONNECTION_ID={connection_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
