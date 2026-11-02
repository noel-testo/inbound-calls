# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording, including "recorded" vs "transcribed" in the greeting, and the discovery-call expert's name and title. *Default:* unchanged; TODO placeholders stay until approved; blocking for Phase 5.
- **Extraction:** the §6 fields now come from ElevenLabs post-call data collection rather than a separate LLM call. *Default:* yes (no extra model provider or key).
- **LLM:** ElevenLabs hosts the agent's LLM in the MVP; a custom LLM via ElevenLabs' custom-LLM setting (`LLM_BASE_URL`) is a post-MVP option (§15). *Default:* ElevenLabs' model, tuned for the latency budget.
- **Scoring:** confirm or change weights and the threshold (50) in `config/scoring.yaml`. *Default:* as shipped.
- **Retention:** no audio recordings in the MVP (SPEC §8), so this is Neon transcripts only — keep them indefinitely? *Default:* kept indefinitely until Noel sets a policy. (Notion rows are 12 months — Answered.)
- **Host:** a small UK (London) VPS for the webhook service + Caddy — see the recommendation in STATUS; who holds root. *Default:* new VPS, 2 vCPU / 4 GB / 80 GB SSD (4 vCPU / 8 GB only if Windmill stays).
- **RingCentral divert:** admin access to set the after-hours / no-answer rules to divert the main number externally to the Telnyx DID (no SIP device or receptionist extension needed now). *Default:* none; blocking for Phase 2.
- **n8n:** export of the current RingCentral missed-call workflow JSON. *Default:* none; blocking for Phase 4.
- **Terms list:** product names, staff names, major client and site names for `config/terms.yaml`. *Default:* placeholders.
- **Apollo → HubSpot sync (blocker for deals):** switch off Apollo's automatic HubSpot sync before setting `APOLLO_CREATE_DEALS=true`; while it is on, Apollo pushes new deals (and may push contacts, accounts, calls and tasks) into HubSpot. *Default:* `APOLLO_CREATE_DEALS=false`; contacts, call records and tasks still go to Apollo as approved — leave `APOLLO_API_KEY` unset if even those must not reach HubSpot.
- **Apollo ids:** the Apollo user who owns logged calls, deals and follow-up tasks (`APOLLO_USER_ID`), an optional deal stage (`APOLLO_DEAL_STAGE_ID`) and how soon the follow-up task is due. *Default:* tasks skipped (and logged) until `APOLLO_USER_ID` is set; Apollo's default stage; due 4 hours after the call.
- **Notion databases:** create "Cody leads" and "Call transcripts", share both with the integration, and send the two database ids; then run `scripts/provision_notion.py --apply`. *Default:* Notion steps are skipped until the ids are set.
- **Existing customers in the caller directory:** Neon `callers` starts empty, so existing customers are only recognised after their first call to Cody. Is there a phone list (name, organisation, number) to import as `relationship = customer`? *Default:* none; the directory fills itself call by call.
- **Windmill:** post-call no longer uses it. Keep it for the n8n RingCentral alert port and the nightly retention job, or drop it and run both as a webhook route + cron on the host? *Default:* recommend dropping it; it stays in compose until you say.
- **Neon scale-to-zero on `production`:** the compute suspends after 5 idle minutes (it was suspended on 2026-11-02), so almost every after-hours call wakes it inside the 1.5 s call-start budget; a slow wake means a known caller is greeted as unknown. Disable scale-to-zero (always-on 0.25 CU) or raise `INIT_LOOKUP_TIMEOUT_MS`? *Default:* leave as is; measure the lookup latency on the Phase 3 test calls (`init_lookup` / `init_lookup_timeout` log lines) and decide then.
- **Webhook hostname + DNS** for Caddy TLS (`WEBHOOK_DOMAIN`, plus `WINDMILL_DOMAIN` if Windmill stays). *Default:* `hooks.controlfreq.…` A-record'd to the host; set in `.env` at bring-up.
- **Telnyx Phase 2 live test:** the DID is now the London 020 `+442045200783` (replacing `+443301900784`). Remaining: set `TELNYX_DID` in `.env`, run `scripts/provision_telnyx.py --apply` + `scripts/provision_elevenlabs.py --apply`, point the RingCentral divert at the 020 number, place a test call, then remove the 0330 number from ElevenLabs and decide whether to release it in Telnyx. *Default:* none; blocking for the Phase 2 live test.
- **CLI on RingCentral divert:** does RingCentral present the *original caller's* CLI when it diverts externally to Telnyx, or its own number? The caller lookup needs the original. *Default:* divert from an **extension / user forwarding rule, not an IVR / call-flow node** — RingCentral preserves the original CLI on the former but shows its own number on the latter even with Preserve Caller ID on; verify before go-live (Noel can test now by forwarding to a mobile).
- **UK regulatory:** Ofcom CLI/presentation rules, 999/112 emergency-call handling (whether the AI line must support/route them), and number-registration obligations. *Default:* the AI line is inbound-only and not advertised as an emergency contact; the greeting's emergency wording directs callers elsewhere; confirm obligations before go-live.

