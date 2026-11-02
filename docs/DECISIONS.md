# Decisions

Record every architecture decision and every pinned version here. One entry per decision, newest first.

## 2026-10-09 — UK 0330 DID (not 020); Telnyx↔ElevenLabs provisioning scripts (Noel)

- **The provisioned Telnyx DID is `+443301900784`, a UK 0330 non-geographic number** — not the London
  020 geographic number assumed on 2026-10-07 (that decision is superseded). 0330 is charged at the
  standard national/geographic rate and is valid for inbound business use; the "London/geographic"
  framing is dropped across the docs.
- **Telnyx account is unblocked.** `TELNYX_API_KEY` + `TELNYX_DID` are now in Noel's `.env`, so Phase 2
  can be wired. The number is already in the Telnyx account; the scripts only connect and route it.
- **Two idempotent provisioning scripts** (default `--dry-run`, apply with `--apply`; never print keys):
  - `scripts/provision_telnyx.py` — ensures an FQDN SIP connection `elevenlabs-inbound` (inbound DNIS
    `+e164`, TCP) with FQDN `sip.rtc.elevenlabs.io:5060`, and assigns the DID to it. Inbound-only: no
    outbound voice profile, no SIP credentials.
  - `scripts/provision_elevenlabs.py` — creates the "Cody" agent (voice `jRAAK67SEFE9m7ci5DhD`,
    `record_voice: false`, `retention_days: 30`, `first_message` + base prompt from `config/`) and
    imports the DID as a `sip_trunk` number bound to the agent.
- **Trunk auth is IP allowlist alone.** ElevenLabs `inbound_trunk_config.allowed_addresses` = Telnyx EU
  signalling IPs `185.246.41.140/32`, `185.246.41.141/32` (verified against `sip.telnyx.com`).
  ElevenLabs does not require SIP credentials for a Telnyx inbound trunk (digest is outbound-only).

## 2026-10-07 — ElevenLabs Agents replaces LiveKit + the Python agent (Noel)

- **The voice loop moves to ElevenLabs Agents.** LiveKit (server + SIP + Redis) and the self-hosted
  Python LiveKit-Agents worker are dropped. Telnyx stays the carrier (UK 0330) and trunks straight to
  ElevenLabs over SIP; RingCentral still forwards after-hours / no-answer calls to the 0330 number.
- **Telnyx → ElevenLabs trunk:** Telnyx FQDN SIP connection to `sip.rtc.elevenlabs.io`, inbound
  `+E.164`, TCP (5060) or TLS (5061); no digest auth, so Allowed Source IPs EU `185.246.41.140`/`.141`
  (TCP/TLS only); Allowed Numbers empty; G.711/G.722. The 0330 number is imported into ElevenLabs.
- **Caller lookup + tools via webhooks.** No SIP or agent code on our host; one small HTTPS **webhook
  service** (replaces the `agent` container): a **conversation-init** webhook (pre-call: reads
  `system__caller_id`, does the HubSpot lookup, returns `dynamic_variables` + `first_message` greeting +
  `asr.keywords` from Neon config — how §13 "config at call start" survives) and **tool webhooks**
  (`check_availability`, `book_meeting`, `take_message`) authed by a secret header, allowlisting
  ElevenLabs egress IPs (EU `35.204.38.71`/`34.147.113.54`, US `34.67.146.145`/`34.59.11.47`). Changes
  §2.2 (tools are no longer Python functions in a worker) and §12 (Caddy also fronts this service).
- **Post-call** `post_call_transcription` webhook (HMAC `ElevenLabs-Signature`, **not** a bearer) → the
  webhook service verifies with the raw body, returns 200, triggers Windmill `post_call`. Idempotent on
  `conversation_id`; failed writes logged not dropped (ElevenLabs retries; refetchable 30 days;
  auto-disables after 10 consecutive failures).
- **No audio recording is not the ElevenLabs default:** set `platform_settings.privacy.record_voice:
  false` and leave the webhook "Send audio data" off; `retention_days: 30` (default is 2 years). Neon is
  the record; Notion rows kept 12 months. Both privacy fields live in the agent config JSON.
- **Dropped:** `redis`, `livekit`, `livekit-sip`, the LiveKit worker, `agent/providers/`,
  `infra/livekit/`, `provision_livekit`; `.env.example` loses `LIVEKIT_*` and the STT/LLM/TTS provider
  vars and gains `ELEVENLABS_API_KEY` / `ELEVENLABS_AGENT_ID` / `ELEVENLABS_WEBHOOK_SECRET` /
  `ELEVENLABS_TOOL_SECRET` + `WEBHOOK_DOMAIN`. `agent/hubspot/` + `agent/calcom/` are reused by the tool
  webhooks. `ELEVENLABS_API_KEY` is in Noel's `.env`, not the repo.
