# Phase 1 / Step 6 — Detector Validation (real-service distribution)

`evaluation/real_eval.py` — an **offline replay** using the **real** runtime
components (FeatureExtractor, SessionStore, RulesEngine, the breast-cancer
calibrated IsolationForest, and the extraction detector). Attack traffic is
**synthetic/controlled**; the feature pipeline and detector are **real**. Live
telemetry from Steps 4–5 is reported separately (SQLite), never merged here.

**Terminology:** F1, precision, recall, TPR, FPR, and *classification accuracy*
are reported as **distinct** metrics. F1 is never called "accuracy."

## Dataset (labeled, controlled)

30-dim Breast Cancer feature space. 1842 events: NORMAL 312 · ABUSE 840 ·
EXTRACTION 623 · ANOMALY 67.

## Ablation — all classes (strategy A)

| Ablation | Precision | Recall | F1 | FPR | Class. accuracy |
|---|---|---|---|---|---|
| A rules only | 1.00 | 0.018 | 0.035 | 0.00 | 0.184 |
| B IsolationForest only | 0.975 | 0.477 | 0.640 | 0.061 | 0.555 |
| C IF + extraction | 0.975 | 0.483 | 0.646 | 0.061 | 0.560 |
| D full hybrid | 0.976 | 0.500 | 0.661 | 0.061 | 0.574 |

The all-classes F1 (0.66) is **held down by ABUSE**, which the content-based
detector is not designed to catch — see the per-class breakdown and the
detector-scope ablation below.

## Per-class recall (full hybrid)

| Class | Total | Detected | Recall |
|---|---|---|---|
| EXTRACTION | 623 | 522 | **0.838** |
| ANOMALY | 67 | 51 | **0.761** |
| ABUSE | 840 | 192 | 0.229 |

**Why ABUSE recall is low here, and why that is correct:** API abuse is a
rate/frequency attack, not a content anomaly. The abuse payloads are
near-duplicate *valid* values, so the content-based IsolationForest/extraction
detector rightly do not flag them. Abuse is handled by the **deterministic rate
limiter**, which this offline detector-only replay does not exercise. The live
Step-5 run showed the rate limiter throttling **53/80** abuse requests. Charging
abuse against the behavioral detector would misrepresent both layers.

## Ablation — detector scope (EXTRACTION + ANOMALY vs NORMAL; ABUSE excluded)

This isolates the behavioral detector's actual responsibility.

| Ablation | Precision | Recall | F1 | FPR |
|---|---|---|---|---|
| A rules only | 1.00 | 0.039 | 0.075 | 0.00 |
| B IsolationForest only | — | 0.778 | 0.862 | 0.061 |
| C IF + extraction | — | 0.793 | 0.871 | 0.061 |
| **D full hybrid** | — | **0.830** | **0.894** | 0.061 |

The hybrid beats each component. **F1 0.894** on the threats the detector owns,
with a **6.1% false-positive rate**.

## Generalization (train/calibrate on normal; test on UNSEEN extraction strategy B)

| Metric | Value |
|---|---|
| Precision | 0.992 |
| Recall (TPR) | 0.891 |
| F1 | 0.939 |
| FPR | 0.026 |
| Classification accuracy | 0.910 |
| Confusion matrix | TP 615 · FN 75 · FP 5 · TN 191 |

The detector was calibrated on **normal behavior only** and evaluated against a
extraction strategy it never saw. **F1 0.939** — it learned general suspicious
behavior, not one attack pattern. This is the flagship research result and it
holds on the real-service distribution.

## Latency (detector path, offline replay)

| p50 | p95 | p99 | mean | max |
|---|---|---|---|---|
| 18.9 ms | 23.8 ms | 30.2 ms | 19.3 ms | 48.2 ms |

Consistent with the < 50 ms detector target. (End-to-end gateway overhead
including the HTTP hop to the ML service was ~28 ms — see Step 4.)

## Honest summary

- The behavioral detector is **strong on its own scope** (extraction F1 0.894,
  generalization F1 0.939) with a modest 6% FPR.
- **Abuse is a rate-limiter concern**, demonstrated live in Step 5; it is not a
  detector weakness.
- Reporting only the all-classes F1 (0.66) would be misleading; the layered
  breakdown is the truthful representation.

Raw results: `experiments/results_real_eval.json`.
Reproduce: `python -m evaluation.real_eval --json experiments/results_real_eval.json`
