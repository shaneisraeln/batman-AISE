# BATMAN — Product Requirements Document

## Behavioral AI Threat Monitoring and Mitigation for ML Models

**Version:** 2.0  
**Status:** Proposed / MVP  
**Target:** One-week academic research prototype

---

## 1. Product Overview

BATMAN is a lightweight, model-agnostic runtime security layer for machine-learning inference systems.

It sits between a client and an ML model/API and combines:

- deterministic runtime security controls,
- behavioral machine learning,
- specialized security agents,
- retrieval-augmented generation (RAG),
- an LLM for threat explanation,
- policy-based response,
- human feedback,
- production telemetry and monitoring.

BATMAN is designed to detect suspicious inference behavior, especially API abuse, anomalous requests, systematic probing, and model-extraction behavior.

BATMAN does not replace the protected ML model and is not intended to secure every part of an organization's cybersecurity infrastructure.

---

## 2. Problem Statement

ML models exposed through APIs can be abused through excessive requests, anomalous inputs, systematic probing, model extraction, and adversarial inputs.

Traditional API security can identify malformed requests, authentication failures, and excessive traffic, but it does not necessarily understand whether a sequence of otherwise valid ML queries is suspicious from the model's perspective.

BATMAN addresses this gap by analyzing **behavior across inference requests**, rather than treating every API request independently.

---

## 3. Product Vision

> Build a lightweight security gateway that understands how an ML model is being queried, detects suspicious inference behavior, explains why it is suspicious, and applies an appropriate response.

### Central Research Question

> **Can behavioral ML detect suspicious activity against a black-box ML inference API using request and session behavior without requiring access to the model's internal parameters?**

---

## 4. Goals

### Primary Goals

1. Protect ML inference APIs at runtime.
2. Detect anomalous inference behavior.
3. Detect systematic probing/model-extraction behavior.
4. Combine deterministic security controls with behavioral ML.
5. Provide explainable threat analysis through agents, RAG, and an LLM.
6. Apply configurable security responses.
7. Collect structured telemetry for evaluation and future improvement.
8. Provide measurable experimental results.

### Secondary Goals

- Provide a simple Python SDK.
- Provide a gateway/proxy deployment.
- Provide a lightweight security dashboard.
- Support human analyst feedback.
- Monitor changes in inference traffic.

---

## 5. Non-Goals

BATMAN will not attempt to:

- guarantee protection against every cyberattack;
- replace a WAF, SIEM, EDR, IAM, or cloud-security platform;
- secure operating systems or cloud infrastructure;
- guarantee detection of every adversarial example;
- inspect every part of the ML lifecycle;
- automatically retrain itself from every production request;
- replace the underlying ML model;
- guarantee zero false positives or false negatives.

---

## 6. Target Users

### ML Developers
Need an easy way to protect inference endpoints without modifying the model.

### ML Engineers
Need behavioral monitoring and security telemetry.

### Security Analysts
Need alerts, explanations, evidence, and response controls.

### Researchers
Need a platform for evaluating ML-specific inference attacks and defenses.

---

## 7. User Journey

```text
Developer integrates BATMAN
        ↓
Client sends inference request
        ↓
BATMAN authenticates and validates
        ↓
Behavioral features are extracted
        ↓
ML detector analyzes behavior
        ↓
Security agents investigate
        ↓
RAG retrieves relevant security context
        ↓
LLM generates explanation
        ↓
Policy engine selects response
        ↓
ALLOW / LOG / RATE_LIMIT / BLOCK
        ↓
Request reaches ML model if allowed
        ↓
Telemetry is stored
        ↓
Analyst can provide feedback
```

---

## 8. Product Architecture

```text
Client
  │
  ▼
┌──────────────────────────────┐
│       BATMAN Gateway         │
│ Authentication               │
│ Input Validation             │
│ Rate Limiting                │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Feature Extraction      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│     Behavioral ML Engine     │
│ Anomaly Detection            │
│ Extraction/Probing Signals   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│      Agent Orchestrator      │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
   Detection  Threat   Response
     Agent   Analysis   Agent
                │
           ┌────┴────┐
           ▼         ▼
          RAG       LLM
           │         │
           └────┬────┘
                ▼
           Explanation
                │
                ▼
        ┌───────────────┐
        │ Policy Engine │
        └───────┬───────┘
                │
       ┌────────┼─────────┐
       ▼        ▼         ▼
     ALLOW    LIMIT      BLOCK
       │
       ▼
    ML Model
       │
       ▼
   Telemetry
       │
   ┌───┴─────────┐
   ▼             ▼
Monitoring     Feedback
```

---

## 9. Core Security Controls

### API Authentication

Each protected application/project receives an API key.

Requirements:

- cryptographically random keys;
- hashed storage;
- revocation support;
- project/model association;
- optional expiration;
- raw keys must never be logged.

The API key identifies the client/project. It is not the security detector itself.

### Input Validation

BATMAN validates:

- request schema;
- input dimensions;
- data types;
- missing values;
- NaN/Inf;
- payload size;
- unexpected fields;
- configurable value ranges.

