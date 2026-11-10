# Agent — webhook service

The voice loop runs in **ElevenLabs Agents**; this `agent/` package is the small **HTTPS webhook
service** that ElevenLabs calls for Cody's three Cal.com tools (SPEC §4.1, §7). It holds no state.
Conversation-init (caller lookup) and post-call run in **n8n**, not here.

| Endpoint | Auth | Does |
|---|---|---|
| `POST /tools/check_availability` | `X-Cody-Secret` | Slots on Noel Sesto's Cal.com calendar. |
| `POST /tools/book_meeting` | `X-Cody-Secret` | Books a 15-minute discovery call with Noel Sesto, Technical Director; `phone`, else the caller's CLI (`caller_phone`, never on a line whose CLI is not the caller), as the attendee phone. `line` adds the line's title prefix (parking: "[Parking] ") and `metadata.line`. |
| `POST /tools/take_message` | `X-Cody-Secret` | Returns a `message_id`; stores nothing (n8n's post-call adds the message to the lead's Notion Summary). |
| `POST /lines/resolve` | `X-Cody-Secret` | Body `{called_number, caller_id, conversation_id?}`. Returns the line (`line_key`, `line_tag`), `lookup_caller`, `screen_and_transfer`, the line's `first_message` and `dynamic_variables`. For n8n's conversation-init. |
| `GET /healthz` | — | Liveness. |

Layout:
- `app.py` — FastAPI app and wiring.
- `tools/` — the three webhook tools.
- `calcom/` — Cal.com v2 client.
- `lines.py` — the line map: resolves a call to a line and builds its greeting, prompt section and dynamic variables from `config/lines.yaml`, `config/greeting.yaml` and `config/prompt_lines.md`.
- `extraction.py` — the §6 schema; provisions ElevenLabs data collection.
- `prompt.py` — fills the host name and deflections into `config/prompt.md` for provisioning.
- `notion/` — Notion client + the two database schemas, used by `scripts/provision_notion.py`.
- `scoring.py`, `apollo/`, `slack.py`, `security.py` (HMAC part) — no longer called by the service
  since post-call moved to n8n; kept until the service itself is dropped once n8n is tested.

Run locally: `uv run uvicorn agent.app:create_app --factory --port 8080`. In compose, Caddy fronts it
at `WEBHOOK_DOMAIN` and reverse-proxies to port 8080.
