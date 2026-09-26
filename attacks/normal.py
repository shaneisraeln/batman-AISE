"""Normal (benign) traffic generator.

Samples realistic inputs from a reference distribution at a modest, jittered
request rate. Ground-truth label: NORMAL.
"""

from __future__ import annotations

import numpy as np

from attacks.common import RequestEvent, make_rng


def generate_normal(
    reference_data: np.ndarray,
    n_sessions: int = 20,
    requests_per_session: tuple[int, int] = (1, 15),
    seed: int = 0,
) -> list[RequestEvent]:
    rng = make_rng(seed)
    ref = np.asarray(reference_data, dtype=float)
    events: list[RequestEvent] = []
    for s in range(n_sessions):
        sid = f"normal_{seed}_{s}"
        # Include cold-start / single-request sessions so the detector learns
        # that a lone first request (request_rate=0, session_count=1) is normal.
        n = int(rng.integers(requests_per_session[0], requests_per_session[1] + 1))
        for _ in range(n):
            idx = int(rng.integers(0, ref.shape[0]))
            # Small noise around a real sample.
            x = ref[idx] + rng.normal(0, 0.01, size=ref.shape[1])
            dt = float(rng.uniform(1.0, 8.0))  # relaxed human-like cadence
            events.append(RequestEvent(x.reshape(1, -1), sid, dt, "NORMAL"))
    return events
