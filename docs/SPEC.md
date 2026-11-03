# Inbound Calls — Build Spec v1.2 (MVP)

Owner: Noel Sesto, ControlFreq Ltd. Builder: Claude Code. Date: 3 October 2026; revised 2 November 2026
(HubSpot removed; Apollo + Notion — DECISIONS 2026-11-02) and 3 November 2026 (Neon and Windmill
dropped; n8n runs caller lookup and post-call against Notion — DECISIONS 2026-11-03).

## 1. Purpose

A self-hosted AI call answering service for ControlFreq that:

- answers **after-hours and unanswered** calls on the main RingCentral number,
- recognises returning callers by CLI from the **Phone field of the Notion "Cody leads" database** and takes a structured message,
- qualifies new enquiries against a fixed schema and books **high-value leads into a 15-minute discovery call** with Noel Sesto, Technical Director, via Cal.com,
- logs every call, transcript and outcome in **Notion** (a lead-review row and a transcript row per call), and puts **qualified callers into Apollo** after the call,
- keeps the **data** under ControlFreq's control (ControlFreq's Notion is the record of every call); the voice loop (STT/LLM/TTS/turn-taking) is hosted by ElevenLabs Agents.

Reference points reverse-engineered for this build: Cyberstaff (call-forwarding ingress, cascaded voice loop, rules, dashboard) and fonio.ai (pre/during/post-call hooks, extraction schema, availability-aware transfer, specialised terms, self-learning knowledge base with approval, outbound campaigns). The MVP takes the first three of fonio's ideas; the rest are scheduled in §15.

## 2. Design principles

1. **The best part is no part.** The components: RingCentral, Telnyx, **ElevenLabs Agents**, Cal.com, **n8n**, Notion, Apollo, Slack (an incoming webhook) — plus one small HTTPS **webhook service** we host for the three Cal.com tools. **Neon and Windmill are dropped** (DECISIONS 2026-11-03); **HubSpot is removed** (2026-11-02). Telephony ingress is Telnyx → ElevenLabs over a SIP trunk; **LiveKit, the self-hosted Python agent, FreeSWITCH and RingCentral SIP registration are all dropped** (DECISIONS 2026-10-07/2026-10-05). The Python service will probably be dropped once n8n's own tools are tested (QUESTIONS).
2. **Nothing slow in the call path.** The caller lookup at call start is an n8n Notion query. Mid-call tools are ElevenLabs webhook tools that call our service, which talks only to Cal.com. **Apollo, Slack and every Notion write are post-call only**, in n8n, after the post-call webhook has been acknowledged.
3. **There is no Cody-owned database.** **Notion is the review surface and the record of every call** (one lead row and one transcript row per call), and the "Cody leads" **Phone** field (`+44` E.164) is the **caller directory** the call-start lookup needs, because Apollo cannot search by phone. **Apollo is the sales record** for qualified callers (contact, account, call record, deal, follow-up task).
4. **The voice loop is ElevenLabs.** STT, LLM, TTS and turn-taking are all hosted by ElevenLabs Agents (no `agent/providers/`, no local VAD/STT/TTS). A custom LLM endpoint is possible later via ElevenLabs' custom-LLM setting if we want to own the model (§15).
5. **No GPU, no inference on the host** in the MVP. Post-call extraction is ElevenLabs data collection (§6), not a separate LLM call.
6. **Nothing a caller hears is invented.** Greeting, disclosures, emergency wording, hours, product claims and pricing come from `config/`. Missing values are questions.
7. **UK compliance by default.** AI disclosure and a call-logging notice in the greeting; transcript retention enforced by a scheduled job; **no audio recording** — ElevenLabs `record_voice: false` and the post-call "Send audio data" toggle off. Notion is the record; transcripts are also processed by and stored at ElevenLabs for **30 days** (`retention_days: 30`), and a transcript + summary is written to ControlFreq's Notion "Call transcripts" database (§11; rows kept 12 months). Qualified callers' details and the call summary go to Apollo.

