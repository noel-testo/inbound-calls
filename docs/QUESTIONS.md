# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording. *Default:* the TODO placeholders stay until approved; blocking for Phase 5.
- **Voice:** Cartesia or ElevenLabs, and which British English voice. *Default:* Cartesia, first suitable British voice, for Phase 3 testing only.
- **LLM endpoint for the MVP:** which hosted model behind `LLM_BASE_URL`. *Default:* whichever is already paid for; swapped later.
- **Scoring:** confirm or change weights and the threshold (50) in `config/scoring.yaml`. *Default:* as shipped.
- **Retention:** recordings 90 days; transcripts kept indefinitely? *Default:* 90 / indefinite.
- **Host:** existing server or a new UK VPS; who holds root. *Default:* new VPS, 4 vCPU / 8 GB.
- **RingCentral divert:** admin access to set the after-hours / no-answer rules to divert the main number externally to the Telnyx DID (no SIP device or receptionist extension needed now). *Default:* none; blocking for Phase 2.
- **n8n:** export of the current RingCentral missed-call workflow JSON. *Default:* none; blocking for Phase 4.
- **Terms list:** product names, staff names, major client and site names for `config/terms.yaml`. *Default:* placeholders.
- **Apollo → HubSpot sync:** confirm it is one-way (enrichment only) so the agent is the only thing creating deals. *Default:* assume yes.
- **Windmill public hostname + DNS** for Caddy TLS (`WINDMILL_DOMAIN`). *Default:* a subdomain on a ControlFreq domain (e.g. `windmill.controlfreq.…`) A-record'd to the host; set in `.env` at bring-up.
- **LiveKit SIP exposure (Phase 2):** with Telnyx as the trunk, `livekit-sip` must be reachable from Telnyx — publish its SIP port + RTP range on the host, firewalled to Telnyx's IP ranges only. *Default:* IP-allowlist Telnyx's documented SIP/media ranges on the trunk and host firewall; confirm exact ranges when the Telnyx account is live.
- **Telnyx account + DID (Phase 2):** account upgrade is blocked on Telnyx support; no credentials yet. Needed: a UK DID + a SIP connection pointing at LiveKit SIP. *Default:* none; blocking for the Phase 2 live test.
- **UK number type:** geographic (01/02) vs non-geographic/national (03) vs mobile (07) for the Telnyx DID. *Default:* an 03 non-geographic number (nationwide, no area tie); confirm with Noel.
- **CLI on RingCentral divert:** does RingCentral present the *original caller's* CLI when it diverts externally to Telnyx, or its own number? The HubSpot lookup needs the original. *Default:* assume original CLI is passed; verify on the first live test and check for a RingCentral/Telnyx setting if not.
- **UK regulatory:** Ofcom CLI/presentation rules, 999/112 emergency-call handling (whether the AI line must support/route them), and number-registration obligations. *Default:* the AI line is inbound-only and not advertised as an emergency contact; the greeting's emergency wording directs callers elsewhere; confirm obligations before go-live.
- **Recording approach (Phase 2/3):** LiveKit track egress to host disk vs Telnyx call recording (SPEC §8). *Default:* LiveKit egress to `RECORDINGS_DIR` to keep recordings on the host per SPEC §7 retention; revisit if egress is too heavy.

## Answered

- **Expert / discovery-call owner:** Noel Sesto, HubSpot owner id 99735767. (2026-10-04)
- **Deal pipeline:** use the existing "Sales Pipeline" (id `default`) — no new `Inbound` pipeline (Starter plan allows two). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (6139983093); Discovery booked → "Initial Contact" (6139983094). (2026-10-04)
- **HubSpot auth:** Service Keys, not a legacy private app — `HUBSPOT_SERVICE_KEY` (runtime) + `HUBSPOT_PROVISION_KEY` (provisioning). (2026-10-04)
- **HubSpot Service Keys provided + verified** (2026-10-05): `HUBSPOT_SERVICE_KEY` has CRM read/write/delete; `HUBSPOT_PROVISION_KEY` has schema access. Both in `.env`; provisioning + CRM live-tested.
- **Discovery-call booking platform:** Cal.com, not HubSpot Meetings. Event type 7103844 ("LiftPulse Trial", 15-min, auto-confirmed; account noelsesto); `CALCOM_API_KEY` + `CALCOM_EVENT_TYPE_ID` in `.env`. HubSpot scheduler scope dropped; no HubSpot meeting link. (2026-10-05)
