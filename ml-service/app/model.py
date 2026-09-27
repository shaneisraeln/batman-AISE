"""Model loading and inference wrapper for the protected ML service."""

from __future__ import annotations

import json
import os

import joblib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "..", "model", "model.joblib")
META_PATH = os.path.join(HERE, "..", "model", "metadata.json")


class Model:
    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(
                "model/model.joblib not found. Train it first: python -m app.train"
            )
        self.pipeline = joblib.load(MODEL_PATH)
        self.metadata = {}
        if os.path.exists(META_PATH):
            with open(META_PATH) as f:
                self.metadata = json.load(f)
        self.target_names = self.metadata.get("target_names", ["0", "1"])
        self.n_features = self.metadata.get("n_features")

    def predict(self, X: np.ndarray) -> dict:
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        labels = self.pipeline.predict(X)
        proba = self.pipeline.predict_proba(X)
        return {
            "predictions": labels.tolist(),
            "labels": [self.target_names[int(i)] for i in labels],
            "probabilities": proba.tolist(),
        }
