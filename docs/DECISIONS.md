# Decisions

Record every architecture decision and every pinned version here. One entry per decision, newest first.

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
  create, patch, associations); discovery-call booking on the **versioned** Meetings scheduler
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

- **Six components only:** RingCentral, FreeSWITCH (temporary), LiveKit, Neon, Windmill, HubSpot. "The best part is no part."
- **Removed from the process:** Apollo (prospecting only, synced to HubSpot), n8n (retired after Windmill takes the RC alert), a second carrier (Telnyx/Simwood), direct Google Calendar integration (via HubSpot Meetings), SMS (HubSpot booking email + invite instead).
- **Ingress:** FreeSWITCH registers to RingCentral as an existing-phone device because LiveKit SIP does not support REGISTER. Preserves CLI, keeps transfers internal later, exposes nothing publicly.
- **HubSpot is the system of record** for sales state; Neon holds the receptionist's own data; Windmill runs on a database in the same Neon project.
- **Synchronous in the agent, asynchronous in Windmill.** Only availability and booking block a call.
- **Hosted model providers in the MVP**, each behind an interface; LLM via an OpenAI-compatible endpoint. No GPU until the flow has earned it.
- **Recording on the FreeSWITCH leg**, not LiveKit egress, to avoid another service.
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
- **Phase 0 bring-up targets a subset.** `freeswitch` (Phase 2) and `agent` (Phase 2/3) have no
  Dockerfile yet, so they are not built or started in Phase 0; the command above names the five
  stack services only. Their base images are pinned when those Dockerfiles are written.
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
- `freeswitch` base image — Phase 2 (Dockerfile not yet written)
- `agent` base image — Phase 2/3 (Dockerfile not yet written)

### Python (`.python-version`, `pyproject.toml`, `uv.lock`)
- CPython 3.12 (resolved 3.12.13)
- Runtime: `asyncpg==0.31.0`, `pyyaml==6.0.3`, `python-dotenv==1.2.4`
- Dev: `ruff==0.16.10`, `pytest==9.1.1`, `pytest-asyncio==1.4.0`
