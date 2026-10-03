# FreeSWITCH — Phase 2

The registration bridge to RingCentral (SPEC §4.1, §12). Built and wired in
**Phase 2 — Telephony**, not Phase 0. This directory will hold:

- `Dockerfile` — pinned FreeSWITCH base image.
- `conf/` — dialplan, vars, and the `external` SIP profile gateway.
- `conf/sip_profiles/external/ringcentral.xml` — rendered from a template at
  container start from the `RC_SIP_*` values in `.env`; git-ignored (it carries
  credentials).

Phase 0 does not build or run this service; the Phase 0 bring-up targets only
redis, livekit, livekit-sip, windmill-server, windmill-worker and caddy.