### Rate Limiting

BATMAN supports:

- per-key limits;
- per-client/session limits;
- rolling-window limits;
- burst limits.

---

## 10. Behavioral Intelligence

BATMAN's primary research component is behavioral analysis.

### Candidate Features

**Request behavior**
- request frequency;
- inter-request time;
- session request count;
- request size;
- burst rate.

**Input behavior**
- input mean;
- input variance;
- minimum/maximum;
- input norm;
- dimensionality;
- NaN/Inf count;
- input diversity.

**Query relationship**
- duplicate ratio;
- similarity between consecutive inputs;
- query diversity;
- progressive probing behavior.

**Model response behavior, where available**
- prediction confidence;
- prediction entropy;
- prediction distribution;
- class-frequency changes.

**Session behavior**
- unique input ratio;
- repeated-query ratio;
- rolling request rate;
- previous anomaly count;
- cumulative threat score.

Not every feature must be used for every model type.

---

## 11. ML Detection

### Primary Detector

**Isolation Forest**

Reason:

- suitable for anomaly detection;
- does not require a large labeled attack dataset;
- supports learning normal behavior;
- suitable for a lightweight prototype.

### Optional Supervised Detector

Random Forest / XGBoost / LightGBM may be evaluated if labeled attack traces are available.

### Research Comparison

1. deterministic rules;
2. ML detector;
3. hybrid rules + ML.

Metrics:

- precision;
- recall;
- F1;
- false-positive rate;
- detection latency;
- throughput/overhead.

---

## 12. Model-Extraction / Probing Detection

Model extraction is a primary BATMAN use case.

The system should detect patterns such as:

- high-volume valid queries;
- high query diversity;
- systematic input variation;
- repeated exploration of decision boundaries;
- suspicious query sequences;
- abnormal prediction harvesting behavior.

The goal is behavioral detection, not proving that every suspicious session is definitively an extraction attack.

---

## 13. Agentic Intelligence

BATMAN uses a small number of purposeful agents.

### Detection Agent

Consumes behavioral ML results, combines detector evidence, identifies suspicious patterns, and produces structured threat evidence.

Tools:
- anomaly detector;
- feature store;
- telemetry database.

### Investigation Agent

Interprets detection evidence, retrieves relevant security knowledge, uses the LLM to produce a human-readable explanation, identifies likely threat category, and identifies uncertainty.

Tools:
- RAG retrieval;
- vector database;
- LLM.

### Response Agent

Interprets policy configuration, selects an allowed response, executes or recommends the response, and escalates uncertain cases.

Possible responses:
- ALLOW;
- LOG;
- RATE_LIMIT;
- BLOCK;
- ESCALATE.

### Orchestrator

The orchestrator:
1. receives detection evidence;
2. invokes the relevant agent;
3. passes structured results between agents;
4. requests investigation when required;
5. invokes the response agent;
6. returns a final security decision.

---

## 14. RAG

BATMAN maintains a small security knowledge base containing:

- model-extraction concepts;
- adversarial ML concepts;
- API abuse;
- security policies;
- detection guidance;
- response procedures;
- relevant security frameworks/references.

A vector store such as FAISS or Chroma may be used.

```text
Threat Evidence
      ↓
Retrieve Relevant Knowledge
      ↓
LLM
      ↓
Threat Explanation
```

RAG provides contextual reasoning and explanation; it does not replace the security detector.

---

## 15. LLM Responsibilities

The LLM should:

- explain why a request/session was flagged;
- summarize evidence;
- provide contextual threat information;
- explain uncertainty;
- recommend an investigation/response rationale.

The LLM should not:

- directly override security controls;
- invent telemetry;
- make unsupported claims;
- independently decide that an attack occurred without detector evidence.

---

## 16. Policy Engine

The policy engine maps threat evidence to configured actions:

```text
LOW       → LOG
MEDIUM    → RATE_LIMIT
HIGH      → BLOCK
UNCERTAIN → ESCALATE
```

Thresholds are configurable and must be evaluated experimentally rather than treated as universal.

Policy decisions may consider:

- threat score;
- confidence;
- attack category;
- request/session history;
- configured sensitivity;
- analyst overrides.

---

## 17. Human-in-the-Loop

For uncertain or high-impact decisions:

```text
BATMAN Alert
     ↓
Analyst Review
     ↓
True Positive / False Positive
     ↓
Feedback Stored
```

Feedback can be used in future evaluation and retraining.

BATMAN should not blindly train on every production request.

---

## 18. Telemetry

Each request should generate structured telemetry.

```json
{
  "timestamp": "...",
  "project_id": "...",
  "model_id": "...",
  "request_id": "...",
  "request_rate": 24,
  "input_norm": 4.82,
  "query_similarity": 0.91,
  "session_requests": 142,
  "anomaly_score": 0.91,
  "threat_type": "MODEL_EXTRACTION",
  "action": "RATE_LIMIT",
  "detector_version": "1.0"
}
```

