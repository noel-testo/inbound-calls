"""Fill the discovery-call wording in `config/prompt.md` from `config/greeting.yaml`.

The prompt keeps `{{expert_name}}`, `{{expert_title}}` and `{{deflections.*}}` so those
sentences are written once, in the greeting file. Per-call variables (`{{caller_*}}`, `{{line_*}}`,
`{{#if …}}`, `{{business_name}}`, `{{now_local}}` and the rest) are left for ElevenLabs.
"""

from __future__ import annotations


def prompt_body(template: str) -> str:
    """Drop the leading dev note (lines starting with "# ")."""
    lines = template.splitlines()
    while lines and lines[0].startswith("# "):
        lines.pop(0)
    return "\n".join(lines).strip()


def fill_greeting_vars(text: str, greeting: dict) -> str:
    """Fill `{{expert_name}}`, `{{expert_title}}` and `{{deflections.*}}` from the greeting file."""
    name = str(greeting["expert_name"])
    title = str(greeting["expert_title"])
    out = text.replace("{{expert_name}}", name).replace("{{expert_title}}", title)
    for key, value in (greeting.get("deflections") or {}).items():
        spoken = str(value).format(expert_name=name, expert_title=title)
        out = out.replace(f"{{{{deflections.{key}}}}}", spoken)
    return out


def render_prompt(template: str, greeting: dict) -> str:
    """Return the prompt with the host name and deflections filled in."""
    return fill_greeting_vars(prompt_body(template), greeting)
