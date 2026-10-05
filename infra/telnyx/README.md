# Telnyx — Phase 2

Telephony ingress (SPEC §4.1, §12). RingCentral stays the office phone system and diverts the
office number's after-hours / no-answer calls to a **Telnyx UK DID**; Telnyx routes the call over a
SIP connection to **LiveKit SIP** (IP-restricted to Telnyx). CLI is preserved so the HubSpot phone
lookup works.

Provisioned in the Telnyx portal + `scripts/provision_livekit.py` (Phase 2):

- A UK DID (number type TBD — see `docs/QUESTIONS.md`).
- A SIP connection whose destination is this host's LiveKit SIP (SIP port + RTP range published and
  firewalled to Telnyx's IP ranges only).
- The LiveKit inbound trunk locked to Telnyx (IP allowlist / credentials) + a dispatch rule
  (every call → agent `inbound-receptionist`, room `call-<uuid>`).

Credentials live in `.env` (`TELNYX_*`), never in the repo. **No credentials yet** — the Telnyx
account upgrade is blocked on Telnyx support.

FreeSWITCH and the RingCentral SIP-registration hack were dropped on 2026-10-05 (see
`docs/DECISIONS.md`). Do not reintroduce them.
