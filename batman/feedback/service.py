"""Feedback service.

Thin layer over the store that validates labels and keeps feedback separate from
immutable telemetry. Feedback is for future evaluation, not automatic retraining.
"""

from __future__ import annotations

from batman.telemetry.schema import VALID_FEEDBACK_LABELS, FeedbackRecord
from batman.telemetry.store import TelemetryStore


class FeedbackService:
    def __init__(self, store: TelemetryStore):
        self.store = store

    def submit(self, request_id: str, label: str, analyst_note: str = "") -> FeedbackRecord:
        if label not in VALID_FEEDBACK_LABELS:
            raise ValueError(f"invalid label: {label}")
        record = FeedbackRecord(
            request_id=request_id, label=label, analyst_note=analyst_note
        )
        self.store.record_feedback(record)
        return record

    def for_request(self, request_id: str) -> list[dict]:
        return self.store.get_feedback(request_id)

    def all(self) -> list[dict]:
        return self.store.get_feedback()