## 3. Scope

### In scope (MVP)
- Ingress: RingCentral after-hours / no-answer forwarding diverts the main office number to a Telnyx London **020** number (`+442045200783`), which trunks over SIP to **ElevenLabs Agents**. Caller ID (`+E.164`) is preserved so the phone lookup works.
- Intents: `new_enquiry`, `existing_customer`, `supplier_or_sales`, `other`.
- Pre-call: CLI lookup by the "Cody leads" Phone field, in n8n, within `INIT_LOOKUP_TIMEOUT_MS`.
- Qualification against the schema in §6, scoring per `config/scoring.yaml`.
- Booking: availability check and booking on Noel Sesto's **Cal.com** event 7747197 (`control-freq-discovery`, "Control Freq discovery call", 15 min, Google Meet) via a webhook tool; Cal.com sends the confirmation email and calendar invite. The booking title is "Discovery call with Noel Sesto, Technical Director – <organisation>". Event 7103844 ("LiftPulse Trial") is not used.
- Message-taking for existing customers and unqualified enquiries.
- Post-call (n8n): ElevenLabs data-collection extraction, scoring, Notion lead row + transcript row for every call; for qualified callers only, Apollo contact/account/call record/follow-up task (deal behind a flag, §9) and a Slack alert.
- Guardrails: max duration, silence handling, no pricing, no promises, AI disclosure.
- **No audio recording** (ElevenLabs `record_voice: false`, post-call "Send audio data" off); full two-sided, timestamped transcripts kept in Notion for every call (see §8).
- The RingCentral missed-call Slack alert stays in its existing n8n workflow.

### Out of scope (MVP) — see §15
Live transfer to a human; daytime overflow before after-hours has run clean; outbound callbacks; self-learning knowledge base; inbox UI; SMS/WhatsApp; self-hosted STT/TTS/LLM; noise cancellation; **Apollo in the call path**; **Apollo sequences** (Cody never enrols a caller in one).

## 4. Architecture

```
Caller ─PSTN─▶ RingCentral (office PBX) ─(after-hours / no-answer divert)─▶ Telnyx UK 020 (+442045200783)
                                                          │ SIP trunk → sip.rtc.elevenlabs.io
                                                          │ (TCP/TLS, +E.164, CLI preserved)
                                                          ▼
                                                 ElevenLabs Agents  (STT · LLM · TTS · turn-taking)
                                                   │ conversation-init webhook (call start) ──▶ n8n ─▶ Notion "Cody leads" by Phone
                                                   │ tool webhooks (mid-call) ──▶ Webhook service (HTTPS, we host) ─▶ Cal.com
                                                   │   check_availability, book_meeting, take_message
                                                   │ post_call_transcription (HMAC-signed, on hang-up)
                                                   ▼
                                          n8n post-call: score ▸ Notion transcript ▸ Notion lead row (+ any message)
                                                 ▸ (qualified) Apollo account ▸ contact ▸ call record ▸ [deal] ▸ task
                                                 ▸ (qualified) Slack alert
```

### 4.1 Components and responsibilities

