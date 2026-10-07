# Inbound Calls — Build Spec v1.0 (MVP)

Owner: Noel Sesto, ControlFreq Ltd. Builder: Claude Code. Date: 3 October 2026.

## 1. Purpose

A self-hosted AI call answering service for ControlFreq that:

- answers **after-hours and unanswered** calls on the main RingCentral number,
- recognises existing customers by CLI and takes a structured message,
- qualifies new enquiries against a fixed schema and books **high-value leads into a 30-minute discovery call** with the solution expert via HubSpot,
- logs every call, transcript and outcome in ControlFreq's own store and in HubSpot,
- keeps the data and the model layer under ControlFreq's control, with every provider swappable.

Reference points reverse-engineered for this build: Cyberstaff (call-forwarding ingress, cascaded voice loop, rules, dashboard) and fonio.ai (pre/during/post-call hooks, extraction schema, availability-aware transfer, specialised terms, self-learning knowledge base with approval, outbound campaigns). The MVP takes the first three of fonio's ideas; the rest are scheduled in §15.

## 2. Design principles

1. **The best part is no part.** Six components and nothing else: RingCentral, Telnyx, LiveKit, Neon, Windmill, HubSpot. Slack is reached only through HubSpot's native integration and Windmill's failure alerts. (Telephony ingress is a Telnyx SIP trunk into LiveKit SIP; FreeSWITCH and RingCentral SIP registration were dropped on 2026-10-05 — see DECISIONS.)
2. **Synchronous in the agent, asynchronous in Windmill.** Mid-call tools are Python functions in the agent worker calling HubSpot and Neon directly. Post-call work and anything with a human in the loop runs in Windmill. Nothing mid-call calls Windmill.
3. **HubSpot is the system of record** for contacts, companies, deals, meetings and call engagements. **Neon is the receptionist's store**: calls, transcripts, events, config, terms. The only overlap is linking IDs.
4. **Providers behind interfaces.** STT, LLM and TTS are hosted providers in the MVP, each behind an interface in `agent/providers/`. The LLM is reached only through an OpenAI-compatible endpoint so moving to a self-hosted model on vLLM is a URL and model-name change.
5. **No GPU, no inference on the host** in the MVP. Prove the flow first; own the inference second.
6. **Nothing a caller hears is invented.** Greeting, disclosures, emergency wording, hours, product claims and pricing come from `config/`. Missing values are questions.
7. **UK compliance by default.** AI disclosure and a call-logging notice in the greeting; transcript retention enforced by a scheduled job; **no audio recording in the MVP**. Transcripts stay on the host except (a) the summary written to HubSpot and (b) the transcript + summary appended to ControlFreq's "Call transcripts" pitch-review document (Phase 4, §11).

## 3. Scope

### In scope (MVP)
- Ingress: RingCentral after-hours rule and no-answer forwarding on the main office number divert the call externally to a Telnyx UK number, which routes over a Telnyx SIP trunk to LiveKit SIP. Caller ID (CLI) is preserved end to end so the HubSpot phone lookup works.
- Intents: `new_enquiry`, `existing_customer`, `supplier_or_sales`, `other`.
- Pre-call: CLI lookup in HubSpot.
- Qualification against the schema in §6, scoring per `config/scoring.yaml`.
- Booking: availability check and booking against the expert's HubSpot meeting link; confirmation email and calendar invite come from HubSpot.
- Message-taking for existing customers and unqualified enquiries.
- Post-call: extraction, HubSpot upsert, deal creation when qualified, call engagement with summary, Neon write, and the transcript + summary appended to a running pitch-review document (§11).
- Guardrails: max duration, silence handling, no pricing, no promises, AI disclosure.
- **No audio recording in the MVP** (`record_session` / egress dropped); full two-sided, timestamped transcripts kept in Neon for every call (see §8).
- Migration of the RingCentral missed-call Slack alert from n8n into Windmill, then n8n switched off.

### Out of scope (MVP) — see §15
Live transfer to a human; daytime overflow before after-hours has run clean; outbound callbacks; self-learning knowledge base; inbox UI; SMS/WhatsApp; self-hosted STT/TTS/LLM; noise cancellation; Apollo in the call path.

## 4. Architecture

