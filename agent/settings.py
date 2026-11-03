"""Runtime settings for the webhook service, read once from the environment (`.env` on the host)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _opt(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Settings:
    tool_secret: str | None = None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(tool_secret=_opt("ELEVENLABS_TOOL_SECRET"))
