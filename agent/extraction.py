"""The §6 qualification schema, extracted post-call by ElevenLabs data collection.

The same field list provisions the agent's `platform_settings.data_collection`
(scripts/provision_elevenlabs.py) and parses `analysis.data_collection_results` in the post-call
webhook, so the two cannot drift. Enum values outside the schema become `unknown`.
"""

from __future__ import annotations

from dataclasses import dataclass

INTENTS = ("new_enquiry", "existing_customer", "supplier_or_sales", "other")


@dataclass(frozen=True)
class Field:
    type: str  # ElevenLabs data-collection type: string | integer | number | boolean
    description: str
    values: tuple[str, ...] = ()
    multi: bool = False


FIELDS: dict[str, Field] = {
    "intent": Field("string", "Why the caller rang.", INTENTS),
    "caller_name": Field("string", "The caller's full name as they gave it, or empty."),
    "organisation": Field("string", "The organisation the caller represents, or empty."),
    "caller_role": Field(
        "string",
        "The caller's role.",
        (
            "facilities_manager",
            "managing_agent",
            "lift_contractor",
            "landlord_owner",
            "consultant",
            "installer",
            "other",
            "unknown",
        ),
    ),
    "asset_type": Field(
        "string",
        "Asset types discussed, comma-separated.",
        ("lifts", "car_parks", "alarm_panels", "other"),
        multi=True,
    ),
    "estate_size": Field(
        "integer", "Number of lifts or sites, whichever the caller gave; 0 if not said."
    ),
    "estate_size_unit": Field("string", "Unit of estate_size.", ("lifts", "sites")),
    "current_connectivity": Field(
        "string",
        "How the assets connect today.",
        ("pstn_copper", "existing_4g", "mixed", "unknown"),
    ),
    "driver": Field(
        "string",
        "What is driving the enquiry.",
        (
            "pstn_switch_off",
            "failures",
            "new_build",
            "contract_renewal",
            "cost",
            "other",
            "unknown",
        ),
    ),
    "timeline": Field(
        "string",
        "When they want to act.",
        ("immediate", "1_3_months", "3_6_months", "6_plus", "unknown"),
    ),
    "decision_authority": Field(
        "string",
        "The caller's part in the decision.",
        ("decision_maker", "influencer", "researcher", "unknown"),
    ),
    "contact_email": Field(
        "string", "The email address the caller confirmed on read-back, or empty."
    ),
    "notes": Field("string", "Anything else material, one short paragraph."),
}


def data_collection_config() -> dict:
    """`platform_settings.data_collection` for the ElevenLabs agent."""
    out = {}
    for key, f in FIELDS.items():
        desc = f.description
        if f.values:
            joiner = "one or more of" if f.multi else "exactly one of"
            desc = f"{desc} Answer with {joiner}: {', '.join(f.values)}."
        out[key] = {"type": f.type, "description": desc}
    return out


def _value(results: dict, key: str):
    item = results.get(key)
    if isinstance(item, dict):
        return item.get("value")
    return item


def _clean_str(v) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())
    return s or None


def parse(results: dict | None) -> dict:
    """Normalise `analysis.data_collection_results` into the §6 extraction dict."""
    results = results or {}
    out: dict = {}
    for key, f in FIELDS.items():
        raw = _value(results, key)
        if f.multi:
            items = [p.strip().lower() for p in str(raw or "").replace(";", ",").split(",")]
            out[key] = [p for p in dict.fromkeys(items) if p in f.values]
        elif f.values:
            v = (_clean_str(raw) or "").lower()
            fallback = (
                "other" if key == "intent" else ("unknown" if "unknown" in f.values else None)
            )
            out[key] = v if v in f.values else fallback
        elif f.type == "integer":
            try:
                n = int(float(raw))
            except (TypeError, ValueError):
                n = 0
            out[key] = max(n, 0) or None
        else:
            out[key] = _clean_str(raw)
    if out.get("contact_email"):
        email = out["contact_email"].replace(" ", "").lower()
        out["contact_email"] = email if "@" in email and "." in email.split("@")[-1] else None
    return out
