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
from backend.core.runtime_paths import (  # noqa: E402
    default_account_db_path,
    default_artifact_dir,
    default_edited_transcript_dir,
    default_job_db_path,
    default_source_dir,
    default_transcript_edit_records_dir,
    default_video_source_dir,
)


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _canonical_provider(value: str | None) -> str | None:
    raw = (value or "").strip().lower()
    if raw in {"elevenlabs", "elevenlabs_scribe", "scribe", "scribe_v2", "cloud", "cloud_stt"}:
        return "elevenlabs_scribe"
    if raw in {"azure", "azure_batch", "azure-fast", "azure_fast"}:
        return "azure_batch"
    if raw in {"local", "faster-whisper", "faster_whisper", "whisper"}:
        return "local"
    return None


def _keyframe_enabled() -> bool:
    value = os.environ.get("FLUENTFLOW_KEYFRAME_EXTRACTION", "1").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def _keyframe_provider() -> str:
    value = os.environ.get("FLUENTFLOW_KEYFRAME_PROVIDER", "local_ffmpeg").strip().lower()
    if value in {"", "local", "ffmpeg", "local_ffmpeg"}:
        return "local_ffmpeg"
    if value in {"cloud", "worker", "cloud_ffmpeg", "cloud_ffmpeg_worker"}:
        return "cloud_ffmpeg_worker"
    if value in {"0", "false", "no", "off", "disabled", "none"}:
        return "disabled"
    return "disabled"


def _allowed_stt_providers(public_mode: bool) -> list[str]:
    raw = os.environ.get("FLUENTFLOW_ALLOWED_STT_PROVIDERS")
    if not raw:
        return ["elevenlabs_scribe"] if public_mode else ["elevenlabs_scribe", "local"]
    providers: list[str] = []
    for item in raw.split(","):
        provider = _canonical_provider(item)
        if provider and provider not in providers:
            providers.append(provider)
    return providers or (["elevenlabs_scribe"] if public_mode else ["elevenlabs_scribe", "local"])


def _int_from_env(name: str, default: int) -> int:
    try:
        return max(int(os.environ.get(name, str(default))), 0)
    except ValueError:
        return default


def _float_from_env(name: str, default: float) -> float:
    try:
        return max(float(os.environ.get(name, str(default))), 0.0)
    except ValueError:
        return default


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


