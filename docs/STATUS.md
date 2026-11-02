# Status

**Current phase:** 1 complete ✅ (HubSpot + Cal.com) · **architecture pivot 2026-10-08: ElevenLabs Agents replaces LiveKit + the Python agent** (docs PR) · Phase 0 host bring-up + Phase 2 telephony blocked on Telnyx
**Last updated:** 2026-10-07

## Done
- Spec, config templates, schema and test suite written.
- **Phase 0 scaffold (code/config complete):**
  - Target repo layout created (`agent/`, `windmill/`, `infra/{livekit,telnyx,caddy}/`, `scripts/`, `tests/`).
  - Single `uv` project at root: `pyproject.toml`, `uv.lock`, `.python-version` (3.12); ruff + pytest configured; `ruff check`/`format` clean.
  - Every Phase-0 image tag pinned in `infra/docker-compose.yml` and recorded in `docs/DECISIONS.md`; LiveKit/SIP/Caddy env wired; secrets kept to `../.env`.
  - `infra/livekit/livekit.yaml`, `infra/livekit/sip.yaml`, `infra/caddy/Caddyfile` written.
  - `db/migrate.py` (idempotent schema apply) and `scripts/seed_config.py` (config + terms, skips TODO) written; both compile.

- **Neon project** (created by Noel): "Inbound Calls" `wandering-union-75946614`, London (aws-eu-west-2), PG 18.6, default branch `production` `br-steep-breeze-za0ra5h9`, databases `receptionist` + `windmill` + default `neondb`.
- **PR #1 merged** (squash `0ed4edf`) → `main`; remote + local branch deleted, main pulled locally. https://github.com/noel-testo/inbound-calls/pull/1
- **CI green** — `Neon Preview Branch` run succeeded (https://github.com/noel-testo/inbound-calls/actions/runs/37158589767). On a fresh preview branch it applied `db/schema.sql` and ran `seed_config.py`. Verified on that branch: `config`=3 keys (greeting, prompt, scoring), `terms`=26, 6 tables, 3 enums. **migrate + seed proven end-to-end.**
- **Phase 0 code is done and on `main`.**
- **Production `receptionist` seeded** (2026-10-04): ran `db/migrate.py` + `scripts/seed_config.py` against the persistent `production` branch (unpooled connection). Verified `select count(*) from config` = **3** (greeting, scoring, prompt); 26 terms, 5 TODO placeholders skipped. The database half of the DoD is met on the persistent store. Only the host bring-up below remains.
- **Phase 1 merged to `main`** (squash `06e4924`, PR #2): `agent/hubspot/` CRM client (`search_contact_by_phone` via `hs_searchable_calculated_*` on the national number, `upsert_contact`, `upsert_company`, `create_deal`, `create_call`), `agent/calcom/` booking client (`get_availability`, `book_meeting` — Cal.com API v2, event 7103844; **live booking verified + cancelled 2026-10-05**), and `scripts/provision_hubspot.py` (idempotent: group pre-check + 12 `cf_` properties per §9; `--dry-run` verified). Service-Key auth; pipeline/stages/owner + Cal.com key in `.env.example`. 17 unit tests; ruff + format clean.

## Next — one host item to close Phase 0 DoD
- **Bring up the stack on the host:** with `.env` present, `cd infra && docker compose --env-file ../.env up -d agent windmill-server windmill-worker caddy`. DoD: containers healthy and the Windmill UI reachable over HTTPS. (No redis/livekit — the voice loop is ElevenLabs.)

## Phase 1 — HubSpot CRM + Cal.com booking — ✅ COMPLETE (2026-10-05)
- **Done:** `agent/hubspot/` CRM client, `agent/calcom/` booking client, and `scripts/provision_hubspot.py` scaffolded + unit-tested (17 tests). Booking = Cal.com event 7103844 ("LiftPulse Trial", 15-min, auto-confirmed). HubSpot pipeline = existing "Sales Pipeline" (`default`); stages Lead Identified (6139983093) / Initial Contact (6139983094); expert Noel Sesto (owner 99735767).
- **Live Cal.com booking verified (2026-10-05):** booked the 2026-10-06 09:00Z slot as "Noel Test" / noel@controlfreq.co.uk / Company "ControlFreq Test" (uid `mL3SW3Q5mM1s5ghMEseT85`, status accepted) → it appeared on Noel's Google Calendar with Company/phone/notes populated → cancelled via `POST /v2/bookings/{uid}/cancel`. **`BOOKINGS_VERSION` 2024-08-13 confirmed** (create + cancel). **`attendeePhoneNumber` is a required, validated field** on this event — the agent must pass the caller's CLI as the attendee phone. Confirmation + cancellation emails confirmed in Noel's inbox (DevOps, 2026-10-05).
- **HubSpot provisioned on `main` (2026-10-05):** `provision_hubspot.py` created the property group + 12 `cf_` properties; idempotent re-run = all "exists". CRM clients live-tested against a throwaway "Noel Test": upsert contact (create + update-by-email), company, deal (pipeline `default`, stage 6139983093), call — all OK; records deleted. Phone lookup matches HubSpot's calculated searchable properties on both the national number and the E.164-without-plus form (one `IN` filter per property, via `phonenumbers`), re-verified live against a real-format UK mobile — see the 2026-10-05 correction in DECISIONS.
- **DoD met.** Deferred to Phase 3: wiring both clients into the agent tools.

## Phase 2 — Telephony (Telnyx → ElevenLabs Agents) — scope (revised 2026-10-08)
- **Ingress:** RingCentral diverts after-hours / no-answer calls to a **UK 0330** Telnyx DID (`+443301900784`); Telnyx trunks over SIP to **ElevenLabs Agents** (`sip.rtc.elevenlabs.io`), which runs the whole voice loop. CLI preserved for the HubSpot lookup. **LiveKit, the Python agent, FreeSWITCH and RingCentral SIP registration are all dropped.**
- **No audio recording:** ElevenLabs `record_voice: false`, post-call audio off; full two-sided, timestamped transcripts in Neon are the record of each call (SPEC §8).
- **To build:** the Telnyx FQDN trunk + number import into ElevenLabs; the ElevenLabs agent (prompt, voice, privacy, tools, conversation-init); the HTTPS webhook service (`agent/`); the RingCentral divert configured.
- **DoD:** dialling the number (directly and via the RingCentral divert) reaches the ElevenLabs agent with the correct CLI, and a Neon `calls` row is created from the post-call webhook.
- **Phase 4 (note):** `post_call` will also append each call to the **Notion** "Call transcripts" database (one row per call; full transcript in the page body) for pitch review — destination decided 2026-10-07.
- **Blocked:** no Telnyx credentials yet (account upgrade pending Telnyx support); open questions in QUESTIONS (CLI-on-divert, UK regulatory).

## Blocked
- **Phase 0 host bring-up:** blocked until a host exists and `WINDMILL_DOMAIN` has DNS pointing at it (Caddy needs the hostname for a TLS cert).
- **Phase 1:** ✅ resolved — HubSpot provisioned + CRM verified on `main` (2026-10-05); Cal.com booking verified earlier. Nothing outstanding.
- **Phase 2 telephony:** Telnyx account upgrade (blocked on Telnyx support) for the UK DID + SIP connection; RingCentral admin to set the after-hours / no-answer divert to that Telnyx number. No Telnyx credentials yet.

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
- [ ] RingCentral after-hours rule → Telnyx number
- [ ] RingCentral no-answer forwarding → Telnyx number
- [ ] Two-week after-hours review period scheduled
