"""Business actions for existing Agent tasks.

Routers should stay thin: validate the request scope, load the job, then call
these use-case functions. This keeps long-lived task behavior away from HTTP
plumbing and makes future actions easier to test without copying route code.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import backend.core.server_helpers as H
from backend.core.chapter_coverage import bind_chapter_coverage_time_ranges


class AgentActionError(Exception):
    def __init__(self, status_code: int, detail: str, *, cause: Exception | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.cause = cause


async def regenerate_agent_note(
    *,
    task_id: str,
    client_id: str,
    job: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = dict(job.get("result") or {})
    transcript_source = "corrected_transcript" if str(result.get("corrected_transcript_text") or "").strip() else "transcript_text"
    transcript = str(result.get("corrected_transcript_text") or result.get("transcript_text") or "").strip()
    route = "/agent/v1/tasks/{task_id}/note/regenerate"
    if not transcript:
        raise AgentActionError(400, "No transcript available for note regeneration")

    kwargs = H._ai_kwargs(
        deepseek_api_key=payload.get("deepseek_api_key"),
        openai_api_key=payload.get("openai_api_key"),
        ai_provider=payload.get("ai_provider"),
        ai_model=payload.get("ai_model"),
        system_prompt=payload.get("system_prompt"),
        note_mode=payload.get("note_mode"),
    )
    kwargs, note_mode_plan = H._plan_note_mode_for_summary(
        kwargs,
        transcript,
        task_id=task_id,
        route=route,
        filename=result.get("filename") or job.get("source_filename"),
        duration_seconds=result.get("audio_duration_seconds") or job.get("source_duration_seconds"),
        current_prompt_preset=payload.get("prompt_preset"),
    )
    started_at = time.perf_counter()
    try:
        loop = asyncio.get_running_loop()
        summary_result = await loop.run_in_executor(
            None,
            lambda: H.summarize_transcript_with_metadata(transcript, **kwargs),
        )
    except Exception as exc:
        friendly_error = H._friendly_error_message(exc)
        result.update({
            "summary_status": "failed",
            "summary_error": friendly_error,
            "summary_skipped": False,
        })
        H.upsert_job(
            task_id=task_id,
            status="failed",
            client_id=client_id,
            stage="summary_regenerate",
            source_type=job.get("source_type"),
            source_filename=job.get("source_filename"),
            summary_status="failed",
            error_reason=friendly_error,
            result=result,
            metadata=job.get("metadata"),
        )
        H.log_event(
            task_id=task_id,
            event_name="agent_note_regenerated",
            source_type=job.get("source_type"),
            source_filename=job.get("source_filename"),
            transcript_length=H._text_len(transcript),
            stage="summary_regenerate",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            metadata=H._metadata(route=route, raw_error=str(exc), note_generation_transcript_source=transcript_source),
        )
        raise AgentActionError(500, friendly_error, cause=exc) from exc

    result.update({
        "summary_markdown": summary_result.markdown,
        "summary_status": "completed",
        "summary_error": None,
        "summary_skipped": False,
        "requested_note_mode": note_mode_plan.get("requested_note_mode") or summary_result.requested_mode,
        "resolved_note_mode": summary_result.resolved_mode,
        "note_mode_chunk_count": summary_result.chunk_count,
        "note_mode_segment_count": getattr(summary_result, "segment_count", None),
        "note_mode_evidence_count": getattr(summary_result, "evidence_count", None),
        "note_mode_chapter_count": getattr(summary_result, "chapter_count", None),
        "note_mode_important_evidence_count": getattr(summary_result, "important_evidence_count", None),
        "note_mode_covered_important_evidence_count": getattr(summary_result, "covered_important_evidence_count", None),
        "note_mode_coverage_missing_count": getattr(summary_result, "coverage_missing_count", None),
        "chapter_coverage": getattr(summary_result, "chapter_coverage", None),
        **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
        "prompt_preset": str(payload.get("prompt_preset") or "").strip() or result.get("prompt_preset"),
        "prompt_preset_label": str(payload.get("prompt_preset_label") or "").strip() or result.get("prompt_preset_label"),
    })
    result = bind_chapter_coverage_time_ranges(result)
    result = H._attach_result_artifacts(task_id, result)
    H.upsert_job(
        task_id=task_id,
        status="completed",
        client_id=client_id,
        stage="done",
        progress=100,
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        summary_status="completed",
        error_reason=None,
        result=result,
        metadata=job.get("metadata"),
    )
    H.log_event(
        task_id=task_id,
        event_name="agent_note_regenerated",
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        transcript_length=H._text_len(transcript),
        summary_length=H._text_len(summary_result.markdown),
        stage="summary_regenerate",
        duration_seconds=round(time.perf_counter() - started_at, 3),
        success=True,
        metadata=H._metadata(route=route, note_generation_transcript_source=transcript_source),
    )
    return H.get_job(task_id, client_id=client_id) or {**job, "result": result}


async def export_agent_note(
    *,
    task_id: str,
    client_id: str,
    job: dict[str, Any],
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = dict(job.get("result") or {})
    route = "/agent/v1/tasks/{task_id}/exports"
    markdown = str(payload.get("markdown") or result.get("summary_markdown") or "").strip()
    if not markdown:
        raise AgentActionError(400, "No markdown note available to export")
    target = str(payload.get("target") or "lark").strip().lower()
    if target not in {"lark", "feishu"}:
        raise AgentActionError(400, "Only lark export is supported")

    title = str(payload.get("title") or result.get("display_title") or job.get("source_filename") or task_id).strip()
    resolved_title = H.resolve_lark_doc_title(markdown, filename_stem="", form_title=title)
    export_target = H._lark_export_target(payload.get("lark_export_route"), payload.get("lark_via_cli"))
    kwargs: dict[str, Any] = {}
    if value := H.resolve_secret(payload.get("lark_app_id"), "lark_app_id"):
        kwargs["app_id"] = value
    if value := H.resolve_secret(payload.get("lark_app_secret"), "lark_app_secret"):
        kwargs["app_secret"] = value
    if payload.get("folder_token"):
        kwargs["folder_token"] = payload.get("folder_token")

    started_at = time.perf_counter()
    H.log_event(
        task_id=task_id,
        event_name="agent_export_started",
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        summary_length=H._text_len(markdown),
        stage="export",
        export_target=export_target,
        metadata=H._metadata(route=route, target=target, doc_title=resolved_title),
    )
    try:
        loop = asyncio.get_running_loop()
        if export_target == "lark_cli":
            export_response = await loop.run_in_executor(
                None,
                lambda: H.export_markdown_via_lark_cli(resolved_title, markdown),
            )
        elif export_target == "feishu_user_oauth":
            account_id = H._account_id_from_client_scope(client_id)
            if not account_id:
                raise AgentActionError(409, "Feishu user OAuth export requires an account-owned Agent API key.")
            user_access_token = H.get_valid_feishu_user_access_token(account_id)
            export_response = await loop.run_in_executor(
                None,
                lambda: H.export_markdown_to_lark(
                    resolved_title,
                    markdown,
                    task_id=task_id,
                    artifact_root=H._artifact_storage_dir(),
                    user_access_token=user_access_token,
                    **kwargs,
                ),
            )
        else:
            export_response = await loop.run_in_executor(
                None,
                lambda: H.export_markdown_to_lark(
                    resolved_title,
                    markdown,
                    task_id=task_id,
                    artifact_root=H._artifact_storage_dir(),
                    **kwargs,
                ),
            )
    except Exception as exc:
        status_code = exc.status_code if isinstance(exc, AgentActionError) else 500
        friendly_error = H._friendly_error_message(exc)
        H.log_event(
            task_id=task_id,
            event_name="agent_export_completed",
            source_type=job.get("source_type"),
            source_filename=job.get("source_filename"),
            summary_length=H._text_len(markdown),
            stage="export",
            duration_seconds=round(time.perf_counter() - started_at, 3),
            success=False,
            error_reason=friendly_error,
            export_target=export_target,
            metadata=H._metadata(route=route, target=target, raw_error=str(exc)),
        )
        raise AgentActionError(status_code, friendly_error, cause=exc) from exc

    if isinstance(export_response, dict):
        export_response["doc_title"] = resolved_title
        export_response["task_id"] = task_id
    export_record = {
        "target": target,
        "route": export_target,
        "title": resolved_title,
        "url": export_response.get("url") if isinstance(export_response, dict) else None,
        "response": export_response,
    }
    exports = result.get("exports") if isinstance(result.get("exports"), list) else []
    result["exports"] = [*exports, export_record]
    H.upsert_job(
        task_id=task_id,
        status=job.get("status") or "completed",
        client_id=client_id,
        stage=job.get("stage") or "done",
        progress=job.get("progress") or 100,
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        summary_status=job.get("summary_status"),
        result=result,
        metadata=job.get("metadata"),
    )
    H.log_event(
        task_id=task_id,
        event_name="agent_export_completed",
        source_type=job.get("source_type"),
        source_filename=job.get("source_filename"),
        summary_length=H._text_len(markdown),
        stage="export",
        duration_seconds=round(time.perf_counter() - started_at, 3),
        success=True,
        export_target=export_target,
        feishu_doc_url=export_record["url"],
        metadata=H._metadata(route=route, target=target, doc_title=resolved_title),
    )
    updated = H.get_job(task_id, client_id=client_id) or {**job, "result": result}
    return updated, export_record
