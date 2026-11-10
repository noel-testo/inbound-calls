"""Fill the discovery-call wording in `config/prompt.md` from `config/greeting.yaml`.

The prompt keeps `{{expert_name}}`, `{{expert_title}}` and `{{deflections.*}}` so those
sentences are written once, in the greeting file. `{{business_hours}}` and `{{closing}}` are
filled from the same file. Per-call variables (`{{caller_*}}`, `{{line_*}}`, `{{#if …}}`,
`{{business_name}}`, `{{now_local}}` and the rest) are left for ElevenLabs.
"""

from __future__ import annotations


def prompt_body(template: str) -> str:
    """Drop the leading dev note (lines starting with "# ")."""
    lines = template.splitlines()
    while lines and lines[0].startswith("# "):
        lines.pop(0)
    return "\n".join(lines).strip()


def _hours_span(value: str) -> str:
    text = str(value).strip()
    if text.lower() == "closed":
        return "closed"
    start, end = text.split("-", 1)
    return f"{start.strip()} to {end.strip()}"


def business_hours_text(greeting: dict) -> str:
    """The spoken hours, from `business_hours` in the greeting file."""
    hours = greeting["business_hours"]
    return (
        f"Monday to Friday {_hours_span(hours['weekdays'])}, "
        f"Saturday {_hours_span(hours['saturday'])}, "
        f"Sunday {_hours_span(hours['sunday'])} ({hours['timezone']})"
    )


def fill_greeting_vars(text: str, greeting: dict) -> str:
    """Fill host, deflections, business hours and the closing line from the greeting file."""
    name = str(greeting["expert_name"])
    title = str(greeting["expert_title"])
    out = text.replace("{{expert_name}}", name).replace("{{expert_title}}", title)
    out = out.replace("{{business_hours}}", business_hours_text(greeting))
    out = out.replace("{{closing}}", " ".join(str(greeting["closing"]).split()))
    for key, value in (greeting.get("deflections") or {}).items():
        spoken = str(value).format(expert_name=name, expert_title=title)
        out = out.replace(f"{{{{deflections.{key}}}}}", spoken)
    return out


def render_prompt(template: str, greeting: dict) -> str:
    """Return the prompt with the host name and deflections filled in."""
    return fill_greeting_vars(prompt_body(template), greeting)
