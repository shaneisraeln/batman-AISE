# Phase 1 / Step 5 — Controlled Security Experiments (measured)

**Scope & ethics:** All attacks target **our own** running BATMAN gateway
(:8000) proxying to **our own** ML service (:9000). This is intentionally
generated, **controlled** attack traffic for a security experiment — not
naturally occurring production traffic. Every attack session is labeled
`CTRL-*` in telemetry so it can never be mistaken for real traffic.

Client: `experiments/attack_client.py`. Every request is a real HTTP call
through the live gateway; results below are from real responses.

## Results

| Experiment | Sent | Allowed | Rate-limited | Blocked | First detection @ | Succeeded before detection | Mean anomaly | Mean extraction |
|---|---|---|---|---|---|---|---|---|
| **A** API abuse | 80 | 27 | 53 | 0 | req #10 | 10 | 0.40 | 0.00 |
| **B** Systematic probing | 80 | 10 | 18 | 52 | req #10 | 10 | 0.81 | 0.25 |
| **C** Model extraction | 140 | 9 | 37 | 94 | req #5 | 5 | 0.80 | 0.45 |
| **D** Anomalous inputs | 60 | 6 | 11 | 43 | req #5 | 5 | 0.87 | 0.22 |

## Reading the results (honest interpretation)

- **A — API abuse** is caught by the **deterministic rate limiter** (53/80
  rate-limited, 0 blocked). The anomaly score stays low (~0.40) because the
  payloads are valid — the problem is *frequency*, not content. This is the
  correct division of labor: rate limiting handles volume abuse; the ML
  detector is not needed.
- **B — Systematic probing** and **C — Model extraction** trigger the
  **behavioral detector**: high anomaly (~0.80) and a rising extraction score
  (0.25 → 0.45). Extraction — the primary BATMAN use case — is detected fastest
  (by request #5) and blocked hardest (94/140). Its extraction score is the
  highest of all experiments, matching its high-diversity input-space sweep.
- **D — Anomalous inputs** produce the highest anomaly scores (0.87) and are
  blocked. Out-of-range / extreme-norm inputs are flagged by the detector and
  (for spikes) the rules.
- **Attacker window:** across all four, only **5–10 requests** succeed before
  BATMAN begins enforcing. This is the honest, measured cost of behavioral
  detection — it needs a few requests of history before the session's behavior
  is unambiguous. (Consistent with the Step-4 warmup design.)

## Telemetry (real, traceable)

- 360 total telemetry rows recorded during the run.
- Threat categories: ANOMALOUS_INPUT 196 · API_ABUSE 61 · MODEL_EXTRACTION 51.
- Actions: ALLOW 16 · LOG 36 · RATE_LIMIT 119 · BLOCK 189.
- **All 308 threat rows are labeled `CTRL-*`** — controlled-test provenance is
  explicit and never presented as production traffic.

## Reproduce

```powershell
# with the real stack running (ML :9000, gateway :8000 + breast_cancer detector)
python -m experiments.attack_client --json experiments/results_attacks.json
```

Raw results: `experiments/results_attacks.json`.
