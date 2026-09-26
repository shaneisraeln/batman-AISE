# BATMAN — Technical Requirements Document

## Behavioral AI Threat Monitoring and Mitigation for ML Models

**Version:** 2.0  
**Status:** Proposed / MVP  
**Target:** One-week academic research prototype

---

# 1. Technical Objective

Build a model-agnostic runtime security system that can be placed in front of an ML inference model/API and:

1. authenticate clients;
2. validate inference requests;
3. rate-limit abusive traffic;
4. extract behavioral features;
5. detect anomalous behavior;
6. identify model-extraction/probing patterns;
7. coordinate specialized security agents;
8. use RAG + LLM for contextual investigation/explanation;
9. apply policy-based responses;
10. collect telemetry and analyst feedback;
11. evaluate security effectiveness and runtime overhead.

---

# 2. Recommended Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| API | FastAPI |
| ML | scikit-learn |
| Primary anomaly model | Isolation Forest |
| Optional supervised model | LightGBM / XGBoost / Random Forest |
| Agent orchestration | Lightweight custom orchestrator |
| LLM | Ollama/local model or cloud LLM |
| Embeddings | Sentence Transformers or equivalent |
| Vector DB | FAISS or Chroma |
| Database | SQLite for MVP / PostgreSQL for deployment |
| Frontend | React + Vite |
| Charts | Recharts |
| Packaging | pyproject.toml |
| Testing | pytest |
| Containerization | Docker |
| Logging | Structured JSON / Python logging |

Avoid introducing a heavy agent framework unless it clearly reduces implementation effort.

---

# 3. Repository Structure

```text
batman/
├── pyproject.toml
├── README.md
├── Dockerfile
├── docker-compose.yml
│
├── batman/
│   ├── __init__.py
│   ├── sdk.py
│   ├── gateway/
│   │   ├── app.py
│   │   ├── auth.py
│   │   ├── validation.py
│   │   └── rate_limit.py
│   ├── features/
│   │   ├── extractor.py
│   │   ├── behavioral.py
│   │   └── session.py
│   ├── detection/
│   │   ├── base.py
│   │   ├── isolation_forest.py
│   │   ├── extraction.py
│   │   └── rules.py
│   ├── agents/
│   │   ├── orchestrator.py
│   │   ├── detection_agent.py
│   │   ├── investigation_agent.py
│   │   └── response_agent.py
│   ├── rag/
│   │   ├── knowledge_base.py
│   │   ├── retriever.py
│   │   └── embeddings.py
│   ├── llm/
│   │   ├── provider.py
│   │   └── prompts.py
│   ├── policy/
│   │   └── engine.py
│   ├── telemetry/
│   │   ├── schema.py
│   │   ├── store.py
│   │   └── logger.py
│   └── feedback/
│       └── service.py
│
├── api/
│   └── routes/
├── dashboard/
├── models/
├── datasets/
├── attacks/
│   ├── normal.py
│   ├── abuse.py
│   ├── extraction.py
│   └── anomalies.py
├── training/
│   ├── prepare.py
│   ├── train.py
│   └── evaluate.py
├── evaluation/
│   ├── metrics.py
│   └── experiments.py
└── tests/
```

---

# 4. Protected Model Interface

BATMAN must support a generic callable model.

```python
class ModelAdapter:
    def predict(self, inputs):
        raise NotImplementedError
```

Example:

```python
class SklearnAdapter(ModelAdapter):
    def __init__(self, model):
        self.model = model

    def predict(self, inputs):
        return self.model.predict(inputs)
```

The security engine must not depend on a specific ML framework.

---

# 5. Python SDK

Target API:

```python
from batman import BATMAN

shield = BATMAN(
    model=model,
    api_key="bm_live_xxxxx",
    mode="enforce"
)

result = shield.predict(X)
```

Modes:

```text
monitor
enforce
```

`monitor` detects and logs without blocking.  
`enforce` applies configured policies.

---

# 6. API Key System

Requirements:

- prefix such as `bm_live_`;
- cryptographically secure random token;
- hash before database storage;
- constant-time verification;
- revocation;
- optional expiration;
- project/model association;
- never log raw keys.

Example:

```json
{
  "key_id": "key_123",
  "key_hash": "...",
  "project_id": "project_1",
  "model_id": "model_1",
  "status": "active",
  "created_at": "...",
  "expires_at": null
}
```

---

# 7. Gateway

FastAPI endpoints:

```text
POST /v1/predict
POST /v1/feedback
GET  /v1/threats
GET  /v1/metrics
GET  /v1/health
```

Prediction flow:

