"""Leaf-level env/config helpers shared across server_helpers sub-modules.

These must have zero imports from server_helpers or any of its sub-modules
so they can be imported by both barrel and sub-modules without circularity.
"""

import hmac
import os
import secrets
from pathlib import Path

from backend.core.versioning import get_app_version

EVENT_SCHEMA_VERSION = "1.3"
APP_VERSION = get_app_version()


def _persistent_internal_queue_token() -> str:
    configured = (os.environ.get("FLUENTFLOW_INTERNAL_QUEUE_TOKEN") or "").strip()
    if configured:
        return configured
    token_path = Path(
        (os.environ.get("FLUENTFLOW_INTERNAL_QUEUE_TOKEN_PATH") or "").strip()
        or (Path(__file__).resolve().parents[1] / "data" / "internal_queue_token")
    ).expanduser()
    try:
        existing = token_path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except FileNotFoundError:
        pass
    except OSError:
        return secrets.token_hex(32)
    token = secrets.token_hex(32)
    try:
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token, encoding="utf-8")
    except OSError:
        pass
    return token


INTERNAL_QUEUE_TOKEN = _persistent_internal_queue_token()
GUEST_TRIAL_TOKEN_HEADER = "x-fluentflow-guest-token"


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _public_mode_enabled() -> bool:
    return _env_truthy("FLUENTFLOW_PUBLIC_MODE")


def _request_is_internal_queue(request) -> bool:
    supplied = request.headers.get("x-fluentflow-internal-queue-token") or ""
    return bool(supplied and hmac.compare_digest(supplied, INTERNAL_QUEUE_TOKEN))
