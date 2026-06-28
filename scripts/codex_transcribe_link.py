#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import re
from pathlib import Path
from typing import Any


DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_CLIENT_ID = os.environ.get("FLUENTFLOW_CLIENT_ID", "local-client")
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATED_VIDEO_PREFIX_RE = re.compile(r"^\d{10,24}[-_]+(?=.)")


class FluentFlowApiError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, payload: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload


def normalize_api_base(value: str | None) -> str:
    text = (value or os.environ.get("FLUENTFLOW_API_BASE") or DEFAULT_API_BASE).strip()
    return text.rstrip("/") or DEFAULT_API_BASE


def api_request(
    method: str,
    api_base: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    client_id: str = DEFAULT_CLIENT_ID,
    access_token: str | None = None,
    local_execution: bool = False,
    timeout: float = 30,
) -> dict[str, Any]:
    url = f"{normalize_api_base(api_base)}{path}"
    body = None
    headers = {
        "Accept": "application/json",
        "X-FluentFlow-Client-Id": client_id,
    }
    token = (access_token or os.environ.get("FLUENTFLOW_ACCESS_TOKEN") or "").strip()
    if token:
        headers["X-FluentFlow-Access-Token"] = token
    if local_execution:
        headers["X-FluentFlow-Execution-Target"] = "local"
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        parsed = parse_json_bytes(raw)
        message = api_error_message(parsed, f"HTTP {exc.code}")
        raise FluentFlowApiError(message, status=exc.code, payload=parsed) from exc
    except urllib.error.URLError as exc:
        raise FluentFlowApiError(f"Cannot reach FluentFlow backend at {url}: {exc.reason}") from exc
    return parse_json_bytes(raw)


