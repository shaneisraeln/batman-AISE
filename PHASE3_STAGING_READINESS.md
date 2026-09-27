# BATMAN Phase 3 — Staging Deployment Readiness

**Purpose:** state exactly how close BATMAN is to a live public/staging
deployment, what has been verified, and the single remaining owner action.
Nothing here is fabricated — no DNS, domain, certificate, or cloud host is
invented.

Labels: **VERIFIED** (actually executed) · **BLOCKED BY OWNER INFRASTRUCTURE**
(ready, needs an asset only the owner controls) · **NOT VERIFIED** (cannot be
checked without that asset).

---

## What is VERIFIED (locally, Phase D)

The entire deployable stack was clean-built and run end to end on this machine:

- Clean `--no-cache` build of all three images (cloud-api, dashboard, landing).
- Full stack up: `postgres` (healthy) → `cloud-api` (healthy) → `dashboard` →
  `landing` → `caddy`, correct health-gated ordering.
- HTTP routing through Caddy on `:80`: `/v1/health` (200, detector ready),
  `/` (landing, 200), `/app/` (dashboard SPA, 200).
- Full persistence path through the stack: `POST /auth/signup` → PostgreSQL →
  token → `GET /auth/me` read-back.

See `docs/DEPLOYMENT.md` → "Phase 3 — Docker stack validation" for the evidence.

**Conclusion:** the deployment artifacts (Dockerfiles, compose, Caddy, env
wiring) are correct and self-contained. Deploying to a real host is a
configuration + infrastructure step, not a code step.

---

## What is BLOCKED BY OWNER INFRASTRUCTURE

Public staging on a real domain requires assets only the owner can provide.
These are intentionally NOT fabricated:

| Requirement | Why blocked |
|---|---|
| A domain name (e.g. `staging.batman.example`) | Owner's registrar/DNS account. |
| DNS A/AAAA record → host public IP | Requires the domain + a host IP. |
| A host/VM with Docker + ports 80/443 open | Owner's cloud account/server. |
| Public HTTPS certificate | Caddy auto-provisions via Let's Encrypt **once** a real domain resolves to the host — cannot be issued for a fake domain. |

**HTTPS auto-provisioning:** config-ready but **NOT VERIFIED** — it is impossible
to verify Let's Encrypt issuance without a real, resolvable domain pointing at a
reachable host. The Caddyfile uses `{$BATMAN_SITE_ADDRESS::80}`; setting
`BATMAN_SITE_ADDRESS` to a real domain switches Caddy from local HTTP to
automatic HTTPS with zero further changes.

---

## Exact remaining owner action (copy-paste)

On a host with Docker and ports 80/443 reachable, DNS already pointing at it:

```bash
git clone <repo> && cd BATMAN
cp .env.cloud.example .env
# Fill .env with STRONG values:
#   POSTGRES_PASSWORD=$(python -c "import secrets;print(secrets.token_urlsafe(24))")
#   BATMAN_SECRET_KEY=$(python -c "import secrets;print(secrets.token_urlsafe(48))")
#   BATMAN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
#   BATMAN_SITE_ADDRESS=staging.batman.example      # your real domain
#   BATMAN_CORS_ORIGINS=https://staging.batman.example
#   BATMAN_ENV=production
#   BATMAN_ALLOW_PRIVATE_UPSTREAM=0

docker compose -f docker-compose.cloud.yml up --build -d
```

Then verify (owner, against the live domain):

```bash
curl -fsS https://staging.batman.example/v1/health          # {"status":"ok",...}
# browse https://staging.batman.example/            -> landing
# browse https://staging.batman.example/app/#/signup -> dashboard onboarding
```

Post-deploy checklist for the owner:
- Confirm the padlock / valid TLS chain in a browser.
- Confirm `BATMAN_ENV=production` startup logs show **no** config warnings
  (see `batman/cloud/prodcheck.py`).
- For multiple API instances, add a shared/edge rate limiter (the built-in
  limiter is per-process — see SECURITY_AUDIT_PHASE3.md).

---

## Status summary

| Item | Status |
|---|---|
| Deployment artifacts (Docker/compose/Caddy/env) | **VERIFIED** locally |
| Full stack bring-up + HTTP + persistence | **VERIFIED** locally |
| Public domain + DNS | **BLOCKED BY OWNER INFRASTRUCTURE** |
| Public HTTPS (Let's Encrypt) | config-ready · **NOT VERIFIED** (needs real domain) |
| Live public staging URL | **BLOCKED BY OWNER INFRASTRUCTURE** |