```
Caller ──PSTN──▶ RingCentral (office PBX) ──(after-hours / no-answer divert)──▶ Telnyx UK number
                                                              │ Telnyx SIP trunk, CLI preserved
                                                              │ (LiveKit SIP IP-restricted to Telnyx)
                                                              ▼
                                                        LiveKit SIP ──▶ LiveKit server ──▶ room per call
                                                                                           │
                                                                                           ▼
                                                                                 Agent worker (Python)
                                                                   VAD · turn detector · STT · LLM · TTS
                                                                   tools: lookup_caller, check_availability,
                                                                          book_meeting, take_message, end_call
                                                                           │ sync            │ on session end
                                                                           ▼                 ▼
                                                                        HubSpot        Windmill flow post_call
                                                                        + Neon         ──▶ extract ▶ score ▶ HubSpot upsert
                                                                                       ──▶ deal ▶ call engagement ▶ Neon
                                                                                       HubSpot workflow ▶ task + Slack
```

### 4.1 Components and responsibilities

| Component | Role | Notes |
|---|---|---|
| RingCentral | Office phone system; ingress divert | Existing office PBX. The after-hours rule and no-answer forwarding on the main number divert the call externally to the Telnyx DID. No SIP registration, no receptionist device. Later: a route for human transfer. |
| Telnyx | SIP trunk + DID | A UK phone number (DID) on a Telnyx SIP connection. Receives the diverted PSTN call and routes it to LiveKit SIP over the internet, IP-restricted to Telnyx (and/or credentialed). Preserves CLI. A London **020** geographic DID; no call recording in the MVP (§8). |
| LiveKit | Voice transport | `livekit-server` + `livekit-sip` + Redis. One inbound trunk accepting INVITEs only from Telnyx. One dispatch rule: every call → agent `inbound-receptionist`, room `call-<uuid>`. |
| Agent worker | The receptionist | Python, LiveKit Agents. Pipeline and tools in §7–§8. |
| Neon | Store | Project with two databases: `receptionist` (schema in `db/schema.sql`) and `windmill`. |
| Windmill | Async + human-in-the-loop | Self-hosted on the host, database on Neon. Flow `post_call`, script `rc_missed_call_alert`, schedule `retention`. |
| HubSpot | System of record for sales | Properties, meeting link, private app, deal pipeline, workflow that creates the expert's task and Slack message. |

### 4.2 Repository layout (target)

```
agent/            LiveKit Agents worker
  main.py         entrypoint, session wiring
  prompt.py       renders config/prompt.md with config values from Neon
  tools/          one module per tool (§7)
  providers/      stt.py, llm.py, tts.py interfaces + implementations
  hubspot/        thin client: contacts, companies, deals, calls, scheduler
  store/          Neon access (asyncpg), event logging
windmill/         Python scripts and exported flow definitions
  post_call/
  rc_missed_call_alert/
  retention/
infra/
  docker-compose.yml
  livekit/          livekit.yaml, sip.yaml, inbound trunk + dispatch JSON
  telnyx/           SIP connection + DID notes (provisioned in the Telnyx portal; Phase 2)
  caddy/            Caddyfile (TLS for Windmill UI)
db/
  schema.sql, migrate.py
config/
  prompt.md, scoring.yaml, terms.yaml, greeting.yaml
scripts/
  provision_hubspot.py, provision_livekit.py, seed_config.py, smoke_call.py
tests/
docs/
```

## 5. Call flow

A state machine executed by the LLM under the prompt and enforced by tool availability per state.

1. **Greeting** — from `config/greeting.yaml`: business name, that this is an AI assistant, that the call is recorded. Fixed text, spoken, not generated.
2. **Identify** — `lookup_caller(cli)` runs before the greeting finishes. Known contact → greet by name; intent defaults to `existing_customer` but is confirmed in one question. Unknown or withheld CLI → ask who is calling and the organisation.
3. **Intent** — one open question ("How can I help?"), classified into the four intents. Ambiguous → one clarifying question, then `other`.
4. **Branch**
   - `new_enquiry` → **Qualify** (§6, conversationally, not as a form; at most one question per turn; skip anything already said) → **Score** → if `high_value`: offer a discovery call with the expert, `check_availability`, offer two slots, `book_meeting`, read back date, time, name and email → close. If not high value: capture organisation, name, email, requirement; say the team will email information; `take_message(category=enquiry)` → close.
   - `existing_customer` → ask site, issue, urgency, best callback number; `take_message(category=support)`. If the caller describes an active emergency, say `emergency_instruction` from `config/greeting.yaml` verbatim first, then take details → close.
   - `supplier_or_sales` → name, company, purpose, email; `take_message(category=supplier)`; no booking, no transfer → close politely.
   - `other` → `take_message(category=other)` → close.
