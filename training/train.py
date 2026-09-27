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


def train(
    seed: int = 42,
    target_fpr: float = 0.05,
    dataset: str = "digits",
    out_path: str | None = None,
) -> dict:
    """Train + calibrate the behavioral anomaly detector on NORMAL traffic.

    dataset selects the reference input pool so the detector is calibrated for
    the distribution it will actually protect:
        "digits"        -> legacy demo detector (models/isolation_forest.joblib)
        "breast_cancer" -> real-service detector
                           (models/isolation_forest_breast_cancer.joblib)
    """
    reference = load_reference(dataset)
    if out_path is None:
        out_path = (
            DETECTOR_PATH
            if dataset == "digits"
            else os.path.join("models", f"isolation_forest_{dataset}.joblib")
        )

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
    detector.save(out_path)

    return {
        "dataset": dataset,
        "train_rows": int(X_train.shape[0]),
        "val_rows": int(X_val.shape[0]),
        "threshold": round(artifacts.threshold, 4),
        "n_features": len(FEATURE_ORDER),
        "path": out_path,
    }


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default="digits", choices=["digits", "breast_cancer"])
    p.add_argument("--target-fpr", type=float, default=0.05)
    args = p.parse_args()
    print("Trained Isolation Forest detector:", train(
        dataset=args.dataset, target_fpr=args.target_fpr
    ))
