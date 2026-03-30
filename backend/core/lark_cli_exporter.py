"""Export Markdown to Feishu via local ``lark-cli`` (user OAuth), parallel to OpenAPI export.

Requires ``lark-cli`` on PATH or ``FLUENTFLOW_LARK_CLI_BIN``. Default location is
``--wiki-space my_library`` (个人「我的文档库」), overridable via
``FLUENTFLOW_LARK_CLI_WIKI_SPACE``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_WIKI_SPACE = "my_library"


def _resolve_lark_cli_bin(explicit: Optional[str] = None) -> Optional[str]:
    if explicit and explicit.strip():
        p = explicit.strip()
        if os.path.isfile(p):
            return p
        return shutil.which(p)
    env_bin = (os.environ.get("FLUENTFLOW_LARK_CLI_BIN") or "").strip()
    if env_bin:
        if os.path.isfile(env_bin):
            return env_bin
        return shutil.which(env_bin)
    return shutil.which("lark-cli")


def export_markdown_via_lark_cli(
    title: str,
    markdown: str,
    *,
    wiki_space: Optional[str] = None,
    lark_cli_bin: Optional[str] = None,
    timeout: int = 120,
) -> Dict[str, Any]:
    """Create a Feishu wiki doc using ``lark-cli docs +create`` (user identity).

    Returns a dict compatible with :func:`export_markdown_to_lark` consumers:
    ``ok``, ``url``, optional ``doc_token`` / ``doc_id``, and ``via: "lark_cli"``.
    """
    bin_path = _resolve_lark_cli_bin(lark_cli_bin)
    if not bin_path:
        raise RuntimeError(
            "lark-cli not found. Install @larksuite/cli globally or set FLUENTFLOW_LARK_CLI_BIN."
        )

    space = (wiki_space or os.environ.get("FLUENTFLOW_LARK_CLI_WIKI_SPACE") or "").strip() or DEFAULT_WIKI_SPACE

    cmd = [
        bin_path,
        "docs",
        "+create",
        "--title",
        title,
        "--markdown",
        markdown,
        "--wiki-space",
        space,
        "--as",
        "user",
    ]

    logger.info("lark-cli export: wiki_space=%s title_len=%d md_len=%d", space, len(title), len(markdown))

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0:
        msg = err or out or f"exit code {proc.returncode}"
        raise RuntimeError(f"lark-cli failed: {msg}")

    try:
        payload = json.loads(out)
    except json.JSONDecodeError as e:
        logger.error("lark-cli stdout not JSON: %s", out[:500])
        raise RuntimeError(f"lark-cli returned non-JSON output: {e}") from e

    if not payload.get("ok"):
        err_obj = payload.get("error") or {}
        raise RuntimeError(err_obj.get("message") or str(payload))

    data = payload.get("data") or {}
    doc_url = data.get("doc_url") or data.get("url")
    doc_id = data.get("doc_id") or data.get("doc_token")

    if not doc_url:
        raise RuntimeError(f"lark-cli response missing doc_url: {payload}")

    return {
        "ok": True,
        "url": doc_url,
        "doc_token": doc_id,
        "via": "lark_cli",
        "wiki_space": space,
    }


__all__ = ["export_markdown_via_lark_cli", "DEFAULT_WIKI_SPACE"]
