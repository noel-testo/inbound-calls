# Inbound Calls — Build Spec v1.0 (MVP)

Owner: Noel Sesto, ControlFreq Ltd. Builder: Claude Code. Date: 3 October 2026.

## 1. Purpose

A self-hosted AI call answering service for ControlFreq that:

- answers **after-hours and unanswered** calls on the main RingCentral number,
- recognises existing customers by CLI and takes a structured message,
- qualifies new enquiries against a fixed schema and books **high-value leads into a discovery call** with the solution expert via Cal.com,
- logs every call, transcript and outcome in ControlFreq's own store and in HubSpot,
- keeps the **data** under ControlFreq's control (Neon is the record of every call); the voice loop (STT/LLM/TTS/turn-taking) is hosted by ElevenLabs Agents.

Reference points reverse-engineered for this build: Cyberstaff (call-forwarding ingress, cascaded voice loop, rules, dashboard) and fonio.ai (pre/during/post-call hooks, extraction schema, availability-aware transfer, specialised terms, self-learning knowledge base with approval, outbound campaigns). The MVP takes the first three of fonio's ideas; the rest are scheduled in §15.

## 2. Design principles

1. **The best part is no part.** The components: RingCentral, Telnyx, **ElevenLabs Agents**, Cal.com, Neon, Windmill, HubSpot — plus one small HTTPS **webhook service** we host (caller lookup, mid-call tools, post-call receiver). Slack is reached only through HubSpot's native integration and Windmill's failure alerts. (Telephony ingress is Telnyx → ElevenLabs over a SIP trunk; **LiveKit, the self-hosted Python agent, FreeSWITCH and RingCentral SIP registration are all dropped** — see DECISIONS 2026-10-07/2026-10-05.)
2. **Synchronous in the webhook service, asynchronous in Windmill.** Mid-call tools are ElevenLabs webhook tools that call our small HTTPS service, which talks to HubSpot, Cal.com and Neon directly (low latency). Post-call work and anything with a human in the loop runs in Windmill. Nothing mid-call calls Windmill.
3. **HubSpot is the system of record** for contacts, companies, deals, meetings and call engagements. **Neon is the receptionist's store**: calls, transcripts, events, config, terms. The only overlap is linking IDs.
4. **The voice loop is ElevenLabs.** STT, LLM, TTS and turn-taking are all hosted by ElevenLabs Agents (no `agent/providers/`, no local VAD/STT/TTS). A custom LLM endpoint is possible later via ElevenLabs' custom-LLM setting if we want to own the model (§15).
5. **No GPU, no inference on the host** in the MVP. Prove the flow first; own the inference second.
6. **Nothing a caller hears is invented.** Greeting, disclosures, emergency wording, hours, product claims and pricing come from `config/`. Missing values are questions.
7. **UK compliance by default.** AI disclosure and a call-logging notice in the greeting; transcript retention enforced by a scheduled job; **no audio recording** — ElevenLabs `record_voice: false` and the post-call "Send audio data" toggle off. Neon is the record; transcripts are also processed by and stored at ElevenLabs for **30 days** (`retention_days: 30`), and a transcript + summary is appended to ControlFreq's Notion "Call transcripts" database (Phase 4, §11; rows kept 12 months). The summary also goes to HubSpot.

## 3. Scope

### In scope (MVP)
- Ingress: RingCentral after-hours / no-answer forwarding diverts the main office number to a Telnyx UK 0330 number, which trunks over SIP to **ElevenLabs Agents**. Caller ID (`+E.164`) is preserved so the HubSpot phone lookup works.
- Intents: `new_enquiry`, `existing_customer`, `supplier_or_sales`, `other`.
- Pre-call: CLI lookup in HubSpot.
- Qualification against the schema in §6, scoring per `config/scoring.yaml`.
- Booking: availability check and booking on the expert's **Cal.com** event (7103844) via a webhook tool; Cal.com sends the confirmation email and calendar invite.
- Message-taking for existing customers and unqualified enquiries.
- Post-call: extraction, HubSpot upsert, deal creation when qualified, call engagement with summary, Neon write, and the transcript + summary appended to a running pitch-review document (§11).
- Guardrails: max duration, silence handling, no pricing, no promises, AI disclosure.
- **No audio recording** (ElevenLabs `record_voice: false`, post-call "Send audio data" off); full two-sided, timestamped transcripts kept in Neon for every call (see §8).
- Migration of the RingCentral missed-call Slack alert from n8n into Windmill, then n8n switched off.

