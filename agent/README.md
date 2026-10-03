# Agent worker — Phase 2/3

The LiveKit Agents receptionist (SPEC §4.2, §7, §8). The package skeleton exists
from Phase 0; the Dockerfile, pipeline wiring, prompt renderer, tools and
provider implementations land in **Phase 2 — Telephony** (a minimal "speak one
sentence" agent) and **Phase 3 — Agent** (the full pipeline).

Layout:

- `main.py` — entrypoint, session wiring.
- `prompt.py` — renders `config/prompt.md` with config values from Neon.
- `tools/` — one module per tool (§7).
- `providers/` — `stt.py`, `llm.py`, `tts.py` interfaces + implementations.
- `hubspot/` — thin HubSpot client (§9).
- `store/` — Neon access (asyncpg), event logging (§10).

Provider SDKs and `livekit-agents` are added to the root `pyproject.toml` in
Phase 3, once the provider choices in `docs/QUESTIONS.md` are settled.
