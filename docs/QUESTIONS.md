# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording. *Default:* the TODO placeholders stay until approved; blocking for Phase 5.
- **LLM:** ElevenLabs hosts the agent's LLM in the MVP; a custom LLM via ElevenLabs' custom-LLM setting (`LLM_BASE_URL`) is a post-MVP option (§15). *Default:* ElevenLabs' model, tuned for the latency budget.
- **Scoring:** confirm or change weights and the threshold (50) in `config/scoring.yaml`. *Default:* as shipped.
- **Retention:** no audio recordings in the MVP (SPEC §8), so this is Neon transcripts only — keep them indefinitely? *Default:* kept indefinitely until Noel sets a policy. (Notion rows are 12 months — Answered.)
- **Host:** existing server or a new UK VPS; who holds root. *Default:* new VPS, 4 vCPU / 8 GB.
- **RingCentral divert:** admin access to set the after-hours / no-answer rules to divert the main number externally to the Telnyx DID (no SIP device or receptionist extension needed now). *Default:* none; blocking for Phase 2.
- **n8n:** export of the current RingCentral missed-call workflow JSON. *Default:* none; blocking for Phase 4.
- **Terms list:** product names, staff names, major client and site names for `config/terms.yaml`. *Default:* placeholders.
- **Apollo → HubSpot sync:** confirm it is one-way (enrichment only) so the agent is the only thing creating deals. *Default:* assume yes.
- **Windmill public hostname + DNS** for Caddy TLS (`WINDMILL_DOMAIN`). *Default:* a subdomain on a ControlFreq domain (e.g. `windmill.controlfreq.…`) A-record'd to the host; set in `.env` at bring-up.
- **Telnyx account + DID (Phase 2):** account upgrade is blocked on Telnyx support; no credentials yet. Needed: a London 020 DID + an FQDN SIP connection to `sip.rtc.elevenlabs.io` (the number imported into ElevenLabs). UK number KYC: ID, company registration certificate, utility bill < 3 months old (~72h to validate). *Default:* none; blocking for the Phase 2 live test.
- **CLI on RingCentral divert:** does RingCentral present the *original caller's* CLI when it diverts externally to Telnyx, or its own number? The HubSpot lookup needs the original. *Default:* divert from an **extension / user forwarding rule, not an IVR / call-flow node** — RingCentral preserves the original CLI on the former but shows its own number on the latter even with Preserve Caller ID on; verify before go-live (Noel can test now by forwarding to a mobile).
- **UK regulatory:** Ofcom CLI/presentation rules, 999/112 emergency-call handling (whether the AI line must support/route them), and number-registration obligations. *Default:* the AI line is inbound-only and not advertised as an emergency contact; the greeting's emergency wording directs callers elsewhere; confirm obligations before go-live.

## Answered

- **Expert / discovery-call owner:** Noel Sesto, HubSpot owner id 99735767. (2026-10-04)
- **Deal pipeline:** use the existing "Sales Pipeline" (id `default`) — no new `Inbound` pipeline (Starter plan allows two). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (6139983093); Discovery booked → "Initial Contact" (6139983094). (2026-10-04)
- **HubSpot auth:** Service Keys, not a legacy private app — `HUBSPOT_SERVICE_KEY` (runtime) + `HUBSPOT_PROVISION_KEY` (provisioning). (2026-10-04)
- **HubSpot Service Keys provided + verified** (2026-10-05): `HUBSPOT_SERVICE_KEY` has CRM read/write/delete; `HUBSPOT_PROVISION_KEY` has schema access. Both in `.env`; provisioning + CRM live-tested.
- **Discovery-call booking platform:** Cal.com, not HubSpot Meetings. Event type 7103844 ("LiftPulse Trial", 15-min, auto-confirmed; account noelsesto); `CALCOM_API_KEY` + `CALCOM_EVENT_TYPE_ID` in `.env`. HubSpot scheduler scope dropped; no HubSpot meeting link. (2026-10-05)
- **UK number type:** London **020** local (geographic) Telnyx DID. (2026-10-07)
- **Audio recording:** none in the MVP — no `record_session` / egress / Telnyx recording; the full two-sided, timestamped Neon transcript is the record of each call (SPEC §8). Audio recording deferred post-MVP. (2026-10-07)
- **"Call transcripts" doc destination:** **Notion** (not Google Docs) — a Notion database, one row per call (date, caller, company, outcome, summary; full transcript in the page body) so it stays searchable/filterable. `NOTION_API_KEY` + `NOTION_TRANSCRIPTS_DB_ID` to come. (2026-10-07)
- **Pitch-review doc (Notion) retention:** rows kept **12 months**, then deleted by the Windmill `retention` job (alongside the Neon transcript policy). (2026-10-07)
- **Voice loop platform:** **ElevenLabs Agents** replaces LiveKit SIP and the self-hosted Python agent; Telnyx trunks straight to ElevenLabs. LiveKit/Redis/SIP and the SIP-exposure question are moot (SIP terminates at ElevenLabs). (2026-10-07)
- **Agent name:** **Cody** — the ElevenLabs agent introduces itself as Cody in the greeting (`config/greeting.yaml`, delivered as `first_message`). (2026-10-09)
- **Agent voice:** ElevenLabs voice `jRAAK67SEFE9m7ci5DhD` (British English), pinned as the agent's `voice_id`. (2026-10-09)
- **ElevenLabs retention + data processing:** `retention_days: 30` with `record_voice: false` (audio off); ElevenLabs processing + storage of transcripts accepted (EU data residency is Enterprise-only). Noel still creates the post-call HMAC + tool-auth secrets in `.env`. (2026-10-09)
- **Discovery-call duration:** **15 minutes**, matching the Cal.com event 7103844; the 30-minute wording in the prompt/spec is corrected to 15. (2026-10-09)
