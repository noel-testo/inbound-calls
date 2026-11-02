#!/usr/bin/env python
"""Finish post-call processing for calls whose pipeline did not complete (processed_at is null).

Re-runs the idempotent pipeline from the payload stored in Neon: steps whose ids are already
recorded are skipped, so nothing is duplicated in Notion, Apollo or Slack. Safe to run from cron.

    uv run python scripts/replay_post_call.py            # every unfinished call (up to 50)
    uv run python scripts/replay_post_call.py conv_abc   # one conversation
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent import log  # noqa: E402
from agent.app import build_services  # noqa: E402
from agent.post_call import process  # noqa: E402
from agent.settings import Settings  # noqa: E402
from agent.store import Store  # noqa: E402


async def main() -> int:
    load_dotenv(ROOT / ".env")
    settings = Settings.from_env()
    if not settings.database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1
    log.configure()
    store = await Store.connect(settings.database_url)
    try:
        services = build_services(settings, store)
        ids = sys.argv[1:] or await store.unprocessed()
        for conversation_id in ids:
            status = await process(services, conversation_id)
            print(f"{conversation_id}: {status}")
    finally:
        await store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
