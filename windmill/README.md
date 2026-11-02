# Windmill — under review

The post-call pipeline no longer runs here: it runs in the webhook service (`agent/post_call.py`),
because the owner-approved CRM plan (DECISIONS 2026-11-02) has the post-call webhook write Neon,
Notion, Apollo and Slack directly, and that path needs no human in the loop.

What would still use Windmill:

- `rc_missed_call_alert/` — port of the current n8n RingCentral missed-call → Slack workflow. Export
  the n8n JSON into `rc_missed_call_alert/reference/` first.
- `retention/` — nightly: delete Notion "Call transcripts" rows older than 12 months, purge Neon
  transcripts if Noel sets a policy, and run `scripts/replay_post_call.py`.

Both are small enough to be one more webhook route plus a cron entry on the host, which would let
Windmill (two containers and a Neon database) be removed. That is a question for Noel
(docs/QUESTIONS.md); until it is answered, the Windmill services stay in compose.
