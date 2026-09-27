# BATMAN Phase 3 — External E2E + Real ML Validation

Covers Phase F (full-funnel external E2E) and Phase G (real external ML model
validation). Both were executed live against running services — not mocked.

**Setup (this machine, clean DB):**
- `ml-service` (real `StandardScaler + LogisticRegression` on Breast Cancer
  Wisconsin) started with `uvicorn app.main:app --port 9000`. Health:
  `{"status":"ok","model_loaded":true,"n_features":30}`.
- BATMAN cloud API started with `uvicorn batman.cloud.app:app --port 8100`,
  a **fresh SQLite DB** (`batman_phase3_e2e.db`, deleted afterward — no dev data),
  `BATMAN_ALLOW_PRIVATE_UPSTREAM=1` (the model is on localhost),
  `BATMAN_DETECTOR_PATH=models/isolation_forest_breast_cancer.joblib`, stub LLM.
  Health: `{"status":"ok","mode":"enforce","detector_ready":true,...}`.
- Driver: `python -m experiments.verify_cloud_e2e` (a real HTTP client + the
  `batman-ml` SDK), plus a targeted upstream-failure probe.

The client only ever talked to the API over HTTP; it never touched the database
directly.

---

## Phase F — Full funnel (VERIFIED)

Actual script output:

```
[1] signed up + logged in as dev+24994@example.com
[2] project/model created; upstream set -> http://127.0.0.1:9000/predict (200)
[3] minted key bm_live_2kp62D…
[4] SDK predict -> action=LOG prediction=[0] request_id=req_1e96c421e1a6…
[5] extraction burst actions: {'LOG': 9, 'ALLOW': 4, 'RATE_LIMIT': 42, 'BlockedError': 65}
[6] tenant metrics: total=121 active_threats=107 threat_rows=50
[7] feedback recorded (HTTP 200); listed=True on_detail=True
[8] revoked key -> HTTP 401 (expect 401)
[9] post-logout (no token) -> HTTP 401 (expect 401)
RESULT: PASS
```

| # | Funnel step | Result |
|---|---|---|
| 1 | Discover / signup / login | **VERIFIED** — real account, real token |
| 2 | Create project + register model | **VERIFIED** |
| 3 | Configure upstream → real ml-service | **VERIFIED** (200) |
| 4 | Generate API key (shown once, `bm_live_`) | **VERIFIED** |
| 5 | Integrate via SDK + send legitimate inference | **VERIFIED** — SDK returned a real prediction `[0]` |
| 6 | Upstream actually receives the request | **VERIFIED** — prediction is the ml-service's real output |
| 7 | Controlled suspicious traffic (extraction burst) | **VERIFIED** |
| 8 | Detection generates real telemetry | **VERIFIED** — total=121, active_threats=107, 50 threat rows |
| 9 | Policy enforcement | **VERIFIED** — 65 BLOCK (403) + 42 RATE_LIMIT |
| 10 | Event visible via dashboard API (metrics/threats) | **VERIFIED** — tenant-scoped metrics/threats populated |
| 11 | Submit analyst feedback | **VERIFIED** — recorded, listed, attached to threat detail |
| 12 | Revoke API key | **VERIFIED** |
| 13 | Reuse revoked key | **VERIFIED** — 401 |
| 14 | Logout → protected route | **VERIFIED** — no token → 401 |

> Note on the UI layer: the dashboard's data path (the `/v1/metrics`,
> `/v1/threats`, `/v1/feedback` APIs it renders) is exercised here and by the
> Vitest suite; a human clicking through the rendered pages against this live
> stack was **not** separately scripted (the API responses the pages consume are
> verified).

---

## Phase G — Real external ML model (VERIFIED)

The chain **Client → BATMAN → real ML API → prediction → telemetry → dashboard
data** was exercised end to end above. Specifics:

- **Legitimate requests work:** the SDK received `prediction=[0]` — the genuine
  output of the deployed `LogisticRegression` pipeline, proxied through BATMAN.
- **Telemetry recorded:** 121 requests produced tenant-scoped metrics and 50
  threat rows, each request-traceable.
- **Suspicious traffic detected + enforced:** the extraction burst produced 65
  BLOCK and 42 RATE_LIMIT decisions from the policy engine.
- **Upstream errors handled safely and distinctly:** pointing the model at a
  non-existent upstream path returned **HTTP 502 `upstream_error`** — NOT a
  false threat and NOT a 200. This confirms BATMAN separates:
  - **BATMAN detection** → `403` (policy BLOCK) / `429` (rate limit), and
  - **upstream model failure** → `502` (`upstream_error`).
- **Latency:** acceptable for the MVP; a quantified overhead measurement is in
  Phase K (PHASE3_PERFORMANCE.md).

The ml-service is a real, independently-running model API (not a
frontend-only mock): BATMAN reaches it over HTTP exactly as it would any
third-party model.

---

## Honest scope notes

- Run **locally**, not against a public domain (public deploy is BLOCKED BY
  OWNER INFRASTRUCTURE — see PHASE3_STAGING_READINESS.md). The funnel logic is
  identical regardless of host; only the base URL differs.
- `BATMAN_ALLOW_PRIVATE_UPSTREAM=1` was set because the model is on localhost.
  In production the SSRF guard stays ON and the upstream is a public/allowed
  host.
- The throwaway DB was deleted after the run; no development database was used
  or mutated.
