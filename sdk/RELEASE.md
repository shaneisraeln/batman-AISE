# Releasing `batman-ml` to PyPI

The SDK is a standalone package under `sdk/` (import name `batman_ml`, distribution
name `batman-ml`). This document is the release runbook. **Publishing requires the
owner's PyPI credentials and is a deliberate, manual step — it is not automated.**

## Pre-publish checklist (all verified)

- [x] Package builds: `python -m build` → sdist + wheel.
- [x] `twine check dist/*` PASSED (both artifacts).
- [x] Clean-install test: wheel installs in a fresh venv pulling only `httpx`
      (+ its transitive deps). No `sklearn`/`numpy`/`fastapi`/server package.
- [x] Import + functional smoke test pass in the clean venv.
- [x] API key never leaked in `repr()` or errors.
- [x] Wheel contains only `batman_ml/*.py` + metadata + LICENSE — no secrets, no tests.
- [x] SDK unit tests pass (13).
- [x] `LICENSE` (MIT) and `README.md` present; version set in `_version.py` + `pyproject.toml`.

## Name availability

`batman-ml` was checked on PyPI and is **available** (`batman` itself is taken by
an unrelated project). Fallback: `batman-shield`.

## Build

```bash
cd sdk
python -m pip install --upgrade build twine
rm -rf dist build *.egg-info        # PowerShell: Remove-Item dist,build,*.egg-info -Recurse -Force
python -m build                      # -> dist/batman_ml-0.1.0.tar.gz + .whl
python -m twine check dist/*
```

## Clean-install verification (recommended before every release)

```bash
python -m venv /tmp/sdktest && /tmp/sdktest/bin/python -m pip install dist/batman_ml-0.1.0-py3-none-any.whl
/tmp/sdktest/bin/python -c "import batman_ml; print(batman_ml.__version__)"
```

## Publish — OWNER ACTION (requires PyPI token; not performed here)

**Do not commit or hardcode the token.** Use a PyPI API token via env var or
`~/.pypirc`. Recommended: test on TestPyPI first.

```bash
# 1) TestPyPI dry run
python -m twine upload --repository testpypi dist/*
python -m pip install --index-url https://test.pypi.org/simple/ --no-deps batman-ml

# 2) Real PyPI (final)
python -m twine upload dist/*
```

Provide the token non-interactively with:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-XXXXXXXX   # the owner's PyPI API token
python -m twine upload dist/*
```

## Post-publish

- Tag the release: `git tag sdk-v0.1.0 && git push --tags`.
- Bump `sdk/batman_ml/_version.py` and `sdk/pyproject.toml` for the next version.

## Note on the license-metadata warning

`python -m build` emits a setuptools deprecation notice about the
`license = { text = "MIT" }` table form. It is non-blocking and the build
succeeds; a future cleanup can switch to the SPDX string form
(`license = "MIT"`) once the toolchain baseline supports it everywhere.
