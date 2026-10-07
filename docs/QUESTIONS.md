# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording. *Default:* the TODO placeholders stay until approved; blocking for Phase 5.
- **TTS voice id:** which ElevenLabs British-English voice (`TTS_VOICE_ID`). *Default:* a neutral British voice for Phase 3 testing; Noel confirms the final voice.
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
- **Telnyx account + DID (Phase 2):** account upgrade is blocked on Telnyx support; no credentials yet. Needed: a London 020 DID + a SIP connection pointing at LiveKit SIP. UK number KYC: ID, company registration certificate, utility bill < 3 months old (~72h to validate). *Default:* none; blocking for the Phase 2 live test.
- **CLI on RingCentral divert:** does RingCentral present the *original caller's* CLI when it diverts externally to Telnyx, or its own number? The HubSpot lookup needs the original. *Default:* divert from an **extension / user forwarding rule, not an IVR / call-flow node** — RingCentral preserves the original CLI on the former but shows its own number on the latter even with Preserve Caller ID on; verify before go-live (Noel can test now by forwarding to a mobile).
- **UK regulatory:** Ofcom CLI/presentation rules, 999/112 emergency-call handling (whether the AI line must support/route them), and number-registration obligations. *Default:* the AI line is inbound-only and not advertised as an emergency contact; the greeting's emergency wording directs callers elsewhere; confirm obligations before go-live.
- **Pitch-review doc data retention (for Noel):** the Notion "Call transcripts" database holds personal data (names, numbers, company). Does it need a retention / erasure rule like the Neon transcripts, or is it kept indefinitely for pitch review? *Default:* kept indefinitely until Noel sets a policy.

## Answered

- **Expert / discovery-call owner:** Noel Sesto, HubSpot owner id 99735767. (2026-10-04)
- **Deal pipeline:** use the existing "Sales Pipeline" (id `default`) — no new `Inbound` pipeline (Starter plan allows two). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (6139983093); Discovery booked → "Initial Contact" (6139983094). (2026-10-04)
- **HubSpot auth:** Service Keys, not a legacy private app — `HUBSPOT_SERVICE_KEY` (runtime) + `HUBSPOT_PROVISION_KEY` (provisioning). (2026-10-04)
- **HubSpot Service Keys provided + verified** (2026-10-05): `HUBSPOT_SERVICE_KEY` has CRM read/write/delete; `HUBSPOT_PROVISION_KEY` has schema access. Both in `.env`; provisioning + CRM live-tested.
- **Discovery-call booking platform:** Cal.com, not HubSpot Meetings. Event type 7103844 ("LiftPulse Trial", 15-min, auto-confirmed; account noelsesto); `CALCOM_API_KEY` + `CALCOM_EVENT_TYPE_ID` in `.env`. HubSpot scheduler scope dropped; no HubSpot meeting link. (2026-10-05)
- **UK number type:** London **020** local (geographic) Telnyx DID. (2026-10-07)
- **Audio recording:** none in the MVP — no `record_session` / egress / Telnyx recording; the full two-sided, timestamped Neon transcript is the record of each call (SPEC §8). Audio recording deferred post-MVP. (2026-10-07)
- **"Call transcripts" doc destination:** **Notion** (not Google Docs) — a Notion database, one row per call (date, caller, company, outcome, summary; full transcript in the page body) so it stays searchable/filterable. `NOTION_API_KEY` + `NOTION_TRANSCRIPTS_DB_ID` to come. (2026-10-07)
- **TTS provider:** ElevenLabs for the MVP (`TTS_PROVIDER=elevenlabs`, `ELEVENLABS_API_KEY` in `.env`), behind the `TTSProvider` interface; Cartesia remains a swappable alternate. (2026-10-07)
