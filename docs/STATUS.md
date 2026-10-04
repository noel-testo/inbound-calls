# Status

**Current phase:** 0 — Scaffold and stack — *code complete & merged, production seeded; host bring-up outstanding*
**Last updated:** 2026-10-04

## Done
- Spec, config templates, schema and test suite written.
- **Phase 0 scaffold (code/config complete):**
  - Target repo layout created (`agent/`, `windmill/`, `infra/{livekit,freeswitch,caddy}/`, `scripts/`, `tests/`).
  - Single `uv` project at root: `pyproject.toml`, `uv.lock`, `.python-version` (3.12); ruff + pytest configured; `ruff check`/`format` clean.
  - Every Phase-0 image tag pinned in `infra/docker-compose.yml` and recorded in `docs/DECISIONS.md`; LiveKit/SIP/Caddy env wired; secrets kept to `../.env`.
  - `infra/livekit/livekit.yaml`, `infra/livekit/sip.yaml`, `infra/caddy/Caddyfile` written.
  - `db/migrate.py` (idempotent schema apply) and `scripts/seed_config.py` (config + terms, skips TODO) written; both compile.

- **Neon project** (created by Noel): "Inbound Calls" `wandering-union-75946614`, London (aws-eu-west-2), PG 18.6, default branch `production` `br-steep-breeze-za0ra5h9`, databases `receptionist` + `windmill` + default `neondb`.
- **PR #1 merged** (squash `0ed4edf`) → `main`; remote + local branch deleted, main pulled locally. https://github.com/noel-testo/inbound-calls/pull/1
- **CI green** — `Neon Preview Branch` run succeeded (https://github.com/noel-testo/inbound-calls/actions/runs/37158589767). On a fresh preview branch it applied `db/schema.sql` and ran `seed_config.py`. Verified on that branch: `config`=3 keys (greeting, prompt, scoring), `terms`=26, 6 tables, 3 enums. **migrate + seed proven end-to-end.**
- **Phase 0 code is done and on `main`.**
- **Production `receptionist` seeded** (2026-10-04): ran `db/migrate.py` + `scripts/seed_config.py` against the persistent `production` branch (unpooled connection). Verified `select count(*) from config` = **3** (greeting, scoring, prompt); 26 terms, 5 TODO placeholders skipped. The database half of the DoD is met on the persistent store. Only the host bring-up below remains.

## Next — one host item to close Phase 0 DoD
- **Bring up the stack on the host:** on the server, with `.env` present, run `cd infra && docker compose --env-file ../.env up -d redis livekit livekit-sip windmill-server windmill-worker caddy`. DoD: all five containers healthy and the Windmill UI reachable over HTTPS.

Then → Phase 1 (HubSpot).

## Blocked
- **Host bring-up:** blocked until a host exists and `WINDMILL_DOMAIN` has DNS pointing at it (Caddy needs the hostname to obtain a TLS cert). Nothing else outstanding for Phase 0.
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
