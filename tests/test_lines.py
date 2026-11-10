"""Line map: matching, per-line greeting and prompt, the /lines/resolve endpoint, line-tagged
bookings, and the transfer tool provisioning (issue #13)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent import extraction, lines, slack
from agent.app import create_app
from agent.lines import LineConfigError, load_line_map, parse_line_map
from agent.notion.schema import LEADS, TRANSCRIPTS
from agent.settings import Settings
from tests.test_app import FakeCalCom

ROOT = Path(__file__).parents[1]
H = {"X-Cody-Secret": "tool-secret"}
MOBILE = "+447700900123"  # Ofcom drama range; not Noel's number

LINE_MAP = load_line_map()
GREETING = lines.load_greeting()
SECTIONS = lines.load_prompt_sections()


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("called", "caller", "expected"),
    [
        ("+442045200783", "02081584403", "noel-direct"),
        ("+442045200783", "+442081584403", "noel-direct"),
        ("+442045200783", "020 8158 4403", "noel-direct"),
        ("+442045208242", "+447400123456", "parking"),
        ("+442045208242", "02081584403", "parking"),
        ("+442045208242", None, "parking"),
        ("+442045200783", "+447400123456", "general"),
        ("+442045200783", "anonymous", "general"),
        ("+442045200783", None, "general"),
        ("+443301900784", "02081584403", "general"),
        (None, None, "general"),
    ],
)
def test_resolve(called, caller, expected):
    assert LINE_MAP.resolve(called, caller).key == expected


def test_rc_placeholder_lines_never_match_until_numbers_are_added():
    for key in ("sales", "accounts", "support"):
        line = LINE_MAP.by_key[key]
        assert line.pending and not line.caller_ids
        assert not line.matches("+442045200783", "+442081584403")
        assert not line.matches("+442045200783", None)
    assert not LINE_MAP.by_key["general"].has_matchers


def test_filling_in_an_rc_number_routes_that_line():
    data = yaml.safe_load((ROOT / "config" / "lines.yaml").read_text())
    for entry in data["lines"]:
        if entry["key"] == "sales":
            entry["match"]["caller_ids"] = ["+442081110000"]
    line_map = parse_line_map(data)
    assert line_map.resolve("+442045200783", "02081110000").key == "sales"
    assert line_map.resolve("+442045200783", "02081584403").key == "noel-direct"
    assert line_map.resolve("+442045200783", "+447400123456").key == "general"


def test_config_errors_are_loud():
    with pytest.raises(LineConfigError):
        parse_line_map({"default": "nope", "lines": [{"key": "a", "label": "A"}]})
    with pytest.raises(LineConfigError):
        parse_line_map(
            {"lines": [{"key": "general", "label": "A"}, {"key": "general", "label": "B"}]}
        )
    with pytest.raises(LineConfigError):
        parse_line_map(
            {"lines": [{"key": "general", "label": "G", "match": {"caller_ids": ["12"]}}]}
        )
    with pytest.raises(LineConfigError):
        parse_line_map({"lines": [{"key": "general", "label": "G", "screen_and_transfer": True}]})


def test_line_flags_and_called_numbers():
    noel = LINE_MAP.by_key["noel-direct"]
    assert noel.screen_and_transfer and not noel.caller_id_is_caller
    assert noel.transfer.destination_env == "NOEL_MOBILE_E164"
    assert [ln.key for ln in LINE_MAP.lines if ln.screen_and_transfer] == ["noel-direct"]
    assert LINE_MAP.by_key["parking"].caller_id_is_caller
    assert LINE_MAP.called_numbers == ("+442045200783", "+442045208242")


def test_every_line_has_a_prompt_section_and_a_greeting_with_the_disclosures():
    for line in LINE_MAP.lines:
        assert SECTIONS.get(line.key), line.key
        spoken = lines.first_message(line, GREETING)
        assert "Calls may be transcribed for quality and training purposes." in spoken
        assert "I'm Cody, an AI assistant" in spoken
        assert "TODO" not in spoken and "\n" not in spoken
    assert set(GREETING["line_greetings"]) <= set(LINE_MAP.keys)
    assert lines.first_message(LINE_MAP.default, GREETING) == " ".join(GREETING["greeting"].split())


def test_prompt_sections_hold_no_comments_or_unfilled_wording():
    for key, text in SECTIONS.items():
        assert "<!--" not in text and "PLACEHOLDER" not in text, key
        filled = lines.instructions(LINE_MAP.by_key[key], SECTIONS, GREETING)
        assert "{{expert_name}}" not in filled and "{{deflections." not in filled
    parking = lines.instructions(LINE_MAP.by_key["parking"], SECTIONS, GREETING)
    assert "Noel Sesto, our Technical Director" in parking
    noel = " ".join(SECTIONS["noel-direct"].split())
    assert "transfer_to_number" in noel and "call-back number" in noel
    assert "Noel doesn't take unsolicited sales calls." in noel
    assert "When in doubt, transfer." in noel
    assert "do not take a message" in noel and "do not ask for a call-back number" in noel
    for key in ("general", "sales", "accounts", "support", "parking"):
        assert "transfer_to_number" not in SECTIONS[key].replace("Do not transfer", "")


def test_dynamic_variables_blank_the_cli_on_rc_lines():
    by_key = LINE_MAP.by_key
    noel = lines.dynamic_variables(by_key["noel-direct"], GREETING, SECTIONS, "02081584403")
    assert noel["caller_phone"] == "" and noel["caller_id_is_caller"] == "false"
    assert noel["line_key"] == "noel-direct"
    parking = lines.dynamic_variables(by_key["parking"], GREETING, SECTIONS, "07400 123456")
    assert parking["caller_phone"] == "+447400123456"
    assert parking["caller_id_is_caller"] == "true"
    assert all(isinstance(v, str) for v in {**noel, **parking}.values())


def make_client(**kw):
    calcom = FakeCalCom()
    app = create_app(Settings(tool_secret="tool-secret"), calcom=calcom, **kw)
    return TestClient(app), calcom


def test_resolve_endpoint_noel_direct_parking_and_generic():
    client, _ = make_client()
    with client:
        assert client.post("/lines/resolve", json={}).status_code == 401
        noel = client.post(
            "/lines/resolve",
            headers=H,
            json={"called_number": "+442045200783", "caller_id": "02081584403"},
        ).json()
        parking = client.post(
            "/lines/resolve",
            headers=H,
            json={"called_number": "+442045208242", "caller_id": "+447400123456"},
        ).json()
        other = client.post(
            "/lines/resolve",
            headers=H,
            json={"called_number": "+442045200783", "caller_id": "+447400123456"},
        ).json()
    assert noel["line_tag"] == "noel-direct" and noel["screen_and_transfer"] is True
    assert noel["lookup_caller"] is False
    assert noel["first_message"].startswith("Thanks for calling Noel Sesto at ControlFreq.")
    assert parking["line_tag"] == "parking" and parking["lookup_caller"] is True
    assert parking["dynamic_variables"]["caller_phone"] == "+447400123456"
    assert "car park" in parking["first_message"]
    assert other["line_tag"] == "general" and other["screen_and_transfer"] is False
    assert other["first_message"] == " ".join(GREETING["greeting"].split())
    assert other["dynamic_variables"]["caller_phone"] == "+447400123456"


BOOKING = {
    "conversation_id": "conv_1",
    "slot_iso": "2026-11-03T09:00:00Z",
    "name": "Jane Smith",
    "email": "jane@acme.example",
    "organisation": "Acme",
    "caller_phone": "02081584403",
}


def book(body):
    client, calcom = make_client()
    with client:
        client.post("/tools/book_meeting", headers=H, json=body)
    return calcom.booked[0][4]


def test_parking_bookings_get_the_prefix_and_metadata():
    kw = book({**BOOKING, "line": "parking", "caller_phone": "07400 123456"})
    assert kw["title"] == "[Parking] Discovery call with Noel Sesto, Technical Director – Acme"
    assert kw["metadata"] == {"line": "parking"}
    assert kw["phone"] == "+447400123456"


def test_rc_line_booking_never_uses_the_cli_as_the_phone():
    kw = book({**BOOKING, "line": "noel-direct"})
    assert kw["phone"] is None
    assert kw["metadata"] == {"line": "noel-direct"} and kw["title"].startswith("Discovery call")
    kw = book({**BOOKING, "line": "noel-direct", "phone": "07700 900123"})
    assert kw["phone"] == MOBILE


def test_booking_without_a_line_is_unchanged():
    kw = book(BOOKING)
    assert "title" not in kw and "metadata" not in kw and kw["phone"] == "+442081584403"
    kw = book({**BOOKING, "line": "no-such-line"})
    assert kw["metadata"] == {"line": "general"} and kw["title"].startswith("Discovery call")


def test_notion_schema_has_a_line_select_for_every_line():
    for schema in (LEADS, TRANSCRIPTS):
        names = [o["name"] for o in schema["Line"]["select"]["options"]]
        assert names == list(LINE_MAP.keys)
    outcomes = [o["name"] for o in LEADS["Outcome"]["select"]["options"]]
    assert "Callback number" in LEADS
    assert "transferred" in outcomes and "cold_call_declined" in outcomes


def test_callback_number_extraction():
    assert "callback_number" in extraction.data_collection_config()
    got = extraction.parse({"callback_number": {"value": "07700 900123"}})
    assert got["callback_number"] == MOBILE
    assert extraction.parse({"callback_number": "ext 5"})["callback_number"] == "ext 5"
    assert extraction.parse({})["callback_number"] is None
    assert extraction.parse({})["cold_call_declined"] is False
    assert extraction.parse({"cold_call_declined": {"value": True}})["cold_call_declined"] is True
    assert extraction.parse({"cold_call_declined": "no"})["cold_call_declined"] is False
    assert extraction.data_collection_config()["cold_call_declined"]["type"] == "boolean"


def test_slack_texts_name_the_line():
    qualified = slack.qualified_call_text(
        name="Jane",
        organisation="Acme",
        phone=None,
        email=None,
        score=70,
        outcome="discovery_booked",
        summary=None,
        notion_url=None,
        apollo_contact_url=None,
        line_label="Parking line",
    )
    assert qualified.startswith("*Qualified call (Parking line):* Jane, Acme")
    plain = slack.qualified_call_text(
        name="Jane",
        organisation=None,
        phone=None,
        email=None,
        score=70,
        outcome="x",
        summary=None,
        notion_url=None,
        apollo_contact_url=None,
    )
    assert plain.startswith("*Qualified call:* Jane")
    msg = slack.message_call_text(
        line_label="Noel direct line",
        name="Sam",
        organisation="Lifts Ltd",
        callback_number=MOBILE,
        outcome="message_taken",
        summary="Wants a call about a quote",
        notion_url="https://notion.example/p",
    )
    assert msg.splitlines()[0] == "*Call on Noel direct line:* Sam, Lifts Ltd"
    assert f"Call back: {MOBILE}" in msg and "message taken" in msg
    declined = slack.cold_call_declined_text(
        name="Sam", organisation="Leads Co", summary="SEO pitch"
    )
    assert declined == "Cold call declined (Noel direct line): Sam, Leads Co — SEO pitch."
    assert "\n" not in declined and "Call back" not in declined
    assert slack.cold_call_declined_text(name=None, organisation=None) == (
        "Cold call declined (Noel direct line): Unknown caller."
    )


def test_transfer_tool_is_built_from_the_line_config_and_env_number():
    el = load_script("provision_elevenlabs")
    body = el._phase3_settings(MOBILE)
    tool = body["conversation_config"]["agent"]["prompt"]["built_in_tools"]["transfer_to_number"]
    transfer = tool["params"]["transfers"][0]
    assert transfer["transfer_destination"] == {"type": "phone", "phone_number": MOBILE}
    assert transfer["transfer_type"] == "conference"
    assert "Never for a cold sales call, and never on any other line." in transfer["condition"]
    assert "prompt" not in el._phase3_settings()["conversation_config"]["agent"]
    synced = el._phase3_settings(None, sync_prompt=True)["conversation_config"]["agent"]["prompt"]
    assert "built_in_tools" not in synced and "{{line_instructions}}" in synced["prompt"]


def test_new_agent_body_keeps_prompt_and_adds_the_tool():
    el = load_script("provision_elevenlabs")
    agent = el._agent_body(MOBILE)["conversation_config"]["agent"]
    assert "{{line_instructions}}" in agent["prompt"]["prompt"]
    assert "transfer_to_number" in agent["prompt"]["built_in_tools"]
    assert "built_in_tools" not in el._agent_body()["conversation_config"]["agent"]["prompt"]


def test_line_placeholders_and_dids():
    el = load_script("provision_elevenlabs")
    ph = el.DYNAMIC_VARIABLES
    assert ph["line_key"] == "general" and ph["caller_id_is_caller"] == "true"
    assert {"line_label", "line_instructions"} <= set(ph)
    assert el._dids("+442045200783") == ["+442045200783", "+442045208242"]
    assert load_script("provision_telnyx")._dids("+442045200783") == el._dids("+442045200783")


def test_dry_run_never_prints_noel_s_number(monkeypatch, capsys):
    el = load_script("provision_elevenlabs")
    monkeypatch.setenv("NOEL_MOBILE_E164", MOBILE)
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "agent_x")
    monkeypatch.setattr("sys.argv", ["provision_elevenlabs.py", "--dry-run"])
    import asyncio

    assert asyncio.run(el.main()) == 0
    out = capsys.readouterr().out
    assert MOBILE not in out and "07700900123" not in out
    assert el.REDACTED_DESTINATION in out and "--sync-prompt is not set" in out


def test_noel_mobile_env_is_validated():
    el = load_script("provision_elevenlabs")
    assert el._noel_mobile(None) is None and el._noel_mobile("  ") is None
    assert el._noel_mobile("07700 900123") == MOBILE
    with pytest.raises(SystemExit):
        el._noel_mobile("not a number")


def test_env_example_lists_noel_mobile_with_no_value():
    example = (ROOT / ".env.example").read_text()
    row = next(ln for ln in example.splitlines() if ln.startswith("NOEL_MOBILE_E164="))
    assert row.split("=", 1)[1].split("#")[0].strip() == ""