```text
Request
 ↓
Authenticate
 ↓
Validate
 ↓
Rate Limit
 ↓
Extract Features
 ↓
Update Session
 ↓
Behavioral Detection
 ↓
Agent Investigation if required
 ↓
Policy Decision
 ↓
ALLOW?
 ├── No → response
 └── Yes → model.predict()
 ↓
Record telemetry
 ↓
Return response
```

---

# 8. Input Validation

Implement:

```python
validate_request(request)
```

Checks:

- schema;
- required fields;
- data type;
- dimensions;
- payload size;
- NaN;
- Inf;
- configurable bounds.

Validation failures should be recorded as security events.

---

# 9. Rate Limiter

Implement a sliding-window or token-bucket limiter.

Minimum dimensions:

```text
API key
Session
```

Example:

```yaml
rate_limit:
  requests_per_minute: 60
  burst: 10
```

Exceeded limits return:

```http
429 Too Many Requests
```

---

# 10. Behavioral Feature Extraction

Implement:

```python
class FeatureExtractor:
    def extract(self, request, session, response=None):
        ...
```

Candidate features:

```text
request_rate
inter_request_time
session_request_count
request_size
input_mean
input_std
input_min
input_max
input_norm
input_dimension
nan_count
inf_count
unique_input_ratio
duplicate_ratio
query_similarity
confidence
prediction_entropy
prediction_distribution
previous_anomaly_count
```

Features unavailable for a model type should be marked unavailable rather than fabricated.

---

# 11. Session State

Maintain bounded per-client/session state:

```python
SessionState(
    request_count,
    timestamps,
    recent_features,
    recent_inputs,
    anomaly_history,
    prediction_history
)
```

Example bounds:

```text
last 100 requests
last 5 minutes
```

---

# 12. Detection Interface

```python
class Detector:
    def predict(self, features):
        raise NotImplementedError
```

Return:

```json
{
  "is_anomalous": true,
  "score": 0.91,
  "detector": "isolation_forest",
  "version": "1.0"
}
```

Do not present raw Isolation Forest scores as calibrated probabilities unless calibration has actually been performed.

---

# 13. Isolation Forest

Train primarily on normal behavior:

```text
Normal telemetry
      ↓
Feature preprocessing
      ↓
Isolation Forest
      ↓
Anomaly score
```

Requirements:

- save preprocessing configuration;
- save feature ordering;
- version detector artifacts;
- calibrate operational thresholds using validation data.

---

# 14. Model-Extraction Detector

Implement a behavioral detector using signals such as:

```text
request rate
query diversity
query similarity
sequential input variation
session length
prediction distribution
boundary probing indicators
```

Example output:

```json
{
  "threat_type": "MODEL_EXTRACTION",
  "score": 0.84,
  "evidence": [
    "high query diversity",
    "rapid systematic probing",
    "abnormal session length"
  ]
}
```

The detector reports evidence rather than claiming certainty.

---

# 15. Rules Engine

Implement deterministic rules for:

```text
invalid authentication
malformed input
oversized payload
NaN / Inf
hard rate-limit violation
known blocked key
```

Rules remain independent from the LLM.

---

# 16. Hybrid Detection

Combine:

```text
Rules
+
Behavioral ML
+
Extraction signals
```

Do not blindly average scores.

Use a structured object:

```python
ThreatEvidence(
    anomaly_score=...,
    extraction_score=...,
    rule_events=[...],
    confidence=...,
    evidence=[...]
)
```

The policy layer maps evidence to actions.

---

# 17. Agent Orchestrator

Use a lightweight deterministic workflow:

```python
result = orchestrator.handle(threat_evidence)
```

Flow:

```text
Detection Evidence
       ↓
Detection Agent
       ↓
Need Investigation?
   ├── No → Response Agent
   └── Yes
          ↓
   Investigation Agent
          ↓
      RAG + LLM
          ↓
     Explanation
          ↓
    Response Agent
```

The orchestrator must not allow the LLM to bypass deterministic security controls.

---

# 18. Detection Agent

Input:

```text
ThreatEvidence
```

Output:

```json
{
  "threat_type": "MODEL_EXTRACTION",
  "confidence": 0.91,
  "evidence": [...]
}
```

Tools:

- detector outputs;
- telemetry lookup;
- session history.

---

# 19. Investigation Agent

Input:

```text
ThreatEvidence
Session history
Relevant telemetry
```

Process:

```text
Evidence
 ↓
Retrieve knowledge
 ↓
Construct grounded prompt
 ↓
LLM
 ↓
Structured explanation
```

Required output:

```json
{
  "summary": "...",
  "threat_type": "MODEL_EXTRACTION",
  "evidence": [...],
  "uncertainty": "...",
  "recommended_action": "RATE_LIMIT"
}
```

