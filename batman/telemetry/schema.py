"""Telemetry event schema.

Privacy principle: store the minimum needed for security analysis. Raw
inference inputs are NOT stored by default.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TelemetryEvent:
    request_id: str
    timestamp: str
    project_id: str
    model_id: str
    session_id: str
    detector_version: str
    features: dict[str, Any] = field(default_factory=dict)
    anomaly_score: float = 0.0
    extraction_score: float = 0.0
    threat_type: str = "NONE"
    threat_level: str = "NONE"
    action: str = "ALLOW"
    latency_ms: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "timestamp": self.timestamp,
            "project_id": self.project_id,
            "model_id": self.model_id,
            "session_id": self.session_id,
            "detector_version": self.detector_version,
            "features": self.features,
            "anomaly_score": self.anomaly_score,
            "extraction_score": self.extraction_score,
            "threat_type": self.threat_type,
            "threat_level": self.threat_level,
            "action": self.action,
            "latency_ms": self.latency_ms,
            "reason": self.reason,
        }


@dataclass
class FeedbackRecord:
    request_id: str
    label: str  # TRUE_POSITIVE | FALSE_POSITIVE | TRUE_NEGATIVE | FALSE_NEGATIVE | UNCERTAIN
    analyst_note: str = ""
    created_at: str = field(default_factory=utcnow_iso)


VALID_FEEDBACK_LABELS = {
    "TRUE_POSITIVE",
    "FALSE_POSITIVE",
    "TRUE_NEGATIVE",
    "FALSE_NEGATIVE",
    "UNCERTAIN",
}
