"""Cal.com client errors."""

from __future__ import annotations


class CalComError(RuntimeError):
    """Raised on a non-2xx Cal.com API response, or a client misconfiguration.

    `check_availability` and `book_meeting` are blocking tools (SPEC §5.1); the
    client raises so the tool layer can decide how to recover.
    """

    def __init__(self, status: int, message: str):
        super().__init__(f"Cal.com API {status}: {message}")
        self.status = status
        self.message = message
