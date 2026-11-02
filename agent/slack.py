"""Cody's own Slack alert for qualified calls, via an incoming webhook.

Replaces the Slack post the HubSpot workflow used to make.
"""

from __future__ import annotations

import httpx


class SlackError(RuntimeError):
    pass


class SlackNotifier:
    def __init__(self, webhook_url: str, *, client: httpx.AsyncClient | None = None):
        self.webhook_url = webhook_url
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def post(self, text: str) -> None:
        try:
            resp = await self._client.post(self.webhook_url, json={"text": text})
        except httpx.TimeoutException as e:
            raise SlackError("Slack webhook timed out") from e
        if resp.status_code >= 400:
            raise SlackError(f"Slack webhook {resp.status_code}: {resp.text}")


def qualified_call_text(
    *,
    name: str | None,
    organisation: str | None,
    phone: str | None,
    email: str | None,
    score: int,
    outcome: str,
    summary: str | None,
    notion_url: str | None,
    apollo_contact_url: str | None,
) -> str:
    who = name or "Unknown caller"
    if organisation:
        who = f"{who}, {organisation}"
    outcome_text = {
        "discovery_booked": "discovery call booked",
        "qualified_not_booked": "qualified, not booked: please call back",
    }.get(outcome, outcome.replace("_", " "))
    lines = [
        f"*Qualified call:* {who}",
        f"Score {score} · {outcome_text}",
    ]
    contact = " · ".join(x for x in (phone, email) if x)
    if contact:
        lines.append(contact)
    if summary:
        lines.append(f"> {summary}")
    links = " · ".join(
        f"<{u}|{label}>"
        for label, u in (("Notion", notion_url), ("Apollo", apollo_contact_url))
        if u
    )
    if links:
        lines.append(links)
    return "\n".join(lines)
