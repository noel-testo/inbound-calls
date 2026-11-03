# Windmill — replaced by n8n

Windmill is no longer part of inbound-calls (DECISIONS 2026-11-03). It ran on a Neon database, and
Neon is dropped; **n8n** replaces it.

What was planned for Windmill now belongs in n8n:

- **Conversation-init** — caller lookup by phone in the Notion "Cody leads" database.
- **Post-call** — the Notion rows for every call; for qualified callers, Apollo and the Slack alert.
- **RingCentral missed-call → Slack alert** — already an n8n workflow; it stays there.
- **Retention** — delete Notion "Call transcripts" rows older than 12 months.

The Windmill containers and Caddy site are removed from `infra/`. This folder can be deleted once
nothing points at it.
