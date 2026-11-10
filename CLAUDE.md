# Inbound Calls — how to work in this repo

This is ControlFreq's self-hosted AI call answering service. Read `docs/SPEC.md` in full before doing anything; it is the source of truth for *what* to build. This file is *how* to work.

## Working rules

1. Build in the phase order in SPEC §14. Do not start a phase until the previous phase's definition of done is met, tested and committed.
2. **The best part is no part.** The components are in SPEC §2: RingCentral, Telnyx, ElevenLabs Agents, Cal.com, n8n, Notion, Apollo, a Slack incoming webhook, and our one webhook service. Telephony ingress is a Telnyx SIP trunk into ElevenLabs. Neon and Windmill (removed 2026-11-03), HubSpot (2026-11-02), LiveKit and the Python voice agent (2026-10-07), FreeSWITCH and the RingCentral SIP-registration hack (2026-10-05) are gone — see DECISIONS; do not reintroduce them. Do not add a service, library, queue, cache, framework or SaaS without writing the reason in `docs/DECISIONS.md` and getting a yes from Noel. Prefer deleting over adding.
3. Only the n8n Notion lookup and Cal.com are touched during a call. Apollo, Slack and every Notion write run post-call in n8n, after the post-call webhook has been acknowledged. Apollo is never called mid-call and nobody is ever added to an Apollo sequence.
4. Apollo is the sales record for qualified callers; Notion is the review surface and the record of every call, and its "Cody leads" Phone field (+44 E.164) is the phone-keyed caller directory the call-start lookup needs (Apollo cannot search by phone). There is no Cody-owned database.
5. The voice loop (STT, LLM, TTS) is ElevenLabs; model and voice choices are agent config, never code.
6. Secrets only in `.env` on the host and in n8n credentials. Never in code, tests, fixtures, logs or commits. `.env.example` lists every variable with a placeholder.
7. British English in everything a caller or Noel reads. No orphan copy in any UI or spoken string: it fits on one line or breaks evenly across two.
8. Nothing a caller hears is invented. Greeting, disclosures, business hours and anything about pricing or products come from `config/` and are questions if missing. There is no emergency script (DECISIONS 2026-11-10).

## Questions

- **Non-blocking** questions go in `docs/QUESTIONS.md` under "Open", one line each, with your proposed default. Carry on using the default. Post the batch to Noel once per session, not one at a time.
- **Blocking** questions (cannot proceed, or a choice that is expensive to reverse) stop work and go to Noel immediately, with the options and your recommendation.
- Always a question, never a guess: credentials, phone numbers, extension numbers, existing Apollo user/stage ids or Notion database ids, business hours, pricing, and any wording callers will hear.

## Conventions

- Python 3.12 for everything in this repo: the webhook service, provisioning, tooling. n8n workflows live in n8n. `uv` for environments, `ruff` for lint and format, `pytest` for tests.
- One `docker compose` file in `infra/`. Pin every image tag in Phase 0 and record the versions in `docs/DECISIONS.md`.
- Provisioning scripts are idempotent and safe to rerun, dry-run by default: `scripts/provision_telnyx.py`, `scripts/provision_elevenlabs.py`, `scripts/provision_notion.py`.
- Structured JSON logs, one line per event, `call_id` on every line that belongs to a call.
- Commit per unit of work with a message that says *why*. One PR per phase, branch `phase-N-<slug>`.
- Tests: unit tests for every tool, for scoring and extraction, and for the HTTP clients, with external APIs mocked at the HTTP layer; the scripted call suite in `docs/TEST-CALLS.md` run by hand before go-live and logged in `docs/STATUS.md`.

## When you finish a phase

Update `docs/STATUS.md` (done, next, blocked), open the PR, and post the summary together with the open questions batch.
