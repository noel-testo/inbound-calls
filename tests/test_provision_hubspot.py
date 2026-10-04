"""Unit tests for the HubSpot provisioning specs (no network).

Validates the 12 cf_ property definitions against SPEC §9/§6 before they're ever
sent to HubSpot.
"""

from __future__ import annotations

from scripts.provision_hubspot import GROUP_NAME, PROPERTIES, humanize

EXPECTED_NAMES = {
    "cf_caller_role",
    "cf_asset_type",
    "cf_estate_size",
    "cf_estate_size_unit",
    "cf_current_connectivity",
    "cf_driver",
    "cf_timeline",
    "cf_decision_authority",
    "cf_lead_score",
    "cf_high_value",
    "cf_last_ai_call_id",
    "cf_ai_call_summary",
}


def test_twelve_properties_match_spec():
    names = [p["name"] for p in PROPERTIES]
    assert len(names) == 12
    assert len(set(names)) == 12
    assert set(names) == EXPECTED_NAMES


def test_all_properties_in_group():
    assert all(p["groupName"] == GROUP_NAME for p in PROPERTIES)


def test_enum_properties_have_unique_options():
    for p in PROPERTIES:
        if p["type"] == "enumeration":
            values = [o["value"] for o in p["options"]]
            assert values, p["name"]
            assert len(values) == len(set(values)), p["name"]


def test_specific_types_and_options():
    by = {p["name"]: p for p in PROPERTIES}
    assert by["cf_estate_size"]["type"] == "number"
    assert by["cf_lead_score"]["type"] == "number"
    assert by["cf_high_value"]["type"] == "bool"
    assert by["cf_ai_call_summary"]["fieldType"] == "textarea"
    assert by["cf_asset_type"]["fieldType"] == "checkbox"  # multi-enum
    assert [o["value"] for o in by["cf_caller_role"]["options"]] == [
        "facilities_manager",
        "managing_agent",
        "lift_contractor",
        "landlord_owner",
        "consultant",
        "installer",
        "other",
        "unknown",
    ]


def test_humanize():
    assert humanize("1_3_months") == "1–3 months"
    assert humanize("pstn_copper") == "PSTN copper"
    assert humanize("existing_4g") == "Existing 4G"
    assert humanize("decision_maker") == "Decision maker"
