# Telnyx — trunk to ElevenLabs

Telephony carrier. RingCentral diverts after-hours / no-answer calls to the **London 020 Telnyx DID
`+442045200783`** (replacing the 0330 number `+443301900784`); Telnyx trunks the call to
**ElevenLabs Agents** (not our host). CLI preserved. `scripts/provision_telnyx.py` wires this up
idempotently and defaults to the 020 number (`TELNYX_DID` overrides).

## Telnyx portal

- The DID `+442045200783` in the account (UK number KYC: ID, company registration certificate,
  utility bill under 3 months old).
- An **FQDN SIP connection** `elevenlabs-inbound` to `sip.rtc.elevenlabs.io`:
  - inbound destination number format **`+E.164`**;
  - transport **TCP** (5060) or **TLS** (`sip.rtc.elevenlabs.io:5061;transport=tls`);
  - ElevenLabs accepts the trunk from Telnyx's EU signalling IPs `185.246.41.140` and
    `185.246.41.141` (no digest auth on inbound);
  - **Allowed Numbers** left empty (diverted callers can be anyone);
  - codec G.711 / G.722.
- The existing connection (id 3067081943628646021, applied for the 0330 number on PR #9) can carry
  the 020 number too: `provision_telnyx.py --apply` finds it by name and assigns the new DID.

## ElevenLabs

- Phone Numbers → Import number → From SIP Trunk, with `+442045200783` in E.164. See `infra/elevenlabs/`.

Credentials (`TELNYX_*`) live in `.env`, never in the repo.
