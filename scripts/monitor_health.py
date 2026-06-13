#!/usr/bin/env python3
"""Check a FluentFlow deployment and return non-zero on unhealthy status."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


def _get_json(url: str, *, token: str | None, timeout: float) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["X-FluentFlow-Session"] = token
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _join_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor FluentFlow HTTP health and ops status.")
    parser.add_argument("--base-url", required=True, help="Example: https://fluentflow.example.com")
    parser.add_argument("--session-token", default="", help="Optional account session token for /ops/status.")
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--skip-ops", action="store_true", help="Only check /health.")
    args = parser.parse_args()

    report: dict[str, Any] = {"base_url": args.base_url, "checks": []}
    failed = False
    try:
        health = _get_json(_join_url(args.base_url, "/health"), token=None, timeout=args.timeout)
        report["checks"].append({"name": "health", "status": health.get("status"), "payload": health})
        if health.get("status") != "ok":
            failed = True
    except Exception as exc:
        report["checks"].append({"name": "health", "status": "fail", "error": str(exc)})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    if not args.skip_ops:
        try:
            ops = _get_json(_join_url(args.base_url, "/ops/status"), token=args.session_token or None, timeout=args.timeout)
            report["checks"].append({"name": "ops", "status": ops.get("status"), "payload": ops})
            if ops.get("status") == "fail":
                failed = True
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                report["checks"].append({
                    "name": "ops",
                    "status": "skipped",
                    "detail": "需要账号 session token；基础 /health 已通过。",
                })
            else:
                report["checks"].append({"name": "ops", "status": "fail", "error": f"HTTP {exc.code}"})
                failed = True
        except Exception as exc:
            report["checks"].append({"name": "ops", "status": "fail", "error": str(exc)})
            failed = True

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