| Component | Role | Notes |
|---|---|---|
| RingCentral | Office phone system; ingress divert | The after-hours rule and no-answer forwarding on the main number divert the call externally to the Telnyx DID. No SIP registration. Later: a route for human transfer. |
| Telnyx | SIP trunk + DID | A UK London **020** DID (`+442045200783`, replacing `+443301900784`) on a Telnyx FQDN SIP connection to `sip.rtc.elevenlabs.io` (TCP/TLS, inbound `+E.164`). Preserves CLI. No call recording (§8). |
| ElevenLabs Agents | The receptionist (voice loop) | Agent `agent_6901m4gzr6bdfjwsmte3fxepq946` ("Cody"). Hosts STT · LLM · TTS · turn-taking and post-call data collection (§6). Calls n8n for the call-start lookup and our service for the mid-call tools, and posts the signed transcript to n8n on hang-up. Privacy: `record_voice: false`, `retention_days: 30`. |
| n8n | Caller lookup + post-call | Conversation-init (Notion lookup by Phone) and the post-call flow (§11). Also the existing RingCentral missed-call alert and transcript retention. Has an inactive "Cody – Tools" workflow with the same three tools as our service. |
| Webhook service | Mid-call tools (HTTPS) | `agent/` (FastAPI): the three Cal.com tool webhooks, with no state. |
| Notion | Record + review + caller directory | "Cody leads" (one row per call, triage status; its Phone field is the caller directory) and "Call transcripts" (one row per call, transcript in the page body). Schemas in `agent/notion/schema.py`. |
| Apollo | Sales record for qualified callers | Post-call REST only: account, contact, call record (`call_identifier` = ElevenLabs conversation id), optional deal, follow-up task. No sequences. |
| Slack | Alert | Cody posts its own qualified-call alert to an incoming webhook (replaces the HubSpot workflow alert). |
| Cal.com | Discovery-call booking | Noel Sesto's event 7747197 (`control-freq-discovery`, https://cal.com/noelsesto/control-freq-discovery); the webhook service checks availability and books a 15-minute call with Noel Sesto, Technical Director, and Cal.com sends the calendar invite + confirmation email (§7). Not event 7103844. |

### 4.2 Repository layout

```
agent/            webhook service (FastAPI), no state
  app.py          HTTPS endpoints: the three tool webhooks
  tools/          one handler per webhook tool (§7)
  calcom/         Cal.com v2 client: availability + booking
  extraction.py   §6 schema ↔ ElevenLabs data collection
  prompt.py       fills the host name and deflections into config/prompt.md (provisioning)
  notion/         thin Notion client + the two database schemas (provisioning)
  scoring.py, apollo/, slack.py   no longer called since post-call moved to n8n (QUESTIONS)
  Dockerfile
windmill/         tombstone: replaced by n8n
infra/
  docker-compose.yml
  telnyx/           SIP connection + DID notes
  elevenlabs/       agent config notes: webhooks, tools, privacy
  caddy/            Caddyfile (TLS for the webhook service)
config/
  prompt.md, scoring.yaml, terms.yaml, greeting.yaml
scripts/
  provision_telnyx.py, provision_elevenlabs.py, provision_notion.py
tests/
docs/
```

The n8n workflows live in n8n, not in this repo.

## 5. Call flow

A state machine executed by the LLM under the prompt and enforced by tool availability per state.

1. **Greeting** — from `config/greeting.yaml`: the assistant's name (**Cody**), business name, that this is an AI assistant, and a call-logging notice (the call is transcribed and logged; no audio recording — §8). Wording is Noel's (§13). Delivered as the ElevenLabs agent's `first_message` via the conversation-init webhook — fixed text, not generated.
2. **Identify** — n8n's conversation-init webhook looks up `caller_id` (E.164) in the "Cody leads" Phone field before the greeting. Known caller → greet by name; intent defaults to `existing_customer` if they are a known customer, but is confirmed in one question. Unknown or withheld CLI → ask who is calling and the organisation.
3. **Intent** — one open question ("How can I help?"), classified into the four intents. Ambiguous → one clarifying question, then `other`.
4. **Branch**
   - `new_enquiry` → **Qualify** (§6, conversationally, not as a form; at most one question per turn; skip anything already said) → if high value: offer a 15-minute discovery call with Noel Sesto, our Technical Director, `check_availability`, offer two slots, `book_meeting`, read back date, time, that it is with Noel Sesto, name and email → close. If not high value: capture organisation, name, email, requirement; say the team will email information; `take_message(category=enquiry)` → close.
   - `existing_customer` → ask site, issue, urgency, best callback number; `take_message(category=support)`. If the caller describes an active emergency, say `emergency_instruction` from `config/greeting.yaml` verbatim first, then take details → close.
   - `supplier_or_sales` → name, company, purpose, email; `take_message(category=supplier)`; no booking, no transfer → close politely.
   - `other` → `take_message(category=other)` → close.
