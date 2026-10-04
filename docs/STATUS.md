# Status

**Current phase:** 1 — HubSpot (client scaffolded) · Phase 0 host bring-up still outstanding
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
- **Phase 1 HubSpot client scaffolded** (branch `phase-1-hubspot-client`): `agent/hubspot/` thin async client — `search_contact_by_phone`, `upsert_contact`, `upsert_company`, `create_deal`, `create_call`, `get_availability`, `book_meeting`. 11 unit tests via `httpx.MockTransport`; ruff clean. `httpx` added to deps.

## Next — one host item to close Phase 0 DoD
- **Bring up the stack on the host:** on the server, with `.env` present, run `cd infra && docker compose --env-file ../.env up -d redis livekit livekit-sip windmill-server windmill-worker caddy`. DoD: all five containers healthy and the Windmill UI reachable over HTTPS.

## Phase 1 — HubSpot (in progress)
- **Done:** `agent/hubspot/` client scaffolded + unit-tested (see Done above).
- **Next:** `scripts/provision_hubspot.py` to create the `cf_` contact properties + `Inbound` pipeline/stages (idempotent, create-only); later wire the client into the agent tools (Phase 3).
- **DoD (blocked):** a test script books a real meeting on the expert's link → appears in Google Calendar → confirmation email arrives, and unit tests pass against fixtures. Unit tests done; the live booking needs the blocking answers below.

## Blocked
- **Phase 0 host bring-up:** blocked until a host exists and `WINDMILL_DOMAIN` has DNS pointing at it (Caddy needs the hostname for a TLS cert).
- **Phase 1 live DoD:** blocked on the expert's identity, the HubSpot meeting-link slug, and the private-app token — plus confirm whether to use an existing deal pipeline or create `Inbound` (QUESTIONS default: create `Inbound`). Client code + tests are done; provisioning and a real booking need these.
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
