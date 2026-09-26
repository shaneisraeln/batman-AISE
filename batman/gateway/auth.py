"""API key system.

- prefix ``bm_live_``
- cryptographically secure random token
- hashed (SHA-256) before storage; raw key returned only once at creation
- constant-time verification
- revocation + optional expiration
- project/model association
- raw keys are never logged
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

KEY_PREFIX = "bm_live_"


@dataclass
class APIKeyRecord:
    key_id: str
    key_hash: str
    project_id: str
    model_id: str
    status: str  # "active" | "revoked"
    created_at: str
    expires_at: str | None = None


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Return a fresh raw API key. Store only its hash."""
    return f"{KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_key(raw_key: str) -> str:
    return _hash_key(raw_key)


def verify_key_hash(raw_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of a presented key against a stored hash."""
    if not raw_key or not stored_hash:
        return False
    computed = _hash_key(raw_key)
    return hmac.compare_digest(computed, stored_hash)


def is_expired(record: APIKeyRecord, now: datetime | None = None) -> bool:
    if not record.expires_at:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        exp = datetime.fromisoformat(record.expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return now >= exp


class AuthError(Exception):
    """Raised on authentication failure."""


class APIKeyStore:
    """Persists key records via the telemetry/store backend (SQLite)."""

    def __init__(self, store):
        self.store = store

    def create_key(
        self,
        project_id: str,
        model_id: str,
        expires_at: str | None = None,
    ) -> tuple[str, APIKeyRecord]:
        raw = generate_api_key()
        key_id = f"key_{secrets.token_hex(8)}"
        record = APIKeyRecord(
            key_id=key_id,
            key_hash=hash_key(raw),
            project_id=project_id,
            model_id=model_id,
            status="active",
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=expires_at,
        )
        self.store.save_api_key(record)
        # Return raw key ONLY here; it is never persisted or logged.
        return raw, record

    def authenticate(self, raw_key: str) -> APIKeyRecord:
        if not raw_key or not raw_key.startswith(KEY_PREFIX):
            raise AuthError("invalid_key_format")
        record = self.store.get_api_key_by_hash(hash_key(raw_key))
        if record is None:
            raise AuthError("unknown_key")
        # Defensive constant-time re-check.
        if not verify_key_hash(raw_key, record.key_hash):
            raise AuthError("key_mismatch")
        if record.status != "active":
            raise AuthError("key_revoked")
        if is_expired(record):
            raise AuthError("key_expired")
        return record

    def revoke(self, key_id: str) -> bool:
        return self.store.revoke_api_key(key_id)
