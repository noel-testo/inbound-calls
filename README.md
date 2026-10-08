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

Stack: RingCentral (office PBX, diverts after-hours / no-answer) → Telnyx (SIP trunk + London 020 DID) → **ElevenLabs Agents** (the voice loop) → a small HTTPS webhook service we host → HubSpot, with Windmill for post-call work and Neon as the record. Discovery-call booking is on Cal.com; the transcript log is a Notion database. No audio recording in the MVP.
