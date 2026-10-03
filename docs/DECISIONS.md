# Decisions

Record every architecture decision and every pinned version here. One entry per decision, newest first.

## 2026-10-03 — Initial architecture (Noel, with Claude)

- **Six components only:** RingCentral, FreeSWITCH (temporary), LiveKit, Neon, Windmill, HubSpot. "The best part is no part."
- **Removed from the process:** Apollo (prospecting only, synced to HubSpot), n8n (retired after Windmill takes the RC alert), a second carrier (Telnyx/Simwood), direct Google Calendar integration (via HubSpot Meetings), SMS (HubSpot booking email + invite instead).
- **Ingress:** FreeSWITCH registers to RingCentral as an existing-phone device because LiveKit SIP does not support REGISTER. Preserves CLI, keeps transfers internal later, exposes nothing publicly.
- **HubSpot is the system of record** for sales state; Neon holds the receptionist's own data; Windmill runs on a database in the same Neon project.
- **Synchronous in the agent, asynchronous in Windmill.** Only availability and booking block a call.
- **Hosted model providers in the MVP**, each behind an interface; LLM via an OpenAI-compatible endpoint. No GPU until the flow has earned it.
- **Recording on the FreeSWITCH leg**, not LiveKit egress, to avoid another service.
- **MVP scope:** after-hours and unanswered calls only; no live transfer until daytime traffic.

## Version pins

(Phase 0 — record every image tag and Python package version here with the date.)
