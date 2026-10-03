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
- **Neon project created** (by Noel): "Inbound Calls" `wandering-union-75946614`, region London (aws-eu-west-2), PG 18.6, branch `production` `br-steep-breeze-za0ra5h9`, databases `receptionist` + `windmill` + default `neondb`. ADMIN access.
- **Schema + seed still to apply** — the connected Neon MCP is **read-only** (reads work; every write returns "read-only transaction"; no migration/write tool exposed). Unblock by any one of:
  - Re-authorise the Neon MCP with write access → Claude applies `db/schema.sql`, seeds config + terms, verifies.
  - Set `DATABASE_URL`/`WINDMILL_DATABASE_URL` in `.env` (strings from the Neon console) and run `uv run python db/migrate.py` then `uv run python scripts/seed_config.py`; Claude verifies `select count(*) from config` via the MCP read.
- **Then host bring-up:** `cd infra && docker compose --env-file ../.env up -d redis livekit livekit-sip windmill-server windmill-worker caddy`.
- **DoD to confirm:** five containers healthy, Windmill UI reachable over TLS, `select count(*) from config` returns the seeded keys.
- Then Phase 1 (HubSpot).

## Blocked
- **Neon writes:** the connected Neon MCP is read-only — needs a writable reconnect, or Noel runs migrate/seed with the `.env` connection strings. (It also cannot create projects; Noel created "Inbound Calls" in the console.)
- **Host bring-up:** host access for `docker compose up`, plus the Windmill public hostname/DNS for Caddy TLS (`WINDMILL_DOMAIN`).
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
