"""Runtime settings for the webhook service, read once from the environment (`.env` on the host)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _opt(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    database_url: str | None = None
    tool_secret: str | None = None
    webhook_secret: str | None = None
    agent_id: str | None = None
    did: str = "+442045200783"
    business_tz: str = "Europe/London"
    init_lookup_timeout_s: float = 1.5

    apollo_api_key: str | None = None
    apollo_user_id: str | None = None
    apollo_create_deals: bool = False
    apollo_deal_stage_id: str | None = None
    apollo_task_due_hours: float = 4.0

    notion_api_key: str | None = None
    notion_leads_db_id: str | None = None
    notion_transcripts_db_id: str | None = None

    slack_webhook_url: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            database_url=_opt("DATABASE_URL"),
            tool_secret=_opt("ELEVENLABS_TOOL_SECRET"),
            webhook_secret=_opt("ELEVENLABS_WEBHOOK_SECRET"),
            agent_id=_opt("ELEVENLABS_AGENT_ID"),
            did=_opt("TELNYX_DID") or cls.did,
            business_tz=_opt("BUSINESS_TZ") or cls.business_tz,
            init_lookup_timeout_s=float(_opt("INIT_LOOKUP_TIMEOUT_MS") or 1500) / 1000,
            apollo_api_key=_opt("APOLLO_API_KEY"),
            apollo_user_id=_opt("APOLLO_USER_ID"),
            apollo_create_deals=_flag("APOLLO_CREATE_DEALS", default=False),
            apollo_deal_stage_id=_opt("APOLLO_DEAL_STAGE_ID"),
            apollo_task_due_hours=float(_opt("APOLLO_TASK_DUE_HOURS") or 4),
            notion_api_key=_opt("NOTION_API_KEY"),
            notion_leads_db_id=_opt("NOTION_LEADS_DB_ID"),
            notion_transcripts_db_id=_opt("NOTION_TRANSCRIPTS_DB_ID"),
            slack_webhook_url=_opt("SLACK_WEBHOOK_URL"),
        )
