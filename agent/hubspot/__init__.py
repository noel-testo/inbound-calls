"""Thin HubSpot client (§9): contacts, companies, deals, calls, scheduler."""

from .client import HubSpotClient
from .errors import HubSpotError

__all__ = ["HubSpotClient", "HubSpotError"]
