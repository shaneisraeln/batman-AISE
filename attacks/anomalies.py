"""Anomalous input generator: out-of-range values, extreme norms, NaN/Inf, and
distribution shifts.

Ground-truth label: ANOMALY.
"""

from __future__ import annotations

import numpy as np

from attacks.common import RequestEvent, make_rng


def generate_anomalies(
    reference_data: np.ndarray,
    n_sessions: int = 8,
    requests_per_session: tuple[int, int] = (3, 12),
    seed: int = 3,
    include_nan_inf: bool = True,
) -> list[RequestEvent]:
    rng = make_rng(seed)
    ref = np.asarray(reference_data, dtype=float)
    dim = ref.shape[1]
    events: list[RequestEvent] = []
    for s in range(n_sessions):
        sid = f"anomaly_{seed}_{s}"
        n = int(rng.integers(requests_per_session[0], requests_per_session[1] + 1))
        for _ in range(n):
            kind = rng.integers(0, 4 if include_nan_inf else 2)
            if kind == 0:  # extreme norm
                x = rng.normal(0, 50.0, size=dim)
            elif kind == 1:  # out-of-range
                x = ref[int(rng.integers(0, ref.shape[0]))] * rng.uniform(8, 20)
            elif kind == 2:  # NaN injection
                x = ref[int(rng.integers(0, ref.shape[0]))].copy()
                x[int(rng.integers(0, dim))] = np.nan
            else:  # Inf injection
                x = ref[int(rng.integers(0, ref.shape[0]))].copy()
                x[int(rng.integers(0, dim))] = np.inf
            dt = float(rng.uniform(0.5, 5.0))
            events.append(RequestEvent(x.reshape(1, -1), sid, dt, "ANOMALY"))
    return events
