# BATMAN Phase 3 — SDK Finalization & PyPI Status

## Phase H — SDK finalization (VERIFIED)

Package: **`batman-ml`** (import `batman_ml`), version **0.1.0**, MIT licensed,
`requires-python >= 3.9`, single runtime dependency **`httpx`**.

Verified this phase:

- **Fresh build:** `python -m build` → `batman_ml-0.1.0-py3-none-any.whl` +
  `batman_ml-0.1.0.tar.gz`. (The setuptools license-metadata deprecation notice
  is non-blocking and documented in `sdk/RELEASE.md`.)
- **`twine check dist/*` → PASSED** for both wheel and sdist.
- **Clean-venv install (VERIFIED):** in a brand-new virtualenv, `pip install`
  of the wheel pulled **only** `httpx` + its transitive deps
  (anyio, certifi, h11, httpcore, idna, typing_extensions). **No** `sklearn`,
  `numpy`, `fastapi`, or any server package — the SDK stays lightweight.
- **Documented API works (VERIFIED)** in that clean env:
  - `import batman_ml; batman_ml.__version__ == "0.1.0"`
  - `protect(api_key=..., base_url=...)` → `ProtectedModel`
  - `BatmanClient(api_key=..., base_url=...)` constructs; the API key is **not**
    present in `repr()` (redacted)
  - An invalid key format raises `AuthenticationError`
- **SDK unit tests:** 13 passed.
- **Metadata / README / LICENSE:** present and consistent (name, version,
  Python versions, `httpx` dependency, project URLs).

The README quickstart and the dashboard's integration snippets match the actual
public API (`protect`, `BatmanClient`, `x-api-key`, `POST /v1/predict`).

## Phase I — PyPI publication (BLOCKED BY OWNER CREDENTIALS)

Everything up to the publish boundary is done and verified. Publishing requires
the owner's PyPI API token and is intentionally **not** performed here — no
token is fabricated.

**Status: PyPI publication ready — owner token required.**

Exact owner action (from `sdk/RELEASE.md`):

```bash
cd sdk
python -m build
python -m twine check dist/*

export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX      # owner's PyPI API token

# recommended dry run first
python -m twine upload --repository testpypi dist/*
# then the real index
python -m twine upload dist/*
```

Post-publish verification the owner should run:

```bash
python -m venv /tmp/verify && /tmp/verify/bin/pip install batman-ml
/tmp/verify/bin/python -c "import batman_ml; print(batman_ml.__version__)"   # 0.1.0
```

Until published, the wheel installs directly from `sdk/dist/` (as verified
above). Nothing in the dashboard or docs claims the package is already on PyPI.
