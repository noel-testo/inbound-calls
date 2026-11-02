"""Phone-number normalisation. Cody's caller directory is keyed by E.164 (`+44…`)."""

from __future__ import annotations

import phonenumbers

WITHHELD = {"", "anonymous", "unknown", "withheld", "private", "restricted", "unavailable"}


def to_e164(raw: str | None, region: str = "GB") -> str | None:
    """Return the number in E.164, or None if it is withheld or unparseable."""
    if raw is None or raw.strip().lower() in WITHHELD:
        return None
    try:
        parsed = phonenumbers.parse(raw.strip(), region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def is_mobile(e164: str) -> bool:
    try:
        kind = phonenumbers.number_type(phonenumbers.parse(e164, None))
    except phonenumbers.NumberParseException:
        return False
    return kind in (
        phonenumbers.PhoneNumberType.MOBILE,
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
    )