5. **Close** — summarise what will happen next in one sentence, thank, `end_call`.

### 5.1 Guardrails (in code where possible, in prompt otherwise)
- Max call duration `MAX_CALL_SECONDS` (default 480): at 420 s the agent wraps up; at 480 s it closes with the message.
- Silence: after 8 s of no speech, the silence prompt; after a second 8 s, close.
- The agent never: quotes prices or lead times, promises SLAs or outcomes, claims to be human, discusses other customers, takes card details, gives engineering advice. Each has a one-line deflection in `config/prompt.md`.
- Only `check_availability` and `book_meeting` are blocking tools (target < 2 s). `take_message` and `lookup_caller` fail soft: on error the call continues and the failure is logged to `events` for Windmill to retry.
- Dictation mode: when asking for an email, postcode, phone number or a name spelling, turn-detector patience is raised and the value is read back before moving on.

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

All tools are Python functions registered with the LiveKit Agents session. Each validates input, times out, logs an `events` row, and returns a compact dict the model can speak from.

| Tool | Input | Output | Behaviour |
|---|---|---|---|
| `lookup_caller` | `phone_e164` | `{found, contact_id, first_name, company, lifecycle_stage, open_deal_count, last_summary}` | HubSpot contacts search on `phone` and `mobilephone`, trying E.164 and UK national formats. 1.5 s timeout, fail soft. |
| `check_availability` | `from_iso, to_iso` | `{slots: [iso…]}` (max 6) | HubSpot Scheduler API for the expert's meeting link. Business hours only. Cached 60 s per call. |
| `book_meeting` | `slot_iso, first_name, last_name, email, phone, organisation, notes` | `{meeting_id, start_iso, confirmation_sent}` | Books on the HubSpot meeting link. Returns the start time for read-back. |
| `take_message` | `category, summary, callback_number, urgency, site` | `{message_id}` | Writes to Neon `messages`; HubSpot note/task is created post-call by Windmill. |
| `end_call` | `reason` | — | Marks outcome, triggers session end. |

State-gated availability: `check_availability` and `book_meeting` are registered only once `high_value` is true for a `new_enquiry`. `take_message` is always available.

## 8. Agent pipeline

- **VAD:** Silero.
- **Turn detection:** LiveKit's end-of-turn model (English). Patience raised in dictation mode.
- **STT:** Deepgram streaming with key terms from `config/terms.yaml` and Neon `terms` (product names, standards, staff names, major client names). Interface `STTProvider`; later implementation `whisper_local`.
- **LLM:** OpenAI-compatible client against `LLM_BASE_URL`; tool calling and streaming required. Interface `LLMProvider`. Prompt rendered by `prompt.py` from `config/prompt.md` plus runtime values (caller context, hours, expert name, current date and time in `Europe/London`).
- **TTS:** Cartesia or ElevenLabs, a British English voice chosen by Noel; streaming. Interface `TTSProvider`; later `kokoro_local`.
- **Noise cancellation:** none in MVP (self-hosted LiveKit; G.711 narrowband audio). Revisit with RNNoise or DeepFilterNet if needed.
- **Latency budget:** ≤ 800 ms from caller end-of-turn to first audio. Measured and logged per turn (`events.type = turn_latency`).
- **Recording:** **no audio recording in the MVP** — `record_session` / LiveKit egress / Telnyx recording are all dropped. Instead the full two-sided transcript (every turn, timestamped, roles agent/caller) is persisted to Neon `transcripts` for every call. `calls.recording_path` stays null (column kept for a later phase). Audio recording may return post-MVP (§15).
- **Session end:** the agent POSTs `{call_id, room, started_at, ended_at, caller_e164, cli_present, intent, outcome, transcript[], extraction_draft, tool_results, recording_path}` to `WINDMILL_POST_CALL_WEBHOOK` with bearer `WINDMILL_WEBHOOK_TOKEN`. Retries 3× with backoff; on final failure the payload is written to Neon `events` for the `retention` job to replay.

## 9. HubSpot configuration

Provisioned idempotently by `scripts/provision_hubspot.py` (creates what is missing; never renames or deletes).

