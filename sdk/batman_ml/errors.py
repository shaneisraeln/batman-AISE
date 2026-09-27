"""Exception hierarchy for the BATMAN client.

All client errors derive from ``BatmanError`` so callers can catch broadly or
narrowly. API keys are never included in exception messages.
"""

from __future__ import annotations


class BatmanError(Exception):
    """Base class for all BATMAN client errors."""


class AuthenticationError(BatmanError):
    """The API key was missing, malformed, unknown, revoked, or expired (HTTP 401)."""


class AuthorizationError(BatmanError):
    """The key is valid but not permitted for this resource (HTTP 403 non-block)."""


class BlockedError(BatmanError):
    """BATMAN blocked the request by policy (HTTP 403 block decision).

    Carries the security decision so callers can inspect why.
    """

    def __init__(self, message: str, decision: dict | None = None):
        super().__init__(message)
        self.decision = decision or {}


class RateLimitedError(BatmanError):
    """The request was rate-limited (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class ValidationError(BatmanError):
    """The request payload failed validation (HTTP 400/422)."""


class UpstreamError(BatmanError):
    """The protected upstream model/API failed (HTTP 502/504 from BATMAN)."""


class ConnectionError(BatmanError):
    """Could not reach the BATMAN API (network error, DNS, refused, timeout)."""


class TimeoutError(BatmanError):
    """The request exceeded the configured timeout."""


class ServerError(BatmanError):
    """BATMAN returned an unexpected 5xx error."""
