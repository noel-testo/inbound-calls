#!/usr/bin/env python
"""Apply db/schema.sql to the Neon `receptionist` database, idempotently.

Reads DATABASE_URL from the environment (or the repo-root .env). Safe to rerun:
schema.sql uses `if not exists` / duplicate-object guards throughout.

    uv run python db/migrate.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

SCHEMA = Path(__file__).parent / "schema.sql"


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    sql = SCHEMA.read_text()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()

    print(f"Applied {SCHEMA.name} to receptionist")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