### Out of scope (MVP) — see §15
Live transfer to a human; daytime overflow before after-hours has run clean; outbound callbacks; self-learning knowledge base; inbox UI; SMS/WhatsApp; self-hosted STT/TTS/LLM; noise cancellation; Apollo in the call path.

## 4. Architecture

```
Caller ─PSTN─▶ RingCentral (office PBX) ─(after-hours / no-answer divert)─▶ Telnyx UK 0330
                                                          │ SIP trunk → sip.rtc.elevenlabs.io
                                                          │ (TCP/TLS, +E.164, CLI preserved)
                                                          ▼
                                                 ElevenLabs Agents  (STT · LLM · TTS · turn-taking)
                                                   │ conversation-init webhook (pre-call: caller_id → lookup, dynamic vars)
                                                   │ tool webhooks (mid-call: check_availability, book_meeting, take_message)
                                                   ▼
                                          Webhook service (HTTPS, we host) ─sync─▶ HubSpot · Cal.com · Neon
                                                   │ post_call_transcription (HMAC-signed, on hang-up)
                                                   ▼
                                          Windmill flow post_call ──▶ extract ▸ score ▸ HubSpot upsert
                                                                   ──▶ deal ▸ call engagement ▸ Neon ▸ Notion
                                                                   HubSpot workflow ▸ task + Slack
```

### 4.1 Components and responsibilities

| Component | Role | Notes |
|---|---|---|
| RingCentral | Office phone system; ingress divert | Existing office PBX. The after-hours rule and no-answer forwarding on the main number divert the call externally to the Telnyx DID. No SIP registration, no receptionist device. Later: a route for human transfer. |
| Telnyx | SIP trunk + DID | A UK **0330** non-geographic DID (`+443301900784`) on a Telnyx FQDN SIP connection to `sip.rtc.elevenlabs.io` (TCP/TLS, inbound `+E.164`). Preserves CLI. No call recording (§8). |
| ElevenLabs Agents | The receptionist (voice loop) | Hosts STT · LLM · TTS · turn-taking. The 0330 number is imported from the SIP trunk. Calls our webhook service for caller lookup (conversation-init) and mid-call tools, and posts the signed transcript on hang-up (§7, §8). Privacy: `record_voice: false`, `retention_days: 30`. |
| Webhook service | Our glue (HTTPS) | One small service we host (replaces the Python agent): conversation-init (caller lookup + dynamic vars from Neon config), tool webhooks (`check_availability`, `book_meeting`, `take_message`), and the HMAC-verified post-call receiver that triggers Windmill. Calls HubSpot/Cal.com/Neon. |
| Neon | Store | Project with two databases: `receptionist` (schema in `db/schema.sql`) and `windmill`. |
| Windmill | Async + human-in-the-loop | Self-hosted on the host, database on Neon. Flow `post_call`, script `rc_missed_call_alert`, schedule `retention`. |
| HubSpot | System of record for sales | `cf_` properties, Service Keys, the existing Sales Pipeline (`default`), and the workflow that creates the expert's task + Slack message. Booking is not here. |
| Cal.com | Discovery-call booking | The expert's event type (7103844); the webhook service checks availability and books, and Cal.com sends the calendar invite + confirmation email (§7). |

### 4.2 Repository layout (target)

