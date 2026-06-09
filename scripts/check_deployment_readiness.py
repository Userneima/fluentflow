#!/usr/bin/env python3
"""Check whether a FluentFlow server is ready for a closed cloud beta.

The script validates deployment-facing configuration without printing secret
values. It is intended for maintainers before exposing the service through
Nginx.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.local_config import credential_status, load_project_env  # noqa: E402


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _canonical_provider(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if raw in {"azure", "azure_batch", "azure-fast", "azure_fast", "cloud"}:
        return "azure_batch"
    if raw in {"local", "faster-whisper", "faster_whisper", "whisper"}:
        return "local"
    return None


def _allowed_stt_providers(public_mode: bool) -> list[str]:
    raw = os.environ.get("FLUENTFLOW_ALLOWED_STT_PROVIDERS")
    if not raw:
        return ["azure_batch"] if public_mode else ["azure_batch", "local"]
    providers: list[str] = []
    for item in raw.split(","):
        provider = _canonical_provider(item)
        if provider and provider not in providers:
            providers.append(provider)
    return providers or (["azure_batch"] if public_mode else ["azure_batch", "local"])


def _path_from_env(name: str, default: Path) -> Path:
    override = (os.environ.get(name) or "").strip()
    return Path(override).expanduser() if override else default


def _check_writable_dir(path: Path) -> tuple[bool, str]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=".fluentflow_write_", dir=path, delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
        return True, str(path)
    except Exception as exc:
        return False, f"{path}: {exc}"


def run_checks(*, allow_local_mode: bool = False, require_lark: bool = False) -> dict[str, Any]:
    load_project_env()
    checks: list[CheckResult] = []
    public_mode = _truthy(os.environ.get("FLUENTFLOW_PUBLIC_MODE"))
    allowed_providers = _allowed_stt_providers(public_mode)
    default_provider = _canonical_provider(os.environ.get("FLUENTFLOW_DEFAULT_STT_PROVIDER") or "azure_batch")
    credentials = credential_status()

    if public_mode:
        checks.append(CheckResult("public_mode", "pass", "FLUENTFLOW_PUBLIC_MODE=1"))
    elif allow_local_mode:
        checks.append(CheckResult("public_mode", "warn", "当前不是公共云服务器模式；仅适合本地开发或内网自用。"))
    else:
        checks.append(CheckResult("public_mode", "fail", "云服务器试用应设置 FLUENTFLOW_PUBLIC_MODE=1。"))

    access_token_configured = bool(
        (os.environ.get("FLUENTFLOW_ACCESS_TOKEN") or "").strip()
        or (os.environ.get("FLUENTFLOW_ACCESS_TOKENS") or "").strip()
    )
    checks.append(CheckResult(
        "access_control",
        "pass" if access_token_configured else "fail",
        "访问口令已配置。" if access_token_configured else "缺少 FLUENTFLOW_ACCESS_TOKEN 或 FLUENTFLOW_ACCESS_TOKENS。",
    ))

    provider_status = "pass"
    provider_detail = f"allowed={','.join(allowed_providers)} default={default_provider or 'unknown'}"
    if public_mode and allowed_providers != ["azure_batch"]:
        provider_status = "fail"
        provider_detail = "公共模式只应开放 azure_batch，避免用户触发本地 STT 消耗服务器资源。"
    elif default_provider not in allowed_providers:
        provider_status = "fail"
        provider_detail = "FLUENTFLOW_DEFAULT_STT_PROVIDER 不在 FLUENTFLOW_ALLOWED_STT_PROVIDERS 中。"
    checks.append(CheckResult("stt_provider_policy", provider_status, provider_detail))

    azure_missing = [
        label
        for label, configured in (
            ("AZURE_SPEECH_ENDPOINT", credentials["azure_speech_endpoint_configured"]),
            ("AZURE_SPEECH_KEY", credentials["azure_speech_key_configured"]),
            ("AZURE_BLOB_CONTAINER_SAS_URL", credentials["azure_blob_container_sas_url_configured"]),
        )
        if not configured
    ]
    checks.append(CheckResult(
        "azure_batch_credentials",
        "pass" if not azure_missing else "fail",
        "Azure Speech 和 Blob/SAS 已配置。" if not azure_missing else "缺少：" + ", ".join(azure_missing),
    ))

    ai_configured = bool(credentials["deepseek_api_key_configured"] or credentials["openai_api_key_configured"])
    checks.append(CheckResult(
        "summary_model_credentials",
        "pass" if ai_configured else "fail",
        "摘要模型 Key 已配置。" if ai_configured else "缺少 DEEPSEEK_API_KEY 或 OPENAI_API_KEY。",
    ))

    lark_openapi_configured = bool(credentials["lark_app_id_configured"] and credentials["lark_app_secret_configured"])
    lark_cli_bin = (os.environ.get("FLUENTFLOW_LARK_CLI_BIN") or "").strip()
    lark_cli_configured = bool((Path(lark_cli_bin).is_file() if lark_cli_bin else False) or shutil.which(lark_cli_bin or "lark-cli"))
    lark_ok = lark_openapi_configured or lark_cli_configured
    checks.append(CheckResult(
        "lark_export",
        "pass" if lark_ok else ("fail" if require_lark else "warn"),
        "飞书导出已配置。" if lark_ok else "飞书导出未配置；若上线需要自动导出，请配置 LARK_APP_ID/LARK_APP_SECRET 或 lark-cli。",
    ))

    ffmpeg_ok = bool(shutil.which("ffmpeg"))
    ffprobe_ok = bool(shutil.which("ffprobe"))
    checks.append(CheckResult(
        "ffmpeg",
        "pass" if ffmpeg_ok and ffprobe_ok else "fail",
        "ffmpeg/ffprobe 可用。" if ffmpeg_ok and ffprobe_ok else "缺少 ffmpeg 或 ffprobe，音视频预处理会失败。",
    ))

    storage_dirs = {
        "sources": _path_from_env("FLUENTFLOW_SOURCE_DIR", PROJECT_ROOT / "data" / "sources"),
        "artifacts": _path_from_env("FLUENTFLOW_ARTIFACT_DIR", PROJECT_ROOT / "data" / "artifacts"),
        "edited_transcripts": _path_from_env("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", PROJECT_ROOT / "data" / "edited_transcripts"),
        "transcript_edit_records": _path_from_env("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", PROJECT_ROOT / "data" / "transcript_edit_records"),
        "video_sources": _path_from_env("FLUENTFLOW_VIDEO_SOURCE_DIR", PROJECT_ROOT / "视频文件"),
    }
    for label, path in storage_dirs.items():
        ok, detail = _check_writable_dir(path)
        checks.append(CheckResult(f"storage_{label}", "pass" if ok else "fail", detail))

    upload_mb = os.environ.get("FLUENTFLOW_MAX_UPLOAD_MB") or "2048"
    try:
        upload_value = float(upload_mb)
        upload_status = "pass" if upload_value > 0 else "fail"
    except ValueError:
        upload_status = "fail"
    checks.append(CheckResult(
        "upload_limit",
        upload_status,
        f"FLUENTFLOW_MAX_UPLOAD_MB={upload_mb}；Nginx client_max_body_size 应不低于该值。",
    ))

    statuses = [item.status for item in checks]
    overall = "fail" if "fail" in statuses else ("warn" if "warn" in statuses else "pass")
    return {
        "status": overall,
        "project_root": str(PROJECT_ROOT),
        "checks": [asdict(item) for item in checks],
    }


def _print_text(payload: dict[str, Any]) -> None:
    print(f"FluentFlow deployment readiness: {payload['status']}")
    for item in payload["checks"]:
        marker = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}[item["status"]]
        print(f"[{marker}] {item['name']}: {item['detail']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--allow-local-mode", action="store_true", help="Warn instead of failing when FLUENTFLOW_PUBLIC_MODE is not enabled")
    parser.add_argument("--require-lark", action="store_true", help="Treat missing Lark export config as a failure")
    args = parser.parse_args()

    payload = run_checks(allow_local_mode=args.allow_local_mode, require_lark=args.require_lark)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if payload["status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
