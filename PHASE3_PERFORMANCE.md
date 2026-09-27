# BATMAN Phase 3 — Performance Check

**Goal:** quantify the per-request latency overhead BATMAN adds in front of a
real ML model, and confirm it is acceptable for the MVP.

**Method (VERIFIED, executed):** the real `ml-service` (breast-cancer
`LogisticRegression`) on `:9000` and the BATMAN cloud API on `:8100`, both local.
`experiments/perf_overhead.py` sends the **same** legitimate 30-feature request
200 times each way (15 warmup), measuring wall-clock latency:

- **DIRECT** → `POST :9000/predict` (client straight to the model)
- **BATMAN** → `POST :8100/v1/predict` (client → BATMAN → model, full path:
  auth → behavioral features → detection → policy → telemetry → upstream proxy)

Rate limits were raised for the run so the limiter did not throttle the loop
(pure overhead, not back-pressure).

> This is a single-process localhost micro-benchmark of **per-request
> overhead**, not a load/throughput/soak test.

---

## A performance defect was found and fixed

**Initial measurement (before fix):**

```
DIRECT  ml-service   p50=3.89ms  p95=5.62ms
BATMAN  ->ml-service p50=415.42ms p95=450.78ms   ← ~100x
```

Investigation (isolating with `analyze_only=true`, which runs
detection+policy+telemetry but skips the upstream call) showed:

```
analyze_only (no upstream) p50=29.6ms      ← BATMAN's own detection cost (fine)
full (with upstream)       p50=417.3ms      ← the extra ~388ms was the proxy hop
```

**Root cause:** the data-plane `/v1/predict` built a **new `HTTPModelAdapter`
(new httpx client → new TCP connection) on every request** and closed it. On
this platform a fresh connection per request cost ~380 ms.

**Fix (cloud layer only — Phase 1 engine untouched):** cache one upstream
adapter per `(model_id, config-version)` in the cloud app so the connection pool
is reused across requests; a changed upstream config transparently supersedes
the cached adapter. (`batman/cloud/app.py`, `_get_adapter`.)

---

## Results (after fix, VERIFIED)

| Path | p50 | p95 | mean |
|---|---:|---:|---:|
| DIRECT → ml-service | **3.9 ms** | 5.3 ms | 4.0 ms |
| BATMAN → ml-service (full) | **34.5 ms** | 40.6 ms | 35.1 ms |
| **Overhead** | **+30.6 ms** | +35.3 ms | +31.1 ms |

- BATMAN's detection-only cost (`analyze_only`) is ~30 ms p50, consistent with
  the Phase 1 detector measurement (~24 ms p95 for the detector alone; the extra
  is feature extraction + policy + telemetry write + FastAPI overhead).
- The upstream proxy hop, with connection pooling, now adds only a few ms on top.
- 12x improvement on the full path from the fix (417 ms → 34.5 ms p50).

## Assessment

~31 ms of overhead per request to add behavioral monitoring, anomaly +
extraction detection, policy enforcement, and request-traceable telemetry in
front of a model is **acceptable for the MVP** and for typical ML inference
(where the model itself is often tens to hundreds of ms). No further
optimization is pursued now, per "don't optimize prematurely."

## Honest limitations of this measurement

- Localhost, single process, single client — not a concurrent load test.
  Throughput under concurrency and tail latency at load are **NOT** measured
  here.
- SQLite telemetry (synchronous write on the request path). Under high
  concurrency, PostgreSQL + async/batched telemetry writes would matter — future
  work.
- Memory was not rigorously profiled; the cloud-api image is ~706 MB (includes
  sklearn + the trained detector), and per-request memory is dominated by the
  detector already resident in RAM.
- The in-memory rate limiter and session state are per-process (documented in
  SECURITY_AUDIT_PHASE3.md); horizontal scaling needs a shared store.

**Recommended perf follow-ups (next phase, not now):** concurrent load test
(throughput + tail latency), async/batched telemetry, and a PostgreSQL-backed
run under load.