```
agent/            webhook service (FastAPI) — the glue; code lands in Phase 3
  app.py          HTTPS endpoints: conversation-init, tool webhooks, post-call receiver
  config.py       renders greeting/first_message, asr.keywords, prompt from Neon config
  tools/          one handler per webhook tool (§7)
  hubspot/        thin client: contacts, companies, deals, calls
  calcom/         Cal.com v2 client: availability + booking
  store/          Neon access (asyncpg), event logging
windmill/         Python scripts and exported flow definitions
  post_call/
  rc_missed_call_alert/
  retention/
infra/
  docker-compose.yml
  telnyx/           SIP connection + DID notes (Telnyx portal; Phase 2)
  elevenlabs/       agent config (prompt, tools, privacy) — `elevenlabs agents pull` JSON; Phase 3
  caddy/            Caddyfile (TLS for the webhook service + Windmill UI)
db/
  schema.sql, migrate.py
config/
  prompt.md, scoring.yaml, terms.yaml, greeting.yaml
scripts/
  provision_hubspot.py, seed_config.py
tests/
docs/
```

## 5. Call flow

A state machine executed by the LLM under the prompt and enforced by tool availability per state.

1. **Greeting** — from `config/greeting.yaml`: the assistant's name (**Cody**), business name, that this is an AI assistant, and a call-logging notice (the call is transcribed and logged; no audio recording — §8). Wording is Noel's (§13). Delivered as the ElevenLabs agent's `first_message` via the conversation-init webhook — fixed text, not generated.
2. **Identify** — `lookup_caller(cli)` runs before the greeting finishes. Known contact → greet by name; intent defaults to `existing_customer` but is confirmed in one question. Unknown or withheld CLI → ask who is calling and the organisation.
3. **Intent** — one open question ("How can I help?"), classified into the four intents. Ambiguous → one clarifying question, then `other`.
4. **Branch**
   - `new_enquiry` → **Qualify** (§6, conversationally, not as a form; at most one question per turn; skip anything already said) → **Score** → if `high_value`: offer a discovery call with the expert, `check_availability`, offer two slots, `book_meeting`, read back date, time, name and email → close. If not high value: capture organisation, name, email, requirement; say the team will email information; `take_message(category=enquiry)` → close.
   - `existing_customer` → ask site, issue, urgency, best callback number; `take_message(category=support)`. If the caller describes an active emergency, say `emergency_instruction` from `config/greeting.yaml` verbatim first, then take details → close.
   - `supplier_or_sales` → name, company, purpose, email; `take_message(category=supplier)`; no booking, no transfer → close politely.
   - `other` → `take_message(category=other)` → close.
5. **Close** — summarise what will happen next in one sentence, thank, `end_call`.

### 5.1 Guardrails (in code where possible, in prompt otherwise)
- Max call duration and silence handling are **ElevenLabs agent settings**, not our code: a max-duration cap (≈ `MAX_CALL_SECONDS`, default 480) after which the agent wraps up and closes, and a silence timeout that plays the `config/greeting.yaml` silence prompt, then closes if still silent.
- The agent never: quotes prices or lead times, promises SLAs or outcomes, claims to be human, discusses other customers, takes card details, gives engineering advice. Each has a one-line deflection in `config/prompt.md` (part of the ElevenLabs agent prompt).
- `check_availability` and `book_meeting` are the slow webhook tools (keep the handler quick). `take_message` and the conversation-init lookup fail soft: on error the call continues and the failure is logged to `events`.
- Dictation mode: when capturing an email, postcode, phone number or a name spelling, the agent reads the value back before moving on (prompt-driven; ElevenLabs handles turn-taking).

## 6. Qualification schema

Populated by the LLM during the call (draft) and extracted again from the transcript post-call in Windmill (authoritative). Stored on the HubSpot contact as custom properties prefixed `cf_`, and in Neon `calls.extraction`.

| Field | Type | Values |
|---|---|---|
| `organisation` | string | |
| `caller_role` | enum | `facilities_manager`, `managing_agent`, `lift_contractor`, `landlord_owner`, `consultant`, `installer`, `other`, `unknown` |
| `asset_type` | multi-enum | `lifts`, `car_parks`, `alarm_panels`, `other` |
| `estate_size` | int | number of lifts or sites, whichever the caller gives |
| `estate_size_unit` | enum | `lifts`, `sites` |
| `current_connectivity` | enum | `pstn_copper`, `existing_4g`, `mixed`, `unknown` |
| `driver` | enum | `pstn_switch_off`, `failures`, `new_build`, `contract_renewal`, `cost`, `other`, `unknown` |
| `timeline` | enum | `immediate`, `1_3_months`, `3_6_months`, `6_plus`, `unknown` |
| `decision_authority` | enum | `decision_maker`, `influencer`, `researcher`, `unknown` |
| `contact_email` | string | validated, read back |
| `notes` | string | anything else material, one paragraph |

