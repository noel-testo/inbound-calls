"""Webhook authentication.

- tool webhooks: a shared secret header (`X-Cody-Secret`) configured on the ElevenLabs side,
  compared in constant time.
- post_call_transcription (now received by n8n; not used by the service): HMAC-SHA256 in the
  `ElevenLabs-Signature` header, `t=<unix>,v0=<hex>`, over `"<t>.<raw body>"` — the scheme the
  ElevenLabs SDK's `construct_event` verifies. Verified on the raw bytes before any JSON parsing;
  stale timestamps are rejected to blunt replays.
"""

from __future__ import annotations

import hashlib
import hmac
import time

SECRET_HEADER = "x-cody-secret"
SIGNATURE_HEADER = "elevenlabs-signature"
TOLERANCE_S = 30 * 60


class SignatureError(ValueError):
    pass


def secret_ok(presented: str | None, expected: str | None) -> bool:
    if not expected or not presented:
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def sign(body: bytes, secret: str, timestamp: int) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v0={digest}"


def verify_signature(
    body: bytes, header: str | None, secret: str | None, *, now: float | None = None
) -> None:
    if not secret:
        raise SignatureError("webhook secret not configured")
    if not header:
        raise SignatureError("missing signature header")
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        timestamp = int(parts["t"])
        presented = parts["v0"]
    except (KeyError, ValueError) as e:
        raise SignatureError("malformed signature header") from e
    now = time.time() if now is None else now
    if abs(now - timestamp) > TOLERANCE_S:
        raise SignatureError("signature timestamp outside tolerance")
    expected = sign(body, secret, timestamp).split("v0=", 1)[1]
    if not hmac.compare_digest(presented, expected):
        raise SignatureError("signature mismatch")
