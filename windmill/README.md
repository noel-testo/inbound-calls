# Windmill — Phase 4

Async and human-in-the-loop work (SPEC §11). Self-hosted on the host, database on
Neon (`WINDMILL_DATABASE_URL`). Python scripts only. Built in **Phase 4**:

- `post_call/` — the webhook-triggered flow: ingest, extract, score, hubspot_upsert,
  deal, call_engagement, messages, finalise.
- `rc_missed_call_alert/` — port of the current n8n RingCentral missed-call -> Slack
  workflow. Export the n8n JSON into `rc_missed_call_alert/reference/` first.
- `retention/` — nightly schedule: prune recordings past retention, replay undelivered
  post_call payloads from `events`.

Nothing mid-call calls Windmill (SPEC §2). Phase 0 only stands up the Windmill
server/worker containers against Neon; the flows are authored in Phase 4.