- **Settled on review (2026-10-09, Noel):**
  - **Agent name: Cody.** The ElevenLabs agent introduces itself as Cody in the greeting (the AI-assistant
    disclosure names it) — wording lives in `config/greeting.yaml` (§13), delivered as `first_message`.
  - **Voice: `jRAAK67SEFE9m7ci5DhD`** (British English) — pinned as the agent's `voice_id`, no longer open.
  - **Retention: 30 days, audio off — confirmed.** `retention_days: 30` and `record_voice: false` stand;
    ElevenLabs processing + storage of transcripts accepted (EU data residency is Enterprise-only).
  - **Discovery call: 15 minutes.** Matches the Cal.com event (7103844); the 30-minute wording in the
    prompt/spec is corrected to 15. See the discovery-call-duration question (now Answered).
- **Telnyx account now provisioned** (2026-10-09); wiring is handled by the provisioning scripts above.
- **For Noel (remaining action):** create the post-call HMAC secret + the tool-auth secret in `.env`.

## 2026-10-07 — Notion "Call transcripts" retention: 12 months (Noel)

- The Notion pitch-review "Call transcripts" rows are kept for **12 months**, then deleted automatically
  by the Windmill `retention` job (alongside the Neon transcript policy). Resolves the pitch-review-doc
  data-retention question; the Retention line no longer says "until Noel sets a policy" for Notion.

## 2026-10-07 — London 020 number; no audio recording; transcript pitch-review doc (Noel)

- **Telnyx DID is a London 020 local (geographic) number**, not an 03 non-geographic. Resolves the
  "UK number type" open question. *(Superseded 2026-10-09 — the number actually provisioned,
  `+443301900784`, is a UK 0330 non-geographic number; see the 2026-10-09 entry.)*
- **No audio recording in the MVP.** `record_session`, LiveKit egress and Telnyx call recording are all
  dropped. The **full two-sided, timestamped transcript** (roles agent/caller) persisted to Neon
  `transcripts` is the record of every call. `calls.recording_path` stays null and is the
  only recording placeholder; `RECORDINGS_DIR` / `RECORDING_RETENTION_DAYS` dropped from `.env.example`.
  Audio recording may return post-MVP (SPEC §15). The greeting disclosure should change from "recorded" to a call-logging
  notice — flagged for Noel (caller-facing wording).
