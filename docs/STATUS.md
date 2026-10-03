# Status

**Current phase:** 0 — Scaffold and stack
**Last updated:** 2026-10-03

## Done
- Spec, config templates, schema and test suite written.
- **Phase 0 scaffold (code/config complete):**
  - Target repo layout created (`agent/`, `windmill/`, `infra/{livekit,freeswitch,caddy}/`, `scripts/`, `tests/`).
  - Single `uv` project at root: `pyproject.toml`, `uv.lock`, `.python-version` (3.12); ruff + pytest configured; `ruff check`/`format` clean.
  - Every Phase-0 image tag pinned in `infra/docker-compose.yml` and recorded in `docs/DECISIONS.md`; LiveKit/SIP/Caddy env wired; secrets kept to `../.env`.
  - `infra/livekit/livekit.yaml`, `infra/livekit/sip.yaml`, `infra/caddy/Caddyfile` written.
  - `db/migrate.py` (idempotent schema apply) and `scripts/seed_config.py` (config + terms, skips TODO) written; both compile.

## Next
- **Phase 0 bring-up (needs host + Neon — not yet done):**
  1. Provision the Neon project with `receptionist` and `windmill` databases; set `DATABASE_URL` / `WINDMILL_DATABASE_URL` in `.env` on the host.
  2. `uv run python db/migrate.py` then `uv run python scripts/seed_config.py`.
  3. `cd infra && docker compose --env-file ../.env up -d redis livekit livekit-sip windmill-server windmill-worker caddy`.
  4. Confirm DoD: all five containers healthy, Windmill UI reachable over TLS, `select count(*) from config` returns the seeded keys.
- Then Phase 1 (HubSpot).

## Blocked
- Phase 0 bring-up: host access and a Neon project (DATABASE_URL, WINDMILL_DATABASE_URL), plus the Windmill public hostname for Caddy TLS.
- Expert identity and HubSpot meeting link (Phase 1).
- RingCentral admin access and the receptionist extension (Phase 2).

## Test-call log
| Date | # | call_id | Pass/Fail | Notes |
|---|---|---|---|---|

## Go-live checklist (Phase 5)
- [ ] All 20 test calls pass and are logged above
- [ ] `config/greeting.yaml` approved by Noel (no TODO remains)
- [ ] `config/terms.yaml` populated
- [ ] HubSpot workflow (task + Slack) verified on a test deal
- [ ] Retention schedule running
- [ ] n8n RC alert disabled; Windmill port verified
- [ ] RingCentral after-hours rule → receptionist extension
- [ ] RingCentral no-answer forwarding → receptionist extension
- [ ] Two-week after-hours review period scheduled
