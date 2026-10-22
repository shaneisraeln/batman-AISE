#!/usr/bin/env python3
"""Deploy BATMAN to Render.

Supports:
1. Direct Deploy Hook (POST https://api.render.com/deploy/srv-...)
2. Render REST API (with RENDER_API_KEY / rnd_...) to trigger deploy or inspect services
3. 1-Click Blueprint guidance with pre-generated encryption key

Usage:
    python scripts/deploy_render.py
    python scripts/deploy_render.py --deploy-hook https://api.render.com/deploy/srv-...
    python scripts/deploy_render.py --api-key rnd_...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER_API_BASE = "https://api.render.com/v1"
GITHUB_REPO_URL = "https://github.com/shaneisraeln/batman-AISE"


def get_or_generate_encryption_key() -> str:
    try:
        from cryptography.fernet import Fernet
        return Fernet.generate_key().decode()
    except Exception:
        import base64
        import secrets
        return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def trigger_deploy_hook(hook_url: str) -> int:
    print(f"\n==> Triggering Render Deploy Hook: {hook_url}")
    try:
        resp = httpx.post(hook_url, timeout=30.0)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.is_success:
            print("\n Successfully triggered Render deployment!")
            return 0
        else:
            print(f"\n❌ Render deploy hook returned error status {resp.status_code}")
            return 1
    except Exception as exc:
        print(f"\n❌ Failed to trigger deploy hook: {exc}")
        return 1


def trigger_via_api(api_key: str, service_id: str | None = None) -> int:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    client = httpx.Client(base_url=RENDER_API_BASE, headers=headers, timeout=30.0)

    try:
        if not service_id:
            print("\n==> Querying Render services...")
            resp = client.get("/services")
            if not resp.is_success:
                print(f"❌ Failed to query Render services ({resp.status_code}): {resp.text}")
                return 1

            services = resp.json()
            if not services:
                print("No services found in this Render account.")
                return 1

            # Match batman-api
            matched = None
            for item in services:
                svc = item.get("service", item)
                name = svc.get("name", "")
                if "batman" in name.lower():
                    matched = svc
                    break

            if not matched:
                print("Found Render services:")
                for item in services:
                    svc = item.get("service", item)
                    print(f" - ID: {svc.get('id')} | Name: {svc.get('name')} | Type: {svc.get('type')}")
                print("\nPlease specify --service-id <id>")
                return 1

            service = matched
            service_id = service["id"]
            name = service.get("name")
            service_url = service.get("serviceDetails", {}).get("url") or f"https://{name}.onrender.com"
            print(f"Found service: {name} (ID: {service_id})")
            print(f"Public URL: {service_url}")

        print(f"\n==> Triggering deploy for service {service_id}...")
        deploy_resp = client.post(f"/services/{service_id}/deploys", json={"clearCache": "do_not_clear"})
        if deploy_resp.is_success:
            deploy_data = deploy_resp.json()
            deploy_id = deploy_data.get("id")
            status = deploy_data.get("status")
            print(f"\n Deployment initiated!")
            print(f"Deploy ID: {deploy_id}")
            print(f"Status: {status}")
            print(f"Dashboard: https://dashboard.render.com/web/{service_id}/deploys/{deploy_id}")
            return 0
        else:
            print(f"❌ Deploy trigger failed ({deploy_resp.status_code}): {deploy_resp.text}")
            return 1

    except Exception as exc:
        print(f"❌ Error communicating with Render API: {exc}")
        return 1
    finally:
        client.close()


def print_manual_guide():
    fernet_key = get_or_generate_encryption_key()
    blueprint_url = f"https://dashboard.render.com/blueprint/new?repo={GITHUB_REPO_URL}"

    print("=" * 72)
    print(" BATMAN -> Render Cloud Deployment")
    print("=" * 72)
    print("\nOption 1: 1-Click Render Blueprint (Recommended)")
    print(f"1. Open this link in your browser:")
    print(f"   {blueprint_url}")
    print("\n2. Render will automatically read 'render.yaml' and configure 'batman-api'.")
    print("\n3. When prompted in the Render Dashboard, fill in these Environment Variables:")
    print(f"   - BATMAN_ENCRYPTION_KEY : {fernet_key}")
    print(f"   - BATMAN_DATABASE_URL    : (Paste your Neon PostgreSQL URL, or leave blank to test with SQLite)")
    print(f"   - BATMAN_CORS_ORIGINS   : (Your frontend URL, or '*' for initial testing)")
    print("   - BATMAN_SECRET_KEY      : (Render generates this automatically)")
    print("\n4. Click 'Apply' to start building.")
    print("   Render will build the Docker container and start your API service.")
    print("\n" + "-" * 72)
    print("Option 2: Automated Deploy via CLI/Script")
    print("If you have a Render API Key or Deploy Hook, you can run:")
    print("   python scripts/deploy_render.py --api-key <rnd_...>")
    print("   or")
    print("   python scripts/deploy_render.py --deploy-hook https://api.render.com/deploy/srv-...")
    print("=" * 72)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy BATMAN backend to Render.")
    parser.add_argument("--deploy-hook", help="Render deploy hook URL (https://api.render.com/deploy/srv-...)")
    parser.add_argument("--api-key", help="Render API key (rnd_...)")
    parser.add_argument("--service-id", help="Render service ID (srv-...)")
    args = parser.parse_args()

    hook = args.deploy_hook or os.getenv("RENDER_DEPLOY_HOOK")
    api_key = args.api_key or os.getenv("RENDER_API_KEY")

    # Check .env for credentials if not in args/env
    if not hook and not api_key:
        env_path = REPO_ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("RENDER_DEPLOY_HOOK="):
                    hook = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("RENDER_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")

    if hook:
        return trigger_deploy_hook(hook)

    if api_key:
        return trigger_via_api(api_key, service_id=args.service_id)

    print_manual_guide()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
