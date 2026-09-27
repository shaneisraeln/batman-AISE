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


def prepare_breast_cancer(seed: int = 42) -> dict:
    """Reference pool matching the REAL protected ML service (Step 2).

    The behavioral detector must be calibrated against the input distribution it
    will actually see in production. This saves the Breast Cancer training-split
    inputs as datasets/reference_breast_cancer.npz so the detector learns normal
    behavior for THAT service, not the unrelated digits demo.
    """
    from sklearn.datasets import load_breast_cancer

    os.makedirs(DATASETS_DIR, exist_ok=True)
    data = load_breast_cancer()
    X = data.data.astype(float)
    y = data.target
    # Same 60/20/20 split family as the ML service; use the 60% train pool.
    X_train, _, _, _ = train_test_split(
        X, y, test_size=0.40, random_state=seed, stratify=y
    )
    path = os.path.join(DATASETS_DIR, "reference_breast_cancer.npz")
    np.savez_compressed(path, X=X_train, feature_dim=X_train.shape[1])
    return {
        "n_features": int(X.shape[1]),
        "reference_samples": int(X_train.shape[0]),
        "path": path,
    }


def load_reference(name: str = "digits") -> np.ndarray:
    """Load a reference input pool.

    name="digits"        -> datasets/reference.npz            (legacy demo)
    name="breast_cancer" -> datasets/reference_breast_cancer.npz (real service)
    """
    fname = "reference.npz" if name == "digits" else f"reference_{name}.npz"
    path = os.path.join(DATASETS_DIR, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} not found. Run: python -m training.prepare "
            f"({'default' if name == 'digits' else 'then prepare_' + name})"
        )
    return np.load(path)["X"]


if __name__ == "__main__":
    info = prepare()
    print("Prepared demo model + reference dataset:", info)
    bc = prepare_breast_cancer()
    print("Prepared breast-cancer reference pool:", bc)
