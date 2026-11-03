# Inbound Calls

ControlFreq's AI receptionist, **Cody**. Answers after-hours and unanswered calls on the main RingCentral number, recognises returning callers by CLI, qualifies new enquiries, books high-value leads into a discovery call on Cal.com, and logs every call.

- `CLAUDE.md` — how Claude Code works in this repo
- `docs/SPEC.md` — the build spec (source of truth)
- `docs/TEST-CALLS.md` — scripted acceptance calls
- `docs/QUESTIONS.md` — open questions, batched for Noel
- `docs/DECISIONS.md` — architecture decisions and version pins
- `docs/STATUS.md` — current phase, done, next, blocked
- `config/` — greeting, prompt, scoring rules, terms (editable without code changes)
- `agent/` — the HTTPS webhook service for Cody's three Cal.com tools
- `infra/docker-compose.yml` — the host stack

Stack: RingCentral (office PBX, diverts after-hours / no-answer) → Telnyx (SIP trunk + London 020 DID `+442045200783`) → **ElevenLabs Agents** (the voice loop). At call start **n8n** looks the caller up by phone in the Notion "Cody leads" database; mid-call a small HTTPS webhook service we host checks and books Cal.com slots and takes messages; after the call n8n writes a Notion lead row and transcript for every call, and — for qualified callers only — Apollo records and a Slack alert. No database of our own, no HubSpot, no audio recording.

```bash
uv sync
uv run pytest
uv run uvicorn agent.app:create_app --factory --port 8080   # needs .env (see .env.example)
```
