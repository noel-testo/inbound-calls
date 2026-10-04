# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **HubSpot meeting-link slug + Service Keys:** the expert's 30-minute discovery-call link slug, and the `HUBSPOT_SERVICE_KEY` (runtime) / `HUBSPOT_PROVISION_KEY` (provisioning) values. *To follow from Noel; blocks the live Phase 1 booking and the provisioning run.*
- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording. *Default:* the TODO placeholders stay until approved; blocking for Phase 5.
- **Voice:** Cartesia or ElevenLabs, and which British English voice. *Default:* Cartesia, first suitable British voice, for Phase 3 testing only.
- **LLM endpoint for the MVP:** which hosted model behind `LLM_BASE_URL`. *Default:* whichever is already paid for; swapped later.
- **Scoring:** confirm or change weights and the threshold (50) in `config/scoring.yaml`. *Default:* as shipped.
- **Retention:** recordings 90 days; transcripts kept indefinitely? *Default:* 90 / indefinite.
- **Host:** existing server or a new UK VPS; who holds root. *Default:* new VPS, 4 vCPU / 8 GB.
- **RingCentral:** admin access to add the existing-phone device and edit call-handling rules; the receptionist extension number. *Default:* none; blocking for Phase 2.
- **n8n:** export of the current RingCentral missed-call workflow JSON. *Default:* none; blocking for Phase 4.
- **Terms list:** product names, staff names, major client and site names for `config/terms.yaml`. *Default:* placeholders.
- **Apollo → HubSpot sync:** confirm it is one-way (enrichment only) so the agent is the only thing creating deals. *Default:* assume yes.
- **Windmill public hostname + DNS** for Caddy TLS (`WINDMILL_DOMAIN`). *Default:* a subdomain on a ControlFreq domain (e.g. `windmill.controlfreq.…`) A-record'd to the host; set in `.env` at bring-up.
- **SIP topology (Phase 2):** FreeSWITCH runs `network_mode: host` but `livekit-sip` is on the compose bridge and unpublished — they can't talk as drawn. *Default:* publish `livekit-sip` 5060/udp + its RTP range bound to the Docker bridge gateway only, firewalled off the public interface, and point FreeSWITCH's dialplan at that address. Revisit in Phase 2; no action needed now.

## Answered

- **Expert / discovery-call owner:** Noel Sesto, HubSpot owner id 99735767. (2026-10-04)
- **Deal pipeline:** use the existing "Sales Pipeline" (id `default`) — no new `Inbound` pipeline (Starter plan allows two). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (6139983093); Discovery booked → "Initial Contact" (6139983094). (2026-10-04)
- **HubSpot auth:** Service Keys, not a legacy private app — `HUBSPOT_SERVICE_KEY` (runtime) + `HUBSPOT_PROVISION_KEY` (provisioning). (2026-10-04)
