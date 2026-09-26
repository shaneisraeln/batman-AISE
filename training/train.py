"""Train the Isolation Forest anomaly detector on NORMAL behavioral traces.

Pipeline:
    reference data -> normal simulator -> replay to behavioral features
    -> train Isolation Forest on normal only -> calibrate threshold
    -> save models/isolation_forest.joblib
"""

from __future__ import annotations

import os

import numpy as np

from attacks.normal import generate_normal
from batman.detection.isolation_forest import (
    IsolationForestDetector,
    train_isolation_forest,
)
from batman.features.behavioral import FEATURE_ORDER
from training.prepare import load_reference
from training.replay import replay_events

DETECTOR_PATH = os.path.join("models", "isolation_forest.joblib")


def train(seed: int = 42, target_fpr: float = 0.05) -> dict:
    reference = load_reference()

    # Generate a healthy amount of normal traffic for training + validation,
    # including cold-start (short) sessions.
    train_events = generate_normal(reference, n_sessions=120, seed=seed)
    val_events = generate_normal(reference, n_sessions=40, seed=seed + 1)

    X_train, _, _ = replay_events(train_events)
    X_val, _, _ = replay_events(val_events)

    artifacts = train_isolation_forest(
        normal_features=X_train,
        validation_features=X_val,
        feature_order=FEATURE_ORDER,
        target_fpr=target_fpr,
    )

    detector = IsolationForestDetector(artifacts)
    detector.save(DETECTOR_PATH)

    return {
        "train_rows": int(X_train.shape[0]),
        "val_rows": int(X_val.shape[0]),
        "threshold": round(artifacts.threshold, 4),
        "n_features": len(FEATURE_ORDER),
        "path": DETECTOR_PATH,
    }


if __name__ == "__main__":
    print("Trained Isolation Forest detector:", train())
