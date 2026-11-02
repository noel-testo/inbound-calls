#!/usr/bin/env python
"""Apply db/migrations/*.sql to the Neon `receptionist` database, in filename order.

Reads DATABASE_URL from the environment (or the repo-root .env). Each file runs once, in its own
transaction, and is recorded in `schema_migrations`; every file is also written to be re-runnable,
so a database that predates the tracking table (production's 0001 baseline) is caught up safely.
Use the unpooled connection string: DDL over asyncpg misbehaves through the PgBouncer pooler.

    uv run python db/migrate.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

MIGRATIONS = Path(__file__).parent / "migrations"


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))


async def apply(conn: asyncpg.Connection) -> list[str]:
    await conn.execute(
        """
        create table if not exists schema_migrations (
          name       text primary key,
          applied_at timestamptz not null default now()
        )
        """
    )
    done = {r["name"] for r in await conn.fetch("select name from schema_migrations")}
    applied: list[str] = []
    for path in migration_files():
        if path.name in done:
            continue
        async with conn.transaction():
            await conn.execute(path.read_text())
            await conn.execute("insert into schema_migrations (name) values ($1)", path.name)
        applied.append(path.name)
    return applied


async def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(dsn)
    try:
        applied = await apply(conn)
    finally:
        await conn.close()

    print(f"Applied: {', '.join(applied)}" if applied else "Up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
