# Agent — webhook service (Phase 3)

The voice loop runs in **ElevenLabs Agents**; this `agent/` package is the small **HTTPS webhook
service** that ElevenLabs calls (SPEC §4.1, §7, §8). Built in Phase 3.

Layout:
- `app.py` — FastAPI app: conversation-init, tool webhooks, post-call receiver.
- `config.py` — renders `first_message` (greeting), `asr.keywords` (terms) and the prompt from Neon config.
- `tools/` — one handler per webhook tool: `check_availability`, `book_meeting`, `take_message`.
- `hubspot/` — thin HubSpot CRM client (contacts, companies, deals, calls). *(exists from Phase 1)*
- `calcom/` — Cal.com v2 client (availability + booking). *(exists from Phase 1)*
- `store/` — Neon access (asyncpg), event logging.

Endpoints:
- **conversation-init** — ElevenLabs calls this before the greeting with `caller_id`; returns
  `dynamic_variables` + `first_message` + `asr.keywords`. Does the HubSpot caller lookup (fail soft).
- **tool webhooks** — `check_availability` / `book_meeting` (Cal.com), `take_message` (Neon); auth via
  the `ELEVENLABS_TOOL_SECRET` header.
- **post-call** — receives `post_call_transcription` (HMAC `ElevenLabs-Signature`, verified with the raw
  body against `ELEVENLABS_WEBHOOK_SECRET`), returns 200, triggers Windmill `post_call`. Idempotent on
  `conversation_id`.

Caddy fronts it (TLS) at `WEBHOOK_DOMAIN`, reverse-proxying to port 8080; lock it to ElevenLabs' egress
IPs (SPEC §12). The LiveKit Agents worker, `providers/` and `prompt.py` from the earlier plan are gone.
