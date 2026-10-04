"""Thin HubSpot client (§9): contacts, companies, deals, calls, scheduler."""

from .client import HubSpotClient, uk_phone_variants
from .errors import HubSpotError

__all__ = ["HubSpotClient", "HubSpotError", "uk_phone_variants"]
