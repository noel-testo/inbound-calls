# Telnyx — Phase 2 (trunk to ElevenLabs)

Telephony carrier. RingCentral diverts after-hours / no-answer calls to a **London 020 Telnyx DID**;
Telnyx trunks the call to **ElevenLabs Agents** (not our host). CLI preserved.

## Telnyx portal

- A **London 020** DID. UK number KYC: ID, company registration certificate, utility bill < 3 months
  old (~72h to validate).
- An **FQDN SIP connection** to `sip.rtc.elevenlabs.io`:
  - inbound destination number format **`+E.164`**;
  - transport **TCP** (5060) or **TLS** (`sip.rtc.elevenlabs.io:5061;transport=tls`); UDP is
    experimental (testing only);
  - **Allowed Source IP Addresses** (works on TCP/TLS only; Telnyx inbound has no digest auth):
    EU `185.246.41.140` and `185.246.41.141`;
  - **Allowed Numbers** left empty (diverted callers can be anyone);
  - codec G.711 / G.722.

## ElevenLabs

- Phone Numbers → Import number → From SIP Trunk, with the 020 number in E.164. See `infra/elevenlabs/`.

Credentials (`TELNYX_*`) live in `.env`, never in the repo. **No credentials yet** — the Telnyx account
upgrade is blocked on Telnyx support.