The output must distinguish observed evidence from inference.

---

# 20. RAG Implementation

Knowledge base:

```text
knowledge/
├── model_extraction/
├── adversarial_ml/
├── api_abuse/
├── policies/
└── response_guidance/
```

Pipeline:

```text
Documents
 ↓
Chunk
 ↓
Embed
 ↓
Vector Store
 ↓
Retrieve top-k
 ↓
LLM
```

Recommended starting value:

```text
top_k = 3–5
```

Retrieved context should be included in the investigation prompt.

---

# 21. LLM Provider

Define:

```python
class LLMProvider:
    def generate(self, prompt, context):
        raise NotImplementedError
```

MVP provider:

```text
Ollama
```

Optional cloud provider can be added later.

If the LLM fails, security enforcement continues using detector evidence and policy.

---

# 22. Response Agent

The response agent receives structured evidence and policy configuration.

Actions:

```text
ALLOW
LOG
RATE_LIMIT
BLOCK
ESCALATE
```

The response agent must only choose actions permitted by policy.

The LLM may recommend an action, but the policy engine remains authoritative.

---

# 23. Policy Engine

Example:

```yaml
policies:
  low:
    action: LOG
  medium:
    action: RATE_LIMIT
  high:
    action: BLOCK
uncertain:
  action: ESCALATE
```

Support:

- threat category;
- confidence;
- score;
- mode;
- analyst override.

---

# 24. Telemetry Schema

Minimum event:

```json
{
  "request_id": "...",
  "timestamp": "...",
  "project_id": "...",
  "model_id": "...",
  "session_id": "...",
  "detector_version": "...",
  "features": {},
  "anomaly_score": 0.91,
  "threat_type": "MODEL_EXTRACTION",
  "action": "RATE_LIMIT",
  "latency_ms": 14.2
}
```

Do not store sensitive raw inputs by default.

---

# 25. Feedback API

```http
POST /v1/feedback
```

Example:

```json
{
  "request_id": "...",
  "label": "FALSE_POSITIVE",
  "analyst_note": "Legitimate batch inference"
}
```

Labels:

```text
TRUE_POSITIVE
FALSE_POSITIVE
TRUE_NEGATIVE
FALSE_NEGATIVE
UNCERTAIN
```

Feedback is stored separately from immutable telemetry.

---

# 26. Dashboard

Minimum screens:

### Overview
- requests;
- threats;
- blocked;
- rate limited;
- detection F1.

### Threats
- timestamp;
- threat type;
- score;
- evidence;
- action;
- status.

### Threat Detail
- session timeline;
- behavioral features;
- detector output;
- RAG context;
- LLM explanation;
- policy decision;
- analyst feedback.

### Monitoring
- traffic volume;
- threat rate;
- latency;
- detector performance;
- basic drift indicator.

---

# 27. Attack Simulator

Build controlled generators.

### Normal
Generate realistic benign requests.

### API Abuse
Generate high-rate, burst, and repeated requests.

### Model Extraction / Probing
Generate high-volume valid queries, high diversity, systematic input variation, and boundary exploration.

### Anomalous Inputs
Generate out-of-range values, extreme norms, and distribution shifts.

### Optional Adversarial Inputs
Generate controlled FGSM/PGD examples where supported.

---

# 28. Evaluation Pipeline

```text
Dataset
 ↓
Replay through BATMAN
 ↓
Ground-truth labels
 ↓
Detector predictions
 ↓
Metrics
```

Required metrics:

```text
Precision
Recall
F1
False Positive Rate
Detection Latency
Throughput
Added inference latency
```

---

# 29. Baseline Experiments

### Experiment A
Rules only.

### Experiment B
Isolation Forest.

### Experiment C
BATMAN:
Rules + behavioral ML + extraction signals.

Compare all three.

This demonstrates whether behavioral ML adds value beyond traditional controls.

---

# 30. Generalization Experiment

Train on:

```text
Normal + Attack Strategy A
```

Test on:

```text
Normal + Attack Strategy B
```

Purpose:

Determine whether BATMAN learns general suspicious behavior rather than memorizing one attack pattern.

---

# 31. Drift Monitoring

Basic implementation:

```text
Training feature distribution
        vs
Recent production feature distribution
```

Possible methods:

- PSI;
- KS statistic;
- distribution distance.

For MVP, implement one method.

If drift is detected:

```text
ALERT
↓
Review
↓
Optional retraining
```

Do not automatically retrain and deploy.

---

# 32. Error Handling

### Detector failure
Fallback to rules + rate limiting.

### RAG failure
Continue with detector evidence.

