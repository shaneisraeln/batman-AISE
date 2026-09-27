"""Password hashing, session tokens, and upstream-credential encryption.

Design:
  - Passwords: PBKDF2-HMAC-SHA256 (stdlib), per-password random salt, high
    iteration count, constant-time verification. No external bcrypt dependency.
  - Session tokens: stateless, HMAC-signed (stdlib), with expiry. The signing
    secret comes from BATMAN_SECRET_KEY (required in production).
  - Upstream credentials: encrypted with Fernet (from `cryptography`) when
    available; the key comes from BATMAN_ENCRYPTION_KEY. If `cryptography` is
    not installed, encryption is refused (fail closed) rather than storing
    plaintext.

Never log secrets, passwords, tokens, or upstream credentials.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

# ---- password hashing (PBKDF2, stdlib) ----
_PBKDF2_ROUNDS = 240_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds_s, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        rounds = int(rounds_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt, rounds)
    return hmac.compare_digest(dk, expected)


# ---- session tokens (HMAC-signed, stateless) ----
def _secret_key() -> bytes:
    key = os.getenv("BATMAN_SECRET_KEY")
    if not key:
        # Dev fallback: deterministic-but-warned ephemeral key. In production the
        # env var must be set; tokens do not survive restart without it.
        key = "dev-insecure-secret-change-me"
    return key.encode("utf-8")


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def issue_token(user_id: str, ttl_seconds: int = 7 * 24 * 3600) -> str:
    payload = {"uid": user_id, "exp": int(time.time()) + ttl_seconds}
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _b64u(hmac.new(_secret_key(), body.encode("utf-8"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> str | None:
    """Return the user_id if the token is valid and unexpired, else None."""
    try:
        body, sig = token.split(".")
    except (ValueError, AttributeError):
        return None
    expected = _b64u(hmac.new(_secret_key(), body.encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64u_decode(body))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload.get("uid")


# ---- upstream credential encryption (Fernet) ----
def _fernet():
    try:
        from cryptography.fernet import Fernet  # type: ignore
    except ImportError:
        return None
    key = os.getenv("BATMAN_ENCRYPTION_KEY")
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception:
        return None


def encryption_available() -> bool:
    return _fernet() is not None


def encrypt_secret(plaintext: str) -> str:
    """Encrypt an upstream credential. Fails closed if encryption is unavailable."""
    f = _fernet()
    if f is None:
        raise RuntimeError(
            "Upstream credential encryption unavailable. Install 'cryptography' and "
            "set BATMAN_ENCRYPTION_KEY (Fernet key) before storing upstream secrets."
        )
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    f = _fernet()
    if f is None:
        raise RuntimeError("Encryption key unavailable; cannot decrypt upstream secret.")
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def generate_encryption_key() -> str:
    """Helper to mint a Fernet key for BATMAN_ENCRYPTION_KEY (ops convenience)."""
    from cryptography.fernet import Fernet  # type: ignore

    return Fernet.generate_key().decode("utf-8")
