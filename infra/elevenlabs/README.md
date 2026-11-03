# ElevenLabs Agents

The receptionist voice loop (STT · LLM · TTS · turn-taking) runs here. Agent:
**`agent_6901m4gzr6bdfjwsmte3fxepq946`** ("ControlFreq receptionist (Cody)"), voice
`jRAAK67SEFE9m7ci5DhD`, `record_voice: false`, `retention_days: 30`.

## Phone number
- Import the Telnyx London 020 DID **`+442045200783`**: Phone Numbers → Import number → From SIP
  Trunk (E.164), or run `scripts/provision_elevenlabs.py --apply`. Trunk details in `infra/telnyx/`.
- The old 0330 number `+443301900784` is still imported and bound to Cody (checked 2026-11-02).
  Remove it once the 020 number answers; the script reports it but never deletes it.

## Agent settings owned by this repo (`scripts/provision_elevenlabs.py`)
- **Data collection** (`platform_settings.data_collection`): the §6 fields from `agent/extraction.py`.
  The post-call webhook parses `analysis.data_collection_results`.
- **Dynamic variables** (placeholders): `caller_known`, `caller_name`, `caller_first_name`,
  `caller_company`, `caller_relationship`, `caller_phone` — filled by conversation-init.
- **Overrides** (Security tab): conversation-init data from webhook enabled; `first_message` and
  ASR keywords overridable.

## Set in the dashboard once `WEBHOOK_DOMAIN` is live
- **Conversation-initiation webhook** (Agents settings): `https://$WEBHOOK_DOMAIN/elevenlabs/conversation-init`,
  header `X-Cody-Secret: <ELEVENLABS_TOOL_SECRET>` (store it as an ElevenLabs secret).
- **Post-call webhook** (workspace webhook, HMAC): `https://$WEBHOOK_DOMAIN/elevenlabs/post-call`,
  transcript events only, "Send audio data" **off**; its HMAC secret is `ELEVENLABS_WEBHOOK_SECRET`.
  Enable retries.
- **Webhook tools** (POST, JSON body, header `X-Cody-Secret`); every tool has a `conversation_id`
  body parameter assigned from the dynamic variable `system__conversation_id`:

| Tool | URL | Body parameters |
|---|---|---|
| `check_availability` | `/tools/check_availability` | `from_iso`, `to_iso` (ISO 8601). Slots on event 7747197 (`control-freq-discovery`), not 7103844. |
| `book_meeting` | `/tools/book_meeting` | `slot_iso`, `name`, `email`, `organisation`, `phone` (optional; the event requires a number, so the service sends the caller's CLI), `notes` (optional; "Enquiry details"). Title: "Discovery call with Noel Sesto, Technical Director – <organisation>". |
| `take_message` | `/tools/take_message` | `category` (enquiry/support/supplier/other), `summary`, `callback_number`, `urgency` (normal/high), `site` |

## Egress IPs (optional allowlist at Caddy)
EU `35.204.38.71`, `34.147.113.54`; US `34.67.146.145`, `34.59.11.47`.

Credentials (`ELEVENLABS_*`) live in `.env`, never in the repo.