### LLM failure
Continue with detector evidence and policy.

### Telemetry failure
Use local buffered logging or configurable fallback.

### Model failure
Return a controlled inference error without exposing internal exceptions.

---

# 33. Security Requirements

### Secrets
Never hard-code API keys, LLM credentials, or database credentials.

### Logging
Never log raw API keys, secrets, or sensitive raw inference data by default.

### Input Safety
Treat client input as untrusted.

### LLM Safety
Treat threat evidence and retrieved documents as untrusted context.

The LLM must not execute arbitrary tools based solely on retrieved/client content.

---

# 34. Performance Targets

Prototype targets:

| Metric | Target |
|---|---:|
| Deterministic gateway overhead | <10 ms |
| Behavioral detector overhead | <50 ms |
| LLM/RAG path | asynchronous/non-blocking where possible |
| Normal request success | >99% in controlled test |
| Memory | bounded session state |
| Detection throughput | benchmark on local hardware |

LLM explanation latency should not be the required latency for every inference request.

---

# 35. Testing Strategy

### Unit Tests
- API authentication;
- validation;
- rate limiter;
- feature extraction;
- detector;
- policy engine;
- telemetry;
- feedback.

### Model Tests
- training;
- serialization;
- inference;
- threshold calibration;
- reproducibility.

### Agent Tests
- orchestrator flow;
- tool invocation;
- structured output;
- failure handling;
- LLM fallback.

### Integration Tests

```text
Client
 → Gateway
 → Detector
 → Agents
 → Policy
 → Model
 → Telemetry
```

### Attack Tests
Replay all attack scenarios through the complete system.

---

# 36. Definition of Done

- [ ] ML model can be protected through SDK.
- [ ] Gateway accepts authenticated inference requests.
- [ ] Invalid requests are rejected.
- [ ] Rate limiting works.
- [ ] Telemetry is generated.
- [ ] Behavioral features are extracted.
- [ ] Isolation Forest detector works.
- [ ] Extraction/probing detector works.
- [ ] Hybrid policy works.
- [ ] Three agents communicate through orchestrator.
- [ ] RAG retrieves relevant context.
- [ ] LLM generates grounded explanations.
- [ ] LLM failure does not disable security enforcement.
- [ ] Human feedback can be recorded.
- [ ] Dashboard displays threats.
- [ ] Attack simulator generates controlled scenarios.
- [ ] Rules vs ML vs BATMAN evaluation is complete.
- [ ] Latency overhead is measured.
- [ ] Tests pass.
- [ ] Docker deployment works.
- [ ] Documentation explains limitations.

---

# 37. Implementation Order

## Stage 1 — Core Runtime
1. Repository
2. Demo model
3. SDK
4. Gateway
5. API key
6. Validation
7. Rate limiter

## Stage 2 — Detection
8. Telemetry
9. Session state
10. Feature extraction
11. Isolation Forest
12. Rules
13. Extraction detector
14. Policy engine

## Stage 3 — Agentic Layer
15. Orchestrator
16. Detection Agent
17. Investigation Agent
18. RAG
19. LLM
20. Response Agent

## Stage 4 — Product Layer
21. Dashboard
22. Feedback
23. Attack simulator

## Stage 5 — Evaluation
24. Dataset generation
25. Baselines
26. Experiments
27. Metrics
28. Latency benchmark
29. Optional drift detection

## Stage 6 — Finalization
30. Tests
31. Docker
32. Documentation
33. Demo scenario
34. Presentation

---

# 38. Recommended Demo

```text
1. Start protected ML model.
2. Normal user sends requests.
   → BATMAN allows them.
3. Simulated attacker starts systematic probing.
4. Request rate and query behavior change.
5. Behavioral detector flags the session.
6. Detection Agent summarizes evidence.
7. Investigation Agent retrieves model-extraction
   knowledge using RAG.
8. LLM explains the threat.
9. Response Agent invokes policy.
10. BATMAN rate-limits or blocks the attacker.
11. Dashboard shows the incident.
12. Analyst marks the detection as true/false positive.
13. Telemetry is retained for future evaluation.
```

---

# 39. Final Technical Principle

BATMAN maintains a strict separation:

```text
DETERMINISTIC CONTROLS
        ↓
Behavioral ML
        ↓
Threat Evidence
        ↓
Agents
        ↓
RAG + LLM
        ↓
Policy
        ↓
Enforcement
```

- **ML detector:** behavioral intelligence.
- **Agents:** investigation and coordination.
- **RAG + LLM:** context and explanation.
- **Policy engine:** authoritative enforcement.
- **Gateway:** runtime protection.

The LLM must never become the sole security decision-maker.
