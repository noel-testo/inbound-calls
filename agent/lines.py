"""Which line a call came in on, and what Cody does differently there (issue #13).

`config/lines.yaml` is the line map, `config/greeting.yaml` (`line_greetings`) holds what callers
hear and `config/prompt_lines.md` holds the per-line prompt sections. This module only resolves a
call to a line and builds the per-call values ElevenLabs needs; it holds no state and no numbers of
its own. The transfer destination is never read here: provisioning reads it from the environment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agent.phone import to_e164
from agent.prompt import fill_greeting_vars

CONFIG = Path(__file__).resolve().parents[1] / "config"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SECTION = re.compile(r"^## line:\s*(\S+)\s*$", re.MULTILINE)


class LineConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Transfer:
    destination_env: str
    type: str
    condition: str


@dataclass(frozen=True)
class Line:
    key: str
    label: str
    called_numbers: tuple[str, ...] = ()
    caller_ids: tuple[str, ...] = ()
    caller_id_is_caller: bool = True
    screen_and_transfer: bool = False
    transfer: Transfer | None = None
    calcom_title_prefix: str = ""
    pending: bool = False  # a matcher is listed but still empty: a placeholder, never matches

    @property
    def has_matchers(self) -> bool:
        return bool(self.called_numbers or self.caller_ids)

    def matches(self, called_e164: str | None, caller_e164: str | None) -> bool:
        if self.pending or not self.has_matchers:
            return False
        if self.called_numbers and called_e164 not in self.called_numbers:
            return False
        return not (self.caller_ids and caller_e164 not in self.caller_ids)


@dataclass(frozen=True)
class LineMap:
    lines: tuple[Line, ...]
    default_key: str
    by_key: dict[str, Line] = field(default_factory=dict, compare=False)

    @property
    def default(self) -> Line:
        return self.by_key[self.default_key]

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(line.key for line in self.lines)

    @property
    def called_numbers(self) -> tuple[str, ...]:
        """Every number dialled on Telnyx that a line is matched on, in config order."""
        return tuple(dict.fromkeys(n for line in self.lines for n in line.called_numbers))

    def get(self, key: str | None) -> Line:
        """The line for a key, or the default line for a missing or unknown key."""
        return self.by_key.get(key or "", self.default)

    def resolve(self, called_number: str | None, caller_id: str | None) -> Line:
        called = to_e164(called_number)
        caller = to_e164(caller_id)
        for line in self.lines:
            if line.matches(called, caller):
                return line
        return self.default


def _numbers(values) -> tuple[str, ...]:
    out = []
    for raw in values or []:
        e164 = to_e164(str(raw))
        if e164 is None:
            raise LineConfigError(f"not a phone number in config/lines.yaml: {raw!r}")
        out.append(e164)
    return tuple(out)


def parse_line_map(data: dict) -> LineMap:
    lines = []
    for entry in data.get("lines") or []:
        match = entry.get("match") or {}
        transfer = entry.get("transfer")
        lines.append(
            Line(
                key=str(entry["key"]),
                label=str(entry["label"]),
                called_numbers=_numbers(match.get("called_numbers")),
                caller_ids=_numbers(match.get("caller_ids")),
                caller_id_is_caller=bool(entry.get("caller_id_is_caller", True)),
                screen_and_transfer=bool(entry.get("screen_and_transfer", False)),
                transfer=Transfer(
                    destination_env=str(transfer["destination_env"]),
                    type=str(transfer.get("type", "conference")),
                    condition=" ".join(str(transfer["condition"]).split()),
                )
                if transfer
                else None,
                calcom_title_prefix=str((entry.get("calcom") or {}).get("title_prefix", "")),
                pending=any(k in match and not match[k] for k in ("called_numbers", "caller_ids")),
            )
        )
    keys = [line.key for line in lines]
    if len(set(keys)) != len(keys):
        raise LineConfigError("duplicate line key in config/lines.yaml")
    default_key = str(data.get("default", "general"))
    if default_key not in keys:
        raise LineConfigError(f"default line {default_key!r} is not in config/lines.yaml")
    for line in lines:
        if line.screen_and_transfer and line.transfer is None:
            raise LineConfigError(f"line {line.key!r} screens but has no transfer settings")
    return LineMap(tuple(lines), default_key, {line.key: line for line in lines})


def load_line_map(path: Path | None = None) -> LineMap:
    return parse_line_map(yaml.safe_load((path or CONFIG / "lines.yaml").read_text()))


def parse_prompt_sections(text: str) -> dict[str, str]:
    """Split `config/prompt_lines.md` into {line key: section text}, comments removed."""
    text = _COMMENT.sub("", text)
    parts = _SECTION.split(text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def load_prompt_sections(path: Path | None = None) -> dict[str, str]:
    return parse_prompt_sections((path or CONFIG / "prompt_lines.md").read_text())


def load_greeting(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG / "greeting.yaml").read_text())


def first_message(line: Line, greeting: dict) -> str:
    """What Cody says first on this line: the line's own greeting, else the general one."""
    spoken = (greeting.get("line_greetings") or {}).get(line.key) or greeting["greeting"]
    return " ".join(str(spoken).split())


def instructions(line: Line, sections: dict[str, str], greeting: dict) -> str:
    text = sections.get(line.key) or sections.get("general", "")
    return fill_greeting_vars(text, greeting)


def dynamic_variables(
    line: Line, greeting: dict, sections: dict[str, str], caller_id: str | None = None
) -> dict[str, str]:
    """The per-call variables for this line. All values are strings, as ElevenLabs requires.

    `caller_phone` is the CLI in E.164 only where the CLI really is the caller; on the
    RingCentral lines it is blank so nothing downstream treats the dialled DDI as the caller.
    """
    caller = to_e164(caller_id) if line.caller_id_is_caller else None
    return {
        "line_key": line.key,
        "line_label": line.label,
        "line_instructions": instructions(line, sections, greeting),
        "caller_id_is_caller": "true" if line.caller_id_is_caller else "false",
        "caller_phone": caller or "",
    }


def resolve_call(
    called_number: str | None,
    caller_id: str | None,
    *,
    line_map: LineMap,
    greeting: dict,
    sections: dict[str, str],
) -> dict:
    """The conversation-init answer for one call (see POST /lines/resolve)."""
    line = line_map.resolve(called_number, caller_id)
    return {
        "line_key": line.key,
        "line_label": line.label,
        "line_tag": line.key,
        "lookup_caller": line.caller_id_is_caller,
        "screen_and_transfer": line.screen_and_transfer,
        "first_message": first_message(line, greeting),
        "dynamic_variables": dynamic_variables(line, greeting, sections, caller_id),
    }
