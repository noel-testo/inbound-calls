"""Provisioning helpers: Notion schema diff and the ElevenLabs Phase 3 patch body."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from agent.extraction import FIELDS
from agent.notion.schema import LEADS, TRANSCRIPTS

SCRIPTS = Path(__file__).parents[1] / "scripts"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_notion_missing_skips_existing_and_title():
    notion = load("provision_notion")
    todo = notion.missing(LEADS, {"Name": {"type": "title"}, "Phone": {"type": "phone_number"}})
    assert "Name" not in todo and "Phone" not in todo
    assert set(todo) == set(LEADS) - {"Name", "Phone"}
    assert notion.missing(TRANSCRIPTS, TRANSCRIPTS) == {}


def test_elevenlabs_patch_carries_data_collection_and_placeholders():
    el = load("provision_elevenlabs")
    body = el._phase3_settings()
    agent = body["conversation_config"]["agent"]
    placeholders = agent["dynamic_variables"]["dynamic_variable_placeholders"]
    assert placeholders == el.DYNAMIC_VARIABLES and placeholders["caller_known"] == "false"
    ps = body["platform_settings"]
    assert set(ps["data_collection"]) == set(FIELDS)
    assert ps["overrides"]["enable_conversation_initiation_client_data_from_webhook"] is True
    assert "tts" not in body["conversation_config"] and "privacy" not in ps
    assert "first_message" not in agent


def test_discovery_host_is_named_once_and_privacy_line_unchanged():
    root = Path(__file__).parents[1]
    greeting = (root / "config" / "greeting.yaml").read_text()
    prompt = (root / "config" / "prompt.md").read_text()
    terms = (root / "config" / "terms.yaml").read_text()
    example = (root / ".env.example").read_text()
    assert 'expert_name: "Noel Sesto"' in greeting
    assert 'expert_title: "our Technical Director"' in greeting
    assert "{expert_name}" in greeting and "{expert_title}" in greeting
    assert "Noel Sesto, our Technical Director" not in greeting
    assert "{{expert_name}}" in prompt and "{{deflections.pricing}}" in prompt
    assert "Noel Sesto" not in prompt
    assert "Noel Sesto" in terms and "TODO expert name" not in terms
    assert "CALCOM_EVENT_TYPE_ID=7747197" in example
    assert "7103844" not in example.split("Not 7103844", 1)[0]
    rendered = load("provision_elevenlabs")._base_prompt()
    assert "15-minute discovery call with Noel Sesto, our Technical Director" in rendered
    assert "but Noel Sesto, our Technical Director, can on the discovery call." in rendered
    assert "book a call with Noel Sesto, our Technical Director." in rendered
    assert "{{expert_name}}" not in rendered and "{{deflections." not in rendered
    assert "Monday to Friday 08:00 to 18:00" in rendered
    assert "Saturday 09:00 to 17:00" in rendered
    assert "Sunday 10:00 to 16:00 (Europe/London)" in rendered
    assert "Thanks for calling ControlFreq. Goodbye." in rendered
    assert "Please hold while I try to put you through." in rendered
    assert "{{business_hours}}" not in rendered and "{{closing}}" not in rendered
    assert "emergency instruction" not in rendered.lower()
    first = load("provision_elevenlabs")._first_message()
    assert "Calls may be transcribed for quality and training purposes." in first
    assert "recorded" not in first.lower()


def test_new_agent_body_keeps_voice_privacy_and_greeting():
    el = load("provision_elevenlabs")
    body = el._agent_body()
    assert body["conversation_config"]["tts"]["voice_id"] == "jRAAK67SEFE9m7ci5DhD"
    assert body["platform_settings"]["privacy"] == {"record_voice": False, "retention_days": 30}
    assert body["conversation_config"]["agent"]["first_message"].startswith(
        "Thanks for calling ControlFreq."
    )


def test_default_did_is_the_020_number():
    assert load("provision_telnyx").DEFAULT_DID == "+442045200783"
    assert load("provision_elevenlabs").DEFAULT_DID == "+442045200783"
