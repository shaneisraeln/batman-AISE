# BATMAN — Phase 1 Validation Report

**Objective:** transform BATMAN from a synthetic demonstration into a validated
security system protecting a **real, separately deployed ML inference service**.

**Result: PASS.** All acceptance criteria met with real, executed evidence. No
metric or dashboard event in this report is fabricated — each comes from an
actual run recorded in `experiments/*.json` or the SQLite telemetry store.

> Scope note: this report covers **Phase 1 only**. Productization (SDK/PyPI,
> hosted cloud, landing page, key-management UI, professional dashboard) is
> **NOT** started and is explicitly out of scope until this gate is accepted.

---

## Architecture achieved

```
Client → BATMAN gateway (:8000) → HTTPModelAdapter → ML service (:9000) → real model → prediction
                     ↓
              SQLite telemetry → dashboard
```

The only code change to the core engine was additive: a new `HTTPModelAdapter`
implementing the existing `ModelAdapter` interface. No detector, policy, agent,
or engine logic was rewritten.

---

## Acceptance criteria

### ML service
- [x] **Real dataset** — Breast Cancer Wisconsin (Diagnostic), 569×30, binary.
- [x] **Real trained model** — `Pipeline(StandardScaler+LogisticRegression)`,
      60/20/20 stratified split. Held-out **test F1 0.993**, ROC-AUC 0.997.
- [x] **Real FastAPI inference endpoint** — `POST /predict`, schema-validated.
- [x] **Dockerized** — `ml-service/Dockerfile`, image builds, container healthy.
- [x] **Real predictions verified** — direct and via-BATMAN predictions match.

### BATMAN integration
- [x] **BATMAN sits in front of the ML API** — proxy via `HTTPModelAdapter`.
- [x] **Legitimate requests work** — 197/200 predictions returned, correct.
- [x] **Blocked requests do NOT reach the model** — measured: burst of 30 →
      4 allowed, and the ML service's `predict_calls` counter rose by **exactly 4**.
- [x] **Rate limiting works** — abuse burst → 53/80 rate-limited (Step 5).
- [x] **Telemetry is real** — 415 rows, **0 untraceable**, every row has a
      request_id + timestamp.
- [x] **Dashboard reflects actual requests** — served from the same telemetry
      store; every event resolvable via `GET /v1/threats/{id}`.

### Security validation (controlled, against our OWN service)
- [x] **API abuse tested** — rate limiter throttles it (content detector rightly quiet).
- [x] **Probing tested** — anomaly 0.81, mostly blocked.
- [x] **Extraction tested** — detected fastest (req #5), blocked hardest (94/140),
      highest extraction score (0.45).
- [x] **Anomalous behavior tested** — highest anomaly score (0.87), blocked.
- [x] **Per-class metrics generated** — EXTRACTION recall 0.838, ANOMALY 0.761,
      ABUSE 0.229 (abuse owned by rate limiter, not the content detector).
- [x] **Confusion matrix generated** — in `experiments/results_real_eval.json`.
- [x] **Ablation A/B/C/D generated** — detector-scope: A 0.075 → B 0.862 →
      C 0.871 → **D (hybrid) F1 0.894**; hybrid beats each component.
- [x] **Generalization tested** — calibrated on normal only, tested on **unseen**
      extraction strategy B: **F1 0.939**, recall 0.891, FPR 0.026.
- [x] **Latency measured** — detector path p50 18.9 / p95 23.8 / p99 30.2 ms;
      end-to-end gateway overhead ~28 ms (includes the HTTP hop to the ML API).

### Reproducibility
- [x] **One-command local startup** — `scripts/run_stack.ps1` / `run_stack.sh`.
- [x] **Docker Compose works** — `docker compose build` + `up` verified; both
      containers built, ml-service **Healthy**, gateway proxied a real prediction.
- [x] **Tests pass** — **55 total** (49 BATMAN + 6 ML-service).
- [x] **Evaluation procedure documented** — per-step docs + this report.
- [x] **No fabricated metrics** — every number traces to a recorded run.
- [x] **No fabricated dashboard events** — demo seeder isolated to
      `batman_demo.db` with `DEMO-` prefixes; real DB has **0** demo rows.

---

## Headline results (all measured)

| Area | Result | Source |
|---|---|---|
| Protected model quality | test F1 0.993, ROC-AUC 0.997 | `ml-service/model/metadata.json` |
| Legit false-positive rate | 1.5% | Step 4 |
| Blocked-never-reach-model | exact (`predict_calls` +4 of 4 allowed) | Step 3 |
| Detector scope (extraction+anomaly) | **F1 0.894**, FPR 0.061 | Step 6 |
| Generalization (unseen strategy B) | **F1 0.939**, recall 0.891 | Step 6 |
| Detector latency | p95 23.8 ms | Step 6 |
| End-to-end gateway overhead | ~28 ms | Step 4 |
| Telemetry traceability | 100% (0 untraceable of 415) | Step 7 |
| Tests | 55 passing | Step 8 |
| Docker compose | builds + runs, verified live | Step 8 |

---

## Honest findings & limitations

1. **Per-service detector calibration is mandatory.** The first normal-traffic
   run showed an **80% false-positive rate** because the detector was calibrated
   on the unrelated `digits` distribution. Recalibrating on the real service's
   feature distribution dropped it to **1.5%**. A behavioral detector is only
   valid for the distribution it was calibrated on.
2. **API abuse is a rate-limiter concern, not a content-detector one.** Reporting
   a single aggregate F1 that lumps in abuse (0.66) is misleading; the honest
   figure is the detector-scope F1 (0.894) plus the live rate-limiter result.
3. **Attacker window.** 5–10 requests succeed before behavioral enforcement
   engages — inherent to detecting behavior *across* requests (warmup).
4. **Overhead** is ~28 ms end-to-end because BATMAN adds a network hop to the ML
   service; the detector compute alone is ~17–19 ms.
5. Single-process, in-memory session/rate state and SQLite telemetry — adequate
   for this validation, not for production scale (would need Redis/PostgreSQL).
6. Attack traffic is **controlled/synthetic** and labeled `CTRL-*`; it targets
   only our own service and is never presented as production traffic.

---

## How to reproduce

```powershell
# 1. one-time: train the real model + detectors
python -m training.prepare
python -m training.train --dataset breast_cancer
cd ml-service; python -m app.train; cd ..

# 2. start the real stack (two windows)
.\scripts\run_stack.ps1
#   ML:  http://127.0.0.1:9000/health   BATMAN: http://127.0.0.1:8000/v1/health

# 3. reproduce the experiments
python -m experiments.verify_integration
python -m experiments.normal_client --requests 60
python -m experiments.attack_client --json experiments/results_attacks.json
python -m evaluation.real_eval --json experiments/results_real_eval.json
python -m experiments.verify_telemetry

# or the whole stack in containers
docker compose up --build
```

---

## Gate decision

**Phase 1 acceptance criteria are all satisfied with real evidence.**
BATMAN protects a real, separately deployed ML inference service; legitimate
traffic flows and receives real predictions; controlled attacks are detected and
enforced; metrics are rigorous and honestly scoped; telemetry is fully traceable;
the stack runs by one command and in Docker; 55 tests pass.

**Phase 2 (productization) may now begin — and is intentionally NOT started in
this phase.**
