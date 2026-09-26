"""Basic drift detection via the Population Stability Index (PSI).

Compares a reference feature distribution against a recent one, per feature.
PSI < 0.1: no significant shift; 0.1-0.25: moderate; > 0.25: significant.
"""

from __future__ import annotations

import numpy as np


def _psi_for_feature(ref: np.ndarray, cur: np.ndarray, bins: int = 10) -> float:
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size == 0 or cur.size == 0:
        return 0.0
    quantiles = np.linspace(0, 1, bins + 1)
    edges = np.unique(np.quantile(ref, quantiles))
    if edges.size < 2:
        return 0.0
    ref_counts, _ = np.histogram(ref, bins=edges)
    cur_counts, _ = np.histogram(cur, bins=edges)
    ref_pct = ref_counts / max(1, ref_counts.sum())
    cur_pct = cur_counts / max(1, cur_counts.sum())
    eps = 1e-6
    ref_pct = np.clip(ref_pct, eps, None)
    cur_pct = np.clip(cur_pct, eps, None)
    return float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))


def compute_psi(
    reference: np.ndarray, recent: np.ndarray, feature_names: list[str]
) -> dict:
    reference = np.asarray(reference, dtype=float)
    recent = np.asarray(recent, dtype=float)
    per_feature = {}
    for i, name in enumerate(feature_names):
        if i < reference.shape[1] and i < recent.shape[1]:
            per_feature[name] = round(
                _psi_for_feature(reference[:, i], recent[:, i]), 4
            )
    max_psi = max(per_feature.values()) if per_feature else 0.0
    if max_psi > 0.25:
        status = "significant_drift"
    elif max_psi > 0.1:
        status = "moderate_drift"
    else:
        status = "stable"
    return {"status": status, "max_psi": round(max_psi, 4), "per_feature": per_feature}
