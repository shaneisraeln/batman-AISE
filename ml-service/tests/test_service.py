"""Tests for the protected ML inference service."""

import os
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.datasets import load_breast_cancer

# Ensure the service package is importable when run from ml-service/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402
from app.preprocessing import N_FEATURES  # noqa: E402

client = TestClient(app)


def _sample():
    return load_breast_cancer().data[0].tolist()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["model_loaded"] is True
    assert r.json()["n_features"] == N_FEATURES


def test_info_reports_real_metrics():
    r = client.get("/info")
    assert r.status_code == 200
    body = r.json()
    assert body["dataset"].startswith("Breast Cancer")
    assert "test_metrics" in body and body["test_metrics"]["f1"] > 0.8


def test_predict_returns_real_prediction():
    r = client.post("/predict", json={"instances": [_sample()]})
    assert r.status_code == 200
    body = r.json()
    assert len(body["predictions"]) == 1
    assert body["labels"][0] in ("malignant", "benign")
    assert len(body["probabilities"][0]) == 2


def test_predict_batch():
    data = load_breast_cancer().data[:5].tolist()
    r = client.post("/predict", json={"instances": data})
    assert r.status_code == 200
    assert len(r.json()["predictions"]) == 5


def test_wrong_dimension_rejected():
    r = client.post("/predict", json={"instances": [[1.0, 2.0, 3.0]]})
    assert r.status_code == 422  # schema validation


def test_empty_rejected():
    r = client.post("/predict", json={"instances": []})
    assert r.status_code == 422
