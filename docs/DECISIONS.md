# Decisions

Record every architecture decision and every pinned version here. One entry per decision, newest first.

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
