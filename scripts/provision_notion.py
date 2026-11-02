#!/usr/bin/env python
"""Idempotently add Cody's properties to the two Notion databases (create-only, never renames).

Noel creates two empty databases in Notion — "Cody leads" and "Call transcripts" — shares both with
the integration, and puts their ids in NOTION_LEADS_DB_ID / NOTION_TRANSCRIPTS_DB_ID. This script
adds every property from agent/notion/schema.py that is missing; existing properties (including
the default "Name" title) are left alone, so it is safe to rerun.

    uv run python scripts/provision_notion.py --dry-run   # print the schema, no API calls
    uv run python scripts/provision_notion.py --apply     # needs NOTION_API_KEY + both db ids
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.notion import NotionClient  # noqa: E402
from agent.notion.schema import SCHEMAS  # noqa: E402

ENV = {"leads": "NOTION_LEADS_DB_ID", "transcripts": "NOTION_TRANSCRIPTS_DB_ID"}


def missing(schema: dict, existing: dict) -> dict:
    """Properties to add. The title property is never added: every database already has one."""
    return {
        name: spec for name, spec in schema.items() if name not in existing and "title" not in spec
    }


async def main() -> int:
    load_dotenv(ROOT / ".env")
    args = sys.argv[1:]
    apply = "--apply" in args
    if not apply and "--dry-run" not in args:
        print("usage: provision_notion.py [--dry-run | --apply]", file=sys.stderr)
        return 2

    if not apply:
        for key, schema in SCHEMAS.items():
            print(f"{key} ({ENV[key]}):")
            for name, spec in schema.items():
                print(f"  {name}: {json.dumps(spec)}")
        return 0

    key = os.environ.get("NOTION_API_KEY")
    if not key:
        print("NOTION_API_KEY is not set (use --dry-run to preview)", file=sys.stderr)
        return 1
    client = NotionClient(key)
    try:
        for name, schema in SCHEMAS.items():
            db_id = os.environ.get(ENV[name], "").strip()
            if not db_id:
                print(f"{ENV[name]} is not set — skipping {name}", file=sys.stderr)
                continue
            db = await client.get_database(db_id)
            todo = missing(schema, db.get("properties") or {})
            if not todo:
                print(f"{name}: all {len(schema)} properties exist")
                continue
            await client.update_database(db_id, todo)
            print(f"{name}: added {', '.join(todo)}")
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
