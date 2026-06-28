"""Leaf-level env/config helpers shared across server_helpers sub-modules.

These must have zero imports from server_helpers or any of its sub-modules
so they can be imported by both barrel and sub-modules without circularity.
"""

import hmac
import os
import uuid

EVENT_SCHEMA_VERSION = "1.3"
APP_VERSION = "local"
INTERNAL_QUEUE_TOKEN = os.environ.get("FLUENTFLOW_INTERNAL_QUEUE_TOKEN") or uuid.uuid4().hex
GUEST_TRIAL_TOKEN_HEADER = "x-fluentflow-guest-token"


def _env_truthy(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _public_mode_enabled() -> bool:
    return _env_truthy("FLUENTFLOW_PUBLIC_MODE")


def _request_is_internal_queue(request) -> bool:
    supplied = request.headers.get("x-fluentflow-internal-queue-token") or ""
    return bool(supplied and hmac.compare_digest(supplied, INTERNAL_QUEUE_TOKEN))
