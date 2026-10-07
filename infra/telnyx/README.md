# Telnyx — Phase 2

Telephony ingress (SPEC §4.1, §12). RingCentral stays the office phone system and diverts the office
number's after-hours / no-answer calls to a **London 020 Telnyx DID**; Telnyx routes the call over a
SIP connection to **LiveKit SIP** (IP-restricted to Telnyx). CLI is preserved so the HubSpot phone
lookup works.

## Telnyx portal (Phase 2)

- A **London 020** DID. UK local/national numbers need KYC: ID, a company registration certificate,
  and a utility bill < 3 months old; ~72h to validate (Telnyx UK DID requirements).
- An **FQDN SIP connection** pointing at this host's LiveKit SIP, per LiveKit's Telnyx guide:
  - inbound `ani_number_format: "+E.164"` (CLI reaches the room as `+44…`),
  - transport **TCP** (recommended),
  - `anchorsite_override: "Latency"`,
  - inbound **SIP region: Europe**.
- Inbound-only, so no SIP username/password — auth is the IP allowlist on the LiveKit trunk.

## LiveKit side (`scripts/provision_livekit.py`, Phase 2)

- Inbound trunk `allowed_addresses` = Telnyx EU signalling IPs **185.246.41.140** and
  **185.246.41.141**. Media comes from Telnyx's published subnets (sip.telnyx.com), which Telnyx
  extends over time — build the host firewall from that page, not a one-off hard-code.
- Dispatch rule: every call → agent `inbound-receptionist`, room `call-<uuid>`.
- `livekit-sip` networking: either `network_mode: host`, or bridge + published ports with
  `use_external_ip: true` in `sip.yaml` (else SDP advertises the private IP and the call has no audio).
  Docker-published ports bypass `ufw`, so IP rules go in the `DOCKER-USER` chain (SPEC §12).

Credentials live in `.env` (`TELNYX_*`), never in the repo. **No credentials yet** — the Telnyx account
upgrade is blocked on Telnyx support.

FreeSWITCH and the RingCentral SIP-registration hack were dropped on 2026-10-05 (see
`docs/DECISIONS.md`). Do not reintroduce them.
