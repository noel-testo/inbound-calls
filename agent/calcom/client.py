"""Thin async Cal.com client (SPEC §7 scheduling).

The discovery-call booking runs on Cal.com, not HubSpot Meetings (decision 2026-10-05).
Two endpoints, each pinned to the cal-api-version that serves it:

  GET  /v2/slots      availability   cal-api-version 2024-09-04
  POST /v2/bookings   create booking cal-api-version 2024-08-13 (confirm in the live
                                     DoD booking test; see docs/DECISIONS.md)

Event type 7103844 ("LiftPulse Trial", 15 min, auto-confirmed). Its booking fields,
confirmed live via GET /v2/event-types/7103844: attendee name/email/phone are system
fields; custom slugs are `Company` (text, required), `title` (text, required, hidden),
and `notes` (textarea, optional). A custom User-Agent is set because Cal.com's
Cloudflare returns 1010 to the default Python client signature.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

from .errors import CalComError

SLOTS_VERSION = "2024-09-04"
BOOKINGS_VERSION = "2024-08-13"
USER_AGENT = "ControlFreqReceptionist/1.0"


def _parse(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _to_utc_z(iso: str) -> str:
    return _parse(iso).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class CalComClient:
    def __init__(
        self,
        api_key: str,
        event_type_id: int,
        *,
        base_url: str = "https://api.cal.com",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.event_type_id = event_type_id
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

    @classmethod
    def from_env(cls, **overrides) -> CalComClient:
        api_key = os.environ.get("CALCOM_API_KEY")
        if not api_key:
            raise CalComError(0, "CALCOM_API_KEY is not set")
        etid = os.environ.get("CALCOM_EVENT_TYPE_ID")
        if not etid:
            raise CalComError(0, "CALCOM_EVENT_TYPE_ID is not set")
        return cls(api_key=api_key, event_type_id=int(etid), **overrides)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> CalComClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def _request(
        self, method: str, path: str, version: str, *, timeout: float | None = None, **kw
    ) -> dict:
        eff_timeout = httpx.USE_CLIENT_DEFAULT if timeout is None else timeout
        try:
            resp = await self._client.request(
                method, path, headers={"cal-api-version": version}, timeout=eff_timeout, **kw
            )
        except httpx.TimeoutException as e:
            raise CalComError(0, f"request to {path} timed out") from e
        if resp.status_code >= 400:
            message = resp.text or "request failed"
            try:
                body = resp.json()
                message = (body.get("error") or {}).get("message") or body.get("message") or message
            except ValueError:
                pass
            raise CalComError(resp.status_code, message)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    async def get_availability(
        self,
        from_iso: str,
        to_iso: str,
        *,
        timezone_name: str = "Europe/London",
        limit: int = 6,
        timeout: float | None = None,
    ) -> dict:
        """Return up to `limit` available slot start times (ISO 8601 UTC) within
        [from_iso, to_iso] for the event type (SPEC §7). Blocking tool — tight timeout."""
        params = {
            "eventTypeId": self.event_type_id,
            "start": from_iso,
            "end": to_iso,
            "timeZone": timezone_name,
        }
        body = await self._request(
            "GET", "/v2/slots", SLOTS_VERSION, params=params, timeout=timeout
        )
        by_date = body.get("data") or {}
        start, end = _parse(from_iso), _parse(to_iso)
        slots: list[str] = []
        for date in sorted(by_date):
            for slot in by_date[date]:
                s = slot.get("start")
                if not s:
                    continue
                if start <= _parse(s) <= end:
                    slots.append(_to_utc_z(s))
                if len(slots) >= limit:
                    return {"slots": slots}
        return {"slots": slots}

    async def book_meeting(
        self,
        start_iso: str,
        name: str,
        email: str,
        organisation: str,
        *,
        phone: str | None = None,
        notes: str | None = None,
        title: str | None = None,
        timezone_name: str = "Europe/London",
        timeout: float | None = None,
    ) -> dict:
        """Book `start_iso` on the event type (SPEC §7). Cal.com sends the calendar
        invite and confirmation email. Returns the start time for read-back.

        `organisation` is required (the `Company` booking field is required); `title`
        (required, hidden) defaults to "Intro call – <organisation>"; `notes` carries
        the qualification summary.
        """
        start_utc = _to_utc_z(start_iso)
        attendee = {"name": name, "email": email, "timeZone": timezone_name, "language": "en"}
        if phone:
            attendee["phoneNumber"] = phone
        responses = {
            "Company": organisation,
            "title": title or f"Intro call – {organisation}",
        }
        if notes:
            responses["notes"] = notes
        payload = {
            "eventTypeId": self.event_type_id,
            "start": start_utc,
            "attendee": attendee,
            "bookingFieldsResponses": responses,
        }
        body = await self._request(
            "POST", "/v2/bookings", BOOKINGS_VERSION, json=payload, timeout=timeout
        )
        data = body.get("data", body)
        return {
            "booking_id": data.get("uid") or data.get("id"),
            "start_iso": start_utc,
            "status": data.get("status"),
        }