## Answered

- **CRM:** HubSpot removed; Neon caller directory for the call-start lookup, Notion lead-review rows for every call, Apollo (post-call, qualified callers only, never sequences) and Cody's own Slack alert. Deal creation behind `APOLLO_CREATE_DEALS` (default off). (2026-11-02)
- **Telnyx DID:** London 020 `+442045200783`, replacing `+443301900784`. (2026-11-02)

- **Expert / discovery-call owner:** Noel Sesto, HubSpot owner id 99735767. (2026-10-04) *(The HubSpot owner id is moot since 2026-11-02; Noel is still the expert.)*
- **Deal pipeline:** use the existing "Sales Pipeline" (id `default`) — no new `Inbound` pipeline (Starter plan allows two). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (6139983093); Discovery booked → "Initial Contact" (6139983094). (2026-10-04) *(Superseded 2026-11-02: HubSpot removed.)*
- **HubSpot auth:** Service Keys, not a legacy private app — `HUBSPOT_SERVICE_KEY` (runtime) + `HUBSPOT_PROVISION_KEY` (provisioning). (2026-10-04) *(Superseded 2026-11-02: HubSpot removed.)*
- **HubSpot Service Keys provided + verified** (2026-10-05): `HUBSPOT_SERVICE_KEY` has CRM read/write/delete; `HUBSPOT_PROVISION_KEY` has schema access. Both in `.env`; provisioning + CRM live-tested. *(Superseded 2026-11-02: HubSpot removed.)*
- **Discovery-call booking platform:** Cal.com, not HubSpot Meetings. Event type 7103844 ("LiftPulse Trial", 15-min, auto-confirmed; account noelsesto); `CALCOM_API_KEY` + `CALCOM_EVENT_TYPE_ID` in `.env`. HubSpot scheduler scope dropped; no HubSpot meeting link. (2026-10-05)
- **UK number type:** UK **0330** non-geographic Telnyx DID `+443301900784`. (2026-10-09 — supersedes the 2026-10-07 "London 020" answer; the number actually provisioned is 0330.) *(Superseded 2026-11-02: now the London 020 `+442045200783`.)*
- **Audio recording:** none in the MVP — no `record_session` / egress / Telnyx recording; the full two-sided, timestamped Neon transcript is the record of each call (SPEC §8). Audio recording deferred post-MVP. (2026-10-07)
- **"Call transcripts" doc destination:** **Notion** (not Google Docs) — a Notion database, one row per call (date, caller, company, outcome, summary; full transcript in the page body) so it stays searchable/filterable. `NOTION_API_KEY` + `NOTION_TRANSCRIPTS_DB_ID` to come. (2026-10-07)
- **Pitch-review doc (Notion) retention:** rows kept **12 months**, then deleted by the Windmill `retention` job (alongside the Neon transcript policy). (2026-10-07)
- **Voice loop platform:** **ElevenLabs Agents** replaces LiveKit SIP and the self-hosted Python agent; Telnyx trunks straight to ElevenLabs. LiveKit/Redis/SIP and the SIP-exposure question are moot (SIP terminates at ElevenLabs). (2026-10-07)
- **Agent name:** **Cody** — the ElevenLabs agent introduces itself as Cody in the greeting (`config/greeting.yaml`, delivered as `first_message`). (2026-10-09)
- **Agent voice:** ElevenLabs voice `jRAAK67SEFE9m7ci5DhD` (British English), pinned as the agent's `voice_id`. (2026-10-09)
- **ElevenLabs retention + data processing:** `retention_days: 30` with `record_voice: false` (audio off); ElevenLabs processing + storage of transcripts accepted (EU data residency is Enterprise-only). Noel still creates the post-call HMAC + tool-auth secrets in `.env`. (2026-10-09)
- **Discovery-call duration:** **15 minutes**, matching the Cal.com event 7103844; the 30-minute wording in the prompt/spec is corrected to 15. (2026-10-09)
