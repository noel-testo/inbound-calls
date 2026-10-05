"""Thin async HubSpot client (SPEC §9) — CRM only.

One small wrapper over the HubSpot CRM REST API using httpx — not the heavy
`hubspot-api-client` SDK ("the best part is no part"). Contacts, companies, deals and
call engagements on the stable `/crm/v3/objects/...` endpoints.

Discovery-call scheduling is NOT here: it moved to Cal.com (`agent/calcom/`) on
2026-10-05 — there is no HubSpot meeting link. HubSpot remains the system of record
for sales state (SPEC §2).

Every method raises `HubSpotError` on failure; the tool layer (SPEC §7) decides what
fails soft (lookup, message). Returned dicts are compact so the model can speak from
them. Live behaviour is blocked until the HubSpot Service Key is issued.
"""

from __future__ import annotations

import os

import httpx

from .errors import HubSpotError

CRM = "/crm/v3/objects"

# HubSpot-defined association type IDs (category HUBSPOT_DEFINED).
ASSOC_DEAL_TO_CONTACT = 3
ASSOC_DEAL_TO_COMPANY = 5
ASSOC_CALL_TO_CONTACT = 194
ASSOC_CALL_TO_COMPANY = 182
ASSOC_CALL_TO_DEAL = 206


def uk_phone_variants(phone: str) -> list[str]:
    """Return the phone in the forms HubSpot contacts are stored in (SPEC §9).

    HubSpot stores numbers as entered, so a lookup tries compact E.164, UK national,
    and spaced E.164 "+44 XXXX XXXXXX" (existing contacts use the spaced form). Order
    preserved, duplicates removed.
    """
    p = phone.strip().replace(" ", "")
    out = [p]
    nsn = None
    if p.startswith("+44"):
        nsn = p[3:]
        out.append("0" + nsn)
    elif p.startswith("0"):
        nsn = p[1:]
        out.append("+44" + nsn)
    if nsn and len(nsn) >= 5:
        out.append(f"+44 {nsn[:4]} {nsn[4:]}")
    return list(dict.fromkeys(out))


class HubSpotClient:
    def __init__(
        self,
        token: str,
        *,
        owner_id: str | None = None,
        pipeline_id: str | None = None,
        stage_discovery_booked: str | None = None,
        stage_qualified_not_booked: str | None = None,
        base_url: str = "https://api.hubapi.com",
        timeout: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
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
        token = os.environ.get("HUBSPOT_SERVICE_KEY")
        if not token:
            raise HubSpotError(0, "HUBSPOT_SERVICE_KEY is not set")
        return cls(
            token=token,
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

    # ---- contacts ------------------------------------------------------------

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
        """Find a contact by `phone` or `mobilephone`, trying E.164, UK national and
        spaced forms (SPEC §7). Returns the compact shape the lookup tool speaks from, or None."""
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

    # ---- deals and calls -----------------------------------------------------

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
