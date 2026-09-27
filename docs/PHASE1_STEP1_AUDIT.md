# BATMAN — Phase 1 / Step 1: Repository Audit & Implementation Report

**Date:** 2026-09-26
**Scope:** Read-only audit of the existing prototype + plan for real ML-service integration.
**Rule observed:** No productization. No rewrites of working components. Existing tests preserved.

---

## 1. Baseline (verified, not assumed)

| Item | Status | Evidence |
|---|---|---|
| Test suite | **44 passed** | `pytest -q` → `44 passed, 1 warning in 13.04s` |
| Dashboard build | **passing** | `npm run build` → 836 modules, built in ~5.5s |
| Trained victim model | present | `models/demo_model.joblib` (4.7 MB) |
| Trained detector | present | `models/isolation_forest.joblib` (2.9 MB) |
| Reference dataset | present | `datasets/reference.npz` (56 KB) |
| Docker | present | `Dockerfile`, `dashboard/Dockerfile`, `docker-compose.yml` |

Previously observed detection metrics (from `evaluation/experiments.py`, synthetic replay):
Rules-only F1 ≈ 0.036 · IsolationForest F1 ≈ 0.967 · BATMAN hybrid F1 ≈ 0.975 · Generalization A→B F1 ≈ 0.950 · detector latency ≈ 17 ms mean / 22 ms p95.
**These are synthetic-replay numbers and will be re-derived against the real service in Steps 5–6.**

---

## 2. Component inventory

### Core security engine — `batman/`
- **`engine.py`** — `SecurityEngine.analyze_request()` runs the full pipeline: rate-limit → validate → session update → feature extraction → rules → IsolationForest → extraction detector → detection agent → orchestrator (investigation + policy) → **model call** → telemetry. Returns `(decision, model_output, event)`.
- **`sdk.py`** — `BATMAN(model=..., api_key=..., mode=...)`, `.predict()`, `.analyze()`. Wraps a model in-process.
- **`adapters.py`** — `ModelAdapter` interface + `SklearnAdapter`, `CallableAdapter`, `to_adapter()`. **This is the clean seam for HTTP proxying.**
- **`config.py`** — env-driven settings (DB path, mode, LLM provider, thresholds, rate limits).
- **`types.py`** — `Action`, `ThreatLevel`, `ThreatType`, `ThreatEvidence`, `Explanation`, `SecurityDecision`.

### Gateway — `batman/gateway/`
- **`app.py`** — FastAPI app via `create_app(model=..., enable_llm=...)`. Routes:
  `POST /v1/predict`, `POST /v1/feedback`, `GET /v1/threats`, `GET /v1/threats/{id}`, `GET /v1/metrics`, `GET /v1/health`, `POST /v1/keys`.
  Default instance loads a **local joblib model in-process** (`_default_model()`).
- **`auth.py`** — `bm_live_` keys, SHA-256 hashed, constant-time verify, revoke, expiry.
- **`validation.py`** — schema/dtype/dimension/NaN/Inf/bounds/payload checks.
- **`rate_limit.py`** — sliding-window + burst limiter.

### Detection — `batman/detection/`
`base.py` (interface), `isolation_forest.py` (train + calibrated threshold + normalization bounds), `extraction.py` (behavioral probing detector), `rules.py` (deterministic rules).

### Features — `batman/features/`
`extractor.py`, `behavioral.py` (17 canonical features, vectorized), `session.py` (bounded per-session state + warmup).

### Agents — `batman/agents/`
`detection_agent.py`, `investigation_agent.py` (RAG+LLM, deterministic fallback), `response_agent.py`, `orchestrator.py` (deterministic flow, per-session LLM cooldown, policy authoritative).

### RAG / LLM — `batman/rag/`, `batman/llm/`
`retriever.py` (memory/Chroma), `embeddings.py` (hashing default, sentence-transformers scaffold), `knowledge_base.py`; `provider.py` (stub/groq/bedrock with fallback), `prompts.py`.

