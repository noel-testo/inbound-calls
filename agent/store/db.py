"""Neon access for the webhook service (asyncpg pool). One short query or transaction per method."""

from __future__ import annotations

import json
from datetime import datetime

import asyncpg

CALL_COLUMNS = {
    "outcome",
    "intent",
    "lead_score",
    "high_value",
    "extraction",
    "summary",
    "booking_id",
    "processed_at",
    "apollo_contact_id",
    "apollo_account_id",
    "apollo_call_id",
    "apollo_deal_id",
    "apollo_task_id",
    "notion_lead_page_id",
    "notion_transcript_page_id",
    "slack_alerted_at",
}
CALLER_COLUMNS = {
    "name",
    "email",
    "organisation",
    "relationship",
    "apollo_contact_id",
    "apollo_account_id",
}


async def _init_conn(conn: asyncpg.Connection) -> None:
    for name in ("json", "jsonb"):
        await conn.set_type_codec(name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class Store:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    @classmethod
    async def connect(cls, dsn: str, **kw) -> Store:
        # Neon suspends an idle compute after 5 minutes and drops its connections; closing ours
        # after 60 s idle means a call-start lookup opens a fresh one instead of hitting a dead one.
        kw.setdefault("max_inactive_connection_lifetime", 60.0)
        pool = await asyncpg.create_pool(dsn, min_size=0, max_size=5, init=_init_conn, **kw)
        return cls(pool)

    async def close(self) -> None:
        await self.pool.close()

    # ---- conversation-init ----

    async def lookup_caller(self, phone_e164: str) -> dict | None:
        row = await self.pool.fetchrow("select * from callers where phone_e164 = $1", phone_e164)
        return dict(row) if row else None

    async def load_config(self, key: str) -> dict | None:
        return await self.pool.fetchval("select value from config where key = $1", key)

    async def active_terms(self, limit: int = 100) -> list[str]:
        rows = await self.pool.fetch(
            "select term from terms where active order by weight desc, term limit $1", limit
        )
        return [r["term"] for r in rows]

    async def start_call(
        self,
        conversation_id: str,
        caller_e164: str | None,
        called_number: str | None,
        caller_id=None,
    ) -> str:
        return str(
            await self.pool.fetchval(
                """
                insert into calls
                  (conversation_id, caller_e164, cli_present, called_number, caller_id)
                values ($1, $2, $3, $4, $5)
                on conflict (conversation_id) do update
                  set caller_e164 = coalesce(calls.caller_e164, excluded.caller_e164),
                      called_number = coalesce(calls.called_number, excluded.called_number),
                      caller_id = coalesce(calls.caller_id, excluded.caller_id)
                returning id
                """,
                conversation_id,
                caller_e164,
                caller_e164 is not None,
                called_number,
                caller_id,
            )
        )

    # ---- tools ----

    async def get_call(self, conversation_id: str) -> dict | None:
        row = await self.pool.fetchrow(
            "select * from calls where conversation_id = $1", conversation_id
        )
        return dict(row) if row else None

    async def ensure_call(self, conversation_id: str) -> dict:
        await self.pool.execute(
            "insert into calls (conversation_id) values ($1)"
            " on conflict (conversation_id) do nothing",
            conversation_id,
        )
        return await self.get_call(conversation_id)

    async def add_message(self, call_id, category, summary, callback_number, urgency, site) -> str:
        return str(
            await self.pool.fetchval(
                """
                insert into messages (call_id, category, summary, callback_number, urgency, site)
                values ($1, $2, $3, $4, $5, $6) returning id
                """,
                call_id,
                category,
                summary,
                callback_number,
                urgency,
                site,
            )
        )

    async def messages_for(self, call_id) -> list[dict]:
        rows = await self.pool.fetch(
            "select * from messages where call_id = $1 order by created_at", call_id
        )
        return [dict(r) for r in rows]

    async def log_event(self, call_id, type_: str, payload: dict | None = None) -> None:
        await self.pool.execute(
            "insert into events (call_id, type, payload) values ($1, $2, $3)",
            call_id,
            type_,
            payload or {},
        )

    # ---- post-call ----

    async def record_post_call(self, conversation_id: str, payload: dict) -> dict:
        """Store the verified payload first, so a failed run can be replayed from Neon."""
        await self.pool.execute(
            """
            insert into calls (conversation_id, post_call_payload) values ($1, $2)
            on conflict (conversation_id) do update
              set post_call_payload = excluded.post_call_payload
            """,
            conversation_id,
            payload,
        )
        return await self.get_call(conversation_id)

    async def ingest(
        self,
        conversation_id: str,
        *,
        caller_e164: str | None,
        called_number: str | None,
        started_at: datetime | None,
        ended_at: datetime | None,
        duration_s: int | None,
        turns: list[tuple[str, str, datetime]],
    ) -> dict:
        async with self.pool.acquire() as conn, conn.transaction():
            call_id = await conn.fetchval(
                """
                update calls set
                  caller_e164 = coalesce(caller_e164, $2),
                  cli_present = coalesce(caller_e164, $2) is not null,
                  called_number = coalesce(called_number, $3),
                  started_at = coalesce($4, started_at),
                  ended_at = $5,
                  duration_s = $6
                where conversation_id = $1
                returning id
                """,
                conversation_id,
                caller_e164,
                called_number,
                started_at,
                ended_at,
                duration_s,
            )
            await conn.execute("delete from transcripts where call_id = $1", call_id)
            await conn.executemany(
                "insert into transcripts (call_id, seq, role, text, ts)"
                " values ($1, $2, $3, $4, $5)",
                [(call_id, i, role, text, ts) for i, (role, text, ts) in enumerate(turns)],
            )
        return await self.get_call(conversation_id)

    async def upsert_caller(
        self,
        phone_e164: str,
        *,
        name: str | None,
        email: str | None,
        organisation: str | None,
        relationship: str,
        last_call_at: datetime | None,
    ) -> dict:
        row = await self.pool.fetchrow(
            """
            insert into callers (phone_e164, name, email, organisation, relationship, last_call_at)
            values ($1, $2, $3, $4, $5, $6)
            on conflict (phone_e164) do update set
              name = coalesce(excluded.name, callers.name),
              email = coalesce(excluded.email, callers.email),
              organisation = coalesce(excluded.organisation, callers.organisation),
              relationship = case when callers.relationship = 'customer' then 'customer'
                                  else excluded.relationship end,
              last_call_at = greatest(callers.last_call_at, excluded.last_call_at),
              updated_at = now()
            returning *
            """,
            phone_e164,
            name,
            email,
            organisation,
            relationship,
            last_call_at,
        )
        return dict(row)

    async def link_caller(self, conversation_id: str, caller_id) -> None:
        await self.pool.execute(
            "update calls set caller_id = $2 where conversation_id = $1", conversation_id, caller_id
        )

    async def claim(self, conversation_id: str, seconds: int = 300) -> bool:
        got = await self.pool.fetchval(
            """
            update calls set post_call_lock_until = now() + make_interval(secs => $2)
            where conversation_id = $1
              and (post_call_lock_until is null or post_call_lock_until < now())
            returning true
            """,
            conversation_id,
            seconds,
        )
        return bool(got)

    async def release(self, conversation_id: str) -> None:
        await self.pool.execute(
            "update calls set post_call_lock_until = null where conversation_id = $1",
            conversation_id,
        )

    async def update_call(self, conversation_id: str, **cols) -> None:
        bad = set(cols) - CALL_COLUMNS
        if bad:
            raise ValueError(f"not updatable on calls: {sorted(bad)}")
        if not cols:
            return
        names = list(cols)
        sets = ", ".join(f"{n} = ${i + 2}" for i, n in enumerate(names))
        await self.pool.execute(
            f"update calls set {sets} where conversation_id = $1",
            conversation_id,
            *(cols[n] for n in names),
        )

    async def update_caller(self, caller_id, **cols) -> None:
        bad = set(cols) - CALLER_COLUMNS
        if bad:
            raise ValueError(f"not updatable on callers: {sorted(bad)}")
        if not cols:
            return
        names = list(cols)
        sets = ", ".join(f"{n} = ${i + 2}" for i, n in enumerate(names))
        await self.pool.execute(
            f"update callers set {sets}, updated_at = now() where id = $1",
            caller_id,
            *(cols[n] for n in names),
        )

    async def get_caller(self, caller_id) -> dict | None:
        row = await self.pool.fetchrow("select * from callers where id = $1", caller_id)
        return dict(row) if row else None

    async def unprocessed(self, limit: int = 50) -> list[str]:
        rows = await self.pool.fetch(
            """
            select conversation_id from calls
            where processed_at is null and post_call_payload is not null
            order by created_at limit $1
            """,
            limit,
        )
        return [r["conversation_id"] for r in rows]