5. **Close** — summarise what will happen next in one sentence, thank, `end_call`.

### 5.1 Guardrails (in code where possible, in prompt otherwise)
- Max call duration and silence handling are **ElevenLabs agent settings**, not our code: a max-duration cap (≈ `MAX_CALL_SECONDS`, default 480) after which the agent wraps up and closes, and a silence timeout that plays the `config/greeting.yaml` silence prompt, then closes if still silent.
- The agent never: quotes prices or lead times, promises SLAs or outcomes, claims to be human, discusses other customers, takes card details, gives engineering advice. Each has a one-line deflection in `config/prompt.md` (part of the ElevenLabs agent prompt).
- `check_availability` and `book_meeting` are the slow webhook tools (Cal.com, 8 s timeout). On failure they return a `take_message` fallback and the caller never hears an error. n8n's conversation-init lookup must fail soft: on timeout or error the call starts as an unknown caller.
- Dictation mode: when capturing an email, postcode, phone number or a name spelling, the agent reads the value back before moving on (prompt-driven; ElevenLabs handles turn-taking).

## 6. Qualification schema

Extracted post-call by **ElevenLabs data collection** (`platform_settings.data_collection`, provisioned from `agent/extraction.py`) and parsed from `analysis.data_collection_results`; values outside the schema become `unknown`. Stored on the Notion lead row; qualified callers' name/email/organisation also go to Apollo.

| Field | Type | Values |
|---|---|---|
| `intent` | enum | `new_enquiry`, `existing_customer`, `supplier_or_sales`, `other` |
| `caller_name` | string | |
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

Scoring is a weighted sum defined in `config/scoring.yaml` with a `high_value_threshold`, applied by n8n's post-call flow (how the file reaches n8n is open — QUESTIONS). **Qualified** = `intent = new_enquiry` and score ≥ threshold. Weights and threshold are Noel's to set.

## 7. Agent tools

Tools are **ElevenLabs webhook tools** that call our HTTPS webhook service, plus the call-start **conversation-init** webhook, which is n8n's. Auth on the tools: the `X-Cody-Secret` header (`ELEVENLABS_TOOL_SECRET`); optionally allowlist ElevenLabs' egress IPs at Caddy (§12). Every tool takes `conversation_id`, mapped from the system variable `system__conversation_id`. The service stores nothing; each tool logs one JSON line with the `call_id`.

| Tool | Input | Output | Behaviour |
|---|---|---|---|
| conversation-init (n8n) | `caller_id, called_number, conversation_id` | `dynamic_variables` + `first_message` + `asr.keywords` | n8n looks up the "Cody leads" Phone field by E.164 and returns `caller_known`, `caller_name`, `caller_first_name`, `caller_company`, `caller_relationship`, `caller_phone`, the greeting and STT terms. Budget `INIT_LOOKUP_TIMEOUT_MS` (default 1500 ms); on timeout/error → unknown caller and the agent's own first message. Never calls Apollo. Apollo ids never reach the LLM. |
| `check_availability` | `conversation_id, from_iso, to_iso` | `{slots: [iso…]}` (max 6) | `POST /tools/check_availability` → Cal.com `GET /v2/slots` for event 7747197. |
| `book_meeting` | `conversation_id, slot_iso, name, email, organisation, phone?, caller_phone, notes?` | `{booking_id, start_iso, status}` | `POST /tools/book_meeting` → Cal.com `POST /v2/bookings` on event 7747197. Title: "Discovery call with Noel Sesto, Technical Director – <organisation>". `Company` is required; phone is `phone`, else `caller_phone` (the CLI, mapped from `system__caller_id`), because `attendeePhoneNumber` is required; `notes` is the optional "Enquiry details" question. |
| `take_message` | `conversation_id, category, summary, callback_number, urgency, site` | `{message_id}` | `POST /tools/take_message` returns a new `message_id` and stores nothing; n8n's post-call adds the message to the lead's Notion Summary. |
| `end_call` | — | — | ElevenLabs' built-in tool; the outcome is derived post-call. |

