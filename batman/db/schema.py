"""Schema definition + idempotent migration.

Portable SQL that runs on both SQLite and PostgreSQL. Existing Phase 1 tables
(api_keys, telemetry, feedback) are preserved with identical columns; new
multi-tenant tables are added. All statements are IF NOT EXISTS / additive, so
running against an existing dev database never destroys data.

Tenancy hierarchy:
    users -> projects -> models -> api_keys / upstream_configs
Telemetry and feedback remain keyed by request_id and carry project_id/model_id
for tenant-scoped queries.
"""

from __future__ import annotations

from batman.db.database import Database

# TEXT/REAL/INTEGER are understood by both SQLite and PostgreSQL.
BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'development',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

-- Per-model upstream configuration for protecting an already-deployed ML API.
-- Credentials are stored ENCRYPTED (see batman/cloud/crypto.py); never plaintext.
CREATE TABLE IF NOT EXISTS upstream_configs (
    model_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    url TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'POST',
    predict_path TEXT NOT NULL DEFAULT '/predict',
    request_format TEXT NOT NULL DEFAULT 'instances',
    response_format TEXT NOT NULL DEFAULT 'predictions',
    auth_type TEXT NOT NULL DEFAULT 'none',
    auth_secret_enc TEXT,
    auth_header_name TEXT,
    timeout_s REAL NOT NULL DEFAULT 15.0,
    created_at TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    user_id TEXT,
    name TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    last_used_at TEXT
);

CREATE TABLE IF NOT EXISTS telemetry (
    request_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    project_id TEXT,
    model_id TEXT,
    session_id TEXT,
    detector_version TEXT,
    features TEXT,
    anomaly_score REAL,
    extraction_score REAL,
    threat_type TEXT,
    threat_level TEXT,
    action TEXT,
    latency_ms REAL,
    reason TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    label TEXT NOT NULL,
    analyst_note TEXT,
    created_at TEXT NOT NULL
);
"""

# PostgreSQL needs SERIAL rather than SQLite's AUTOINCREMENT.
BASE_SCHEMA_PG = BASE_SCHEMA.replace(
    "id INTEGER PRIMARY KEY AUTOINCREMENT", "id SERIAL PRIMARY KEY"
)

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_telemetry_ts ON telemetry(timestamp);
CREATE INDEX IF NOT EXISTS idx_telemetry_threat ON telemetry(threat_type);
CREATE INDEX IF NOT EXISTS idx_telemetry_session ON telemetry(session_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_project ON telemetry(project_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_model ON telemetry(model_id);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_models_project ON models(project_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_project ON api_keys(project_id);
"""

# Additive columns that may be missing on a pre-existing Phase 1 SQLite DB.
# (SQLite ignores errors here via our safe wrapper; Postgres uses IF NOT EXISTS.)
_MIGRATIONS = [
    ("api_keys", "user_id", "TEXT"),
    ("api_keys", "name", "TEXT"),
    ("api_keys", "last_used_at", "TEXT"),
    ("upstream_configs", "auth_header_name", "TEXT"),
]


def init_schema(db: Database) -> None:
    """Create tables/indexes if absent; add new columns to legacy tables."""
    db.executescript(BASE_SCHEMA_PG if db.is_postgres else BASE_SCHEMA)
    db.executescript(INDEXES)
    _apply_column_migrations(db)


def _apply_column_migrations(db: Database) -> None:
    for table, column, coltype in _MIGRATIONS:
        if _column_exists(db, table, column):
            continue
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        except Exception:
            # Column already exists or backend raced; safe to ignore.
            pass


def _column_exists(db: Database, table: str, column: str) -> bool:
    if db.is_postgres:
        row = db.query_one(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = ? AND column_name = ?",
            (table, column),
        )
        return row is not None
    # SQLite
    rows = db.query(f"PRAGMA table_info({table})")
    return any(r.get("name") == column for r in rows)
