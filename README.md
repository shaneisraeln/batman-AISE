# 🦇 BATMAN

**Behavioral AI Threat Monitoring and Mitigation for ML Models**

A lightweight, model-agnostic runtime security gateway for ML inference APIs. BATMAN sits between a client and a protected model and combines deterministic security controls, behavioral machine learning, a small multi-agent investigation layer, RAG + LLM explanation, and policy-based enforcement.

> **Core principle:** Detect with ML. Explain with AI. Enforce with policy. Improve through validated feedback.

---

## What it does

BATMAN analyzes **behavior across inference requests** rather than treating each request independently. It is designed to detect:

- API abuse (excessive / bursty / repeated requests)
- Anomalous inputs (out-of-range, extreme norms, NaN/Inf)
- **Model-extraction / probing** behavior (high-volume, high-diversity, systematic query sequences)

For each request it produces a structured decision: `ALLOW`, `LOG`, `RATE_LIMIT`, `BLOCK`, or `ESCALATE`.

---

## Architecture

```
Client → Gateway (auth · validation · rate limit)
       → Feature Extraction (behavioral, per-session)
       → Detection (rules + Isolation Forest + extraction detector)
       → Detection Agent (structured ThreatEvidence)
       → Orchestrator → Investigation Agent (RAG + LLM)  [only when needed]
       → Response Agent → Policy Engine (authoritative)
       → Enforcement → Model (if allowed) → Telemetry
```

The **policy engine is authoritative**. Deterministic rules and rate limiting form a security floor that remains active even if the ML detector, RAG, or LLM fail. The LLM never becomes the sole security decision-maker.

---

## Quick start

### 1. Install (Python 3.11)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Optional extras: `.[llm]` (Groq/Bedrock), `.[rag]` (Chroma), `.[embeddings]` (sentence-transformers), or `.[all]`.

### 2. Prepare the demo model + train the detector

```powershell
python -m training.prepare   # trains a RandomForest victim model on sklearn `digits`
python -m training.train     # trains + calibrates the Isolation Forest detector
```

### 3a. Protect a model via the SDK

```python
import joblib
from batman import BATMAN

model = joblib.load("models/demo_model.joblib")
shield = BATMAN(model=model, api_key="bm_live_xxx", mode="enforce")

result = shield.predict(X)          # normal traffic → allowed, prediction returned
print(result.action, result.threat_type, result.prediction)
```

Modes: `monitor` (detect + log, never block) or `enforce` (apply policy).

### 3b. Or run the gateway

```powershell
uvicorn batman.gateway.app:app --reload --port 8000
```

Endpoints: `POST /v1/predict`, `POST /v1/feedback`, `POST /v1/keys`, `GET /v1/threats`, `GET /v1/threats/{id}`, `GET /v1/metrics`, `GET /v1/health`.

### 4. Dashboard

```powershell
cd dashboard
npm install
npm run dev        # http://localhost:5173  (proxies /v1 → :8000)
```

### 5. Run the demo scenario

```powershell
python -m scripts.demo                       # drives the engine directly
python -m scripts.demo --http http://localhost:8000   # drives the running gateway
```

---

## Configuration

Copy `.env.example` to `.env`. Everything has safe defaults — the system runs with a **stub LLM and lightweight embeddings**, no external services required.

| Variable | Default | Purpose |
|---|---|---|
| `BATMAN_MODE` | `enforce` | `monitor` or `enforce` |
| `BATMAN_LLM_PROVIDER` | `stub` | `stub` / `groq` / `bedrock` |
| `GROQ_API_KEY` | — | Groq key (free tier) for LLM explanations |
| `BEDROCK_MODEL_ID` | Claude Haiku | Amazon Bedrock model |
| `BATMAN_EMBEDDINGS_BACKEND` | `hashing` | `hashing` (no heavy deps) or `sentence_transformers` |
| `BATMAN_VECTOR_STORE` | `memory` | `memory` or `chroma` |

If a configured LLM/embeddings backend is unavailable, BATMAN falls back automatically so enforcement never breaks.

---

## Evaluation

```powershell
python -m evaluation.experiments
```

Runs three baselines and the flagship generalization test on controlled attack traces:

| Experiment | Precision | Recall | F1 | FPR |
|---|---:|---:|---:|---:|
| **A** — Rules only | 1.00 | 0.02 | 0.04 | 0.00 |
| **B** — Isolation Forest | 0.99 | 0.95 | 0.97 | 0.07 |
| **C** — BATMAN (rules + ML + extraction) | 0.99 | 0.96 | **0.97** | 0.07 |
| Generalization (train strat A → test strat B) | 0.99 | 0.92 | 0.95 | 0.05 |

*(Representative numbers from a local run; regenerate with the command above.)*

- **Detector-path latency:** ~17 ms mean, ~22 ms p95 (target < 50 ms).
- **Drift:** PSI-based feature-distribution comparison (`evaluation/drift.py`).

The takeaway: behavioral ML adds substantial recall over deterministic rules alone, and the hybrid generalizes to an unseen extraction strategy.

---

## Docker

```powershell
docker compose up --build
# gateway → http://localhost:8000 , dashboard → http://localhost:4173
```

---

## Testing

```powershell
pytest -q
```

Covers authentication, validation, rate limiting, feature extraction, detectors, policy, telemetry/feedback, RAG, agents, and full SDK + gateway integration.

---

## Design notes

- **Behavioral warmup.** The anomaly detector reasons over per-session behavioral history. During a session's first few requests that history is empty, so the anomaly signal alone cannot escalate to a block — deterministic rules and the volume-dependent extraction detector are unaffected. This encodes the PRD intent to detect behavior *across* requests, not in isolation.
- **Calibrated, not probabilistic.** Isolation Forest decision scores are min-max normalized to `[0,1]`; they are **not** presented as calibrated probabilities. The operational threshold is calibrated against a normal validation set to a target false-positive rate.
- **Evidence, not certainty.** The extraction detector and agents report weighted evidence rather than claiming an attack is definitive.

---

## Limitations

BATMAN is a one-week academic research prototype. It deliberately does **not**:

- guarantee protection against every cyberattack, or zero false positives/negatives;
- replace a WAF, SIEM, EDR, IAM, or cloud-security platform;
- secure operating systems, networks, or cloud infrastructure;
- guarantee detection of every adversarial example, or provide comprehensive adversarial defense;
- perform autonomous online learning — feedback is stored for **future** evaluation, never used to auto-retrain and deploy;
- provide enterprise IAM, a model registry, or multi-cloud deployment.

The Isolation Forest thresholds and extraction-detector weights are tuned on synthetic/controlled traffic and **must be recalibrated** for any real workload. Session state and rate limiting are in-memory (single-process) in this MVP; a production deployment would need a shared store (e.g. Redis) and PostgreSQL telemetry.

---

## Repository layout

```
batman/        core package: gateway, features, detection, agents, rag, llm, policy, telemetry, feedback, sdk, engine
attacks/       controlled traffic simulators (normal, abuse, extraction, anomalies)
training/      demo model + detector training, trace replay
evaluation/    metrics, baseline experiments, drift
dashboard/     React + Vite + Recharts security dashboard
scripts/       demo driver
tests/         pytest suite
```
