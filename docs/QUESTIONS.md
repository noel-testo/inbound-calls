# Questions for Noel

Non-blocking questions go under **Open** with the default Claude Code will use until answered. Blocking
questions are raised in the session immediately and recorded here afterwards.

## Open

- **Business hours** for `config/greeting.yaml` and for "after hours". *Default:* Mon–Fri 09:00–17:30.
- **Greeting, closing, emergency instruction** wording, including "recorded" vs "transcribed" in the greeting, and the discovery-call expert's name and title. *Default:* unchanged; TODO placeholders stay until approved; blocking for Phase 5.
- **Extraction:** the §6 fields now come from ElevenLabs post-call data collection rather than a separate LLM call. *Default:* yes (no extra model provider or key).
- **LLM:** ElevenLabs hosts the agent's LLM in the MVP; a custom LLM via ElevenLabs' custom-LLM setting (`LLM_BASE_URL`) is a post-MVP option (§15). *Default:* ElevenLabs' model, tuned for the latency budget.
- **Scoring:** confirm or change weights and the threshold (50) in `config/scoring.yaml`. *Default:* as shipped.
- **Host:** a small UK (London) VPS for the tool service + Caddy, if the Python service stays (below); who holds root. *Default:* new VPS, 2 vCPU / 4 GB / 80 GB SSD.
- **RingCentral divert:** admin access to set the after-hours / no-answer rules to divert the main number externally to the Telnyx DID (no SIP device or receptionist extension needed now). *Default:* none; blocking for Phase 2.
- **Is the Python service still needed?** n8n already has check_availability, book_meeting and take_message in an inactive "Cody – Tools" workflow. Once n8n's tools, conversation-init and post-call are tested, drop `agent/` (and the host, Caddy and `WEBHOOK_DOMAIN`) and point the ElevenLabs tools at n8n? *Default:* keep the Python Cal.com tools until n8n is tested, then decide.
- **n8n post-call scope:** does n8n's post-call flow do everything SPEC §6, §9 and §11 describe — scoring with `config/scoring.yaml`, Apollo for qualified callers only (never sequences, deals behind the HubSpot-sync switch) and the Slack alert — or only the Notion rows? *Default:* yes, all of it, same rules as the spec.
- **How `config/` reaches n8n:** the greeting, STT terms and scoring weights used to be seeded into Neon and read at call start. n8n doesn't read this repo. *Default:* `config/` stays the source of truth and Noel copies changes into the n8n flows by hand; revisit if they drift.
- **Duplicate protection in n8n:** Neon recorded each Apollo and Notion id as it was made and stopped two deliveries of the same call running at once. Without it, an ElevenLabs retry could create a second Apollo contact or follow-up task. *Default:* n8n searches before it creates (Notion by Conversation ID, Apollo contact by email, account by name); Apollo call records already upsert on `call_identifier`. TEST-CALLS #21 checks it.
- **Notion lookup speed at call start:** a Notion database query is usually 300–800 ms, inside the 1.5 s budget but with less margin than Neon had; a slow lookup means a known caller is greeted as unknown. *Default:* measure it on the Phase 3 test calls from n8n's execution times, and decide then.
- **Unused Python modules:** `agent/scoring.py`, `agent/apollo/`, `agent/slack.py` and the HMAC half of `agent/security.py` are no longer called by the service. *Default:* keep them until the question above is settled, then delete them with the service or on their own.
- **Neon leftovers:** the GitHub secret `NEON_API_KEY`, the variable `NEON_PROJECT_ID` and the Neon project "Inbound Calls" itself. *Default:* left alone; Noel decides.
- **CI:** the only workflow was the Neon preview branch, so nothing now runs `pytest` or `ruff` on PRs. *Default:* none until the service's future is settled; a one-job workflow if it stays.
- **Terms list:** product names, staff names, major client and site names for `config/terms.yaml`. *Default:* placeholders.
- **Apollo → HubSpot sync (blocker for deals):** switch off Apollo's automatic HubSpot sync before setting `APOLLO_CREATE_DEALS=true`; while it is on, Apollo pushes new deals (and may push contacts, accounts, calls and tasks) into HubSpot. *Default:* `APOLLO_CREATE_DEALS=false`; contacts, call records and tasks still go to Apollo as approved — leave `APOLLO_API_KEY` unset if even those must not reach HubSpot.
- **Apollo ids:** the Apollo user who owns logged calls, deals and follow-up tasks (`APOLLO_USER_ID`), an optional deal stage (`APOLLO_DEAL_STAGE_ID`) and how soon the follow-up task is due. *Default:* tasks skipped (and logged) until `APOLLO_USER_ID` is set; Apollo's default stage; due 4 hours after the call.
- **Existing customers in the caller directory:** the Notion "Cody leads" Phone field is the directory, so existing customers are only recognised once they have a row. Is there a phone list (name, organisation, number) to import as rows? *Default:* none; the directory fills itself call by call.
- **Webhook hostname + DNS** for Caddy TLS (`WEBHOOK_DOMAIN`), if the Python service stays. *Default:* `hooks.controlfreq.…` A-record'd to the host; set in `.env` at bring-up.
- **Telnyx Phase 2 live test:** the DID is now the London 020 `+442045200783` (replacing `+443301900784`). Remaining: set `TELNYX_DID` in `.env`, run `scripts/provision_telnyx.py --apply` + `scripts/provision_elevenlabs.py --apply`, point the RingCentral divert at the 020 number, place a test call, then remove the 0330 number from ElevenLabs and decide whether to release it in Telnyx. *Default:* none; blocking for the Phase 2 live test.
- **CLI on RingCentral divert:** does RingCentral present the *original caller's* CLI when it diverts externally to Telnyx, or its own number? The caller lookup needs the original. *Default:* divert from an **extension / user forwarding rule, not an IVR / call-flow node** — RingCentral preserves the original CLI on the former but shows its own number on the latter even with Preserve Caller ID on; verify before go-live (Noel can test now by forwarding to a mobile).
- **UK regulatory:** Ofcom CLI/presentation rules, 999/112 emergency-call handling (whether the AI line must support/route them), and number-registration obligations. *Default:* the AI line is inbound-only and not advertised as an emergency contact; the greeting's emergency wording directs callers elsewhere; confirm obligations before go-live.

