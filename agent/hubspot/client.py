"""Thin async HubSpot client (SPEC §9).

One small wrapper over the HubSpot REST API using httpx — not the heavy
`hubspot-api-client` SDK ("the best part is no part"). CRM objects use the stable
`/crm/v3/objects/...` endpoints; the discovery-call booking uses the versioned
Meetings scheduler endpoints `/scheduler/2026-03/meetings/meeting-links/book/...`.

Every method raises `HubSpotError` on failure; the tool layer (SPEC §7) decides
what fails soft (lookup, message) vs. what blocks the call (availability, booking).
Returned dicts are compact so the model can speak from them.

Live behaviour (a real booking landing in Google Calendar with a confirmation
email — the Phase 1 definition of done) is blocked until the expert's meeting-link
slug, owner id, pipeline and private-app token are known. The scheduler
request/response shapes below follow HubSpot's docs and are covered by unit tests
against fixtures; they must be re-checked against the real meeting link in the
live phase (see docs/QUESTIONS.md).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import httpx

from .errors import HubSpotError

CRM = "/crm/v3/objects"
SCHEDULER = "/scheduler/2026-03/meetings/meeting-links"

# HubSpot-defined association type IDs (category HUBSPOT_DEFINED).
ASSOC_DEAL_TO_CONTACT = 3
ASSOC_DEAL_TO_COMPANY = 5
ASSOC_CALL_TO_CONTACT = 194
ASSOC_CALL_TO_COMPANY = 182
ASSOC_CALL_TO_DEAL = 206


def uk_phone_variants(phone: str) -> list[str]:
    """Return the phone in both E.164 and UK national forms (SPEC §9).

    HubSpot stores numbers as entered, so a lookup tries both. Order preserved,
    duplicates removed.
    """
    p = phone.strip().replace(" ", "")
    out = [p]
    if p.startswith("+44"):
        out.append("0" + p[3:])
    elif p.startswith("0"):
        out.append("+44" + p[1:])
    return list(dict.fromkeys(out))


def _iso_to_epoch_ms(iso: str) -> int:
    return int(_parse_iso(iso).timestamp() * 1000)


def _epoch_ms_to_iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


class HubSpotClient:
    def __init__(
        self,
        token: str,
        *,
        meeting_slug: str | None = None,
        owner_id: str | None = None,
        pipeline_id: str | None = None,
        stage_discovery_booked: str | None = None,
        stage_qualified_not_booked: str | None = None,
        base_url: str = "https://api.hubapi.com",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.meeting_slug = meeting_slug
        self.owner_id = owner_id
        self.pipeline_id = pipeline_id
        self.stage_discovery_booked = stage_discovery_booked
        self.stage_qualified_not_booked = stage_qualified_not_booked
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    @classmethod
    def from_env(cls, **overrides) -> HubSpotClient:
        """Build from the HUBSPOT_* variables in the environment (SPEC §9)."""
        token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
        if not token:
            raise HubSpotError(0, "HUBSPOT_PRIVATE_APP_TOKEN is not set")
        return cls(
            token=token,
            meeting_slug=os.environ.get("HUBSPOT_MEETING_LINK_SLUG"),
            owner_id=os.environ.get("HUBSPOT_EXPERT_OWNER_ID"),
            pipeline_id=os.environ.get("HUBSPOT_DEAL_PIPELINE_ID"),
            stage_discovery_booked=os.environ.get("HUBSPOT_STAGE_DISCOVERY_BOOKED"),
            stage_qualified_not_booked=os.environ.get("HUBSPOT_STAGE_QUALIFIED_NOT_BOOKED"),
            **overrides,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HubSpotClient:
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, *, timeout: float | None = None, **kw) -> dict:
        try:
            resp = await self._client.request(method, path, timeout=timeout, **kw)
        except httpx.TimeoutException as e:
            raise HubSpotError(0, f"request to {path} timed out") from e
        if resp.status_code >= 400:
            body: dict = {}
            try:
                body = resp.json()
            except ValueError:
                pass
            raise HubSpotError(
                resp.status_code,
                body.get("message") or resp.text or "request failed",
                correlation_id=body.get("correlationId"),
            )
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    # ---- CRM: contacts -------------------------------------------------------

    async def _search_one(
        self, object_type: str, prop: str, value: str, properties: list[str]
    ) -> dict | None:
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": prop, "operator": "EQ", "value": value}]}
            ],
            "properties": properties,
            "limit": 1,
        }
        data = await self._request("POST", f"{CRM}/{object_type}/search", json=payload)
        results = data.get("results") or []
        return results[0] if results else None

    async def search_contact_by_phone(
        self, phone_e164: str, *, timeout: float | None = None
    ) -> dict | None:
        """Find a contact by `phone` or `mobilephone`, trying E.164 and UK national
        forms (SPEC §7). Returns the compact shape the lookup tool speaks from, or None."""
        variants = uk_phone_variants(phone_e164)
        filter_groups = [
            {"filters": [{"propertyName": prop, "operator": "EQ", "value": v}]}
            for prop in ("phone", "mobilephone")
            for v in variants
        ]
        payload = {
            "filterGroups": filter_groups,
            "properties": ["firstname", "company", "lifecyclestage", "cf_ai_call_summary"],
            "limit": 1,
        }
        data = await self._request("POST", f"{CRM}/contacts/search", json=payload, timeout=timeout)
        results = data.get("results") or []
        if not results:
            return None
        c = results[0]
        props = c.get("properties", {})
        contact_id = c["id"]
        return {
            "found": True,
            "contact_id": contact_id,
            "first_name": props.get("firstname"),
            "company": props.get("company"),
            "lifecycle_stage": props.get("lifecyclestage"),
            "open_deal_count": await self._open_deal_count(contact_id, timeout=timeout),
            "last_summary": props.get("cf_ai_call_summary"),
        }

    async def _open_deal_count(self, contact_id: str, *, timeout: float | None = None) -> int:
        data = await self._request(
            "GET", f"{CRM}/contacts/{contact_id}/associations/deals", timeout=timeout
        )
        return len(data.get("results") or [])

    async def upsert_contact(
        self, properties: dict, *, email: str | None = None, phone: str | None = None
    ) -> dict:
        """Create or update a contact, matched by email then phone (SPEC §11)."""
        existing_id: str | None = None
        if email:
            found = await self._search_one("contacts", "email", email, ["email"])
            existing_id = found["id"] if found else None
        if not existing_id and phone:
            for v in uk_phone_variants(phone):
                found = await self._search_one("contacts", "phone", v, ["phone"])
                if found:
                    existing_id = found["id"]
                    break
        if existing_id:
            data = await self._request(
                "PATCH", f"{CRM}/contacts/{existing_id}", json={"properties": properties}
            )
        else:
            data = await self._request("POST", f"{CRM}/contacts", json={"properties": properties})
        return {"contact_id": data["id"], "created": existing_id is None}

    async def upsert_company(self, name: str, properties: dict | None = None) -> dict:
        """Create or update a company matched by name (SPEC §11)."""
        props = {"name": name, **(properties or {})}
        found = await self._search_one("companies", "name", name, ["name"])
        if found:
            data = await self._request(
                "PATCH", f"{CRM}/companies/{found['id']}", json={"properties": props}
            )
            return {"company_id": data["id"], "created": False}
        data = await self._request("POST", f"{CRM}/companies", json={"properties": props})
        return {"company_id": data["id"], "created": True}

    # ---- CRM: deals and calls ------------------------------------------------

    @staticmethod
    def _assoc(to_id: str, type_id: int) -> dict:
        return {
            "to": {"id": to_id},
            "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": type_id}],
        }

    async def create_deal(
        self, properties: dict, *, contact_id: str | None = None, company_id: str | None = None
    ) -> dict:
        """Create a deal, associated to a contact and/or company (SPEC §11 step 5)."""
        associations = []
        if contact_id:
            associations.append(self._assoc(contact_id, ASSOC_DEAL_TO_CONTACT))
        if company_id:
            associations.append(self._assoc(company_id, ASSOC_DEAL_TO_COMPANY))
        body = {"properties": properties, "associations": associations}
        data = await self._request("POST", f"{CRM}/deals", json=body)
        return {"deal_id": data["id"]}

    async def create_call(
        self,
        properties: dict,
        *,
        contact_id: str | None = None,
        company_id: str | None = None,
        deal_id: str | None = None,
    ) -> dict:
        """Create a call engagement with the §9 properties, associated where present."""
        associations = []
        if contact_id:
            associations.append(self._assoc(contact_id, ASSOC_CALL_TO_CONTACT))
        if company_id:
            associations.append(self._assoc(company_id, ASSOC_CALL_TO_COMPANY))
        if deal_id:
            associations.append(self._assoc(deal_id, ASSOC_CALL_TO_DEAL))
        body = {"properties": properties, "associations": associations}
        data = await self._request("POST", f"{CRM}/calls", json=body)
        return {"call_id": data["id"]}

    # ---- Meetings scheduler --------------------------------------------------

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
        [from_iso, to_iso] for the expert's meeting link (SPEC §7).

        Blocking tool: keep the timeout tight. Requires `meeting_slug`.
        """
        if not self.meeting_slug:
            raise HubSpotError(0, "meeting_slug is not configured")
        data = await self._request(
            "GET",
            f"{SCHEDULER}/book/{self.meeting_slug}",
            params={"timezone": timezone_name},
            timeout=timeout,
        )
        start = _parse_iso(from_iso)
        end = _parse_iso(to_iso)
        slots: list[str] = []
        for ms in _iter_slot_millis(data):
            dt = datetime.fromtimestamp(ms / 1000, tz=UTC)
            if start <= dt <= end:
                slots.append(_epoch_ms_to_iso(ms))
            if len(slots) >= limit:
                break
        return {"slots": slots}

    async def book_meeting(
        self,
        slot_iso: str,
        first_name: str,
        last_name: str,
        email: str,
        *,
        phone: str | None = None,
        organisation: str | None = None,
        notes: str | None = None,
        duration_ms: int = 30 * 60 * 1000,
        timezone_name: str = "Europe/London",
        timeout: float | None = None,
    ) -> dict:
        """Book `slot_iso` on the expert's meeting link (SPEC §7). HubSpot sends the
        confirmation email and calendar invite. Returns the start time for read-back.

        `formFields` names depend on the meeting link's form configuration and must
        be confirmed against the real link in the live phase.
        """
        if not self.meeting_slug:
            raise HubSpotError(0, "meeting_slug is not configured")
        form_fields = [
            {"name": "email", "value": email},
            {"name": "firstName", "value": first_name},
            {"name": "lastName", "value": last_name},
        ]
        if phone:
            form_fields.append({"name": "phone", "value": phone})
        if organisation:
            form_fields.append({"name": "company", "value": organisation})
        body = {
            "slug": self.meeting_slug,
            "duration": duration_ms,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "startTime": _iso_to_epoch_ms(slot_iso),
            "timezone": timezone_name,
            "formFields": form_fields,
            "likelyAvailableUserIds": [],
        }
        if notes:
            body["formFields"].append({"name": "notes", "value": notes})
        data = await self._request(
            "POST",
            f"{SCHEDULER}/book",
            params={"timezone": timezone_name},
            json=body,
            timeout=timeout,
        )
        return {
            "meeting_id": data.get("id") or data.get("bookId") or data.get("engagementId"),
            "start_iso": slot_iso,
            "confirmation_sent": True,
        }


def _iter_slot_millis(data: dict):
    """Yield slot start times (epoch ms) from a meeting-link availability payload.

    Walks the documented linkAvailability.linkAvailabilityByDuration[*].availabilities[*]
    shape, falling back to any nested startMillisUtc / startTime keys so a minor
    response-shape change doesn't silently return nothing.
    """
    link = data.get("linkAvailability") or {}
    by_duration = link.get("linkAvailabilityByDuration") or {}
    seen_structured = False
    for bucket in by_duration.values():
        for slot in bucket.get("availabilities", []) if isinstance(bucket, dict) else []:
            ms = slot.get("startMillisUtc") or slot.get("startTime")
            if ms is not None:
                seen_structured = True
                yield int(ms)
    if seen_structured:
        return

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("startMillisUtc", "startTime") and isinstance(v, (int, float, str)):
                    try:
                        yield int(v)
                    except (TypeError, ValueError):
                        pass
                else:
                    yield from walk(v)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    yield from walk(data)
