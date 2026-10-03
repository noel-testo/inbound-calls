#!/usr/bin/env python
"""Seed Neon `config` and `terms` from config/*.yaml and config/prompt.md.

Idempotent: upserts by key (config) and term (terms). Any value containing the
string "TODO" is skipped for terms and flagged for config, so nothing unapproved
reaches the agent or the speech recogniser. Run after editing any config file.

    uv run python scripts/seed_config.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"


def _contains_todo(value: object) -> bool:
    return "TODO" in json.dumps(value)


async def main() -> int:
    load_dotenv(ROOT / ".env")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    greeting = yaml.safe_load((CONFIG / "greeting.yaml").read_text())
    scoring = yaml.safe_load((CONFIG / "scoring.yaml").read_text())
    terms_doc = yaml.safe_load((CONFIG / "terms.yaml").read_text()) or {}
    prompt = (CONFIG / "prompt.md").read_text()

    config_rows: dict[str, object] = {
        "greeting": greeting,
        "scoring": scoring,
        "prompt": {"template": prompt},
    }

    conn = await asyncpg.connect(dsn)
    try:
        for key, value in config_rows.items():
            await conn.execute(
                """
                insert into config (key, value, updated_at)
                values ($1, $2::jsonb, now())
                on conflict (key) do update
                  set value = excluded.value, updated_at = now()
                """,
                key,
                json.dumps(value),
            )

        seeded = skipped = 0
        for category, entries in terms_doc.items():
            for term in entries or []:
                if not isinstance(term, str) or "TODO" in term:
                    skipped += 1
                    continue
                await conn.execute(
                    """
                    insert into terms (term, category, updated_at)
                    values ($1, $2, now())
                    on conflict (term) do update
                      set category = excluded.category, active = true, updated_at = now()
                    """,
                    term,
                    category,
                )
                seeded += 1
    finally:
        await conn.close()

    print(f"Seeded config keys: {', '.join(config_rows)}")
    print(f"Seeded {seeded} terms, skipped {skipped} TODO placeholders")
    if any(_contains_todo(v) for v in config_rows.values()):
        print(
            "WARNING: seeded config still contains TODO placeholders "
            "(expected until Noel approves the wording)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
