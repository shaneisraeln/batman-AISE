"""Behavioral feature computation helpers.

Pure functions over numpy arrays and session history. Features that cannot be
computed for a given model type are marked unavailable rather than fabricated.
"""

from __future__ import annotations

import numpy as np

# Canonical feature ordering used by the detector. Keep in sync with training.
FEATURE_ORDER: list[str] = [
    "request_rate",
    "inter_request_time",
    "session_request_count",
    "request_size",
    "input_mean",
    "input_std",
    "input_min",
    "input_max",
    "input_norm",
    "input_dimension",
    "nan_count",
    "inf_count",
    "unique_input_ratio",
    "duplicate_ratio",
    "query_similarity",
    "prediction_entropy",
    "previous_anomaly_count",
]


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    # Guard against NaN/Inf inputs (e.g. anomalous requests) which would
    # otherwise poison the dot product / norm.
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b))):
        return 0.0
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def input_stats(vec: np.ndarray) -> dict[str, float]:
    finite = vec[np.isfinite(vec)]
    if finite.size == 0:
        return {
            "input_mean": 0.0,
            "input_std": 0.0,
            "input_min": 0.0,
            "input_max": 0.0,
            "input_norm": 0.0,
            "input_dimension": float(vec.size),
        }
    return {
        "input_mean": float(np.mean(finite)),
        "input_std": float(np.std(finite)),
        "input_min": float(np.min(finite)),
        "input_max": float(np.max(finite)),
        "input_norm": float(np.linalg.norm(finite)),
        "input_dimension": float(vec.size),
    }


def _stack_matching(current: np.ndarray, recent_inputs) -> np.ndarray | None:
    """Stack recent inputs matching current's shape into a finite matrix."""
    rows = [
        np.asarray(p, dtype=float).ravel()
        for p in recent_inputs
        if np.asarray(p, dtype=float).ravel().shape == current.shape
    ]
    if not rows:
        return None
    return np.vstack(rows)


def query_similarity(current: np.ndarray, recent_inputs) -> float:
    """Max cosine similarity between the current input and recent inputs.

    Vectorized: computes all cosine similarities against the recent-input
    matrix in one pass.
    """
    if not recent_inputs or not np.all(np.isfinite(current)):
        return 0.0
    M = _stack_matching(current, recent_inputs)
    if M is None:
        return 0.0
    cur_norm = np.linalg.norm(current)
    row_norms = np.linalg.norm(M, axis=1)
    denom = row_norms * cur_norm
    finite_rows = np.all(np.isfinite(M), axis=1) & (denom > 0)
    if not finite_rows.any():
        return 0.0
    sims = np.zeros(M.shape[0])
    sims[finite_rows] = (M[finite_rows] @ current) / denom[finite_rows]
    return float(np.max(sims))


def duplicate_and_unique_ratios(current: np.ndarray, recent_inputs) -> tuple[float, float]:
    """(duplicate_ratio, unique_input_ratio) over the recent-input window.

    Uses rounded byte hashing for O(n) duplicate counting instead of O(n^2)
    pairwise comparison.
    """
    all_inputs = list(recent_inputs) + [current]
    n = len(all_inputs)
    if n <= 1:
        return 0.0, 1.0
    seen: set[bytes] = set()
    duplicates = 0
    for vec in all_inputs:
        vec = np.asarray(vec, dtype=float).ravel()
        # Round to make near-identical floats hash together; NaN-safe via nan_to_num.
        key = np.round(np.nan_to_num(vec, nan=0.0, posinf=1e18, neginf=-1e18), 8).tobytes()
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    duplicate_ratio = duplicates / n
    unique_ratio = len(seen) / n
    return float(duplicate_ratio), float(unique_ratio)


def prediction_entropy(proba: np.ndarray | None) -> float:
    """Shannon entropy of a probability vector; 0.0 if unavailable."""
    if proba is None:
        return 0.0
    p = np.asarray(proba, dtype=float).ravel()
    p = p[p > 0]
    if p.size == 0:
        return 0.0
    return float(-np.sum(p * np.log2(p)))
