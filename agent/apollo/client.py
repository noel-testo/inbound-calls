"""Thin async Apollo REST client (https://api.apollo.io/api/v1, header `x-api-key`).

Post-call only, qualified callers only. Deliberately has no sequence/emailer-campaign methods: Cody
never adds a caller to a sequence. Apollo does not dedupe accounts or tasks on create, so callers of
this client must search first; contacts are created with `run_dedupe`, and call records upsert on
`call_identifier`. Logging call records needs a *master* API key.

Not wired into the service: post-call runs in n8n since DECISIONS 2026-11-03 (see QUESTIONS).
"""

from __future__ import annotations

import httpx

from .errors import ApolloError

BASE_URL = "https://api.apollo.io/api/v1"


class ApolloClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ):
        self._headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Cache-Control": "no-cache",
        }
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kw) -> dict:
        try:
            resp = await self._client.request(method, path, headers=self._headers, **kw)
        except httpx.TimeoutException as e:
            raise ApolloError(0, f"request to {path} timed out") from e
        if resp.status_code >= 400:
            message = resp.text or "request failed"
            try:
                body = resp.json()
                message = body.get("error") or body.get("message") or message
            except ValueError:
                pass
            raise ApolloError(resp.status_code, str(message))
        return resp.json() if resp.content else {}

    # ---- accounts ----

    async def find_account(self, name: str) -> dict | None:
        """Exact (case-insensitive) name match among saved accounts, else None."""
        body = await self._request(
            "POST", "/accounts/search", json={"q_organization_name": name, "per_page": 10}
        )
        wanted = name.strip().casefold()
        for acc in body.get("accounts") or []:
            if (acc.get("name") or "").strip().casefold() == wanted:
                return acc
        return None

    async def create_account(self, name: str, *, phone: str | None = None) -> dict:
        payload = {"name": name}
        if phone:
            payload["phone"] = phone
        return (await self._request("POST", "/accounts", json=payload))["account"]

    # ---- contacts ----

    async def find_contact_by_email(self, email: str) -> dict | None:
        body = await self._request(
            "POST", "/contacts/search", json={"q_keywords": email, "per_page": 5}
        )
        wanted = email.strip().lower()
        for c in body.get("contacts") or []:
            if (c.get("email") or "").strip().lower() == wanted:
                return c
        return None

    async def create_contact(self, fields: dict) -> dict:
        payload = {**fields, "run_dedupe": True}
        return (await self._request("POST", "/contacts", json=payload))["contact"]

    async def update_contact(self, contact_id: str, fields: dict) -> dict:
        return (await self._request("PATCH", f"/contacts/{contact_id}", json=fields))["contact"]

    # ---- activity ----

    async def log_call(
        self,
        *,
        call_identifier: str,
        contact_id: str,
        account_id: str | None,
        from_number: str | None,
        to_number: str | None,
        start_time: str | None,
        end_time: str | None,
        duration: int | None,
        note: str,
        user_id: str | None,
    ) -> dict:
        params: list[tuple[str, str]] = [
            ("logged", "true"),
            ("status", "completed"),
            ("call_identifier", call_identifier),
            ("contact_id", contact_id),
            ("note", note),
        ]
        optional = {
            "account_id": account_id,
            "from_number": from_number,
            "to_number": to_number,
            "start_time": start_time,
            "end_time": end_time,
            "duration": None if duration is None else str(duration),
        }
        params += [(k, v) for k, v in optional.items() if v]
        if user_id:
            params.append(("user_id[]", user_id))
        return (await self._request("POST", "/phone_calls", params=params))["phone_call"]

    async def create_deal(
        self,
        *,
        name: str,
        account_id: str,
        owner_id: str | None,
        stage_id: str | None,
    ) -> dict:
        payload = {"name": name, "account_id": account_id}
        if owner_id:
            payload["owner_id"] = owner_id
        if stage_id:
            payload["opportunity_stage_id"] = stage_id
        return (await self._request("POST", "/opportunities", json=payload))["opportunity"]

    async def create_task(
        self,
        *,
        user_id: str,
        contact_id: str,
        due_at: str,
        title: str,
        note: str,
        priority: str = "high",
    ) -> dict:
        payload = {
            "user_id": user_id,
            "contact_id": contact_id,
            "type": "call",
            "priority": priority,
            "status": "scheduled",
            "due_at": due_at,
            "title": title,
            "note": note,
        }
        return (await self._request("POST", "/tasks", json=payload))["task"]
