"""Train the protected model with proper train / validation / test separation.

Dataset: Breast Cancer Wisconsin (Diagnostic), bundled with scikit-learn.
  - 569 samples, 30 real-valued features, binary target (malignant / benign).
  - Source: UCI ML Repository (Wolberg et al.).

Split:
  - 60% train, 20% validation, 20% test (stratified, fixed seed).
  - Validation is used for a light hyperparameter sanity check; the test set is
    touched exactly once for the final held-out metrics.

Artifact: a single sklearn Pipeline(StandardScaler -> LogisticRegression) saved
to model/model.joblib, plus model/metadata.json with metrics and the feature
contract.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.datasets import load_breast_cancer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(HERE, "..", "model")
MODEL_PATH = os.path.join(MODEL_DIR, "model.joblib")
META_PATH = os.path.join(MODEL_DIR, "metadata.json")
SEED = 42


def train() -> dict:
    os.makedirs(MODEL_DIR, exist_ok=True)
    data = load_breast_cancer()
    X, y = data.data.astype(float), data.target

    # 60 / 20 / 20 stratified split.
    X_train, X_tmp, y_train, y_tmp = train_test_split(
        X, y, test_size=0.40, random_state=SEED, stratify=y
    )
    X_val, X_test, y_val, y_test = train_test_split(
        X_tmp, y_tmp, test_size=0.50, random_state=SEED, stratify=y_tmp
    )

    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=5000, random_state=SEED)),
        ]
    )
    pipeline.fit(X_train, y_train)

    # Validation sanity check (reported, not used to peek at test).
    val_pred = pipeline.predict(X_val)
    val_f1 = float(f1_score(y_val, val_pred))

    # Final held-out test metrics (touched once).
    test_pred = pipeline.predict(X_test)
    test_proba = pipeline.predict_proba(X_test)[:, 1]
    metrics = {
        "accuracy": float(accuracy_score(y_test, test_pred)),
        "precision": float(precision_score(y_test, test_pred)),
        "recall": float(recall_score(y_test, test_pred)),
        "f1": float(f1_score(y_test, test_pred)),
        "roc_auc": float(roc_auc_score(y_test, test_proba)),
    }

    joblib.dump(pipeline, MODEL_PATH)

    metadata = {
        "model_type": "sklearn Pipeline(StandardScaler + LogisticRegression)",
        "dataset": "Breast Cancer Wisconsin (Diagnostic)",
        "dataset_source": "UCI ML Repository / sklearn.datasets.load_breast_cancer",
        "n_features": int(X.shape[1]),
        "feature_names": list(data.feature_names),
        "target_names": list(data.target_names),
        "split": {"train": len(X_train), "val": len(X_val), "test": len(X_test)},
        "seed": SEED,
        "validation_f1": round(val_f1, 4),
        "test_metrics": {k: round(v, 4) for k, v in metrics.items()},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "classification_report": classification_report(
            y_test, test_pred, target_names=list(data.target_names)
        ),
    }
    with open(META_PATH, "w") as f:
        json.dump(metadata, f, indent=2)

    return metadata


if __name__ == "__main__":
    meta = train()
    print("Trained protected model:")
    print(json.dumps({k: v for k, v in meta.items() if k != "feature_names"}, indent=2))
