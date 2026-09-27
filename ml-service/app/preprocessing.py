"""Preprocessing shared by training and inference.

The pipeline (StandardScaler + classifier) is saved as a single artifact, so
inference applies exactly the same transform seen at training time. This module
holds the feature contract: names, order, and dimensionality.
"""

from __future__ import annotations

from sklearn.datasets import load_breast_cancer

# Load once to expose the canonical feature contract.
_DATA = load_breast_cancer()

FEATURE_NAMES: list[str] = list(_DATA.feature_names)
N_FEATURES: int = len(FEATURE_NAMES)
TARGET_NAMES: list[str] = list(_DATA.target_names)  # ["malignant", "benign"]


def feature_contract() -> dict:
    return {
        "n_features": N_FEATURES,
        "feature_names": FEATURE_NAMES,
        "target_names": TARGET_NAMES,
    }
