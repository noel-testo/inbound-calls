# ElevenLabs Agents — Phase 3

The receptionist voice loop (STT · LLM · TTS · turn-taking) runs here. The agent config is managed in
the ElevenLabs dashboard and can be pulled into this folder with `elevenlabs agents pull` (JSON), so the
prompt / tools / privacy settings are versioned with the repo.

## Phone number
- Import the Telnyx 0330 DID (`+443301900784`): Phone Numbers → Import number → From SIP Trunk (E.164),
  or run `scripts/provision_elevenlabs.py`. Trunk details in `infra/telnyx/`.

## Agent config
- **Prompt / first message / keywords** are supplied per call by the conversation-init webhook
  (greeting → `first_message`, `config/terms.yaml` → `asr.keywords`, plus the prompt), reading Neon config.
- **Tools** (webhook tools → our service, `ELEVENLABS_TOOL_SECRET` header): `check_availability`,
  `book_meeting`, `take_message`. `check_availability` / `book_meeting` are enabled only for high-value
  new enquiries.
- **Privacy (Advanced tab):** `platform_settings.privacy.record_voice: false` (no audio) and
  `retention_days: 30`. The post-call webhook's "Send audio data" is **off** — handle only
  `post_call_transcription`, never `post_call_audio`.
- **Post-call webhook:** points at the webhook service (`WEBHOOK_DOMAIN`), HMAC-signed with
  `ELEVENLABS_WEBHOOK_SECRET`.

## Egress IPs (allowlist on the webhook service)
EU `35.204.38.71`, `34.147.113.54`; US `34.67.146.145`, `34.59.11.47`.

Credentials (`ELEVENLABS_*`) live in `.env`, never in the repo.
