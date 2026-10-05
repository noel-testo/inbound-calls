"""Thin Cal.com client (§7): discovery-call availability and booking."""

from .client import CalComClient
from .errors import CalComError

__all__ = ["CalComClient", "CalComError"]