- **Contact properties** (group "ControlFreq AI Receptionist"): `cf_caller_role`, `cf_asset_type`, `cf_estate_size`, `cf_estate_size_unit`, `cf_current_connectivity`, `cf_driver`, `cf_timeline`, `cf_decision_authority`, `cf_lead_score` (number), `cf_high_value` (bool), `cf_last_ai_call_id`, `cf_ai_call_summary` (text).
- **Deal pipeline:** `Inbound` with stages `Qualified – not booked` and `Discovery booked` (IDs into `.env`). If Noel already has a pipeline, use his — question, not guess.
- **Meeting link:** the expert's 30-minute "Discovery call", connected to their Google Calendar, booking-form fields mapped to the properties above where HubSpot allows.
- **Private app scopes:** contacts, companies, deals (read/write); calls engagements (read/write); scheduler meeting links (read) and booking; owners (read). Verify exact scope names against current HubSpot docs when creating the app.
- **Call engagement per call:** `hs_timestamp`, `hs_call_title` ("AI receptionist — <intent>"), `hs_call_body` (summary, outcome, Windmill call-record link), `hs_call_direction=INBOUND`, `hs_call_status=COMPLETED`, `hs_call_duration`, `hs_call_from_number`, `hs_call_to_number`; associated to contact, company and deal where they exist. `hs_call_recording_url` left empty in MVP.
- **Workflow (built in the HubSpot UI, documented in `docs/DECISIONS.md`):** when `cf_high_value = true` and a deal is created in `Inbound` → task for the expert due same day, and a Slack post via HubSpot's Slack integration with contact, organisation, score and summary.

Phone matching: HubSpot stores numbers as entered. On every write, store E.164 in `phone`. On lookup, search E.164 and UK national formats.

## 10. Neon schema

See `db/schema.sql`. Tables: `calls`, `transcripts`, `events`, `messages`, `config`, `terms`. `db/migrate.py` applies the schema idempotently; `scripts/seed_config.py` loads `config/*.yaml` and `config/prompt.md` into `config` and `terms`.

## 11. Windmill

Self-hosted on the host, Postgres on Neon (`WINDMILL_DATABASE_URL`). Python scripts only.

- **Flow `post_call`** (webhook trigger, bearer token):
  1. `ingest` — upsert Neon `calls` and `transcripts` from the payload (idempotent on `call_id`).
  2. `extract` — one LLM call over the full transcript with the §6 schema as a strict JSON schema; overrides the agent's draft.
  3. `score` — same rules as the agent (`config/scoring.yaml` from Neon); writes `lead_score`, `high_value`.
  4. `hubspot_upsert` — contact by phone/email, company by organisation name (create if missing), properties set.
  5. `deal` — if `high_value` and intent `new_enquiry`: create a deal in `Inbound` at the stage matching outcome, associated to contact and company; idempotent on `cf_last_ai_call_id`.
  6. `call_engagement` — create the HubSpot call engagement (§9).
  7. `messages` — for each Neon `messages` row for this call: HubSpot note on the contact, or a task if `urgency = high`.
  8. `transcript_log` — append this call's full transcript plus a short summary (caller, company, outcome, objections, questions we couldn't answer) to the running "Call transcripts" document for pitch review. Destination (Google Doc vs Notion) is an open question (§16 / `docs/QUESTIONS.md`); idempotent on `call_id` so reruns don't duplicate.
  9. `finalise` — update Neon `calls` with HubSpot IDs and `processed_at`.
  Retries: 3 per step with backoff; on terminal failure, Slack message to Noel with `call_id` and step. Reruns are safe.
- **Script `rc_missed_call_alert`** — port of the current n8n workflow (RingCentral webhook → Slack DM). Export the n8n workflow JSON into `windmill/rc_missed_call_alert/reference/` first; preserve behaviour exactly; then disable the n8n workflow.
- **Schedule `retention`** — nightly: no audio recordings in the MVP, so nothing to prune there; purge transcripts older than the retention policy if Noel sets one; replay undelivered `post_call` payloads from `events`.

## 12. Infrastructure

- **Host:** Ubuntu 24.04, 4 vCPU / 8 GB, UK region, public IPv4. Docker Compose, single file `infra/docker-compose.yml`.
- **Services:** `redis`, `livekit`, `livekit-sip`, `agent`, `windmill-server`, `windmill-worker`, `caddy`. (No FreeSWITCH — Telnyx is an external SIP trunk, not a container.)
- **Network:**
  - LiveKit SIP must be reachable from Telnyx: publish its SIP signalling port and RTP range on the host, firewalled to Telnyx's SIP/media IP ranges only. The inbound trunk authenticates Telnyx (IP allowlist, and/or SIP credentials).
  - CLI is carried in the SIP `From` / `P-Asserted-Identity` header from Telnyx and preserved into the room so `lookup_caller` can use it.
  - Caddy terminates TLS for the Windmill UI and nothing else.
