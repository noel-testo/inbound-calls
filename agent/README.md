# Agent — webhook service

The voice loop runs in **ElevenLabs Agents**; this `agent/` package is the small **HTTPS webhook
service** that ElevenLabs calls (SPEC §4.1, §7, §8, §11).

| Endpoint | Auth | Does |
|---|---|---|
| `POST /elevenlabs/conversation-init` | `X-Cody-Secret` | Caller lookup in Neon `callers` by E.164 within `INIT_LOOKUP_TIMEOUT_MS`; returns dynamic variables, the greeting (`first_message`) and STT keywords. Fails soft. |
| `POST /tools/check_availability` | `X-Cody-Secret` | Slots on Noel Sesto's Cal.com calendar. |
| `POST /tools/book_meeting` | `X-Cody-Secret` | Books a 15-minute discovery call with Noel Sesto, Technical Director; caller's CLI as the attendee phone. |
| `POST /tools/take_message` | `X-Cody-Secret` | Neon `messages`. |
| `POST /elevenlabs/post-call` | HMAC `ElevenLabs-Signature` | Verifies on the raw body, stores the payload, answers 200, then runs `post_call.py`. |
| `GET /healthz` | — | Liveness. |

Layout:
- `app.py` — FastAPI app and wiring.
- `conversation_init.py` — call-start lookup (Neon only; never Apollo).
- `tools/` — the three webhook tools.
- `post_call.py` — Neon ingest ▸ score ▸ Notion transcript ▸ Notion lead ▸ Apollo (qualified) ▸ Slack (qualified). Idempotent; replay with `scripts/replay_post_call.py`.
- `extraction.py` / `scoring.py` — the §6 schema (also provisions ElevenLabs data collection) and scoring.
- `apollo/`, `notion/`, `calcom/`, `slack.py` — thin HTTP clients. The Apollo client has no sequence methods.
- `store/` — Neon access (asyncpg).

Run locally: `uv run uvicorn agent.app:create_app --factory --port 8080`. In compose, Caddy fronts it
at `WEBHOOK_DOMAIN` and reverse-proxies to port 8080.
