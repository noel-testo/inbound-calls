"""Scoring, data-collection parsing, webhook signatures and phone normalisation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agent import extraction
from agent.phone import is_mobile, to_e164
from agent.scoring import is_qualified, score
from agent.security import SignatureError, secret_ok, sign, verify_signature
from tests.fakes import QUALIFIED, dc

SCORING = yaml.safe_load((Path(__file__).parents[1] / "config" / "scoring.yaml").read_text())


def test_score_against_shipped_config():
    x = extraction.parse(QUALIFIED)
    # managing_agent 30 + lifts 15 + 40 lifts (band ≥10) 20 + copper 20 + switch-off 15
    # + 1–3 months 10 + decision maker 10
    assert score(x, SCORING) == 120
    assert is_qualified(x, SCORING) == (120, True)


def test_threshold_and_intent_gate():
    low = extraction.parse(dc(intent="new_enquiry", caller_role="installer"))
    assert is_qualified(low, SCORING) == (15, False)
    customer = extraction.parse({**QUALIFIED, **dc(intent="existing_customer")})
    assert is_qualified(customer, SCORING)[1] is False


def test_asset_types_count_each_and_bands_take_first_match():
    x = {"asset_type": ["lifts", "car_parks"], "estate_size": 3}
    assert score(x, SCORING) == 15 + 10 + 10
    assert score({"estate_size": None}, SCORING) == 0


def test_parse_normalises_values():
    x = extraction.parse(
        dc(
            intent="New_Enquiry",
            caller_role="astronaut",
            asset_type="lifts; car_parks, lifts, boats",
            estate_size="12",
            contact_email=" Jane @Acme.example ",
            caller_name="  Jane   Smith ",
        )
    )
    assert x["intent"] == "new_enquiry"
    assert x["caller_role"] == "unknown"
    assert x["asset_type"] == ["lifts", "car_parks"]
    assert x["estate_size"] == 12
    assert x["contact_email"] == "jane@acme.example"
    assert x["caller_name"] == "Jane Smith"
    assert extraction.parse(None)["intent"] == "other"
    assert extraction.parse(dc(contact_email="not an email"))["contact_email"] is None


def test_data_collection_config_covers_every_field():
    cfg = extraction.data_collection_config()
    assert set(cfg) == set(extraction.FIELDS)
    assert "managing_agent" in cfg["caller_role"]["description"]
    assert cfg["estate_size"]["type"] == "integer"


def test_signature_round_trip_and_failures():
    body = b'{"type":"post_call_transcription"}'
    header = sign(body, "s3cret", 1_000_000)
    verify_signature(body, header, "s3cret", now=1_000_100)
    for bad_header, secret, now in [
        (header, "other", 1_000_100),
        (header, "s3cret", 1_000_000 + 31 * 60),
        ("garbage", "s3cret", 1_000_100),
        (None, "s3cret", 1_000_100),
        (header, None, 1_000_100),
    ]:
        with pytest.raises(SignatureError):
            verify_signature(body, bad_header, secret, now=now)
    with pytest.raises(SignatureError):
        verify_signature(body + b" ", header, "s3cret", now=1_000_100)


def test_secret_ok():
    assert secret_ok("a", "a")
    assert not secret_ok("a", "b") and not secret_ok(None, "a") and not secret_ok("a", None)


def test_phone_normalisation():
    assert to_e164("+44 20 4520 0783") == "+442045200783"
    assert to_e164("020 4520 0783") == "+442045200783"
    assert to_e164("anonymous") is None and to_e164(None) is None and to_e164("12") is None
    assert is_mobile("+447400123456") and not is_mobile("+442045200783")
