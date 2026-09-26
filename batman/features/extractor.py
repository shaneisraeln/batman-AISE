"""FeatureExtractor: turns a request + session (+ optional response) into the
canonical behavioral feature vector consumed by the detectors.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from batman.features import behavioral as bh
from batman.features.session import SessionState


@dataclass
class ExtractedFeatures:
    values: dict[str, float] = field(default_factory=dict)
    unavailable: list[str] = field(default_factory=list)

    def vector(self) -> np.ndarray:
        return np.array([self.values.get(k, 0.0) for k in bh.FEATURE_ORDER], dtype=float)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)


class FeatureExtractor:
    def extract(
        self,
        input_array: np.ndarray,
        session: SessionState,
        proba: np.ndarray | None = None,
        now: float | None = None,
    ) -> ExtractedFeatures:
        now = now if now is not None else time.monotonic()
        # Use the first row as the representative sample for behavioral analysis.
        arr = np.asarray(input_array, dtype=float)
        vec = arr[0].ravel() if arr.ndim == 2 and arr.shape[0] > 0 else arr.ravel()

        values: dict[str, float] = {}
        unavailable: list[str] = []

        # Request behavior.
        values["request_rate"] = session.recent_request_rate(now)
        values["inter_request_time"] = session.inter_request_time(now)
        values["session_request_count"] = float(session.request_count)
        values["request_size"] = float(vec.size)

        # Input behavior.
        values.update(bh.input_stats(vec))
        values["nan_count"] = float(np.isnan(arr).sum())
        values["inf_count"] = float(np.isinf(arr).sum())

        # Query-relationship behavior.
        dup_ratio, uniq_ratio = bh.duplicate_and_unique_ratios(vec, session.recent_inputs)
        values["duplicate_ratio"] = dup_ratio
        values["unique_input_ratio"] = uniq_ratio
        values["query_similarity"] = bh.query_similarity(vec, session.recent_inputs)

        # Response behavior (optional).
        if proba is not None:
            first_proba = np.asarray(proba)
            first_proba = first_proba[0] if first_proba.ndim == 2 else first_proba
            values["prediction_entropy"] = bh.prediction_entropy(first_proba)
        else:
            values["prediction_entropy"] = 0.0
            unavailable.append("prediction_entropy")

        # Session behavior.
        values["previous_anomaly_count"] = float(session.previous_anomaly_count())

        return ExtractedFeatures(values=values, unavailable=unavailable)
