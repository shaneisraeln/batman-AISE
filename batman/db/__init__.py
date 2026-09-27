"""BATMAN persistence layer.

A thin backend abstraction over SQL, supporting:
  - SQLite (development default, stdlib, zero-config)
  - PostgreSQL (production, via psycopg if installed)

The abstraction deliberately avoids a heavy ORM: it keeps the raw-SQL clarity of
the Phase 1 store while allowing the same schema/queries to run on either
backend. Telemetry semantics are preserved exactly; new multi-tenant tables
(users, projects, models, upstream_configs) are added alongside.
"""

from batman.db.database import Database, get_database
from batman.db.repositories import (
    ApiKeyRepository,
    FeedbackRepository,
    ModelRepository,
    ProjectRepository,
    TelemetryRepository,
    UpstreamConfigRepository,
    UserRepository,
)

__all__ = [
    "Database",
    "get_database",
    "UserRepository",
    "ProjectRepository",
    "ModelRepository",
    "ApiKeyRepository",
    "UpstreamConfigRepository",
    "TelemetryRepository",
    "FeedbackRepository",
]
