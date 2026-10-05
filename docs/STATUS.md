# Status

**Current phase:** 1 — HubSpot CRM + Cal.com booking (scaffolded) · Phase 0 host bring-up still outstanding
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
- **Phase 1 scaffolded** (branch `phase-1-hubspot-client`): `agent/hubspot/` CRM client (`search_contact_by_phone` incl. spaced `+44` form, `upsert_contact`, `upsert_company`, `create_deal`, `create_call`), `agent/calcom/` booking client (`get_availability`, `book_meeting` — Cal.com API v2, event 7103844), and `scripts/provision_hubspot.py` (idempotent: group pre-check + 12 `cf_` properties per §9; `--dry-run` verified). Service-Key auth; pipeline/stages/owner + Cal.com key wired in `.env.example`. 18 unit tests via `httpx.MockTransport`; ruff + format clean.

## Next — one host item to close Phase 0 DoD
- **Bring up the stack on the host:** on the server, with `.env` present, run `cd infra && docker compose --env-file ../.env up -d redis livekit livekit-sip windmill-server windmill-worker caddy`. DoD: all five containers healthy and the Windmill UI reachable over HTTPS.

## Phase 1 — HubSpot CRM + Cal.com booking (in progress)
- **Done:** `agent/hubspot/` CRM client, `agent/calcom/` booking client, and `scripts/provision_hubspot.py` scaffolded + unit-tested (17 tests). Booking = Cal.com event 7103844 ("LiftPulse Trial", 15-min, auto-confirmed). HubSpot pipeline = existing "Sales Pipeline" (`default`); stages Lead Identified (6139983093) / Initial Contact (6139983094); expert Noel Sesto (owner 99735767).
- **Live Cal.com booking verified (2026-10-05):** booked the 2026-10-06 09:00Z slot as "Noel Test" / noel@controlfreq.co.uk / Company "ControlFreq Test" (uid `mL3SW3Q5mM1s5ghMEseT85`, status accepted) → it appeared on Noel's Google Calendar with Company/phone/notes populated → cancelled via `POST /v2/bookings/{uid}/cancel`. **`BOOKINGS_VERSION` 2024-08-13 confirmed** (create + cancel). **`attendeePhoneNumber` is a required, validated field** on this event — the agent must pass the caller's CLI as the attendee phone. Confirmation email not checked here (Gmail MCP token expired); the calendar invite implies it was sent — verify the inbox.
- **Next:** run `scripts/provision_hubspot.py` once `HUBSPOT_PROVISION_KEY` is issued; wire both clients into the agent tools (Phase 3).
- **DoD:** ✅ real Cal.com booking appears in Google Calendar (email send implied — confirm inbox). Unit tests pass. HubSpot CRM provisioning + upserts still pending the Service Keys.

## Blocked
- **Phase 0 host bring-up:** blocked until a host exists and `WINDMILL_DOMAIN` has DNS pointing at it (Caddy needs the hostname for a TLS cert).
- **Phase 1 HubSpot steps:** running `provision_hubspot.py` and the CRM upserts are blocked on the HubSpot Service Keys (`HUBSPOT_SERVICE_KEY`, `HUBSPOT_PROVISION_KEY`), still to come from Noel. The Cal.com booking is NOT blocked (key present) — the live booking test can run.
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
