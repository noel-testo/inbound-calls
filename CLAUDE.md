# Inbound Calls — how to work in this repo

This is ControlFreq's self-hosted AI call answering service. Read `docs/SPEC.md` in full before doing anything; it is the source of truth for *what* to build. This file is *how* to work.

## Working rules

1. Build in the phase order in SPEC §14. Do not start a phase until the previous phase's definition of done is met, tested and committed.
2. **The best part is no part.** The system is six components (SPEC §2): RingCentral, Telnyx, LiveKit, Neon, Windmill, HubSpot. Telephony ingress is a Telnyx SIP trunk into LiveKit SIP — FreeSWITCH and the RingCentral SIP-registration hack were dropped on 2026-10-05 (see DECISIONS); do not reintroduce them. Do not add a service, library, queue, cache, framework or SaaS without writing the reason in `docs/DECISIONS.md` and getting a yes from Noel. Prefer deleting over adding.
3. Synchronous work lives in the agent; asynchronous and human-in-the-loop work lives in Windmill. Nothing mid-call calls Windmill.
4. HubSpot is the system of record for sales state. Neon is the receptionist's own store. Never duplicate a HubSpot field in Neon beyond the IDs needed to link records.
5. Every model provider (STT, LLM, TTS) sits behind the interfaces in `agent/providers/`. Switching a provider must be a config change, never a code change.
6. Secrets only in `.env` on the host and in Windmill variables. Never in code, tests, fixtures, logs or commits. `.env.example` lists every variable with a placeholder.
7. British English in everything a caller or Noel reads. No orphan copy in any UI or spoken string: it fits on one line or breaks evenly across two.
8. Nothing a caller hears is invented. Greeting, disclosures, emergency wording, business hours and anything about pricing or products come from `config/` and are questions if missing.

## Questions

- **Non-blocking** questions go in `docs/QUESTIONS.md` under "Open", one line each, with your proposed default. Carry on using the default. Post the batch to Noel once per session, not one at a time.
- **Blocking** questions (cannot proceed, or a choice that is expensive to reverse) stop work and go to Noel immediately, with the options and your recommendation.
- Always a question, never a guess: credentials, phone numbers, extension numbers, existing HubSpot property or pipeline names, business hours, pricing, and any wording callers will hear.

## Conventions

- Python 3.12 everywhere: agent, Windmill scripts, provisioning, tooling. `uv` for environments, `ruff` for lint and format, `pytest` for tests.
- One `docker compose` file in `infra/`. Pin every image tag in Phase 0 and record the versions in `docs/DECISIONS.md`.
- Provisioning scripts are idempotent and safe to rerun: `scripts/provision_hubspot.py`, `db/migrate.py`, `scripts/provision_livekit.py`.
- Structured JSON logs, one line per event, `call_id` on every line that belongs to a call.
- Commit per unit of work with a message that says *why*. One PR per phase, branch `phase-N-<slug>`.
- Tests: unit tests for every tool and for scoring; a recorded-audio smoke test for the pipeline; the scripted call suite in `docs/TEST-CALLS.md` run by hand before go-live and logged in `docs/STATUS.md`.

## When you finish a phase

Update `docs/STATUS.md` (done, next, blocked), open the PR, and post the summary together with the open questions batch.
