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
  n8n's post-call flow parses `analysis.data_collection_results`.
- **Dynamic variables** (placeholders): `caller_known`, `caller_name`, `caller_first_name`,
  `caller_company`, `caller_relationship`, `caller_phone`, plus the line variables `line_key`,
  `line_label`, `line_instructions`, `caller_id_is_caller` — filled by n8n's conversation-init.
- **Transfer tool** (`built_in_tools.transfer_to_number`): one conference transfer to Noel's mobile,
  condition "only on Noel's direct line…" (from `config/lines.yaml`). The number comes from
  `NOEL_MOBILE_E164` in `.env`, never from the repo, and the dry-run hides it. Skipped if the
  variable is unset. It rewrites the agent's whole `transfer_to_number` slot.
- **System prompt**: set on create; on an existing agent only with `--sync-prompt` (the new "This
  line" section needs it).
- **Overrides** (Security tab): conversation-init data from webhook enabled; `first_message` and
  ASR keywords overridable.

## Lines (`config/lines.yaml`)
`+442045200783` serves the main number and the RingCentral lines (told apart by CLI); the parking
number `+442045208242` is bound to Cody too (`provision_elevenlabs.py` imports every number in
`lines.yaml`). Per-call behaviour comes from n8n's conversation-init:

1. Call `POST https://$WEBHOOK_DOMAIN/lines/resolve` (header `X-Cody-Secret`) with
   `{"called_number": system__called_number, "caller_id": system__caller_id, "conversation_id": ...}`.
2. Skip the Notion caller lookup when `lookup_caller` is false (a RingCentral line: the CLI is the
   dialled DDI, not the caller). Otherwise look up as today.
3. Return to ElevenLabs `first_message` from the response, and `dynamic_variables` = the caller
   variables **merged with** the response's `dynamic_variables` (its `caller_phone` wins: blank on
   the RC lines). Keep `line_key` and `line_label` in the conversation's variables: the post-call
   webhook receives them.
4. Post-call: set Notion **Line** (leads and transcripts) to `line_key`; on `noel-direct`, `sales`,
   `accounts` and `support` leave **Phone** empty and put the extracted `callback_number` in
   **Callback number**; use outcome `transferred` when the transcript shows a successful
   `transfer_to_number` call; when data collection `cold_call_declined` is true, set outcome
   `cold_call_declined`, Review "Not a lead", leave Callback number empty and post the one-line
   Slack text (no call-back). When data collection `partner` is `justpark`, set Notion **Partner**
   to `justpark` and add JustPark to the Slack line (a JustPark caller is transferred on every
   line; if the transfer fails the message urgency is high). Otherwise add the line label to the Slack message (Noel direct:
   alert on every other call, whether transferred or a message). Do the Apollo and scoring work
   as today; a declined cold call is not a lead, so nothing goes to Apollo.

Transfers need outbound calling on the SIP trunk: see `infra/telnyx/README.md`. Warm transfer with a
spoken summary (`agent_message`) works only on numbers imported through ElevenLabs' native Twilio
integration; on this Telnyx SIP-trunk number the call connects with no whisper.

## Set in the dashboard
- **Conversation-initiation webhook** (Agents settings): n8n's conversation-init webhook URL. It
  looks the caller up by the "Cody leads" Phone field and must return every dynamic variable above.
- **Post-call webhook** (workspace webhook, HMAC): n8n's post-call webhook URL, transcript events
  only, "Send audio data" **off**; its HMAC secret is `ELEVENLABS_WEBHOOK_SECRET`. Enable retries.
- **Webhook tools** (POST, JSON body, header `X-Cody-Secret`) on `https://$WEBHOOK_DOMAIN`; every
  tool has a `conversation_id` body parameter assigned from the dynamic variable
  `system__conversation_id`:

| Tool | URL | Body parameters |
|---|---|---|
| `check_availability` | `/tools/check_availability` | `from_iso`, `to_iso` (ISO 8601). Slots on event 7747197 (`control-freq-discovery`), not 7103844. |
| `book_meeting` | `/tools/book_meeting` | `line` (from the dynamic variable `line_key`; tags the booking, parking gets "[Parking] " and `metadata.line`), `slot_iso`, `name`, `email`, `organisation`, `phone` (optional), `caller_phone` (from `system__caller_id`; the event requires a number, so the service sends `phone`, else this CLI), `notes` (optional; "Enquiry details"). Title: "Discovery call with Noel Sesto, Technical Director – <organisation>". |
| `take_message` | `/tools/take_message` | `category` (enquiry/support/supplier/other), `summary`, `callback_number`, `urgency` (normal/high), `site` |

## Egress IPs (optional allowlist at Caddy)
EU `35.204.38.71`, `34.147.113.54`; US `34.67.146.145`, `34.59.11.47`.

Credentials (`ELEVENLABS_*`) live in `.env`, never in the repo.