Scoring is a weighted sum defined in `config/scoring.yaml` with a `high_value_threshold`. Weights and threshold are Noel's to set; the file ships with defaults and is loaded at call start from Neon `config` (seeded from the file).

## 7. Agent tools

Tools are **ElevenLabs webhook tools** that call our HTTPS webhook service, plus the pre-call **conversation-init** webhook. Each validates input, logs an `events` row, and returns compact JSON the agent can speak from. Auth: a secret header on each tool; the service allowlists ElevenLabs' egress IPs (§12).

| Tool | Input | Output | Behaviour |
|---|---|---|---|
| `lookup_caller` | (conversation-init) `caller_id` | `dynamic_variables` + `first_message` + `asr.keywords` | Not a mid-call tool: the **conversation-init webhook** runs before the greeting, reads `system__caller_id`, does the HubSpot contact search (§9), and returns the caller context as dynamic variables plus the greeting and STT keywords. Fail soft (unknown caller → generic greeting). |
| `check_availability` | `from_iso, to_iso` | `{slots: [iso…]}` (max 6) | Cal.com `GET /v2/slots` for the expert's event type. Business hours only. Cached 60 s per call. |
| `book_meeting` | `slot_iso, name, email, organisation, phone, notes` | `{booking_id, start_iso, status}` | Cal.com `POST /v2/bookings`; `organisation` and `phone` required. Returns the start time for read-back. |
| `take_message` | `category, summary, callback_number, urgency, site` | `{message_id}` | Writes to Neon `messages`; the HubSpot note/task is created post-call by Windmill. |
| `end_call` | — | — | Handled by ElevenLabs (the agent hangs up); the outcome is derived post-call from the transcript. |

State-gated availability: `check_availability` and `book_meeting` are enabled on the agent only once `high_value` is true for a `new_enquiry`. `take_message` is always available.

## 8. Agent pipeline

