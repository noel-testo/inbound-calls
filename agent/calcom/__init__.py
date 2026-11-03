"""Thin Cal.com client (§7): availability and booking for Noel Sesto's discovery calls."""

from .client import CalComClient
from .errors import CalComError

__all__ = ["CalComClient", "CalComError"]
