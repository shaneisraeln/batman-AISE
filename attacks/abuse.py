"""API abuse generator: high-rate, bursty, and repeated identical requests.

Ground-truth label: ABUSE.
"""

from __future__ import annotations

import numpy as np

from attacks.common import RequestEvent, make_rng


def generate_abuse(
    reference_data: np.ndarray,
    n_sessions: int = 10,
    requests_per_session: tuple[int, int] = (60, 150),
    seed: int = 1,
) -> list[RequestEvent]:
    rng = make_rng(seed)
    ref = np.asarray(reference_data, dtype=float)
    events: list[RequestEvent] = []
    for s in range(n_sessions):
        sid = f"abuse_{seed}_{s}"
        n = int(rng.integers(requests_per_session[0], requests_per_session[1] + 1))
        # Often a single repeated payload hammered at high rate.
        base_idx = int(rng.integers(0, ref.shape[0]))
        base = ref[base_idx]
        for _ in range(n):
            if rng.random() < 0.7:
                x = base  # repeated identical request
            else:
                idx = int(rng.integers(0, ref.shape[0]))
                x = ref[idx]
            dt = float(rng.uniform(0.02, 0.2))  # very high rate / bursts
            events.append(RequestEvent(x.reshape(1, -1), sid, dt, "ABUSE"))
    return events
