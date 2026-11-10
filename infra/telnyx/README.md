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

## Outbound calling for the Noel-direct transfer (not provisioned yet)

The connection above is inbound-only and the 020 numbers cannot place calls. Cody's transfer to
Noel's mobile is a call *out* from ElevenLabs over the trunk, so it needs, on the Telnyx side:

- an **outbound voice profile** allowing calls to UK mobiles (destination whitelist, spend limit),
  attached to the connection that ElevenLabs dials out through;
- **authentication** for ElevenLabs' outbound INVITEs: a credential connection (username and
  password) or IP authentication for ElevenLabs' signalling IPs. The current FQDN connection
  authenticates inbound only by Telnyx's source IPs;
- **caller ID**: the outbound leg is presented as `+442045200783` (a number on the account), so
  Noel's phone shows the 020 number, not the original caller (the original number is not known on
  the RC lines anyway).

and on the ElevenLabs side, an `outbound_trunk_config` on the imported number (address
`sip.telnyx.com`, transport, the credentials above). Noel's mobile voicemail may answer the
transferred leg: test it (TEST-CALLS 24).

`provision_telnyx.py` and `provision_elevenlabs.py` should own this too, as a follow-up once the
credential model is chosen (so the credentials go in `.env` and are never printed): the Telnyx
script creates the outbound voice profile and credential connection and the ElevenLabs script
patches the number's `outbound_trunk_config`, both dry-run by default. They do not do it today, so
nothing in this repo creates a billable outbound path.

## ElevenLabs

- Phone Numbers → Import number → From SIP Trunk, with `+442045200783` in E.164. See `infra/elevenlabs/`.

Credentials (`TELNYX_*`) live in `.env`, never in the repo.
