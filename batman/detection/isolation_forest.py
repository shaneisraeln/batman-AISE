"""Isolation Forest anomaly detector.

Trained primarily on normal behavior. Persists the scaler, feature ordering,
and a calibrated operational threshold alongside the model.

Note: raw Isolation Forest scores are NOT presented as calibrated
probabilities. We map the decision_function to a bounded [0,1] anomaly score
using validation-derived min/max, which is a monotonic normalization, not a
probability calibration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from batman.detection.base import Detector
from batman.features.behavioral import FEATURE_ORDER
from batman.types import DetectorResult
from batman.version import DETECTOR_VERSION


@dataclass
class IFArtifacts:
    model: IsolationForest
    scaler: StandardScaler
    feature_order: list[str]
    score_min: float
    score_max: float
    threshold: float
    version: str = DETECTOR_VERSION


class IsolationForestDetector(Detector):
    def __init__(self, artifacts: IFArtifacts | None = None):
        self.artifacts = artifacts

    @property
    def ready(self) -> bool:
        return self.artifacts is not None

    def _normalize(self, raw_scores: np.ndarray) -> np.ndarray:
        """Map decision_function outputs to [0,1] anomaly scores.

        Lower decision_function => more anomalous, so we invert. Normalization
        uses validation-derived bounds.
        """
        a = self.artifacts
        lo, hi = a.score_min, a.score_max
        if hi == lo:
            return np.full_like(raw_scores, 0.5, dtype=float)
        # Invert: more negative decision => higher anomaly score.
        norm = (hi - raw_scores) / (hi - lo)
        return np.clip(norm, 0.0, 1.0)

    def predict(self, features: np.ndarray) -> DetectorResult:
        if not self.ready:
            # Detector unavailable: signal neutral, non-anomalous. Rules still apply.
            return DetectorResult(
                is_anomalous=False,
                score=0.0,
                detector="isolation_forest",
                version="unavailable",
                extra={"reason": "detector_not_loaded"},
            )
        a = self.artifacts
        x = np.asarray(features, dtype=float).reshape(1, -1)
        x_scaled = a.scaler.transform(x)
        raw = a.model.decision_function(x_scaled)
        score = float(self._normalize(raw)[0])
        return DetectorResult(
            is_anomalous=score >= a.threshold,
            score=score,
            detector="isolation_forest",
            version=a.version,
            extra={"raw_decision": float(raw[0]), "threshold": a.threshold},
        )

    # --- persistence ---
    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        joblib.dump(self.artifacts, path)

    @classmethod
    def load(cls, path: str) -> "IsolationForestDetector":
        if not os.path.exists(path):
            return cls(artifacts=None)
        artifacts = joblib.load(path)
        return cls(artifacts=artifacts)


def train_isolation_forest(
    normal_features: np.ndarray,
    validation_features: np.ndarray | None = None,
    feature_order: list[str] | None = None,
    contamination: float = 0.02,
    n_estimators: int = 200,
    target_fpr: float = 0.05,
    random_state: int = 42,
) -> IFArtifacts:
    """Train on normal behavior and calibrate an operational threshold.

    The threshold is chosen so that at most ``target_fpr`` of the (assumed
    normal) validation set is flagged as anomalous.
    """
    feature_order = feature_order or FEATURE_ORDER
    X = np.asarray(normal_features, dtype=float)
    scaler = StandardScaler().fit(X)
    Xs = scaler.transform(X)

    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
    ).fit(Xs)

    # Normalization bounds from training decision scores, widened by the
    # validation set so that legitimate tail points (e.g. cold-start requests)
    # do not saturate the normalized score at exactly 1.0.
    train_dec = model.decision_function(Xs)
    val_dec_for_bounds = (
        model.decision_function(scaler.transform(np.asarray(validation_features, dtype=float)))
        if validation_features is not None
        else train_dec
    )
    all_dec = np.concatenate([train_dec, val_dec_for_bounds])
    span = float(all_dec.max() - all_dec.min()) or 1.0
    # Pad the lower bound so normal outliers map below 1.0 rather than clipping.
    score_min = float(all_dec.min() - 0.1 * span)
    score_max = float(all_dec.max())

    def normalize(dec: np.ndarray) -> np.ndarray:
        if score_max == score_min:
            return np.full_like(dec, 0.5, dtype=float)
        return np.clip((score_max - dec) / (score_max - score_min), 0.0, 1.0)

    val = validation_features if validation_features is not None else normal_features
    val_scaled = scaler.transform(np.asarray(val, dtype=float))
    val_scores = normalize(model.decision_function(val_scaled))
    # Threshold at the (1 - target_fpr) quantile of normal validation scores.
    threshold = float(np.quantile(val_scores, 1.0 - target_fpr))

    return IFArtifacts(
        model=model,
        scaler=scaler,
        feature_order=feature_order,
        score_min=score_min,
        score_max=score_max,
        threshold=threshold,
    )
