# BATMAN — Render Backend Environment Variables

These are the environment variables the BATMAN cloud API (`batman.cloud.app:app`)
reads. Set them on the Render **Web Service** (Dashboard → the service →
Environment), or via `render.yaml` for the non-secret ones.

**Never commit real secret values.** Only variable names + safe placeholders
appear here and in Git.

## Table

| Variable | Required | Secret | Purpose |
|---|---|---|---|
| `BATMAN_DATABASE_URL` | **Yes** | **Yes** | Neon PostgreSQL connection string, e.g. `postgresql://USER:PASSWORD@ep-xxx.REGION.aws.neon.tech/DB?sslmode=require`. BATMAN auto-creates its schema on boot. |
| `BATMAN_SECRET_KEY` | **Yes** | **Yes** | Signing secret for stateless HMAC session tokens. Render can generate it (`generateValue: true`). If unset, the app falls back to an insecure dev key — never acceptable in production. |
| `BATMAN_ENCRYPTION_KEY` | **Yes** | **Yes** | Fernet key that encrypts stored upstream credentials. Must be a valid Fernet key: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. If missing, storing an upstream secret fails closed (503) — it is never stored in plaintext. |
| `BATMAN_CORS_ORIGINS` | **Yes** | No | Comma-separated allowed browser origins. Set to the exact Vercel URL, e.g. `https://batman-dashboard.vercel.app`. **Never `*`.** No trailing slash. |
| `BATMAN_ENV` | Recommended | No | `production` in prod. Enables startup config-warning checks (flags dev secret, localhost CORS, SQLite, private-upstream-on). |
| `BATMAN_MODE` | No (default `enforce`) | No | `enforce` (apply BLOCK/RATE_LIMIT) or `monitor` (detect + log only). |
| `BATMAN_DETECTOR_PATH` | No (has default) | No | Path to the calibrated Isolation-Forest detector. Use `models/isolation_forest_breast_cancer.joblib` — the Docker image trains it at build time. |
| `BATMAN_LLM_PROVIDER` | No (default `stub`) | No | `stub` (offline, no external calls), or `groq`/`bedrock` (needs a key). Keep `stub` for a zero-cost deploy. |
| `BATMAN_ALLOW_PRIVATE_UPSTREAM` | No (default `0`) | No | Leave **`0`** in production — keeps the SSRF guard on (blocks upstream URLs pointing at loopback/private/metadata addresses). Set `1` only if your protected model is on a trusted private network. |
| `GROQ_API_KEY` | No | Yes (if used) | Only if `BATMAN_LLM_PROVIDER=groq`. Omit for the free stub deploy. |
| `BATMAN_MAX_PREDICT_ROWS` | No (default `1000`) | No | Max rows per `/v1/predict` request (DoS bound). |
| `BATMAN_MAX_PREDICT_COLS` | No (default `4096`) | No | Max features per row (DoS bound). |
| `BATMAN_RL_RPM` | No (default `60`) | No | Per-key requests/minute for `/v1/predict`. |
| `BATMAN_RL_BURST` | No (default `10`) | No | Per-key burst allowance. |
| `PORT` | Auto (Render sets it) | No | Render injects this; the Docker CMD binds `0.0.0.0:$PORT` (falls back to 8100 locally). Do **not** set it manually on Render. |

## Minimal set for a free production deploy

```
BATMAN_DATABASE_URL      = <Neon connection string>        (secret)
BATMAN_SECRET_KEY        = <generated>                      (secret)
BATMAN_ENCRYPTION_KEY    = <Fernet key>                     (secret)
BATMAN_CORS_ORIGINS      = https://<your-app>.vercel.app
BATMAN_ENV               = production
BATMAN_DETECTOR_PATH     = models/isolation_forest_breast_cancer.joblib
BATMAN_LLM_PROVIDER      = stub
BATMAN_ALLOW_PRIVATE_UPSTREAM = 0
```

## How they map to `render.yaml`

- Non-secret values (`BATMAN_ENV`, `BATMAN_MODE`, `BATMAN_DETECTOR_PATH`,
  `BATMAN_LLM_PROVIDER`, `BATMAN_ALLOW_PRIVATE_UPSTREAM`) are set directly in
  `render.yaml`.
- Secrets and the CORS origin use `sync: false` (you enter them in the Render
  UI): `BATMAN_DATABASE_URL`, `BATMAN_ENCRYPTION_KEY`, `BATMAN_CORS_ORIGINS`.
- `BATMAN_SECRET_KEY` uses `generateValue: true` (Render mints a strong random
  value).

## Security notes

- Real values for the three secrets must exist **only** in Render's env store —
  never in Git, source, the frontend bundle, or docs.
- `BATMAN_CORS_ORIGINS` is not a secret but must be the exact production origin.
- The frontend never receives any of these; the only frontend build-time var is
  `VITE_API_BASE` (the public Render URL), set on Vercel.