- **Phase 4 `post_call` appends a pitch-review log.** A new `transcript_log` step appends each call's
  transcript + a short summary (caller, company, outcome, objections, questions we couldn't answer) to a
  running "Call transcripts" document, for reviewing how pitches land. Idempotent on `call_id`.
  **Destination: Notion** (decided 7 Oct) — a Notion database, one row per call (date, caller, company,
  outcome, summary; full transcript in the page body), not an ever-growing page, so it stays searchable.
  `NOTION_API_KEY` + `NOTION_TRANSCRIPTS_DB_ID` to come. This is the first transcript data to leave the
  host, so SPEC §2 principle 7 was updated to allow it; a retention rule for this personal data is open
  for Noel (QUESTIONS).

## 2026-10-05 — Drop FreeSWITCH + RingCentral SIP; Telnyx SIP trunk for ingress (Noel)

- **Telephony ingress is now Telnyx → LiveKit SIP.** FreeSWITCH and the RingCentral SIP-registration
  hack are dropped. RingCentral stays the office phone system; its after-hours and no-answer rules divert
  the main number externally to a Telnyx UK DID, which routes over a Telnyx SIP trunk to LiveKit SIP
  (IP-restricted to Telnyx). CLI is preserved end to end so the HubSpot lookup keeps working.
- **Why:** removes a whole component and the fragile "register FreeSWITCH as a RingCentral device"
  workaround (LiveKit can't REGISTER); a Telnyx SIP trunk is the direct, supported path. Still six
  components — Telnyx replaces FreeSWITCH. This **reverses** the "second carrier (Telnyx/Simwood) removed"
  note in the 2026-10-03 entry.
- **Consequences:** LiveKit SIP must now be publicly reachable from Telnyx (SIP port + RTP range,
  firewalled to Telnyx IPs), whereas before nothing LiveKit-related was exposed. Recording moves off the
  FreeSWITCH leg and is now **TBD** (LiveKit egress vs Telnyx recording — SPEC §8). `.env` drops
  `RC_SIP_*` / `FS_EXTERNAL_IP` and adds `TELNYX_*`; `infra/freeswitch/` removed; `freeswitch` service
  removed from compose.
- **No Telnyx credentials yet** — account upgrade is blocked on Telnyx support. Provisioning + the live
  Phase 2 test wait on the DID + SIP connection.
- **Open questions** flagged in `docs/QUESTIONS.md`: UK number type (geographic vs non-geographic),
  whether RingCentral preserves the original caller's CLI on an external divert, UK regulatory docs
  (Ofcom CLI rules, 999/112 handling, number registration), and the recording approach (since resolved 2026-10-07: no audio recording in the MVP).

## 2026-10-05 — Phase 1 closed: HubSpot provisioned + CRM verified (Claude)

- **Provisioning applied on `main`** with `HUBSPOT_PROVISION_KEY`: created the "ControlFreq AI
  Receptionist" group + all 12 `cf_` properties; idempotent re-run reports "exists" (no duplicates).
- **CRM live-tested** with `HUBSPOT_SERVICE_KEY` against a throwaway "Noel Test" record:
  `upsert_contact` (create + update-by-email), `upsert_company`, `create_deal` (Sales Pipeline
  `default`, stage 6139983093), `create_call` (associated) all succeeded; records deleted afterwards.
  The service key has CRM read + write + delete.
- **Phone-search (corrected after DevOps review, 2026-10-05):** HubSpot stores
  `hs_searchable_calculated_*_number` as the **national significant number** (country code stripped) for
  numbers it can parse — verified live: +44 7917 528642 → `7917528642`, +386 40 414 559 → `40414559`.
  Only unparseable numbers (e.g. Ofcom's 07700 900xxx drama range) fall back to raw E.164 digits — which
  is why an interim fix that matched the `447…` form looked right against the fiction test number but
  broke real contacts. `search_contact_by_phone` now matches **both** the national number and the
  E.164-without-plus form via one `IN` filter per property (2 groups), using the **`phonenumbers`** dep
  (libphonenumber, as HubSpot does) to derive the national number for any country. Re-verified live
  against a real-format UK mobile (`+447400123456` → stored `7400123456`, found). Supersedes the interim
  `_searchable_number` change from PR #3.

## 2026-10-05 — Discovery-call booking moves to Cal.com (Noel)

- **Booking is Cal.com, not HubSpot Meetings.** No HubSpot meeting link/slug is coming; the HubSpot
  scheduler scope is dropped. HubSpot stays the CRM system of record (contacts/companies/deals/calls);
  Cal.com owns scheduling. New provider `agent/calcom/` — recorded per working-rule #2 (a new component
  needs a reason + a yes; this is Noel's decision).
- **Removed** `get_availability` / `book_meeting` and all scheduler code from `agent/hubspot/`;
  `HUBSPOT_MEETING_LINK_SLUG` dropped from `.env.example`.
- **`agent/calcom/` (Cal.com API v2):** `GET /v2/slots` (cal-api-version **2024-09-04**) for
  availability; `POST /v2/bookings` (cal-api-version **2024-08-13**) to book. Versions are per-endpoint.
  A custom `User-Agent` is required — Cal.com's Cloudflare returns error 1010 to the default Python
  client signature (confirmed live).
- **Event type 7103844** ("LiftPulse Trial", 15-min, auto-confirmed). Booking-field slugs confirmed
  live via `GET /v2/event-types/7103844`: attendee name/email/phone are system fields (→ `attendee`
  object); custom `bookingFieldsResponses` keys are `Company` (required), `title` (required, hidden;
  defaults to "Intro call – <organisation>"), `notes` (optional; qualification summary).
- **Config:** `CALCOM_API_KEY` (account noelsesto) + `CALCOM_EVENT_TYPE_ID=7103844` in `.env`. HubSpot
  Service Keys still to come from Noel.
- **Slots response shape:** `{"data": {"YYYY-MM-DD": [{"start": ISO+offset}, …]}}`; the client filters
  to [from, to] and normalises starts to UTC "…Z".
- **Phase 1 DoD now:** a test script books a real Cal.com slot → it appears in Google Calendar →
  confirmation email arrives (plus the unit tests).
- **Live booking verified 2026-10-05:** booked + cancelled a real slot via the API; event appeared on
  Noel's Google Calendar with Company/phone/notes populated. **`BOOKINGS_VERSION` 2024-08-13 confirmed**
  for both create and cancel (`POST /v2/bookings/{uid}/cancel`). **`attendeePhoneNumber` is REQUIRED**
  on event 7103844 and is validated (libphonenumber) — the agent must pass the caller's CLI as the
  attendee phone; `book_meeting` sends it as `attendee.phoneNumber`.

## 2026-10-04 — HubSpot provisioning & auth decisions (Noel)

- **Auth is HubSpot Service Keys, not a legacy private app:** `HUBSPOT_SERVICE_KEY` for the agent
  runtime, `HUBSPOT_PROVISION_KEY` for `scripts/provision_hubspot.py`. `.env.example` updated; the
  client's `from_env` reads `HUBSPOT_SERVICE_KEY`.
- **No new pipeline** (Starter plan allows two). Use the existing **"Sales Pipeline"**
  (`HUBSPOT_DEAL_PIPELINE_ID=default`) and map the receptionist's outcomes onto existing stages:
  **Qualified – not booked → "Lead Identified" (6139983093)**, **Discovery booked → "Initial
  Contact" (6139983094)**. Stage IDs live in `.env`.
- **Expert:** Noel Sesto, owner id **99735767** (`HUBSPOT_EXPERT_OWNER_ID`). Meeting-link slug and
  the Service Keys to follow from Noel.
- **`scripts/provision_hubspot.py`:** idempotent, create-only (never renames/deletes). Checks the
  property group first via the dated properties API `GET /crm/properties/2026-09/contacts/groups`,
  then creates the group + the 12 `cf_` properties per SPEC §9 if missing. `--dry-run` prints the plan
  with no API calls or key. Pipeline/stages are not created — only echoed for confirmation.
- **Phone lookup** now also tries the spaced **"+44 XXXX XXXXXX"** form (existing contacts are stored
  spaced), alongside compact E.164 and UK national.

## 2026-10-04 — Phase 1 HubSpot client scaffold (Claude)

- **Thin async `httpx` client**, not the `hubspot-api-client` SDK ("the best part is no part"). The
  agent's tools are async with tight timeouts; one small wrapper (`agent/hubspot/client.py`) over the
  REST API is leaner and fully mockable. Added `httpx>=0.27` (locked 0.28.1).
- **Endpoints:** CRM objects on stable `/crm/v3/objects/...` (contacts/companies/deals/calls search,
  create, patch, associations). **(Scheduling below superseded 2026-10-05 → Cal.com.)** Discovery-call booking was on the **versioned** Meetings scheduler
  `/scheduler/2026-03/meetings/meeting-links/book/...` (availability via `GET book/{slug}`, booking via
  `POST book`). HubSpot sends the confirmation email + calendar invite.
- **Association type IDs** (category `HUBSPOT_DEFINED`): deal→contact 3, deal→company 5,
  call→contact 194, call→company 182, call→deal 206.
- **Client raises `HubSpotError`; the tool layer decides fail-soft vs blocking** (SPEC §5.1/§7).
  `upsert_contact` matches by email then phone; phone lookups try E.164 + UK national (SPEC §9/§11).
- **Tests** use `httpx.MockTransport` (no new test dependency) and assert the exact request payloads;
  `pytest` gets `pythonpath = ["."]` so `agent` imports without packaging. 11 tests pass; ruff clean.
- **To validate in the live phase** (blocked on the expert's meeting-link slug + Service Keys):
  the scheduler availability JSON shape (`linkAvailability.linkAvailabilityByDuration[*].availabilities[*]`,
  parsed defensively) and the booking `formFields` names, which depend on the link's form config.

## 2026-10-03 — Initial architecture (Noel, with Claude)

- **Six components only:** RingCentral, FreeSWITCH (temporary), LiveKit, Neon, Windmill, HubSpot. "The best part is no part." *(Superseded 2026-10-05: FreeSWITCH → Telnyx.)*
- **Removed from the process:** Apollo (prospecting only, synced to HubSpot), n8n (retired after Windmill takes the RC alert), a second carrier (Telnyx/Simwood), direct Google Calendar integration (via HubSpot Meetings), SMS (HubSpot booking email + invite instead).
- **Ingress:** FreeSWITCH registers to RingCentral as an existing-phone device because LiveKit SIP does not support REGISTER. Preserves CLI, keeps transfers internal later, exposes nothing publicly. *(Superseded 2026-10-05: ingress is now a Telnyx SIP trunk into LiveKit SIP; RingCentral diverts to a Telnyx DID.)*
- **HubSpot is the system of record** for sales state; Neon holds the receptionist's own data; Windmill runs on a database in the same Neon project.
- **Synchronous in the agent, asynchronous in Windmill.** Only availability and booking block a call.
- **Hosted model providers in the MVP**, each behind an interface; LLM via an OpenAI-compatible endpoint. No GPU until the flow has earned it.
- **Recording on the FreeSWITCH leg**, not LiveKit egress, to avoid another service. *(Superseded 2026-10-05: FreeSWITCH removed. Further 2026-10-07: no audio recording in the MVP — SPEC §8.)*
- **MVP scope:** after-hours and unanswered calls only; no live transfer until daytime traffic.

## 2026-10-03 — Phase 0 scaffold decisions (Claude)

- **Single `uv` project at the repo root**, not one per component. "The best part is no part":
  one `pyproject.toml`, one `uv.lock`. The agent runtime deps (`livekit-agents` + provider SDKs)
  are deferred to Phase 3, when the provider choices in `docs/QUESTIONS.md` are settled.
- **One Postgres driver — `asyncpg`** — across the agent (`store/`), `db/migrate.py` and
  `scripts/seed_config.py`. No second driver.
- **LiveKit secrets via env, never in YAML.** `livekit.yaml`/`sip.yaml` carry no keys; the key/secret
  are injected as `LIVEKIT_KEYS` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` from `../.env`. Because
  compose interpolates `${...}` at parse time, the stack must be brought up with the env file:
  `cd infra && docker compose --env-file ../.env up -d redis livekit livekit-sip windmill-server windmill-worker caddy`.
- **Phase 0 bring-up targets a subset.** `agent` (Phase 2/3) has no Dockerfile yet, so it is not
  built or started in Phase 0; the command above names the five stack services only. Its base image
  is pinned when that Dockerfile is written. (FreeSWITCH was later dropped entirely — 2026-10-05.)
- **`seed_config.py` skips `TODO` placeholders** so nothing unapproved reaches the agent or STT, and
  warns when seeded config still contains them (expected until Noel approves wording).
- **Redis healthcheck** added to compose; other services judged via `docker compose ps` for now.

## 2026-10-03 — Neon preview branches in CI (Noel provided the template)

- **Adopted** `.github/workflows/neon-branch.yml` from Neon's create/delete-branch template Noel
  supplied, adapted to our stack: per PR it creates an ephemeral Neon branch of "Inbound Calls",
  sets up `uv`, runs `db/migrate.py` + `scripts/seed_config.py` against the branch's `receptionist`
  database, and posts a schema diff; the branch is deleted on PR close. This is how schema changes
  get validated per PR without touching the main `receptionist` database.
- **Corrected from the pasted template:** create-branch-action v6 outputs are `db_url` /
  `db_url_pooled` (the template's `db_url_with_pooler` and `create_neon_branch_encode` step id are
  from an older version). Migrations use the **unpooled** `db_url` — DDL over asyncpg misbehaves
  through the PgBouncer pooler. Added `database: receptionist` so both actions target our database,
  not the default `neondb`, and `permissions: pull-requests: write` for the diff comment.
- **Requires in GitHub repo settings:** secret `NEON_API_KEY` (write-capable Neon key) and variable
  `NEON_PROJECT_ID = wandering-union-75946614`. Noel to add these.
- GitHub Actions pins: `tj-actions/branch-names@v8`, `neondatabase/create-branch-action@v6`,
  `neondatabase/delete-branch-action@v3`, `neondatabase/schema-diff-action@v1`,
  `actions/checkout@v4`, `astral-sh/setup-uv@v10.2.0` (pinned to the exact release — setup-uv
  publishes only full-semver tags, no bare `vN` major ref, so `@v10` fails to resolve in CI).

## Version pins

Recorded 2026-10-03. Image tags verified against the registries on this date.

### Container images (`infra/docker-compose.yml`)
- `redis:7.4-alpine`
- `livekit/livekit-server:v1.13.7`
- `livekit/sip:v1.17.0`
- `ghcr.io/windmill-labs/windmill:v1.822.0` (server and worker, same tag)
- `caddy:2.8-alpine`
- `agent` base image — Phase 2/3 (Dockerfile not yet written)
- (FreeSWITCH removed 2026-10-05; Telnyx is an external SIP trunk, no image to pin)

### Python (`.python-version`, `pyproject.toml`, `uv.lock`)
- CPython 3.12 (resolved 3.12.13)
- Runtime: `asyncpg==0.31.0`, `pyyaml==6.0.3`, `python-dotenv==1.2.4`
- Dev: `ruff==0.16.10`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`