- **Voice loop:** ElevenLabs Agents hosts VAD, turn-taking, STT, LLM and TTS. There is no local pipeline, no Silero/Deepgram, no `agent/providers/`.
- **Voice + model:** a British-English ElevenLabs voice (Noel to pick — `TTS_VOICE_ID` / agent config) and an agent model chosen for the latency budget. Per-turn latency is reported in `conversation_turn_metrics` (post-call), logged to Neon `events`.
- **Config at call start (§13):** the **conversation-init webhook** returns the agent's `dynamic_variables` (it must include *every* variable defined on the agent) plus `first_message` (the greeting from Neon config), optional `prompt` overrides, and `asr.keywords` (from `config/terms.yaml` / Neon `terms`). This is how "config read from Neon at call start" survives without a local agent.
- **Privacy / no recording:** `platform_settings.privacy.record_voice: false` (no audio stored) and `retention_days: 30` (ElevenLabs keeps the transcript 30 days — also the webhook recovery window). The post-call webhook's "Send audio data" is off, so only `post_call_transcription` reaches us. Both privacy fields live in the agent config JSON (versioned if pulled via `elevenlabs agents pull`).
- **CLI:** Telnyx delivers `+E.164` (`+44…`); `system__caller_id` carries it to the conversation-init webhook, which passes it unchanged to the HubSpot lookup (`search_contact_by_phone` handles the `+` and both forms — PR #4) and later to Cal.com `attendeePhoneNumber`.
- **Session end:** ElevenLabs fires the **`post_call_transcription`** webhook (signed with HMAC `ElevenLabs-Signature`, **not** a bearer token) to our webhook service. The service verifies it with the raw body (`construct_event`), returns 200, and triggers Windmill `post_call`. Idempotent on `data.conversation_id`; transcript turns are `{role: agent|user, message, time_in_call_secs}`; `analysis.transcript_summary` is available but the §11 `extract` step stays authoritative. On a failed Neon/Notion write, log it (don't drop) — ElevenLabs retries and the transcript is refetchable by `conversation_id` for 30 days, and it auto-disables a webhook after 10 consecutive failures with no success in 7 days.

## 9. HubSpot configuration

Provisioned idempotently by `scripts/provision_hubspot.py` (creates what is missing; never renames or deletes).

- **Contact properties** (group "ControlFreq AI Receptionist"): `cf_caller_role`, `cf_asset_type`, `cf_estate_size`, `cf_estate_size_unit`, `cf_current_connectivity`, `cf_driver`, `cf_timeline`, `cf_decision_authority`, `cf_lead_score` (number), `cf_high_value` (bool), `cf_last_ai_call_id`, `cf_ai_call_summary` (text).
- **Deal pipeline:** the existing **Sales Pipeline** (`HUBSPOT_DEAL_PIPELINE_ID=default`). Receptionist outcomes map to existing stages: Qualified – not booked → "Lead Identified" (`6139983093`), Discovery booked → "Initial Contact" (`6139983094`). No new pipeline (Starter allows two).
- **Booking:** on Cal.com (event 7103844), not HubSpot — see §7. There is no HubSpot meeting link.
- **Service Key scopes:** contacts, companies, deals (read/write); call engagements (read/write); owners (read). Auth is a HubSpot Service Key, not a legacy private app (DECISIONS); no scheduler scope since booking is Cal.com. `HUBSPOT_PROVISION_KEY` additionally needs schema (property) write for `provision_hubspot.py`.
- **Call engagement per call:** `hs_timestamp`, `hs_call_title` ("AI receptionist — <intent>"), `hs_call_body` (summary, outcome, Windmill call-record link), `hs_call_direction=INBOUND`, `hs_call_status=COMPLETED`, `hs_call_duration`, `hs_call_from_number`, `hs_call_to_number`; associated to contact, company and deal where they exist. `hs_call_recording_url` left empty in MVP.
- **Workflow (built in the HubSpot UI, documented in `docs/DECISIONS.md`):** when the associated contact's `cf_high_value = true` and a deal is created in the **Sales Pipeline** (`default`) at **either** stage — `6139983093` ("Lead Identified" = Qualified – not booked) **or** `6139983094` ("Initial Contact" = Discovery booked) → task for the expert due same day, and a Slack post via HubSpot's Slack integration with contact, organisation, score and summary. A high-value caller who did *not* book most needs the follow-up, so the trigger covers both stages. (`cf_high_value` is a contact property, so in a deal workflow it is an *associated-contact* filter. Stages show by their HubSpot label — "Lead Identified" / "Initial Contact" — not the outcome name. The trigger must match the real pipeline/stages or the task + alert never fire.)

Phone matching: HubSpot stores numbers as entered. On every write, store E.164 in `phone`. On lookup, search E.164 and UK national formats.

## 10. Neon schema

See `db/schema.sql`. Tables: `calls`, `transcripts`, `events`, `messages`, `config`, `terms`. `db/migrate.py` applies the schema idempotently; `scripts/seed_config.py` loads `config/*.yaml` and `config/prompt.md` into `config` and `terms`.

## 11. Windmill

Self-hosted on the host, Postgres on Neon (`WINDMILL_DATABASE_URL`). Python scripts only.

- **Flow `post_call`** (triggered by the webhook service after it verifies the ElevenLabs `post_call_transcription` HMAC signature — not a bearer token — and forwards the transcript):
  1. `ingest` — upsert Neon `calls` and `transcripts` from the ElevenLabs transcript (idempotent on `conversation_id`).
  2. `extract` — one LLM call over the full transcript with the §6 schema as a strict JSON schema; overrides the agent's draft.
  3. `score` — same rules as the agent (`config/scoring.yaml` from Neon); writes `lead_score`, `high_value`.
  4. `hubspot_upsert` — contact by phone/email, company by organisation name (create if missing), properties set.
  5. `deal` — if `high_value` and intent `new_enquiry`: create a deal in the existing Sales Pipeline (`default`) at the stage matching outcome (Discovery booked → 6139983094, Qualified – not booked → 6139983093), associated to contact and company; idempotent on `cf_last_ai_call_id`.
  6. `call_engagement` — create the HubSpot call engagement (§9).
  7. `messages` — for each Neon `messages` row for this call: HubSpot note on the contact, or a task if `urgency = high`.
  8. `transcript_log` — append this call to the **Notion** "Call transcripts" database (pitch review): one row per call — date, caller, company, outcome, and a short summary (objections, questions we couldn't answer) — with the full transcript in the page body, so it stays searchable/filterable. Idempotent on `call_id` so reruns don't duplicate. Needs `NOTION_API_KEY` + `NOTION_TRANSCRIPTS_DB_ID`.
  9. `finalise` — update Neon `calls` with HubSpot IDs and `processed_at`.
  Retries: 3 per step with backoff; on terminal failure, Slack message to Noel with `call_id` and step. Reruns are safe.
- **Script `rc_missed_call_alert`** — port of the current n8n workflow (RingCentral webhook → Slack DM). Export the n8n workflow JSON into `windmill/rc_missed_call_alert/reference/` first; preserve behaviour exactly; then disable the n8n workflow.
- **Schedule `retention`** — nightly: no audio recordings in the MVP, so nothing to prune there; delete Notion "Call transcripts" rows older than **12 months**; purge Neon transcripts older than the retention policy if Noel sets one; replay undelivered `post_call` payloads from `events`.

## 12. Infrastructure

- **Host:** Ubuntu 24.04, 4 vCPU / 8 GB, UK region, public IPv4. Docker Compose, single file `infra/docker-compose.yml`.
- **Services:** `windmill-server`, `windmill-worker`, the `agent` **webhook service**, `caddy`. No `redis` / `livekit` / `livekit-sip` — the voice loop is ElevenLabs and no SIP reaches our host.
- **Network:**
  - SIP terminates at ElevenLabs, not our host — no SIP/RTP ports, no `use_external_ip`, no SIP firewall rules here. The only inbound surface is **HTTPS**.
  - Caddy terminates TLS and fronts both the webhook service and the Windmill UI.
  - Lock the webhook service down: allowlist ElevenLabs' egress IPs (EU `35.204.38.71`, `34.147.113.54`; US `34.67.146.145`, `34.59.11.47`), require the tool secret header, and verify the post-call HMAC signature.
  - The Telnyx↔ElevenLabs trunk (Telnyx FQDN connection to `sip.rtc.elevenlabs.io`, TCP/TLS, inbound `+E.164`, Allowed Source IPs `185.246.41.140`/`.141`, EU region; number imported into ElevenLabs) is configured in the Telnyx and ElevenLabs portals — see `infra/telnyx/` and `infra/elevenlabs/`.
- **Secrets:** `.env` on the host (mode 0600); Windmill variables for keys used by flows. `ELEVENLABS_API_KEY`, the post-call-webhook HMAC secret, the tool-auth secret, the Telnyx API key (provisioning only) and the Notion key (`NOTION_API_KEY`) live in `.env` (and Windmill variables where a flow needs them), never in the repo.
- **Backups:** Neon handles the database (calls + transcripts). No audio recordings in the MVP. The repo is the configuration.
- **Observability:** JSON logs to stdout; per-turn latency, tool latency and errors in Neon `events`. A SQL view `calls_today` is enough for MVP.

## 13. Config files

- `config/greeting.yaml` — `business_name`, `greeting` (fixed spoken text with AI disclosure and a call-logging notice — wording to reflect "no audio recording, transcript kept"; Noel to approve), `closing`, `silence_prompt`, `emergency_instruction`, `expert_name`, `expert_title`, `business_hours`.
- `config/prompt.md` — the system prompt template. Only `prompt.py` renders it.
- `config/scoring.yaml` — weights and threshold.
- `config/terms.yaml` — STT key terms with categories.

All are seeded into Neon by `scripts/seed_config.py`; the **conversation-init webhook** reads them from Neon at call start (greeting → `first_message`, terms → `asr.keywords`, plus the prompt), so Noel can change behaviour without redeploying the agent.

## 14. Build phases and definition of done

**Phase 0 — Scaffold and stack.** Repo layout, `uv` project, `docker compose up` brings up Windmill on Neon, the webhook service and Caddy (no Redis/LiveKit). `db/migrate.py` applies the schema; `seed_config.py` loads config. Every image tag pinned and recorded. *Done when:* containers healthy, Windmill UI reachable over TLS, `select count(*) from config` returns the seeded keys.

**Phase 1 — HubSpot + Cal.com.** `provision_hubspot.py` creates the `cf_` properties (the pipeline is the existing Sales Pipeline, not created); `agent/hubspot/` CRM client (`search_contact_by_phone`, `upsert_contact`, `upsert_company`, `create_deal`, `create_call`) and `agent/calcom/` booking client (`get_availability`, `book_meeting`). *Done when:* a test script books a real Cal.com slot, it appears in Google Calendar, the confirmation email arrives, and unit tests pass against fixtures.

**Phase 2 — Telephony.** A Telnyx UK 0330 DID (`+443301900784`) on an FQDN SIP connection to `sip.rtc.elevenlabs.io` (TCP/TLS, inbound `+E.164`, Allowed Source IPs `185.246.41.140`/`.141`); the number is imported into ElevenLabs from the SIP trunk; a minimal ElevenLabs agent answers with one fixed line. RingCentral's after-hours / no-answer divert to the 0330 number is configured. *Done when:* dialling the number (directly and via the RingCentral divert) reaches the ElevenLabs agent with the correct CLI, and a Neon `calls` row is created from the post-call webhook.

**Phase 3 — Agent + webhook service.** Configure the ElevenLabs agent (prompt from §13, British voice, `record_voice: false`, `retention_days: 30`, tools §7, conversation-init) and build the webhook service (`agent/`): conversation-init (caller lookup + dynamic vars), the tool webhooks, and the HMAC-verified post-call receiver. *Done when:* the ten core calls in `docs/TEST-CALLS.md` pass over a real call, the tools work mid-call, and the post-call webhook writes the Neon `calls`/`transcripts` row.

**Phase 4 — Windmill.** `post_call` end to end; `rc_missed_call_alert` ported and n8n disabled; `retention` scheduled. *Done when:* a test call produces the HubSpot contact, deal, call engagement, Slack alert and the Notion "Call transcripts" row within 60 s of hang-up, and rerunning the flow changes nothing.

**Phase 5 — Go-live.** All twenty test calls pass; `config/greeting.yaml` wording approved by Noel; RingCentral after-hours rule and no-answer forwarding set to divert to the Telnyx number; go-live checklist in `docs/STATUS.md` signed off. Two weeks after-hours only with every transcript reviewed, then overflow.

## 15. After the MVP (not now)

1. Live warm transfer when the expert is available: availability check, then a transfer via Telnyx/ElevenLabs (or a RingCentral route) to a human, context pushed to Slack before pickup. Unlocks daytime traffic.
2. Self-learning knowledge base: unanswered questions → Neon `kb_queue` → Windmill approval step → Slack approve/edit → `kb_entries` with pgvector → retrieval tool in the agent.
3. Inbox: Windmill App over Neon (calls, transcript, audio, tags, KB queue).
4. Outbound: HubSpot form submission → Windmill → callback within minutes; PSTN switch-off campaign to the existing base.
5. Own the model: a custom LLM behind ElevenLabs' custom-LLM setting (`LLM_BASE_URL`, e.g. vLLM on a GPU host), fine-tuned on reviewed transcripts; self-host STT/TTS only if ElevenLabs is ever replaced.
6. Audio recording if ever needed (ElevenLabs `record_voice` or Telnyx recording) with retention, and recording URLs into HubSpot via signed links.

## 16. Open questions

Tracked in `docs/QUESTIONS.md`. Nothing in this spec that touches a caller's ears or a credential is to be guessed.
