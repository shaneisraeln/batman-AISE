#!/usr/bin/env python3
"""Publish batman-ml SDK package to PyPI or TestPyPI.

Usage:
    python scripts/publish_sdk.py [--repository pypi|testpypi] [--dry-run]
"""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SDK_DIR = REPO_ROOT / "sdk"
DIST_DIR = SDK_DIR / "dist"


def run(cmd: list[str], check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    print(f"==> {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(REPO_ROOT), check=check, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and publish batman-ml to PyPI.")
    parser.add_argument(
        "--repository",
        choices=["pypi", "testpypi"],
        default="pypi",
        help="Repository target (default: pypi)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip rebuilding the wheel and sdist in sdk/dist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run twine check only; do not upload",
    )
    args = parser.parse_args()

    # Step 1: Build package
    if not args.skip_build:
        print("\n--- 1. Building SDK package in sdk/ ---")
        run([sys.executable, "-m", "build", str(SDK_DIR)])

    # Step 2: Twine check
    artifacts = list(DIST_DIR.glob("*.whl")) + list(DIST_DIR.glob("*.tar.gz"))
    if not artifacts:
        print(f"Error: No artifacts found in {DIST_DIR}")
        return 1

    print("\n--- 2. Checking artifacts with twine ---")
    run([sys.executable, "-m", "twine", "check"] + [str(p) for p in artifacts])

    if args.dry_run:
        print("\n[Dry Run] Build and check passed. Skipping upload.")
        return 0

    # Step 3: Get credentials
    token = os.getenv("TWINE_PASSWORD") or os.getenv("PYPI_API_TOKEN")
    if not token:
        # Check .env if present
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("PYPI_API_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
                elif line.startswith("TWINE_PASSWORD="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

    if not token:
        print("\n--- 3. Authentication ---")
        repo_url = "https://pypi.org/manage/account/token/" if args.repository == "pypi" else "https://test.pypi.org/manage/account/token/"
        print(f"PyPI requires an API token to upload packages.")
        print(f"Create one at: {repo_url}")
        print("Note: The token starts with 'pypi-'.")
        token = getpass.getpass("Enter PyPI API Token (hidden): ").strip()
        if not token:
            print("Error: No token provided. Aborting.")
            return 1

    upload_env = os.environ.copy()
    upload_env["TWINE_USERNAME"] = "__token__"
    upload_env["TWINE_PASSWORD"] = token

    # Step 4: Upload
    print(f"\n--- 4. Uploading to {args.repository} ---")
    cmd = [sys.executable, "-m", "twine", "upload"]
    if args.repository == "testpypi":
        cmd.extend(["--repository", "testpypi"])
    cmd.extend([str(p) for p in artifacts])

    result = run(cmd, check=False, env=upload_env)
    if result.returncode == 0:
        print("\n Successfully published to PyPI!")
        if args.repository == "pypi":
            print("Verify installation:")
            print("    pip install --upgrade batman-ml")
        else:
            print("Verify installation from TestPyPI:")
            print("    pip install --index-url https://test.pypi.org/simple/ --no-deps batman-ml")
    else:
        print(f"\n❌ Upload failed with exit code {result.returncode}.")
        return result.returncode

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
