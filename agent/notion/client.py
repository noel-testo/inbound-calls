"""Thin async Notion client (API version 2022-06-28, database-id parents).

Rows are found by their "Conversation ID" property so a re-delivered webhook updates the same page;
the page id is also kept in Neon. Rich text is capped at Notion's 2,000 characters per text object,
and page bodies are appended in batches of 100 blocks (Notion's per-request limit).
"""

from __future__ import annotations

import httpx

BASE_URL = "https://api.notion.com"
NOTION_VERSION = "2022-06-28"
TEXT_LIMIT = 2000
BLOCK_BATCH = 100


class NotionError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Notion API {status}: {message}")
        self.status = status


# ---- property value builders ----


def title(text: str) -> dict:
    return {"title": [{"text": {"content": text[:TEXT_LIMIT]}}]}


def rich(text: str | None) -> dict:
    return {"rich_text": [{"text": {"content": text[:TEXT_LIMIT]}}] if text else []}


def select(name: str | None) -> dict:
    return {"select": {"name": name} if name else None}


def multi(names: list[str] | None) -> dict:
    return {"multi_select": [{"name": n} for n in names or []]}


def number(n) -> dict:
    return {"number": n}


def checkbox(b: bool) -> dict:
    return {"checkbox": bool(b)}


def date(iso: str | None) -> dict:
    return {"date": {"start": iso} if iso else None}


def url(u: str | None) -> dict:
    return {"url": u or None}


def email(e: str | None) -> dict:
    return {"email": e or None}


def phone(p: str | None) -> dict:
    return {"phone_number": p or None}


def paragraph(text: str) -> dict:
    chunks = [text[i : i + TEXT_LIMIT] for i in range(0, len(text), TEXT_LIMIT)] or [""]
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": c}} for c in chunks]},
    }


class NotionClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ):
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }
        self._client = client or httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kw) -> dict:
        try:
            resp = await self._client.request(method, path, headers=self._headers, **kw)
        except httpx.TimeoutException as e:
            raise NotionError(0, f"request to {path} timed out") from e
        if resp.status_code >= 400:
            try:
                message = resp.json().get("message") or resp.text
            except ValueError:
                message = resp.text
            raise NotionError(resp.status_code, message)
        return resp.json() if resp.content else {}

    async def get_database(self, database_id: str) -> dict:
        return await self._request("GET", f"/v1/databases/{database_id}")

    async def update_database(self, database_id: str, properties: dict) -> dict:
        return await self._request(
            "PATCH", f"/v1/databases/{database_id}", json={"properties": properties}
        )

    async def find_by_conversation(self, database_id: str, conversation_id: str) -> str | None:
        body = await self._request(
            "POST",
            f"/v1/databases/{database_id}/query",
            json={
                "filter": {"property": "Conversation ID", "rich_text": {"equals": conversation_id}},
                "page_size": 1,
            },
        )
        results = body.get("results") or []
        return results[0]["id"] if results else None

    async def create_page(
        self, database_id: str, properties: dict, children: list[dict] | None = None
    ) -> dict:
        children = children or []
        page = await self._request(
            "POST",
            "/v1/pages",
            json={
                "parent": {"database_id": database_id},
                "properties": properties,
                "children": children[:BLOCK_BATCH],
            },
        )
        for i in range(BLOCK_BATCH, len(children), BLOCK_BATCH):
            await self._request(
                "PATCH",
                f"/v1/blocks/{page['id']}/children",
                json={"children": children[i : i + BLOCK_BATCH]},
            )
        return page

    async def update_page(self, page_id: str, properties: dict) -> dict:
        return await self._request("PATCH", f"/v1/pages/{page_id}", json={"properties": properties})