State-gated availability: `check_availability` and `book_meeting` are for a high-value `new_enquiry` only (prompt-enforced). `take_message` is always available.

## 8. Agent pipeline

- **Voice loop:** ElevenLabs Agents hosts VAD, turn-taking, STT, LLM and TTS.
- **Voice + model:** British-English voice `jRAAK67SEFE9m7ci5DhD`; the agent model chosen for the latency budget. Per-turn latency is in `conversation_turn_metrics` (post-call).
- **Config at call start (§13):** n8n's conversation-init webhook returns `dynamic_variables` (every variable defined on the agent — placeholders provisioned by `scripts/provision_elevenlabs.py`), `first_message` (the greeting) and `asr.keywords` (the STT terms). The agent must allow those overrides (provisioned).
- **Privacy / no recording:** `record_voice: false`, `retention_days: 30`; the post-call webhook's "Send audio data" is off, so only `post_call_transcription` reaches n8n (other event types are acknowledged and ignored).
- **CLI:** Telnyx delivers `+E.164`. The Notion Phone field holds `+44` E.164, so the lookup matches it directly; our service normalises any form to E.164 (`phonenumbers`) before passing it to Cal.com `attendeePhoneNumber`.
- **Session end:** ElevenLabs fires `post_call_transcription` (HMAC `ElevenLabs-Signature: t=…,v0=…`, **not** a bearer token) to n8n's post-call webhook. n8n must verify it on the raw body (30-minute timestamp tolerance), return 200 and then run §11. Idempotent on `data.conversation_id`.

## 9. Apollo (qualified callers only, post-call)

Run by n8n's post-call flow against the Apollo REST API (`https://api.apollo.io/api/v1`, header `x-api-key`, a **master** key because call records need one). Runs only when the call is qualified (§6). Never called during a call; **never adds anyone to a sequence**. (`agent/apollo/` is the earlier Python client for the same steps; no longer called.)

1. **Account** — exact-name match via `POST /accounts/search`, else `POST /accounts` (Apollo does not dedupe accounts on create, so search first).
2. **Contact** — match by email (`POST /contacts/search`) and update it (`PATCH /contacts/{id}`), else `POST /contacts` with `run_dedupe: true`; name, email, organisation, phone (mobile vs direct by number type) and `account_id` — this links contact to account.
3. **Call record** — `POST /phone_calls` with `call_identifier` = the ElevenLabs conversation id (Apollo upserts on it), from/to numbers, start/end/duration, `status=completed`, and a note carrying the outcome, score, summary, Notion link and conversation id; `user_id[]` = `APOLLO_USER_ID`.
4. **Deal** — **only if `APOLLO_CREATE_DEALS=true` (default `false`)**: `POST /opportunities` on the account (`owner_id` = `APOLLO_USER_ID`, optional `APOLLO_DEAL_STAGE_ID`). Off until Apollo's automatic HubSpot sync is switched off, otherwise Apollo pushes the deal into HubSpot.
5. **Follow-up task** — `POST /tasks` (`type=call`, `priority=high`, `status=scheduled`, due `APOLLO_TASK_DUE_HOURS` after the call) on the contact, owned by `APOLLO_USER_ID`.

With no store of ids, every step must search before it creates so a re-delivered webhook duplicates nothing (QUESTIONS: duplicate protection in n8n).

## 10. Data store

None of our own (Neon dropped 2026-11-03). Notion holds the call record and the caller directory (§11); Apollo holds the sales record for qualified callers (§9); ElevenLabs keeps transcripts for 30 days.

## 11. Post-call pipeline

Runs in **n8n** after it acknowledges ElevenLabs' post-call webhook:

