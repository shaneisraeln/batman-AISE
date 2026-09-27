# Phase 1 / Step 3 — BATMAN ⟶ Real ML API Integration (verified)

**Architecture achieved:**

```
Client → BATMAN gateway (:8000) → HTTPModelAdapter → ML service (:9000) → real prediction
```

## How

- New `batman/adapters_http.py::HTTPModelAdapter` implements the existing
  `ModelAdapter` interface by POSTing to the external ML API's `/predict`.
  **No engine, detector, policy, or agent code changed.**
- Gateway wiring: `BATMAN_PROTECTED_MODEL_URL=http://127.0.0.1:9000` makes the
  default app proxy to the real service (falls back to local joblib if unset).

## Verified (live, `experiments/verify_integration.py`)

| Check | Result |
|---|---|
| Legit request reaches the model | action = LOG/ALLOW, prediction returned |
| BATMAN prediction == ML service prediction | `0 == 0` — genuine proxy, not fabricated |
| Blocked requests do NOT reach the model | burst: 30 sent, 4 allowed, 26 blocked; **ML `predict_calls` rose by exactly 4** |
| Rate limiting activates | burst produced 403s |
| Telemetry generated | 32 rows recorded |
| Every event traceable | legit `request_id` retrievable via `GET /v1/threats/{id}` |

The ML service exposes `GET /stats` (`predict_calls`) purely so the "blocked
requests never reach the model" property can be **measured**, not asserted.

## Tests

- 44 existing tests still pass (no regression).
- +5 new unit tests for `HTTPModelAdapter` (`tests/test_http_adapter.py`) using
  httpx MockTransport. **Total: 49 passing.**

## Run the real stack

```powershell
# terminal 1 — ML service
cd ml-service ; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --port 9000

# terminal 2 — BATMAN proxying to it
$env:BATMAN_PROTECTED_MODEL_URL="http://127.0.0.1:9000"
.\.venv\Scripts\python.exe -m uvicorn batman.gateway.app:app --port 8000

# verify
.\.venv\Scripts\python.exe -m experiments.verify_integration
```
