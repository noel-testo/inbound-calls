"""Cody's own Slack alerts, via an incoming webhook: qualified calls, and calls on a line Noel
wants to see (his direct line). Every alert names the line the call came in on.

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


def _line_suffix(line_label: str | None) -> str:
    return f" ({line_label})" if line_label else ""


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
    line_label: str | None = None,
) -> str:
    who = name or "Unknown caller"
    if organisation:
        who = f"{who}, {organisation}"
    outcome_text = {
        "discovery_booked": "discovery call booked",
        "qualified_not_booked": "qualified, not booked: please call back",
    }.get(outcome, outcome.replace("_", " "))
    lines = [
        f"*Qualified call{_line_suffix(line_label)}:* {who}",
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


def message_call_text(
    *,
    line_label: str,
    name: str | None,
    organisation: str | None,
    callback_number: str | None,
    outcome: str,
    summary: str | None,
    notion_url: str | None,
) -> str:
    """Alert for a call that is not a qualified lead but that Noel should see, such as a message
    taken on his direct line or a transfer that was attempted."""
    who = name or "Unknown caller"
    if organisation:
        who = f"{who}, {organisation}"
    outcome_text = {
        "transferred": "put through to Noel",
        "message_taken": "message taken",
    }.get(outcome, outcome.replace("_", " "))
    lines = [f"*Call on {line_label}:* {who}", outcome_text]
    if callback_number:
        lines.append(f"Call back: {callback_number}")
    if summary:
        lines.append(f"> {summary}")
    if notion_url:
        lines.append(f"<{notion_url}|Notion>")
    return "\n".join(lines)