### Policy — `batman/policy/engine.py`
Authoritative level→action mapping; high-severity rules take precedence; monitor mode downgrades blocking.

### Telemetry — `batman/telemetry/`
`store.py` (SQLite: api_keys, telemetry, feedback), `schema.py`, `logger.py` (redacts secrets).

### Feedback — `batman/feedback/service.py`
Validated labels, stored separately from immutable telemetry.

### Supporting
- **`attacks/`** — `normal.py`, `abuse.py`, `extraction.py` (strategies A/B), `anomalies.py`, `common.py`. Produce `RequestEvent` sequences.
- **`training/`** — `prepare.py` (digits victim model + reference pool), `train.py` (IF detector), `replay.py` (events → behavioral features via the real extractor).
- **`evaluation/`** — `metrics.py`, `experiments.py` (baselines A/B/C, generalization, latency, drift), `drift.py` (PSI).
- **`scripts/`** — `demo.py`, `seed_demo.py` (⚠ **seeds telemetry directly** — must be isolated from the real evaluation path in Step 7).
- **`dashboard/`** — React+Vite+Recharts, polls `/v1/metrics`, `/v1/threats`, `/v1/health`.

---

## 3. Key finding — wrap vs. proxy

**Current:** BATMAN protects a model **in-process** — the gateway loads a joblib file and the engine calls `self.model.predict(arr)` directly.

**Phase 1 target:** BATMAN must sit in front of a **separately deployed real ML inference API** (own service, HTTP).

**Minimal, non-invasive solution:** the engine already talks only to the `ModelAdapter` interface. Add an **`HTTPModelAdapter`** that implements `predict()`/`predict_proba()` by calling the real ML service over HTTP. Pass it to `create_app(model=HTTPModelAdapter(...))`. **No engine, policy, detector, or agent changes required.**

This preserves all 44 tests and every working component.

---

## 4. Gaps to close in Phase 1

| Gap | Step |
|---|---|
| No real, separately-deployed ML service | 2 |
| BATMAN wraps in-process instead of proxying to a real API | 3 (`HTTPModelAdapter`) |
| No real legitimate-traffic client hitting the gateway over HTTP | 4 |
| Attacks replay through the extractor, not through the live gateway→ML path | 5 |
| Metrics are single-F1 summaries; no confusion matrix / per-class / p99 | 6 |
| `seed_demo.py` writes telemetry directly (not request-traceable) | 7 |
| Evaluation reproducibility not documented for the real path | 8 |

---

## 5. Plan (Steps 2–8)

1. **Step 2** — `ml-service/`: real dataset (scikit-learn **Breast Cancer Wisconsin**, a genuine tabular binary classification task with a real-world provenance), proper train/val/test split, saved model, FastAPI `/predict` with Pydantic schema, Dockerfile, tests, docs.
2. **Step 3** — `batman/adapters_http.py::HTTPModelAdapter` + a runnable gateway config that proxies to the ML service. Verify allowed→reaches model, blocked→doesn't, rate-limit, telemetry, request/session correlation.
3. **Step 4** — `experiments/normal_client.py`: legitimate client → BATMAN → ML API, measuring latency/overhead/FP/decisions from **real** responses.
4. **Step 5** — `experiments/attack_client.py`: controlled A/B/C/D attacks **against our own** running gateway→ML service, over HTTP.
5. **Step 6** — `evaluation/real_eval.py`: confusion matrix, precision/recall/F1/FPR/TPR, per-class, latency p50/p95/p99, ablation A/B/C/D, generalization A→B — all from the real path.
6. **Step 7** — isolate `seed_demo.py` behind an explicit `CONTROLLED TEST` marker; ensure every dashboard row traces to a real `request_id`.
7. **Step 8** — one-command startup + compose for the full real stack; re-run tests; write `PHASE1_VALIDATION.md`. Stop before Phase 2.

**Nothing above rewrites a working component; all additions are new files plus one new adapter class and gateway wiring.**
