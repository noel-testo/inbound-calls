# Telnyx — Phase 2 (trunk to ElevenLabs)

Telephony carrier. RingCentral diverts after-hours / no-answer calls to a **UK 0330 Telnyx DID**
(`+443301900784`); Telnyx trunks the call to **ElevenLabs Agents** (not our host). CLI preserved.
`scripts/provision_telnyx.py` wires this up idempotently (see `docs/DECISIONS.md`, 2026-10-09).

## Telnyx portal

- A **UK 0330** non-geographic DID (`+443301900784`). UK number KYC: ID, company registration
  certificate, utility bill < 3 months old (~72h to validate).
- An **FQDN SIP connection** to `sip.rtc.elevenlabs.io`:
  - inbound destination number format **`+E.164`**;
  - transport **TCP** (5060) or **TLS** (`sip.rtc.elevenlabs.io:5061;transport=tls`); UDP is
    experimental (testing only);
  - **Allowed Source IP Addresses** (works on TCP/TLS only; Telnyx inbound has no digest auth):
    EU `185.246.41.140` and `185.246.41.141`;
  - **Allowed Numbers** left empty (diverted callers can be anyone);
  - codec G.711 / G.722.

## ElevenLabs

- Phone Numbers → Import number → From SIP Trunk, with the 0330 number in E.164. See `infra/elevenlabs/`.

Credentials (`TELNYX_*`) live in `.env`, never in the repo. The account is provisioned
(`TELNYX_API_KEY` + `TELNYX_DID` set); wiring is done by `scripts/provision_telnyx.py`.
