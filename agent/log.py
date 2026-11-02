"""Structured JSON logs: one line per event, `call_id` on every line that belongs to a call."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

_logger = logging.getLogger("cody")


def configure() -> None:
    if _logger.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def event(name: str, *, call_id: str | None = None, level: int = logging.INFO, **fields) -> None:
    record = {"ts": datetime.now(UTC).isoformat(), "event": name}
    if call_id:
        record["call_id"] = call_id
    record.update(fields)
    _logger.log(level, json.dumps(record, default=str))