def run_checks(
    *,
    allow_local_mode: bool = False,
    require_lark: bool = False,
    require_visual_evidence: bool = False,
) -> dict[str, Any]:
    load_project_env()
    checks: list[CheckResult] = []
    public_mode = _truthy(os.environ.get("FLUENTFLOW_PUBLIC_MODE"))
    allowed_providers = _allowed_stt_providers(public_mode)
    default_provider = _canonical_provider(os.environ.get("FLUENTFLOW_DEFAULT_STT_PROVIDER") or "elevenlabs_scribe")
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
    auth_mode = (os.environ.get("FLUENTFLOW_AUTH_MODE") or "").strip().lower()
    account_auth_configured = auth_mode in {"account", "accounts"} or _truthy(os.environ.get("FLUENTFLOW_ACCOUNT_AUTH"))
    active_job_limit = _int_from_env("FLUENTFLOW_MAX_ACTIVE_JOBS_PER_CLIENT", 2 if public_mode else 0)
    global_active_job_limit = _int_from_env("FLUENTFLOW_MAX_ACTIVE_JOBS_GLOBAL", 6 if public_mode else 0)
    daily_job_limit = _int_from_env("FLUENTFLOW_DAILY_JOB_LIMIT_PER_CLIENT", 10 if public_mode else 0)
    global_daily_job_limit = _int_from_env("FLUENTFLOW_DAILY_JOB_LIMIT_GLOBAL", 80 if public_mode else 0)
    daily_upload_limit = _float_from_env("FLUENTFLOW_DAILY_UPLOAD_MB_PER_CLIENT", 4096.0 if public_mode else 0.0)
    global_daily_upload_limit = _float_from_env("FLUENTFLOW_DAILY_UPLOAD_MB_GLOBAL", 32768.0 if public_mode else 0.0)
    rate_limit = _int_from_env("FLUENTFLOW_SUBMISSION_RATE_LIMIT_PER_IP", 12 if public_mode else 0)
    quota_guard_configured = bool(
        active_job_limit > 0
        and global_active_job_limit > 0
        and daily_job_limit > 0
        and global_daily_job_limit > 0
        and daily_upload_limit > 0
        and global_daily_upload_limit > 0
        and rate_limit > 0
    )
    access_status = "pass" if (account_auth_configured or access_token_configured) else ("warn" if quota_guard_configured else "fail")
    access_detail = (
        "账号系统已启用。"
        if account_auth_configured
        else "访问口令已配置。"
        if access_token_configured
        else (
            "未设置访问口令；已启用异常额度控制。它能降低误用成本，但不能替代账号系统。"
            if quota_guard_configured
            else "缺少 FLUENTFLOW_ACCESS_TOKEN；若不使用访问码，必须启用个人/全站并发、每日额度和提交频率限制。"
        )
    )
    checks.append(CheckResult(
        "access_control",
        access_status,
        access_detail,
    ))

    account_db_path = _path_from_env("FLUENTFLOW_ACCOUNT_DB_PATH", default_account_db_path())
    account_db_parent_ok, account_db_parent_detail = _check_writable_dir(account_db_path.parent)
    checks.append(CheckResult(
        "account_auth",
        "pass" if account_auth_configured and account_db_parent_ok else ("warn" if not account_auth_configured else "fail"),
        (
            f"账号系统已启用，账号数据库目录可写：{account_db_path.parent}"
            if account_auth_configured and account_db_parent_ok
            else (
                f"账号系统已启用，但账号数据库目录不可写：{account_db_parent_detail}"
                if account_auth_configured
                else "账号系统未启用；当前依赖设备/IP/全站额度控制。"
            )
        ),
    ))

    job_db_path = _path_from_env("FLUENTFLOW_JOB_DB_PATH", default_job_db_path())
    job_db_parent_ok, job_db_parent_detail = _check_writable_dir(job_db_path.parent)
    checks.append(CheckResult(
        "job_store",
        "pass" if job_db_parent_ok else "fail",
        f"任务数据库目录可写：{job_db_path.parent}" if job_db_parent_ok else f"任务数据库目录不可写：{job_db_parent_detail}",
    ))

    checks.append(CheckResult(
        "quota_guard",
        "pass" if quota_guard_configured else ("warn" if access_token_configured else "fail"),
        (
            (
                f"client_active={active_job_limit}, global_active={global_active_job_limit}, "
                f"client_daily_jobs={daily_job_limit}, global_daily_jobs={global_daily_job_limit}, "
                f"client_daily_upload_mb={daily_upload_limit:g}, global_daily_upload_mb={global_daily_upload_limit:g}, "
                f"ip_rate_limit={rate_limit}"
            )
            if quota_guard_configured
            else "未完整配置异常额度控制。建议设置个人/全站并发、个人/全站每日额度和 IP 提交频率限制。"
        ),
    ))

    provider_status = "pass"
    provider_detail = f"allowed={','.join(allowed_providers)} default={default_provider or 'unknown'}"
    if public_mode and allowed_providers != ["elevenlabs_scribe"]:
        provider_status = "fail"
        provider_detail = "公共模式只应开放 elevenlabs_scribe，避免用户触发本地 STT 消耗服务器资源。"
    elif default_provider not in allowed_providers:
        provider_status = "fail"
        provider_detail = "FLUENTFLOW_DEFAULT_STT_PROVIDER 不在 FLUENTFLOW_ALLOWED_STT_PROVIDERS 中。"
    checks.append(CheckResult("stt_provider_policy", provider_status, provider_detail))

    elevenlabs_missing = ["ELEVENLABS_API_KEY"] if not credentials["elevenlabs_api_key_configured"] else []
    checks.append(CheckResult(
        "elevenlabs_credentials",
        "pass" if not elevenlabs_missing else "fail",
        "ElevenLabs API Key 已配置。" if not elevenlabs_missing else "缺少：" + ", ".join(elevenlabs_missing),
    ))

    ai_configured = bool(
        credentials["deepseek_api_key_configured"]
        or credentials["openai_api_key_configured"]
        or credentials["qwen_api_key_configured"]
    )
    checks.append(CheckResult(
        "summary_model_credentials",
        "pass" if ai_configured else "fail",
        "摘要模型 Key 已配置。" if ai_configured else "缺少 DEEPSEEK_API_KEY、OPENAI_API_KEY 或 DASHSCOPE_API_KEY。",
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

    keyframe_enabled = _keyframe_enabled()
    keyframe_provider = _keyframe_provider()
    dashscope_ok = bool(credentials.get("dashscope_api_key_configured") or credentials["qwen_api_key_configured"])
    visual_status = "pass"
    visual_detail = (
        f"provider={keyframe_provider}; "
        "百炼 / DashScope 视觉选择 Key 已配置，视频截图插图可用。"
    )
    if not keyframe_enabled or keyframe_provider == "disabled":
        visual_status = "fail" if require_visual_evidence else "warn"
        visual_detail = "视频截图插图已关闭；设置 FLUENTFLOW_KEYFRAME_EXTRACTION=1 和 FLUENTFLOW_KEYFRAME_PROVIDER=local_ffmpeg。"
    elif keyframe_provider == "cloud_ffmpeg_worker":
        visual_status = "fail" if require_visual_evidence else "warn"
        visual_detail = "cloud_ffmpeg_worker 仍是预留路线；当前要跑通请先在单台 ECS 上使用 FLUENTFLOW_KEYFRAME_PROVIDER=local_ffmpeg。"
    elif not (ffmpeg_ok and ffprobe_ok):
        visual_status = "fail"
        visual_detail = "视频截图插图需要服务器可执行 ffmpeg 和 ffprobe。"
    elif not dashscope_ok:
        visual_status = "fail" if require_visual_evidence else "warn"
        visual_detail = "视频截图插图需要配置 DASHSCOPE_API_KEY（兼容旧名 QWEN_API_KEY）；摘要模型可继续使用 DeepSeek、OpenAI 或 Qwen，ElevenLabs 只负责转录。"
    checks.append(CheckResult(
        "visual_note_screenshots",
        visual_status,
        visual_detail,
    ))

    storage_dirs = {
        "sources": _path_from_env("FLUENTFLOW_SOURCE_DIR", default_source_dir()),
        "artifacts": _path_from_env("FLUENTFLOW_ARTIFACT_DIR", default_artifact_dir()),
        "edited_transcripts": _path_from_env("FLUENTFLOW_EDITED_TRANSCRIPT_DIR", default_edited_transcript_dir()),
        "transcript_edit_records": _path_from_env("FLUENTFLOW_TRANSCRIPT_EDIT_RECORDS_DIR", default_transcript_edit_records_dir()),
        "video_sources": _path_from_env("FLUENTFLOW_VIDEO_SOURCE_DIR", default_video_source_dir()),
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
    parser.add_argument("--require-visual-evidence", action="store_true", help="Treat video screenshot note prerequisites as required")
    args = parser.parse_args()

    payload = run_checks(
        allow_local_mode=args.allow_local_mode,
        require_lark=args.require_lark,
        require_visual_evidence=args.require_visual_evidence,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0 if payload["status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