Privacy principle:

> Store the minimum information required for security analysis and avoid storing sensitive raw inference data unless explicitly configured.

---

## 19. Monitoring

Dashboard should display:

- total requests;
- allowed requests;
- blocked requests;
- rate-limited requests;
- active threats;
- threat categories;
- anomaly scores;
- detection performance;
- detector version;
- traffic trends;
- analyst feedback;
- basic data/model drift indicators.

---

## 20. Continuous Improvement

```text
Production Telemetry
        ↓
Analyst / Controlled Labels
        ↓
Training Dataset
        ↓
Candidate Detector
        ↓
Offline Evaluation
        ↓
Compare Against Current Detector
        ↓
Promote only if quality requirements are met
```

This is a future/improvement workflow rather than an automatic online-learning loop.

---

## 21. Data Strategy

Use a hybrid strategy:

```text
Public security/model-extraction data
            +
Public ML datasets
            +
Controlled attack traces
            +
Validated BATMAN telemetry
```

Victim models can use datasets such as MNIST, CIFAR-10, or suitable tabular classification datasets.

Controlled traces should include:

- normal inference;
- excessive requests;
- systematic probing;
- extraction-style query sequences;
- anomalous inputs;
- optional adversarial examples.

Avoid relying exclusively on trivial synthetic data.

---

## 22. Evaluation Plan

### Flagship Question

> Can behavioral ML detect model-extraction/probing behavior against a black-box inference API while maintaining an acceptable false-positive rate and latency?

### Baselines

**A:** Rules only

**B:** ML anomaly detector

**C:** BATMAN — Rules + ML + behavioral analysis

### Metrics

- Precision
- Recall
- F1
- False Positive Rate
- Detection Latency
- Requests/sec
- Added gateway latency

### Generalization Experiment

Train using one attack strategy and evaluate against a different probing/extraction strategy.

---

## 23. Threat Scenarios

### Normal User
`ALLOW`

### Excessive API Requests
`RATE_LIMIT`

### Model Extraction
`DETECT → INVESTIGATE → RATE_LIMIT/BLOCK`

### Anomalous Input
`DETECT → LOG/BLOCK`

### Uncertain Detection
`LOG → HUMAN REVIEW`

---

## 24. Failure Handling

- Detector unavailable → deterministic controls remain active.
- LLM unavailable → security decision continues using detector/policy evidence.
- RAG unavailable → explanation may be degraded, but gateway remains operational.
- Database unavailable → configurable fallback logging.
- Excessive latency → skip non-critical explanation path.

Security enforcement must not depend exclusively on the LLM.

---

## 25. Deployment

### Python SDK

```python
from batman import BATMAN

shield = BATMAN(
    model=model,
    api_key="bm_live_xxxxx",
    mode="enforce"
)

result = shield.predict(X)
```

### Gateway

```text
Client
  ↓
BATMAN
  ↓
Existing ML API
```

The same detection/policy engine should be shared.

---

## 26. MVP Scope

### Must Have

- Python package;
- API key;
- gateway;
- input validation;
- rate limiting;
- telemetry;
- behavioral feature extraction;
- Isolation Forest;
- model-extraction/probing detection;
- policy engine;
- 3-agent architecture;
- LLM explanation;
- RAG;
- basic dashboard;
- attack simulator;
- evaluation pipeline.

### Nice to Have

- supervised detector;
- adversarial example detection;
- drift detection;
- Docker deployment;
- analyst feedback UI.

### Out of Scope

- autonomous online learning;
- complex model registry;
- enterprise IAM;
- multi-cloud deployment;
- full SIEM integration;
- comprehensive adversarial defense;
- OS/network infrastructure security.

---

## 27. Success Criteria

BATMAN is successful if:

1. It integrates with an ML model without modifying the model.
2. Normal inference traffic passes successfully.
3. Suspicious behavioral patterns are detected.
4. Model-extraction/probing behavior is detectable in controlled experiments.
5. Security actions are applied correctly.
6. The LLM explains detector evidence.
7. RAG provides relevant security context.
8. Human feedback can be recorded.
9. Detection quality is measured against baselines.
10. Runtime overhead is measured.

---

## 28. Seven-Day Plan

**Day 1:** Repository, demo model, SDK, gateway skeleton.

**Day 2:** Authentication, validation, rate limiting, telemetry.

**Day 3:** Feature extraction and behavioral ML.

**Day 4:** Attack simulator and model-extraction detection.

**Day 5:** Agent orchestrator, RAG, LLM explanation.

**Day 6:** Dashboard, policy engine, feedback, integration.

**Day 7:** Testing, experiments, evaluation, Docker, documentation, presentation.

---

## 29. Final Product Definition

> **BATMAN is a model-agnostic runtime inference security gateway that combines deterministic security controls, behavioral machine learning, and agentic threat investigation to detect, explain, and mitigate suspicious behavior targeting ML models.**

**Core principle:**

> **Detect with ML. Explain with AI. Enforce with policy. Improve through validated feedback.**
