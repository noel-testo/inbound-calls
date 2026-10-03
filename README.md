# Inbound Calls

Self-hosted AI call answering for ControlFreq. Answers after-hours and unanswered calls on the main RingCentral number, qualifies new enquiries, books high-value leads into a discovery call via HubSpot, recognises existing customers by CLI, and logs every call.

- `CLAUDE.md` — how Claude Code works in this repo
- `docs/SPEC.md` — the build spec (source of truth)
- `docs/TEST-CALLS.md` — scripted acceptance calls
- `docs/QUESTIONS.md` — open questions, batched for Noel
- `docs/DECISIONS.md` — architecture decisions and version pins
- `docs/STATUS.md` — current phase, done, next, blocked
- `config/` — prompt, scoring rules, terms (editable without code changes)
- `db/schema.sql` — Neon `receptionist` schema
- `infra/docker-compose.yml` — the host stack

Stack: RingCentral → FreeSWITCH (temporary bridge) → LiveKit → Python agent → HubSpot, with Windmill for post-call work and Neon as the store. No GPU in the MVP; model providers are hosted and swappable.
