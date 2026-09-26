"""Prepare the demo victim model and the reference dataset.

Uses scikit-learn's `digits` dataset (bundled, no download) as a tabular
classification task. Trains a RandomForest victim model and saves:
    models/demo_model.joblib
    datasets/reference.npz   (X reference pool for the attack simulators)
"""

from __future__ import annotations

import os

import joblib
import numpy as np
from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split

MODELS_DIR = "models"
DATASETS_DIR = "datasets"


def prepare(seed: int = 42) -> dict:
    os.makedirs(MODELS_DIR, exist_ok=True)
    os.makedirs(DATASETS_DIR, exist_ok=True)

    data = load_digits()
    X = data.data.astype(float)
    y = data.target

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )

    model = RandomForestClassifier(n_estimators=100, random_state=seed).fit(
        X_train, y_train
    )
    acc = float(model.score(X_test, y_test))

    joblib.dump(model, os.path.join(MODELS_DIR, "demo_model.joblib"))
    # Reference pool for simulators = the training inputs.
    np.savez_compressed(
        os.path.join(DATASETS_DIR, "reference.npz"),
        X=X_train,
        feature_dim=X_train.shape[1],
    )

    return {
        "victim_accuracy": acc,
        "n_features": int(X.shape[1]),
        "reference_samples": int(X_train.shape[0]),
    }


def load_reference() -> np.ndarray:
    path = os.path.join(DATASETS_DIR, "reference.npz")
    if not os.path.exists(path):
        raise FileNotFoundError(
            "datasets/reference.npz not found. Run: python -m training.prepare"
        )
    return np.load(path)["X"]


if __name__ == "__main__":
    info = prepare()
    print("Prepared demo model + reference dataset:", info)