## Answered

- **Neon dropped:** caller lookup (Notion "Cody leads" Phone field, `+44` E.164) and all call logging run in n8n; the Python service keeps the three Cal.com tools with no state. (2026-11-03)
- **Windmill:** replaced by n8n; its containers are removed. The RingCentral missed-call alert can stay in its existing n8n workflow. (2026-11-03)
- **Notion databases:** "Cody leads" and "Call transcripts" are created with the full set of fields and their ids are in `.env`; `provision_notion.py --apply` should only confirm them once `NOTION_API_KEY` is on the server. (2026-11-03)
- **Retention:** moot since Neon is dropped. Transcripts live in Notion (12 months) and ElevenLabs (30 days) only. (2026-11-03)
- **CRM:** HubSpot removed; Neon caller directory for the call-start lookup, Notion lead-review rows for every call, Apollo (post-call, qualified callers only, never sequences) and Cody's own Slack alert. Deal creation behind `APOLLO_CREATE_DEALS` (default off). (2026-11-02) *(Neon caller directory superseded 2026-11-03: Notion via n8n.)*
- **Telnyx DID:** London 020 `+442045200783`, replacing `+443301900784`. (2026-11-02)

- **Expert / discovery-call owner:** Noel Sesto, HubSpot owner id 99735767. (2026-10-04) *(The HubSpot owner id is moot since 2026-11-02; Noel is still the expert.)*
- **Deal pipeline:** use the existing "Sales Pipeline" (id `default`) — no new `Inbound` pipeline (Starter plan allows two). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (6139983093); Discovery booked → "Initial Contact" (6139983094). (2026-10-04) *(Superseded 2026-11-02: HubSpot removed.)*
- **HubSpot auth:** Service Keys, not a legacy private app — `HUBSPOT_SERVICE_KEY` (runtime) + `HUBSPOT_PROVISION_KEY` (provisioning). (2026-10-04) *(Superseded 2026-11-02: HubSpot removed.)*
- **HubSpot Service Keys provided + verified** (2026-10-05): `HUBSPOT_SERVICE_KEY` has CRM read/write/delete; `HUBSPOT_PROVISION_KEY` has schema access. Both in `.env`; provisioning + CRM live-tested. *(Superseded 2026-11-02: HubSpot removed.)*
- **Discovery-call booking platform:** Cal.com, not HubSpot Meetings. Event type 7103844 ("LiftPulse Trial", 15-min, auto-confirmed; account noelsesto); `CALCOM_API_KEY` + `CALCOM_EVENT_TYPE_ID` in `.env`. HubSpot scheduler scope dropped; no HubSpot meeting link. (2026-10-05)
- **UK number type:** UK **0330** non-geographic Telnyx DID `+443301900784`. (2026-10-09 — supersedes the 2026-10-07 "London 020" answer; the number actually provisioned is 0330.) *(Superseded 2026-11-02: now the London 020 `+442045200783`.)*
- **Audio recording:** none in the MVP — no `record_session` / egress / Telnyx recording; the full two-sided, timestamped Neon transcript is the record of each call (SPEC §8). Audio recording deferred post-MVP. (2026-10-07) *(Since 2026-11-03 the transcript lives in Notion, not Neon.)*
- **"Call transcripts" doc destination:** **Notion** (not Google Docs) — a Notion database, one row per call (date, caller, company, outcome, summary; full transcript in the page body) so it stays searchable/filterable. `NOTION_API_KEY` + `NOTION_TRANSCRIPTS_DB_ID` to come. (2026-10-07)
- **Pitch-review doc (Notion) retention:** rows kept **12 months**, then deleted by the Windmill `retention` job (alongside the Neon transcript policy). (2026-10-07) *(Since 2026-11-03 the retention job belongs in n8n.)*
- **Voice loop platform:** **ElevenLabs Agents** replaces LiveKit SIP and the self-hosted Python agent; Telnyx trunks straight to ElevenLabs. LiveKit/Redis/SIP and the SIP-exposure question are moot (SIP terminates at ElevenLabs). (2026-10-07)
- **Agent name:** **Cody** — the ElevenLabs agent introduces itself as Cody in the greeting (`config/greeting.yaml`, delivered as `first_message`). (2026-10-09)
- **Agent voice:** ElevenLabs voice `jRAAK67SEFE9m7ci5DhD` (British English), pinned as the agent's `voice_id`. (2026-10-09)
- **ElevenLabs retention + data processing:** `retention_days: 30` with `record_voice: false` (audio off); ElevenLabs processing + storage of transcripts accepted (EU data residency is Enterprise-only). Noel still creates the post-call HMAC + tool-auth secrets in `.env`. (2026-10-09)
- **Discovery-call duration:** **15 minutes**, matching the Cal.com event 7103844; the 30-minute wording in the prompt/spec is corrected to 15. (2026-10-09)
