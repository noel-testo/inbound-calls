"""Lead scoring (SPEC §6): a weighted sum over the extraction, per `config/scoring.yaml`."""

from __future__ import annotations


def score(extraction: dict, config: dict) -> int:
    weights = config.get("weights") or {}
    total = 0
    for field, table in weights.items():
        value = extraction.get(field)
        if field == "asset_type":
            total += sum(int(table.get(v, 0)) for v in (value or []))
        elif field == "estate_size":
            size = value or 0
            for band in table.get("bands", []):
                if size >= band["min"]:
                    total += int(band["points"])
                    break
        elif isinstance(value, str):
            total += int(table.get(value, 0))
    return total


def is_qualified(extraction: dict, config: dict) -> tuple[int, bool]:
    """(score, qualified). Qualified = a new enquiry at or above `high_value_threshold`."""
    points = score(extraction, config)
    threshold = int(config.get("high_value_threshold", 50))
    return points, extraction.get("intent") == "new_enquiry" and points >= threshold
