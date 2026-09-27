"""Production-readiness configuration checks.

These are advisory: they return a list of human-readable warnings about settings
that are unsafe for a public/production deployment. The cloud app logs them at
startup so an operator sees, in one place, whether the environment is
misconfigured — without hard-failing local development.

Trigger stricter behavior by setting ``BATMAN_ENV=production``: in that mode the
same checks are returned as *errors* the caller may choose to refuse to start on.
Default env is "development", which only warns.
"""

from __future__ import annotations

import os

DEV_SECRET = "dev-insecure-secret-change-me"


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def config_warnings() -> list[str]:
    """Return a list of configuration warnings for the current environment."""
    warnings: list[str] = []
    env = os.getenv("BATMAN_ENV", "development").strip().lower()
    is_prod = env in {"production", "prod", "staging"}

    secret = os.getenv("BATMAN_SECRET_KEY")
    if not secret or secret == DEV_SECRET:
        warnings.append(
            "BATMAN_SECRET_KEY is unset or the insecure dev default; set a strong "
            "random value (python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
        )

    if not os.getenv("BATMAN_ENCRYPTION_KEY"):
        warnings.append(
            "BATMAN_ENCRYPTION_KEY is unset; upstream-credential storage will fail "
            "closed. Set a Fernet key "
            "(python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\")."
        )

    cors = os.getenv("BATMAN_CORS_ORIGINS", "")
    if is_prod and ("localhost" in cors or "127.0.0.1" in cors or not cors):
        warnings.append(
            "BATMAN_CORS_ORIGINS still contains localhost (or is unset) while "
            "BATMAN_ENV is production; set it to your real dashboard origin(s)."
        )

    if is_prod and _truthy(os.getenv("BATMAN_ALLOW_PRIVATE_UPSTREAM")):
        warnings.append(
            "BATMAN_ALLOW_PRIVATE_UPSTREAM is enabled in a production environment; "
            "this disables the SSRF private-address guard. Disable it unless your "
            "protected model is on a trusted private network."
        )

    db = os.getenv("BATMAN_DATABASE_URL", "")
    if is_prod and (db.startswith("sqlite") or not db):
        warnings.append(
            "BATMAN_DATABASE_URL is SQLite (or unset) while BATMAN_ENV is production; "
            "use PostgreSQL for a real deployment."
        )

    return warnings


def is_production() -> bool:
    return os.getenv("BATMAN_ENV", "development").strip().lower() in {"production", "prod"}
