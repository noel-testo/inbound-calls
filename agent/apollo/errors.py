"""Apollo client errors."""

from __future__ import annotations


class ApolloError(RuntimeError):
    """Raised on a non-2xx Apollo API response or a timeout. Post-call only, so the pipeline logs it
    to Neon `events` and leaves the step for a replay; a caller never hears it."""

    def __init__(self, status: int, message: str):
        super().__init__(f"Apollo API {status}: {message}")
        self.status = status
        self.message = message
