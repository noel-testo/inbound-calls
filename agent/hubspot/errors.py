"""HubSpot client errors."""

from __future__ import annotations


class HubSpotError(RuntimeError):
    """Raised on a non-2xx HubSpot API response, or a client misconfiguration.

    Tools (SPEC §7) decide whether to fail soft; the client always raises so the
    caller sees failures explicitly.
    """

    def __init__(self, status: int, message: str, *, correlation_id: str | None = None):
        super().__init__(f"HubSpot API {status}: {message}")
        self.status = status
        self.message = message
        self.correlation_id = correlation_id
