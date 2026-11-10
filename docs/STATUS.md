# Status

**Current phase:** 3 — Neon dropped; caller lookup and post-call moving to n8n (not yet tested); the webhook service keeps the three Cal.com tools · Phase 2 live test pending on the new 020 DID · host bring-up pending a host
**Last updated:** 2026-11-03

## Done
- **Line-aware Cody (issue #13, branch `cursor/line-aware-cody-e93a`, PR open)** — see DECISIONS 2026-11-10. Line map in `config/lines.yaml`, `POST /lines/resolve`, per-line greeting and prompt, Notion "Line" select, parking booking tags, Noel-direct transfer tool in `provision_elevenlabs.py`. Nothing was applied to ElevenLabs, Telnyx or Notion. The RC sales, accounts and support DDIs are in `config/lines.yaml`. Still to do by hand: the n8n changes (infra/elevenlabs/README.md), outbound calling on the trunk, and `NOEL_MOBILE_E164`.
- **Neon dropped (2026-11-03, branch `remove-neon`)** — see DECISIONS 2026-11-03. Removed `agent/store/`, `db/`, the Neon preview-branch workflow, `seed_config.py`, `replay_post_call.py`, conversation-init, post-call, `asyncpg`, `DATABASE_URL` and the Windmill containers. The service is now the three Cal.com tools with no state; `take_message` returns a `message_id` only.
- **Phase 0 scaffold** — repo layout, `uv` project, pinned images, Neon project "Inbound Calls" (`wandering-union-75946614`, London, `production` branch), `receptionist` migrated and seeded (2026-10-04), Neon preview branch per PR in CI. *(Neon dropped 2026-11-03.)*
- **Phase 1 — Cal.com** — `agent/calcom/` (availability + booking). Live booking verified 2026-10-05 on event 7103844. Cody now books event 7747197 (`control-freq-discovery`); 7103844 stays LiftPulse. The HubSpot half of Phase 1 was removed on 2026-11-02.
- **Phase 2 wiring (PR #9, open)** — `provision_telnyx.py` + `provision_elevenlabs.py`. Applied live for the old 0330 number: Telnyx connection 3067081943628646021; ElevenLabs agent `agent_6901m4gzr6bdfjwsmte3fxepq946` (voice, greeting, `record_voice: false`, `retention_days: 30`) with `+443301900784` imported and bound to it.
- **CRM plan + Phase 3 webhook service (2026-11-02, PR #10, merged)** — see DECISIONS 2026-11-02. *(The Neon caller lookup, post-call pipeline, migrations and replay below were removed on 2026-11-03; n8n owns them.)*
  - HubSpot removed (code, env vars, Neon columns, docs, tests).
  - `agent/app.py`: conversation-init (Neon caller lookup by E.164 within `INIT_LOOKUP_TIMEOUT_MS`), the three webhook tools, and the HMAC-verified post-call receiver.
  - Post-call pipeline: Neon ingest + scoring; Notion "Call transcripts" + "Cody leads" rows for every call; for qualified callers Apollo account/contact/call record/follow-up task (deal behind `APOLLO_CREATE_DEALS`, default off) and a Slack alert. Idempotent; `scripts/replay_post_call.py` finishes failed runs.
  - Neon migrations as files (`db/migrations/0001`, `0002`); `provision_notion.py`; `provision_elevenlabs.py` patches the agent's data collection, dynamic variables and overrides; DID default `+442045200783`.
  - 49 tests (Apollo/Notion/Slack mocked at the HTTP layer; real-SQL integration test against a throwaway local Postgres). Nothing was run against production Neon or any live API.

## Live state found on 2026-11-02 (read-only checks)
- ElevenLabs agent: no tools, no dynamic variables, no data collection, conversation-init overrides disabled. Only the 0330 number is imported; `+442045200783` is not.
- Neon `production`: the Phase 0 baseline only (no `callers`, no `schema_migrations`); compute suspends when idle. *(No longer used from 2026-11-03.)*
- Notion: "Cody leads" and "Call transcripts" databases created with the full set of fields (2026-11-03); their ids are in `.env`.

## Next
1. Noel: test n8n's conversation-init and post-call flows against Notion, and answer the batch in QUESTIONS (Apollo HubSpot sync, host, whether the Python service is still needed).
2. Host (if the Python service stays): bring up a UK VPS, DNS for `WEBHOOK_DOMAIN`, `docker compose --env-file ../.env up -d agent caddy`.
3. Provisioning (Noel's go-ahead): `provision_telnyx.py --apply`, `provision_elevenlabs.py --apply`, and `provision_notion.py --apply` once `NOTION_API_KEY` is on the server (it should only confirm the existing fields); in the ElevenLabs dashboard set the n8n conversation-init and post-call URLs and the three tools (infra/elevenlabs/README.md).
4. RingCentral divert → `+442045200783`; Phase 2 live test; the ten core test calls (Phase 3 DoD); remove the 0330 number from ElevenLabs.

## Env vars Noel must supply (`.env` on the host)
The Python service reads only `ELEVENLABS_TOOL_SECRET` (any long random string; also stored in ElevenLabs), `CALCOM_API_KEY` and `CALCOM_EVENT_TYPE_ID=7747197` (not 7103844). Provisioning also needs `ELEVENLABS_API_KEY`, `ELEVENLABS_PHONE_NUMBER_ID` (printed by provisioning), `TELNYX_API_KEY`, `TELNYX_DID=+442045200783`, `NOTION_API_KEY`, `NOTION_LEADS_DB_ID` and `NOTION_TRANSCRIPTS_DB_ID`; Caddy needs `WEBHOOK_DOMAIN`. `ELEVENLABS_WEBHOOK_SECRET`, `APOLLO_*` and `SLACK_WEBHOOK_URL` are for n8n's post-call flow (n8n credentials). Leave `APOLLO_CREATE_DEALS=false` until Apollo's HubSpot sync is off.

## Hosting (2026-11-03)
ElevenLabs hosts the voice and n8n runs caller lookup and post-call, so the host only runs the stateless tool service and Caddy. The 2026-11-02 VPS sizing (2 vCPU / 4 GB / 80 GB in London) is more than enough for that, and there is no longer a cold Neon compute in the call-start path. If the Python service is dropped in favour of n8n's "Cody – Tools" workflow, no host is needed for this repo at all (QUESTIONS).

## Blocked
- **Apollo deals:** `APOLLO_CREATE_DEALS` stays false until Apollo's automatic HubSpot sync is switched off (it would push deals into HubSpot).
- **Host bring-up:** needs a host and DNS for `WEBHOOK_DOMAIN`, if the Python service stays.
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
- [ ] Notion transcript retention (12 months) running in n8n
- [ ] n8n conversation-init and post-call flows active and tested; RingCentral missed-call alert still working in n8n
- [ ] RingCentral after-hours rule → `+442045200783`
- [ ] RingCentral no-answer forwarding → `+442045200783`
- [ ] Line test calls 22-29 pass (Noel direct, parking, generic, cold sales declined)
- [ ] Old 0330 number removed from ElevenLabs
- [ ] Once the test calls work: Neon project, GitHub `NEON_API_KEY` secret and `NEON_PROJECT_ID` variable removed
- [ ] Two-week after-hours review period scheduled