def parse_json_bytes(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FluentFlowApiError(f"Backend returned non-JSON response: {raw[:200]!r}") from exc
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def api_error_message(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, dict):
            message = detail.get("message") or detail.get("detail")
            if message:
                return str(message)
    return fallback


def runtime_config(api_base: str, client_id: str, access_token: str | None = None) -> dict[str, Any]:
    try:
        return api_request("GET", api_base, "/runtime-config", client_id=client_id, access_token=access_token, timeout=10)
    except FluentFlowApiError:
        return {}


def resolve_stt_provider(requested: str, config: dict[str, Any]) -> str:
    value = (requested or "auto").strip().lower()
    allowed = [str(item).strip() for item in config.get("allowed_stt_providers") or [] if str(item).strip()]
    default = str(config.get("default_stt_provider") or "").strip() or "elevenlabs_scribe"
    if value in {"", "auto"}:
        return "local" if "local" in allowed else default
    if not allowed or value in allowed:
        return value
    return default


def strip_generated_video_prefix(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\.[a-z0-9]{2,6}$", "", text, flags=re.I).strip()
    return GENERATED_VIDEO_PREFIX_RE.sub("", text).strip() or text


def create_video_job(
    input_text: str,
    *,
    api_base: str,
    client_id: str,
    access_token: str | None,
    stt_provider: str,
    skip_summary: bool,
    stt_model: str,
    stt_speed: str,
    note_mode: str | None,
    prompt_preset: str | None,
) -> dict[str, Any]:
    options: dict[str, str] = {
        "stt_provider": stt_provider,
        "stt_language": "auto",
        "stt_model": stt_model,
        "stt_speed": stt_speed,
        "skip_summary": "true" if skip_summary else "false",
        "export_to_lark": "false",
    }
    if note_mode:
        options["note_mode"] = note_mode
    if prompt_preset:
        options["prompt_preset"] = prompt_preset
    payload = {"input": input_text, "options": options}
    data = api_request(
        "POST",
        api_base,
        "/video-sources/jobs",
        payload=payload,
        client_id=client_id,
        access_token=access_token,
        local_execution=stt_provider == "local",
        timeout=30,
    )
    job = data.get("job")
    if not isinstance(job, dict) or not job.get("task_id"):
        raise FluentFlowApiError(f"Unexpected create job response: {data}")
    return job


def get_job(
    task_id: str,
    *,
    api_base: str,
    client_id: str,
    access_token: str | None,
    local_execution: bool,
) -> dict[str, Any]:
    path = f"/jobs/{urllib.parse.quote(task_id, safe='')}"
    return api_request(
        "GET",
        api_base,
        path,
        client_id=client_id,
        access_token=access_token,
        local_execution=local_execution,
        timeout=30,
    )


def wait_for_job(
    task_id: str,
    *,
    api_base: str,
    client_id: str,
    access_token: str | None,
    local_execution: bool,
    timeout_seconds: float,
    poll_interval: float,
    quiet: bool,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    last_stage = ""
    while True:
        job = get_job(
            task_id,
            api_base=api_base,
            client_id=client_id,
            access_token=access_token,
            local_execution=local_execution,
        )
        status = str(job.get("status") or "")
        stage = str(job.get("stage") or "")
        progress = job.get("progress")
        if not quiet and (status != last_status or stage != last_stage):
            print(f"[fluentflow] {task_id} {status or '-'} / {stage or '-'} / {progress}%", file=sys.stderr)
            last_status = status
            last_stage = stage
        if status in TERMINAL_STATUSES:
            if status != "completed":
                reason = job.get("error_reason") or job.get("summary_status") or f"Job {status}"
                raise FluentFlowApiError(str(reason), payload=job)
            return job
        if time.monotonic() >= deadline:
            raise FluentFlowApiError(f"Timed out waiting for job {task_id}")
        time.sleep(max(1.0, poll_interval))


def artifact_paths(task_id: str, result: dict[str, Any]) -> dict[str, str]:
    base = Path(os.environ.get("FLUENTFLOW_ARTIFACT_DIR") or PROJECT_ROOT / "data" / "artifacts")
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    paths: dict[str, str] = {}
    for kind, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        filename = Path(str(artifact.get("filename") or "")).name
        if filename:
            paths[str(kind)] = str((base / task_id / filename).expanduser())
    return paths


def build_codex_result(job: dict[str, Any], *, api_base: str, client_id: str, stt_provider: str) -> dict[str, Any]:
    task_id = str(job.get("task_id") or "")
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    video_source = metadata.get("video_source") if isinstance(metadata.get("video_source"), dict) else {}
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    display_title = (
        strip_generated_video_prefix(result.get("display_title"))
        or strip_generated_video_prefix(metadata.get("display_title"))
        or strip_generated_video_prefix(video_source.get("display_title"))
        or strip_generated_video_prefix(video_source.get("title"))
        or strip_generated_video_prefix(result.get("filename"))
        or strip_generated_video_prefix(job.get("source_filename"))
    )
    return {
        "ok": True,
        "task_id": task_id,
        "api_base": normalize_api_base(api_base),
        "client_id": client_id,
        "status": job.get("status"),
        "stage": job.get("stage"),
        "title": display_title,
        "raw_title": result.get("raw_title") or metadata.get("raw_title") or video_source.get("raw_title"),
        "display_title": display_title,
        "filename": result.get("filename") or job.get("source_filename"),
        "source_type": job.get("source_type"),
        "stt_provider": result.get("stt_provider") or stt_provider,
        "stt_provider_label": result.get("stt_provider_label"),
        "source_language": result.get("source_language"),
        "detected_language": result.get("detected_language"),
        "subtitle_mode": result.get("subtitle_mode"),
        "translation_status": result.get("translation_status"),
        "transcript_text": result.get("transcript_text") or "",
        "segments": result.get("segments") if isinstance(result.get("segments"), list) else [],
        "translated_segments_zh": result.get("translated_segments_zh")
        if isinstance(result.get("translated_segments_zh"), list)
        else [],
        "summary_markdown": result.get("summary_markdown") or "",
        "summary_status": result.get("summary_status"),
        "summary_error": result.get("summary_error"),
        "artifacts": artifacts,
        "artifact_paths": artifact_paths(task_id, result),
        "job": job,
    }


def default_output_path(task_id: str) -> Path:
    root = Path(os.environ.get("FLUENTFLOW_CODEX_EXPORT_DIR") or PROJECT_ROOT / "data" / "codex_exports")
    return root / f"{task_id}.json"


def write_result(payload: dict[str, Any], output: str | None) -> Path:
    task_id = str(payload.get("task_id") or "fluentflow-codex-result")
    target = Path(output).expanduser() if output else default_output_path(task_id)
    if target.suffix.lower() != ".json":
        target = target / f"{task_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a Douyin/video link to local FluentFlow and export a Codex-readable transcript JSON.",
    )
    parser.add_argument("input", help="Douyin link, video URL, or copied share text.")
    parser.add_argument("--api-base", default=None, help=f"FluentFlow backend URL. Default: {DEFAULT_API_BASE}")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID, help=f"Client scope header. Default: {DEFAULT_CLIENT_ID}")
    parser.add_argument("--access-token", default=os.environ.get("FLUENTFLOW_ACCESS_TOKEN"), help="Optional access token for protected local backends.")
    parser.add_argument(
        "--stt-provider",
        default=os.environ.get("FLUENTFLOW_CODEX_STT_PROVIDER", "auto"),
        choices=["auto", "local", "elevenlabs_scribe", "azure_batch"],
        help="Transcription route. auto prefers local when available.",
    )
    parser.add_argument("--stt-model", default=os.environ.get("FLUENTFLOW_CODEX_STT_MODEL", "medium"))
    parser.add_argument("--stt-speed", default=os.environ.get("FLUENTFLOW_CODEX_STT_SPEED", "balanced"))
    parser.add_argument("--note-mode", default=os.environ.get("FLUENTFLOW_CODEX_NOTE_MODE"))
    parser.add_argument("--prompt-preset", default=os.environ.get("FLUENTFLOW_CODEX_PROMPT_PRESET"))
    parser.add_argument("--no-summary", action="store_true", help="Only transcribe; skip AI summary generation.")
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("FLUENTFLOW_CODEX_TIMEOUT", "7200")))
    parser.add_argument("--poll-interval", type=float, default=float(os.environ.get("FLUENTFLOW_CODEX_POLL_INTERVAL", "5")))
    parser.add_argument("--output", help="Output JSON file or directory. Default: data/codex_exports/<task_id>.json")
    parser.add_argument("--stdout", action="store_true", help="Print the full JSON payload to stdout.")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages on stderr.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_base = normalize_api_base(args.api_base)
    try:
        config = runtime_config(api_base, args.client_id, args.access_token)
        stt_provider = resolve_stt_provider(args.stt_provider, config)
        if not args.quiet:
            print(f"[fluentflow] using {api_base}, stt_provider={stt_provider}", file=sys.stderr)
        job = create_video_job(
            args.input,
            api_base=api_base,
            client_id=args.client_id,
            access_token=args.access_token,
            stt_provider=stt_provider,
            skip_summary=bool(args.no_summary),
            stt_model=args.stt_model,
            stt_speed=args.stt_speed,
            note_mode=args.note_mode,
            prompt_preset=args.prompt_preset,
        )
        task_id = str(job["task_id"])
        if not args.quiet:
            print(f"[fluentflow] created task {task_id}", file=sys.stderr)
        finished = wait_for_job(
            task_id,
            api_base=api_base,
            client_id=args.client_id,
            access_token=args.access_token,
            local_execution=stt_provider == "local",
            timeout_seconds=args.timeout,
            poll_interval=args.poll_interval,
            quiet=args.quiet,
        )
        payload = build_codex_result(finished, api_base=api_base, client_id=args.client_id, stt_provider=stt_provider)
        output_path = write_result(payload, args.output)
        payload["output_path"] = str(output_path)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if args.stdout:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({
                "ok": True,
                "task_id": payload["task_id"],
                "title": payload["title"],
                "output_path": str(output_path),
                "transcript_chars": len(payload["transcript_text"]),
                "summary_chars": len(payload["summary_markdown"]),
            }, ensure_ascii=False))
        return 0
    except FluentFlowApiError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "status": exc.status}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