1. `extract` + `score` — parse data collection (§6); score; `high_value` = qualified.
2. `outcome` — `discovery_booked` (a booking was made), `max_duration`, `qualified_not_booked`, `support_message` / `supplier_logged` / `message_taken` (a `take_message` call), `abandoned` (caller never spoke) or `no_action`.
3. `notion_transcript` — "Call transcripts" row: date, caller, company, outcome, summary; the full transcript in the page body.
4. `notion_lead` — "Cody leads" row (schema below), for every call; any message taken is added to its Summary. Its Phone field is what the next call's lookup finds.
5. `apollo` — §9, qualified only; then the lead row is updated with the Apollo links.
6. `slack` — qualified only, once: name, organisation, phone/email, score, outcome, summary, Notion and Apollo links.

Rows are found by Conversation ID before they are created, so a retried delivery updates rather than duplicates. Failed runs are retried from n8n's execution history.

**"Cody leads" Notion database** (`NOTION_LEADS_DB_ID`), one row per call:

| Property | Type | Source |
|---|---|---|
| Name | title | caller name, or "Unknown caller" |
| Conversation ID | text | ElevenLabs conversation id (idempotency key) |
| Call time | date | call start |
| Phone | phone | CLI (E.164) |
| Email | email | `contact_email` |
| Organisation | text | `organisation` |
| Role, Intent, Outcome, Estate unit, Connectivity, Driver, Timeline, Decision authority | select | §6 / §11 |
| Assets | multi-select | `asset_type` |
| Lead score, Estate size, Duration (s) | number | |
| Qualified, Known caller | checkbox | qualified; the number already had a "Cody leads" row before this call |
| Summary | text | ElevenLabs transcript summary |
| Review | select | `To review` on create (Noel sets `Reviewed` / `Not a lead`; never overwritten) |
| Apollo contact, Apollo account, Apollo deal | url | qualified callers |
| Transcript | url | the "Call transcripts" row |

**"Call transcripts" Notion database** (`NOTION_TRANSCRIPTS_DB_ID`): Name (title: date — caller), Conversation ID, Call time, Caller, Company, Outcome, Summary; transcript in the page body. Rows kept 12 months.

`scripts/provision_notion.py` adds any missing property to both databases.

Other async work in n8n: the existing **RingCentral missed-call alert**, and a nightly **retention** job that deletes Notion "Call transcripts" rows older than 12 months.

## 12. Infrastructure

- **Host:** a small UK VPS running Docker Compose (`infra/docker-compose.yml`): the `agent` webhook service and `caddy`, for as long as the Python service stays (QUESTIONS). n8n is not part of this compose stack.
- **Network:**
  - SIP terminates at ElevenLabs, not our host — no SIP/RTP ports. The only inbound surface is **HTTPS**.
  - Caddy terminates TLS for `WEBHOOK_DOMAIN`.
  - Lock the webhook service down: the `X-Cody-Secret` header on the tools, and optionally an allowlist of ElevenLabs' egress IPs (EU `35.204.38.71`, `34.147.113.54`; US `34.67.146.145`, `34.59.11.47`).
  - The Telnyx↔ElevenLabs trunk (FQDN connection to `sip.rtc.elevenlabs.io`, TCP/TLS, inbound `+E.164`, Allowed Source IPs `185.246.41.140`/`.141`) is configured by the provisioning scripts — see `infra/telnyx/` and `infra/elevenlabs/`.
- **Secrets:** `.env` on the host (mode 0600), never in the repo: `ELEVENLABS_*`, `CALCOM_API_KEY`, `APOLLO_API_KEY`, `NOTION_API_KEY`, `SLACK_WEBHOOK_URL`, `TELNYX_API_KEY` (provisioning only); n8n keeps its own credentials.
- **Backups:** no database of our own; Notion and Apollo hold the records. No audio recordings. The repo is the configuration.
- **Observability:** JSON logs to stdout from the tool service (`call_id` on every call line, with tool latency and errors); n8n execution history for conversation-init and post-call.

## 13. Config files

