# BATMAN — Phase 2 Implementation Plan (Productization)

**Rule honored:** the validated Phase 1 detection engine (Isolation Forest,
extraction detector, rules, threat evidence, policy engine, agents, RAG, LLM
boundary, behavioral features, calibration) is **preserved unchanged**. Phase 2
wraps it in a product; it does not rewrite it.

---

## 1. Audit — what Phase 1 already provides

| Component | File | Reuse in Phase 2 |
|---|---|---|
| Security engine (full pipeline) | `batman/engine.py` | **Reuse as-is** — the data plane calls this. |
| SDK (in-process) | `batman/sdk.py` | Kept for local/embedded use; **new lightweight HTTP client** added separately. |
| Model adapters | `batman/adapters.py`, `batman/adapters_http.py` | **Reuse** — `HTTPModelAdapter` is the existing-ML-API proxy. |
| API keys | `batman/gateway/auth.py` | **Extend** — add `user_id`, `last_used_at`, name; keep hashing/constant-time/revocation. |
| Gateway (FastAPI) | `batman/gateway/app.py` | **Extend** — add control-plane routes; keep `/v1/predict` data plane. |
| Validation / rate limit | `batman/gateway/validation.py`, `rate_limit.py` | **Reuse.** |
| Persistence | `batman/telemetry/store.py` (SQLite, hardcoded) | **Abstract** behind an interface; add PostgreSQL backend; keep SQLite for dev. |
| Telemetry schema | `batman/telemetry/schema.py` | **Preserve semantics**; add tenancy columns (project/model already present). |
| Dashboard | `dashboard/` (React+Vite, polls `/v1/*`) | **Extend** into the professional console + auth + new sections. |
| Docker | `Dockerfile`, `ml-service/Dockerfile`, `docker-compose.yml` | **Extend** — add PostgreSQL + API + dashboard + reverse proxy. |
| Tests | `tests/` (49) + `ml-service/tests/` (6) = 55 | **Must not regress**; add SDK/API/security tests. |

### Key architectural findings
1. **The current SDK runs the whole engine in-process** (imports `engine`,
   detectors, sklearn, agents). A *distributable* SDK must be the opposite: a
   **thin HTTP client** with near-zero deps that calls the hosted API. → New
   client package, separate from the server. This is the single most important
   Phase 2 boundary.
2. **`TelemetryStore` hardwires SQLite** and also stores API keys. Phase 2 needs
   a persistence abstraction (repository interface) with SQLite (dev) and
   PostgreSQL (prod) implementations, plus new tables for users/projects/models.
3. **No `user_id`/tenant concept yet.** Keys map to `project_id`/`model_id`
   strings only. Phase 2 introduces `users → projects → models → api_keys` and
   enforces tenant isolation on every control-plane and query endpoint.
4. **No upstream-config concept.** Existing-ML-API protection needs a per-model
   record (URL, method, auth, req/resp mapping, timeout) with **encrypted**
   upstream credentials. The `HTTPModelAdapter` already does the proxying.

---

## 2. PyPI name availability (checked)

| Name | Status |
|---|---|
| `batman` | **taken** (old deployment toolbelt) |
| `batman-ml` | **available** ✅ (primary choice) |
| `batman-shield` | available (fallback) |

**Decision:** distribute the client as **`batman-ml`**, import name `batman_ml`
(distinct from the server's `batman` package to avoid collision). Public API:

```python
from batman_ml import protect, BatmanClient
protected = protect(model=my_model, api_key="bm_live_xxx", base_url="https://api...")
pred = protected.predict(X)
```

---

## 3. Files to create / modify

### New — SDK client package (`sdk/`, standalone, its own pyproject)
- `sdk/pyproject.toml` (name `batman-ml`, deps: `httpx` only)
- `sdk/batman_ml/__init__.py`, `client.py`, `errors.py`, `_version.py`
- `sdk/README.md`, `sdk/LICENSE`, `sdk/examples/`, `sdk/tests/`

### New — persistence + tenancy (`batman/db/`)
- `batman/db/base.py` (repository interface + models: User, Project, Model, ApiKey, UpstreamConfig)
- `batman/db/sqlite_repo.py` (dev; wraps/extends existing store)
- `batman/db/postgres_repo.py` (prod; SQLAlchemy)
- `batman/db/migrations/` (Alembic) — create tables without destroying dev data

### New — control plane (`batman/cloud/`)
- `batman/cloud/app.py` (FastAPI: auth, projects, models, keys, upstream config)
- `batman/cloud/authn.py` (user auth: signup/login, session/JWT)
- `batman/cloud/tenancy.py` (project/model isolation guards)
- `batman/cloud/crypto.py` (upstream-credential encryption via Fernet)

### Modify (additive, non-breaking)
- `batman/gateway/auth.py` — extend `APIKeyRecord` (user_id, name, last_used_at)
- `batman/gateway/app.py` — data-plane `/v1/predict` resolves upstream config per model
- `batman/telemetry/store.py` — implement the repository interface (keep behavior)

### New — dashboard sections (`dashboard/src/`)
- Auth (login/signup), Projects, Models, API Keys, Analytics, Settings, Docs
- Environment badges (DEV/STAGING/PROD/CONTROLLED TEST)

### New — landing page (`landing/`) + docs (`docs/product/`)

### New — deployment
- `docker-compose.prod.yml` (api + postgres + dashboard + caddy/nginx reverse proxy)

---

## 4. Architectural conflicts & resolutions

| Conflict | Resolution |
|---|---|
| SDK currently pulls the whole engine | New standalone thin client package; leave `batman.sdk` for embedded use. |
| Store hardwires SQLite + mixes keys/telemetry | Repository abstraction; SQLite default, Postgres for prod; keep telemetry semantics. |
| No tenancy in keys/telemetry | Add users/projects/models; enforce isolation in every query. Telemetry already carries project_id/model_id. |
| Upstream credentials | Encrypt at rest (Fernet key from env/secret); never log or return. |
| LLM must stay advisory | Unchanged — control plane never touches the decision path; policy engine remains authoritative. |
| Don't duplicate detector logic | Hosted data plane calls the same `SecurityEngine`. |

---

## 5. Execution order (matches the brief)

1. ✅ Audit + this plan
2. SDK productionization (`batman-ml` thin client) + tests
3. PostgreSQL persistence layer + migrations (SQLite preserved)
4. User/project/model model + extended API-key management
5. Hosted BATMAN API (control plane + reused data plane) + tenant isolation
6. Existing-ML-API proxy config (encrypted upstream creds)
7. End-to-end cloud tests + **re-run Phase 1 suite (no regression)**
8. Professional dashboard (auth-gated, real data, env labels)
9. Landing page
10. Documentation
11. Deployment infra + security audit
12. Clean SDK install test + PyPI prep (**stop at publish boundary**) + final E2E

---

## 6. Guardrails carried through every step

- No fabricated metrics or dashboard data; controlled tests labeled explicitly.
- API keys hashed, shown once, constant-time verify, revocable, never logged.
- Upstream credentials encrypted, never exposed.
- Tenant isolation on all reads/writes.
- HTTPS + rate limiting + input validation + request-size limits for public API.
- Phase 1 detection engine untouched; 55 existing tests must stay green.
- No Kubernetes, no unnecessary microservices, no extra agents/LLMs.
