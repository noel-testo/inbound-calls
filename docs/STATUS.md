# Status

**Current phase:** 3 code complete (webhook service + CRM plan), not yet deployed · Phase 2 live test pending on the new 020 DID · Phase 0 host bring-up pending a host
**Last updated:** 2026-11-02

## Done
- **Phase 0 scaffold** — repo layout, `uv` project, pinned images, Neon project "Inbound Calls" (`wandering-union-75946614`, London, `production` branch), `receptionist` migrated and seeded (2026-10-04), Neon preview branch per PR in CI.
- **Phase 1 — Cal.com** — `agent/calcom/` (availability + booking on event 7103844), live booking verified 2026-10-05. The HubSpot half of Phase 1 was removed on 2026-11-02.
- **Phase 2 wiring (PR #9, open)** — `provision_telnyx.py` + `provision_elevenlabs.py`. Applied live for the old 0330 number: Telnyx connection 3067081943628646021; ElevenLabs agent `agent_6901m4gzr6bdfjwsmte3fxepq946` (voice, greeting, `record_voice: false`, `retention_days: 30`) with `+443301900784` imported and bound to it.
- **CRM plan + Phase 3 webhook service (2026-11-02, this branch)** — see DECISIONS 2026-11-02:
  - HubSpot removed (code, env vars, Neon columns, docs, tests).
  - `agent/app.py`: conversation-init (Neon caller lookup by E.164 within `INIT_LOOKUP_TIMEOUT_MS`), the three webhook tools, and the HMAC-verified post-call receiver.
  - Post-call pipeline: Neon ingest + scoring; Notion "Call transcripts" + "Cody leads" rows for every call; for qualified callers Apollo account/contact/call record/follow-up task (deal behind `APOLLO_CREATE_DEALS`, default off) and a Slack alert. Idempotent; `scripts/replay_post_call.py` finishes failed runs.
  - Neon migrations as files (`db/migrations/0001`, `0002`); `provision_notion.py`; `provision_elevenlabs.py` patches the agent's data collection, dynamic variables and overrides; DID default `+442045200783`.
  - 49 tests (Apollo/Notion/Slack mocked at the HTTP layer; real-SQL integration test against a throwaway local Postgres). Nothing was run against production Neon or any live API.

## Live state found on 2026-11-02 (read-only checks)
- ElevenLabs agent: no tools, no dynamic variables, no data collection, conversation-init overrides disabled. Only the 0330 number is imported; `+442045200783` is not.
- Neon `production`: the Phase 0 baseline only (no `callers`, no `schema_migrations`); compute suspends when idle.

## Next
1. Noel: supply the env vars below and answer the batch in QUESTIONS (Apollo HubSpot sync, Notion databases, host, Windmill).
2. Host: bring up a UK VPS (recommendation below), DNS for `WEBHOOK_DOMAIN`, `docker compose --env-file ../.env up -d agent caddy`.
3. Merge PR #9 and this PR; CI applies the migrations on a Neon preview branch; then run `db/migrate.py` against `production` (unpooled URL) and `seed_config.py`.
4. Provisioning (Noel's go-ahead): `provision_telnyx.py --apply`, `provision_elevenlabs.py --apply`, `provision_notion.py --apply`; in the ElevenLabs dashboard set the conversation-init URL, the post-call webhook and the three tools (infra/elevenlabs/README.md).
5. RingCentral divert → `+442045200783`; Phase 2 live test; the ten core test calls (Phase 3 DoD); remove the 0330 number from ElevenLabs.

## Env vars Noel must supply (`.env` on the host)
`ELEVENLABS_API_KEY`, `ELEVENLABS_WEBHOOK_SECRET` (the post-call webhook's HMAC secret), `ELEVENLABS_TOOL_SECRET` (any long random string; also stored in ElevenLabs), `ELEVENLABS_PHONE_NUMBER_ID` (printed by provisioning), `DATABASE_URL`, `CALCOM_API_KEY`, `TELNYX_API_KEY` (provisioning), `TELNYX_DID=+442045200783`, `WEBHOOK_DOMAIN`, `APOLLO_API_KEY` (master key), `APOLLO_USER_ID`, optionally `APOLLO_DEAL_STAGE_ID`, `NOTION_API_KEY`, `NOTION_LEADS_DB_ID`, `NOTION_TRANSCRIPTS_DB_ID`, `SLACK_WEBHOOK_URL`. Leave `APOLLO_CREATE_DEALS=false` until Apollo's HubSpot sync is off.

## Hosting recommendation (2026-11-02)
ElevenLabs hosts the voice, so the host only runs the webhook service (and Windmill while it exists). **Recommendation: keep a small always-on UK VPS; drop Windmill.** Size: **2 vCPU / 4 GB RAM / 80 GB SSD in London** — ideally in AWS eu-west-2 (e.g. Lightsail London) to sit next to Neon; the service itself needs well under 1 GB, and the headroom covers image builds and logs. If Windmill is kept, the original 4 vCPU / 8 GB stands.

Why not serverless (Vercel Functions, Neon Functions) for now:
- **Call-start latency.** The lookup must answer inside ~1.5 s while the call connects. A warm process with a ready pool does it in tens of milliseconds; a cold Python function start plus a cold Neon compute (likely for after-hours traffic) can eat most of that budget, and the fallback is a known caller greeted as a stranger.
- **Post-call work runs after the 200.** It is around a dozen sequential Notion, Apollo and Slack requests. On a VPS that is a background task; serverless needs a queue or must finish before replying to ElevenLabs.
- **Neon Functions are Node.js only**, which would mean rewriting in TypeScript against the Python-everywhere convention.
- **Cron-shaped jobs** (replay, retention, the RingCentral missed-call alert) are one crontab line each on a VPS.

Serverless stays a cheap option later: the service is a plain ASGI app with no local state, so it can move to a container platform with one warm instance without code changes.

## Blocked
- **Apollo deals:** `APOLLO_CREATE_DEALS` stays false until Apollo's automatic HubSpot sync is switched off (it would push deals into HubSpot).
- **Phase 0 host bring-up:** needs a host and DNS for `WEBHOOK_DOMAIN`.
- **Phase 2 live test:** RingCentral divert to the new 020 number; ElevenLabs import of `+442045200783`.

## Test-call log
| Date | # | call_id | Pass/Fail | Notes |
|---|---|---|---|---|

## Go-live checklist (Phase 5)
- [ ] All 21 test calls pass and are logged above
- [ ] `config/greeting.yaml` approved by Noel (no TODO remains)
- [ ] `config/terms.yaml` populated
- [ ] Qualified test call produces the Apollo contact, call record, task, Notion lead row and Slack alert
- [ ] Apollo HubSpot sync off, then `APOLLO_CREATE_DEALS=true` verified on a test call
- [ ] Retention + replay schedule running
- [ ] n8n RC alert disabled; replacement verified
- [ ] RingCentral after-hours rule → `+442045200783`
- [ ] RingCentral no-answer forwarding → `+442045200783`
- [ ] Old 0330 number removed from ElevenLabs
- [ ] Two-week after-hours review period scheduled
