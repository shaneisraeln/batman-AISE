# Phase 1 / Step 7 — End-to-End Telemetry Traceability (verified)

**Requirement:** every dashboard event must trace back to a real request that
passed through BATMAN. No seeded / fabricated dashboard records in the real
evaluation path.

## Verifier: `experiments/verify_telemetry.py`

Sends real requests through the live gateway, then independently reads the
SQLite DB to confirm traceability.

### Result (PASS)

| Check | Result |
|---|---|
| Requests acknowledged with a `request_id` | 35 |
| Threat rows retrievable via `GET /v1/threats/{id}` | 34/34 |
| Total telemetry rows (independent DB read) | 55 |
| Rows missing `request_id` | **0** |
| Rows missing `timestamp` | **0** |
| DEMO-prefixed rows in the real DB | **0** |
| Spot-check: a sent `request_id` resolves to a stored row | **True** |

Every telemetry row corresponds to an actual request processed by BATMAN, and
each is retrievable by its request_id. There are no untraceable or phantom rows.

## Demo seeder isolated — `scripts/seed_demo.py`

The demo seeder previously wrote to the same DB the real path uses. It is now
fully isolated so it can never be confused with real-service telemetry:

- Writes to its **own database** `batman_demo.db` (set before any settings load).
- **Every session id is prefixed `DEMO-`.**
- Runs the in-process SDK against the local *demo* model (digits) — explicitly
  NOT the real protected ML service.
- The module docstring states it must not be used for validation metrics.

### Isolation proof

```
real batman.db DEMO rows      : 0     (must be 0)  ✓
batman_demo.db total rows     : 757
batman_demo.db non-DEMO rows  : 0     (must be 0)  ✓
```

The demo path and the real evaluation path share no data.

## Provenance summary (Phase 1)

| Source | Path | Traceable | Where |
|---|---|---|---|
| Legitimate traffic | client → live gateway → real ML API | yes (request_id) | `batman.db` |
| Controlled attacks | client → live gateway → real ML API | yes (request_id, `CTRL-*`) | `batman.db` |
| Offline detector eval | replay of real components | n/a (metrics only) | `experiments/results_real_eval.json` |
| Demo dashboard | in-process SDK, demo model | isolated (`DEMO-*`) | `batman_demo.db` |

Reproduce: `python -m experiments.verify_telemetry` (with the live stack running).