- `config/greeting.yaml` — `business_name`, `greeting` (fixed spoken text with AI disclosure and a call-logging notice: calls are transcribed, not recorded), `closing`, `silence_prompt`, `emergency_instruction` (closing and the emergency line are still for Noel to approve), `expert_name` (Noel Sesto), `expert_title` (our Technical Director), `business_hours`. Deflections that name the host use `{expert_name}` and `{expert_title}` so the name is written once.
- `config/prompt.md` — the system prompt template. `agent/prompt.py` fills `{{expert_name}}`, `{{expert_title}}` and `{{deflections.*}}` from the greeting file. Per-call variables stay for ElevenLabs.
- `config/scoring.yaml` — weights and threshold.
- `config/terms.yaml` — STT key terms with categories.

`provision_elevenlabs.py` sets the agent's base prompt and first message from these files. n8n's conversation-init returns the greeting and terms at call start and its post-call flow applies the scoring weights; how changes to `config/` reach n8n is open (QUESTIONS).

## 14. Build phases and definition of done

**Phase 0 — Scaffold and stack.** Repo layout, `uv` project, `docker compose up` brings up the webhook service and Caddy. Every image tag pinned and recorded. *Done when:* containers healthy and the webhook service reachable over TLS.

**Phase 1 — Cal.com.** `agent/calcom/` booking client (`get_availability`, `book_meeting`). *Done when:* a test script books a real Cal.com slot, it appears in Google Calendar, the confirmation email arrives, and unit tests pass. (Met 2026-10-05. The HubSpot half of Phase 1 was removed on 2026-11-02.)

**Phase 2 — Telephony.** The Telnyx London 020 DID (`+442045200783`) on an FQDN SIP connection to `sip.rtc.elevenlabs.io`; the number imported into ElevenLabs and bound to Cody; RingCentral's after-hours / no-answer divert to it. *Done when:* dialling the number (directly and via the divert) reaches the agent with the correct CLI, and n8n's post-call webhook creates the Notion rows.

**Phase 3 — Agent + webhook service.** Agent settings (§6 data collection, dynamic variables, overrides — `provision_elevenlabs.py`), n8n's conversation-init and post-call webhooks and the three tools (against `WEBHOOK_DOMAIN`) configured in ElevenLabs, and the webhook service (`agent/`) deployed. *Done when:* the ten core calls in `docs/TEST-CALLS.md` pass over a real call, the tools work mid-call, and n8n's post-call writes both Notion rows.

**Phase 4 — CRM + alerts.** Apollo for qualified callers (§9), Slack alert, both in n8n; Notion transcript retention scheduled in n8n. *Done when:* a qualified test call produces the Apollo contact (linked to its account), call record, follow-up task, Notion lead row and Slack alert within 60 s of hang-up, a re-delivered webhook changes nothing, and (once HubSpot sync is off and `APOLLO_CREATE_DEALS=true`) a deal on the account.

**Phase 5 — Go-live.** All twenty-one test calls pass; `config/greeting.yaml` wording approved by Noel; RingCentral after-hours rule and no-answer forwarding set to divert to the Telnyx number; go-live checklist in `docs/STATUS.md` signed off. Two weeks after-hours only with every transcript reviewed, then overflow.

## 15. After the MVP (not now)

1. Live warm transfer when Noel Sesto, Technical Director, is available: availability check, then a transfer via Telnyx/ElevenLabs (or a RingCentral route) to him, context pushed to Slack before pickup. Unlocks daytime traffic.
2. Self-learning knowledge base: unanswered questions → a review queue (Notion) → approval step → Slack approve/edit → approved entries → retrieval tool in the agent.
3. Inbox: Notion is the inbox (calls, transcript, review status, KB queue).
4. Outbound: form submission → callback within minutes; PSTN switch-off campaign to the existing base.
5. Own the model: a custom LLM behind ElevenLabs' custom-LLM setting, fine-tuned on reviewed transcripts.
6. Audio recording if ever needed (ElevenLabs `record_voice` or Telnyx recording) with retention.

## 16. Open questions

Tracked in `docs/QUESTIONS.md`. Nothing in this spec that touches a caller's ears or a credential is to be guessed.
