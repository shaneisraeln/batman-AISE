# BATMAN Cloud — Deployment & Release Runbook

This is the exact, copy-pasteable path to stand up the BATMAN cloud stack on a
real domain and publish the SDK. Steps that require **owner infrastructure or
credentials** (a domain, a server, PyPI tokens) are called out and stop at that
boundary — they are not performed automatically.

The stack: Caddy (reverse proxy + auto-HTTPS) → landing (`/`), dashboard SPA
(`/app/`), cloud API (`/v1`, `/auth`, `/projects`, `/models`, `/keys`),
PostgreSQL for persistence.

---

## 1. Prerequisites (owner-provided)

- A host with Docker + Docker Compose (a small VM is enough).
- A domain name with an **A/AAAA record pointing at the host's public IP**
  (required for automatic TLS). Ports **80 and 443** must be reachable.
- Optionally, a Groq API key if you want live LLM investigation summaries
  (the `stub` provider works fully offline otherwise).

## 2. Configure secrets

```bash
cp .env.cloud.example .env
```

Fill `.env` with strong values:

```bash
# strong DB password
POSTGRES_PASSWORD=$(python -c "import secrets; print(secrets.token_urlsafe(24))")

# token signing key
BATMAN_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")

# Fernet key for encrypting upstream credentials at rest
BATMAN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
```

Set your domain so Caddy provisions HTTPS automatically:

```bash
# in .env
BATMAN_SITE_ADDRESS=batman.example.com   # <- your real domain
```

Leave `BATMAN_SITE_ADDRESS=:80` (the default) only for local HTTP testing.

> **Never commit `.env`.** It is gitignored.

## 3. Launch

```bash
docker compose -f docker-compose.cloud.yml up --build -d
```

Caddy will obtain and renew Let's Encrypt certificates for the domain on first
boot. Give it up to a minute on the first run.

Verify:

```bash
curl -fsS https://batman.example.com/v1/health        # API health
# open https://batman.example.com/            -> landing
# open https://batman.example.com/app/#/signup -> dashboard onboarding
```

## 4. First developer journey (self-serve, no backend touch)

1. Visit the landing page, click **Get Started** → `/app/#/signup`.
2. Create an account → onboarding wizard walks project → model → API key →
   integrate.
3. Point the model at an upstream prediction endpoint (Models → Configure).
4. Send traffic with the SDK or REST and watch telemetry populate.

## 5. Local smoke test before going public (optional)

Leave `BATMAN_SITE_ADDRESS=:80` and run the same compose command. The stack
serves plain HTTP on `http://localhost/`. The full automated funnel test
(`tests/test_e2e_funnel.py`) already exercises the same signup→predict→feedback
→revoke→logout path in-process.

---

## 6. Publishing the SDK to PyPI — OWNER ACTION

The package (`batman-ml`) is built and verified; publishing needs the owner's
PyPI token and is intentionally manual. Full detail: `sdk/RELEASE.md`.

Build + verify (already green here):

```bash
cd sdk
python -m build
python -m twine check dist/*
```

Publish (requires the owner's PyPI API token — do NOT hardcode it):

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX     # owner's PyPI token

# recommended: TestPyPI dry run first
python -m twine upload --repository testpypi dist/*

# then the real index
python -m twine upload dist/*
```

After publishing, `pip install batman-ml` works for everyone and the SDK/REST
snippets in the dashboard and landing page are accurate as-is.

---

## What is intentionally NOT automated here

| Step | Why it stops at the boundary |
|---|---|
| Pointing DNS at the host | Requires the owner's domain registrar/DNS. |
| Running on a public server | Requires the owner's infrastructure. |
| `twine upload` to PyPI | Requires the owner's PyPI credentials. |

Everything up to these boundaries is built, wired, and tested.


---

## Phase 3 — Docker stack validation (VERIFIED)

The cloud stack was clean-built (`docker compose -f docker-compose.cloud.yml
build --no-cache`) and brought up locally to confirm the whole chain works:

- **Clean build:** all three images built from scratch — `batman-cloud-api`
  (~706 MB; the calibrated detector is trained at image-build time),
  `batman-dashboard` (~218 MB, `VITE_BASE=/app/`), `batman-landing` (~94 MB).
- **Startup ordering:** `postgres` (healthy) → `cloud-api` (healthy) →
  `dashboard` → `landing` → `caddy`. `cloud-api` waits for Postgres via
  `depends_on: condition: service_healthy`.
- **Health:** both `postgres` and `cloud-api` report Docker `healthy`
  (a cloud-api healthcheck hitting `/v1/health` was added this phase).
- **HTTP chain through Caddy on :80:** `GET /v1/health` → `{"status":"ok",...,
  "detector_ready":true}`; `GET /` → landing (200); `GET /app/` → dashboard SPA
  (200).
- **Full persistence path:** `POST /auth/signup` → 200 → token → `GET /auth/me`
  read the user back — confirming Caddy → FastAPI → **PostgreSQL** end to end.

Hardening added to `docker-compose.cloud.yml` this phase: `restart:
unless-stopped` on every service, a `cloud-api` healthcheck, `BATMAN_ENV=production`
(activates the startup config-warning checks), and an explicit
`BATMAN_ALLOW_PRIVATE_UPSTREAM=0` (SSRF guard stays on in production).

> Run the clean build + local bring-up yourself with a throwaway `.env`
> (POSTGRES_PASSWORD, BATMAN_SECRET_KEY, BATMAN_ENCRYPTION_KEY). Tear down with
> `docker compose -f docker-compose.cloud.yml down -v`.
