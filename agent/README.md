# Agent — webhook service

The voice loop runs in **ElevenLabs Agents**; this `agent/` package is the small **HTTPS webhook
service** that ElevenLabs calls for Cody's three Cal.com tools (SPEC §4.1, §7). It holds no state.
Conversation-init (caller lookup) and post-call run in **n8n**, not here.

| Endpoint | Auth | Does |
|---|---|---|
| `POST /tools/check_availability` | `X-Cody-Secret` | Cal.com slots. |
| `POST /tools/book_meeting` | `X-Cody-Secret` | Cal.com booking; `phone`, else the caller's CLI (`caller_phone`), as the attendee phone. |
| `POST /tools/take_message` | `X-Cody-Secret` | Returns a `message_id`; stores nothing (n8n's post-call adds the message to the lead's Notion Summary). |
| `GET /healthz` | — | Liveness. |

Layout:
- `app.py` — FastAPI app and wiring.
- `tools/` — the three webhook tools.
- `calcom/` — Cal.com v2 client.
- `extraction.py` — the §6 schema; provisions ElevenLabs data collection.
- `notion/` — Notion client + the two database schemas, used by `scripts/provision_notion.py`.
- `scoring.py`, `apollo/`, `slack.py`, `security.py` (HMAC part) — no longer called by the service
  since post-call moved to n8n; kept until QUESTIONS settles whether the service stays.

Run locally: `uv run uvicorn agent.app:create_app --factory --port 8080`. In compose, Caddy fronts it
at `WEBHOOK_DOMAIN` and reverse-proxies to port 8080.