- **Secrets:** `.env` on the host (mode 0600); Windmill variables for keys used by flows. Telnyx SIP credentials / API key live in `.env` (and Windmill variables where a flow needs them), never in the repo.
- **Backups:** Neon handles the database (calls + transcripts). No audio recordings in the MVP. The repo is the configuration.
- **Observability:** JSON logs to stdout; per-turn latency, tool latency and errors in Neon `events`. A SQL view `calls_today` is enough for MVP.

## 13. Config files

- `config/greeting.yaml` — `business_name`, `greeting` (fixed spoken text with AI disclosure and a call-logging notice — wording to reflect "no audio recording, transcript kept"; Noel to approve), `closing`, `silence_prompt`, `emergency_instruction`, `expert_name`, `expert_title`, `business_hours`.
- `config/prompt.md` — the system prompt template. Only `prompt.py` renders it.
- `config/scoring.yaml` — weights and threshold.
- `config/terms.yaml` — STT key terms with categories.

All are seeded into Neon by `scripts/seed_config.py`; the agent reads from Neon at call start so Noel can change behaviour without a deploy.

## 14. Build phases and definition of done

**Phase 0 — Scaffold and stack.** Repo layout, `uv` project, `docker compose up` brings up Redis, LiveKit, LiveKit SIP, Windmill on Neon, Caddy. `db/migrate.py` applies the schema; `seed_config.py` loads config. Every image tag pinned and recorded. *Done when:* all containers healthy, Windmill UI reachable over TLS, `select count(*) from config` returns the seeded keys.

**Phase 1 — HubSpot.** `provision_hubspot.py` creates properties and pipeline; `agent/hubspot/` client with `search_contact_by_phone`, `upsert_contact`, `upsert_company`, `create_deal`, `create_call`, `get_availability`, `book_meeting`. *Done when:* a test script books a real meeting on the expert's link, it appears in Google Calendar, the confirmation email arrives, and unit tests pass against recorded fixtures.

**Phase 2 — Telephony.** A Telnyx UK number on a SIP connection routes inbound calls to LiveKit SIP (IP-restricted to Telnyx), CLI preserved; the LiveKit inbound trunk + dispatch rule are provisioned by `scripts/provision_livekit.py`; a minimal agent speaks one fixed sentence and hangs up. RingCentral's after-hours / no-answer divert to the Telnyx number is configured. *Done when:* dialling the Telnyx number plays the sentence, the room appears in LiveKit, and the Neon `calls` row shows the correct CLI — both dialled directly and via the RingCentral divert.

**Phase 3 — Agent.** Full pipeline (§8), prompt, tools (§7), guardrails (§5.1), dictation mode, latency logging. *Done when:* the ten core calls in `docs/TEST-CALLS.md` pass over a real RingCentral call, median turn latency ≤ 800 ms, and no tool error leaks into speech.

**Phase 4 — Windmill.** `post_call` end to end; `rc_missed_call_alert` ported and n8n disabled; `retention` scheduled. *Done when:* a test call produces the HubSpot contact, deal, call engagement and Slack alert within 60 s of hang-up, and rerunning the flow changes nothing.

**Phase 5 — Go-live.** All twenty test calls pass; `config/greeting.yaml` wording approved by Noel; RingCentral after-hours rule and no-answer forwarding set to the extension; go-live checklist in `docs/STATUS.md` signed off. Two weeks after-hours only with every transcript reviewed, then overflow.

## 15. After the MVP (not now)

1. Live warm transfer when the expert is available: availability check, then a SIP transfer via Telnyx/LiveKit (or a RingCentral route) to a human, context pushed to Slack before pickup. Unlocks daytime traffic.
2. Self-learning knowledge base: unanswered questions → Neon `kb_queue` → Windmill approval step → Slack approve/edit → `kb_entries` with pgvector → retrieval tool in the agent.
3. Inbox: Windmill App over Neon (calls, transcript, audio, tags, KB queue).
4. Outbound: HubSpot form submission → Windmill → callback within minutes; PSTN switch-off campaign to the existing base.
5. Self-hosted inference: `whisper_local`, `kokoro_local`, vLLM behind `LLM_BASE_URL`; GPU host; fine-tune on reviewed transcripts.
6. Audio recording (LiveKit egress or Telnyx) with retention, and recording URLs into HubSpot via signed links.

## 16. Open questions

Tracked in `docs/QUESTIONS.md`. Nothing in this spec that touches a caller's ears or a credential is to be guessed.
