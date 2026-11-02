"""Provisioning helpers: Notion schema diff and the ElevenLabs Phase 3 patch body."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from agent.conversation_init import DYNAMIC_VARIABLES
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
    assert agent["dynamic_variables"]["dynamic_variable_placeholders"] == DYNAMIC_VARIABLES
    ps = body["platform_settings"]
    assert set(ps["data_collection"]) == set(FIELDS)
    assert ps["overrides"]["enable_conversation_initiation_client_data_from_webhook"] is True
    assert "tts" not in body["conversation_config"] and "privacy" not in ps
    assert "first_message" not in agent


def test_discovery_host_is_named_and_privacy_line_unchanged():
    root = Path(__file__).parents[1]
    greeting = (root / "config" / "greeting.yaml").read_text()
    prompt = (root / "config" / "prompt.md").read_text()
    terms = (root / "config" / "terms.yaml").read_text()
    assert 'expert_name: "Noel Sesto"' in greeting
    assert 'expert_title: "our Technical Director"' in greeting
    assert "Noel Sesto, our Technical Director" in greeting
    assert "{expert_name}" not in greeting
    assert "15-minute discovery call with Noel Sesto, our Technical Director" in prompt
    assert "expert_name" not in prompt and "expert_title" not in prompt
    assert "Noel Sesto" in terms and "TODO expert name" not in terms
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
