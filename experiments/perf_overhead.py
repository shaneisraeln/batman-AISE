"""Phase 3 performance probe: BATMAN gateway overhead vs direct ML service.

Measures per-request latency for the SAME legitimate inference, sent two ways:
  (A) DIRECT  -> ml-service  POST :9000/predict {"instances": [[...30...]]}
  (B) BATMAN  -> cloud API   POST :8100/v1/predict {"inputs": [[...30...]]} (x-api-key)

Reports median (p50) and p95 for each, plus absolute + relative overhead.

Prereqs (started externally by the operator/agent):
  - ml-service on :9000
  - BATMAN cloud API on :8100, ideally with BATMAN_RL_RPM/BURST raised so the
    per-key rate limiter does not throttle the measurement loop.

This is a single-process, localhost micro-benchmark to quantify per-request
overhead — NOT a load/throughput test.

Run:  python -m experiments.perf_overhead
"""

from __future__ import annotations

import statistics
import sys
import time

import httpx
from sklearn.datasets import load_breast_cancer

CLOUD = "http://127.0.0.1:8100"
ML = "http://127.0.0.1:9000"
N = 200
WARMUP = 15


def _pctl(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def main() -> int:
    data = load_breast_cancer()
    vec = data.data[0].tolist()  # one real 30-feature sample

    admin = httpx.Client(base_url=CLOUD, timeout=30)
    email = f"perf+{int(time.time())}@example.com"
    admin.post("/auth/signup", json={"email": email, "password": "password123"})
    token = admin.post("/auth/login", json={"email": email, "password": "password123"}).json()["token"]
    H = {"Authorization": f"Bearer {token}"}
    pid = admin.post("/projects", json={"name": "Perf"}, headers=H).json()["project_id"]
    mid = admin.post("/models", json={"project_id": pid, "name": "m"}, headers=H).json()["model_id"]
    admin.put(f"/models/{mid}/upstream",
              json={"url": f"{ML}/predict", "request_format": "instances", "response_format": "predictions"},
              headers=H)
    key = admin.post("/keys", json={"project_id": pid, "model_id": mid}, headers=H).json()["api_key"]

    direct = httpx.Client(base_url=ML, timeout=30)
    gw = httpx.Client(base_url=CLOUD, timeout=30)

    def call_direct():
        r = direct.post("/predict", json={"instances": [vec]})
        r.raise_for_status()

    def call_batman(i):
        r = gw.post("/v1/predict", headers={"x-api-key": key},
                    json={"inputs": [vec], "session_id": f"perf-{i}"})
        r.raise_for_status()

    # Warmup (JIT caches, model warm, connection pools).
    for i in range(WARMUP):
        call_direct(); call_batman(i)

    direct_ms, batman_ms = [], []
    for i in range(N):
        t0 = time.perf_counter(); call_direct(); direct_ms.append((time.perf_counter() - t0) * 1000)
    for i in range(N):
        t0 = time.perf_counter(); call_batman(i); batman_ms.append((time.perf_counter() - t0) * 1000)

    d50, d95 = statistics.median(direct_ms), _pctl(direct_ms, 95)
    b50, b95 = statistics.median(batman_ms), _pctl(batman_ms, 95)

    print(f"samples: {N} (warmup {WARMUP})")
    print(f"DIRECT  ml-service   p50={d50:.2f}ms  p95={d95:.2f}ms  mean={statistics.mean(direct_ms):.2f}ms")
    print(f"BATMAN  ->ml-service p50={b50:.2f}ms  p95={b95:.2f}ms  mean={statistics.mean(batman_ms):.2f}ms")
    print(f"OVERHEAD  p50=+{b50 - d50:.2f}ms  p95=+{b95 - d95:.2f}ms")
    if d50 > 0:
        print(f"OVERHEAD  p50 x{b50 / d50:.2f}  (relative)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
