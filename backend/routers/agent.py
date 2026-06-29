from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Request

import backend.core.server_helpers as H
from backend.core.agent_package import build_agent_task_package, note_generation_diagnosis
from backend.core.agent_task_actions import AgentActionError, export_agent_note, regenerate_agent_note

router = APIRouter(prefix="/agent/v1")


def _truthy_json(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}


def _task_package_response(job: dict[str, Any]) -> dict[str, Any]:
    return build_agent_task_package(job, artifact_root=H._artifact_storage_dir())


def _job_for_request(request: Request, task_id: str) -> dict[str, Any]:
    job = H.get_job(task_id, client_id=H._request_client_scope(request))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/tasks")
async def create_agent_task(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    input_text = str(payload.get("input") or payload.get("url") or "").strip()
    transcript = str(payload.get("transcript_text") or "").strip()
    input_type = str(payload.get("input_type") or "").strip().lower()
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    client_id = H._request_client_scope(request)

    if input_text and input_type in {"", "video_link", "url", "share_text"}:
        if len(input_text) > 4000:
            raise HTTPException(status_code=400, detail="分享文本过长")
        H._enforce_submission_rate_limit(request, incoming=1)
        H._enforce_active_job_limit(client_id, incoming=1)
        H._enforce_global_active_job_limit(incoming=1)
        H._enforce_daily_quota(client_id, incoming_jobs=1)
        H._enforce_global_daily_quota(client_id=client_id, incoming_jobs=1)

        task_id_value = H._new_task_id()
        queue_options = H._queue_options_from_mapping(options)
        raw_title = str(payload.get("title") or input_text[:80]).strip()
        display_name = H.display_title_for_user(raw_title, raw_title)
        metadata = H._metadata(
            route="/agent/v1/tasks",
            agent_input_type="video_link",
            queue_options=queue_options,
            raw_title=raw_title,
            display_title=display_name,
            video_source_input_preview=input_text[:200],
        )
        H.log_event(
            task_id=task_id_value,
            event_name="agent_task_submitted",
            source_type="video_link",
            source_filename=display_name,
            stage="resolving",
            success=True,
            metadata=metadata,
        )
        H.upsert_job(
            task_id=task_id_value,
            status="running",
            client_id=client_id,
            stage="resolving",
            progress=2,
            source_type="video_link",
            source_filename=display_name,
            metadata=metadata,
        )
        H._start_video_source_job({
            "task_id": task_id_value,
            "input": input_text,
            "title": raw_title,
            "options": queue_options,
            "base_url": H._queue_base_url_from_request(request),
            "client_id": client_id,
        })
        job = H.get_job(task_id_value, client_id=client_id) or {"task_id": task_id_value, "status": "running"}
        return {
            "ok": True,
            "task_id": task_id_value,
            "status": job.get("status"),
            "package_url": f"/agent/v1/tasks/{task_id_value}/package",
            "job": job,
        }

    if transcript and input_type in {"", "transcript", "transcript_text"}:
        task_id_value = str(payload.get("task_id") or "").strip() or H._new_task_id()
        title = str(payload.get("title") or "Transcript").strip()
        skip_summary = _truthy_json(options.get("skip_summary") if isinstance(options, dict) else None)
        result: dict[str, Any] = {
            "task_id": task_id_value,
            "filename": title,
            "display_title": title,
            "transcript_text": transcript,
            "transcript_text_preview": transcript[:200],
            "source": "agent_transcript",
        }
        summary_status = "skipped"
        if skip_summary:
            result.update({"summary_skipped": True, "summary_status": "skipped"})
        else:
            kwargs = H._ai_kwargs(
                deepseek_api_key=payload.get("deepseek_api_key"),
                openai_api_key=payload.get("openai_api_key"),
                ai_provider=payload.get("ai_provider"),
                ai_model=payload.get("ai_model"),
                system_prompt=payload.get("system_prompt"),
                note_mode=options.get("note_mode") if isinstance(options, dict) else None,
            )
            kwargs, note_mode_plan = H._plan_note_mode_for_summary(
                kwargs,
                transcript,
                task_id=task_id_value,
                route="/agent/v1/tasks",
                filename=title,
                current_prompt_preset=options.get("prompt_preset") if isinstance(options, dict) else None,
            )
            loop = asyncio.get_running_loop()
            summary_result = await loop.run_in_executor(
                None,
                lambda: H.summarize_transcript_with_metadata(transcript, **kwargs),
            )
            result.update({
                "summary_markdown": summary_result.markdown,
                "summary_status": "completed",
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
                **{key: value for key, value in note_mode_plan.items() if key.startswith("note_mode_plan_")},
            })
            summary_status = "completed"
        result = H._attach_result_artifacts(task_id_value, result)
        H.upsert_job(
            task_id=task_id_value,
            status="completed",
            client_id=client_id,
            stage="done",
            progress=100,
            source_type="agent_transcript",
            source_filename=title,
            summary_status=summary_status,
            result=result,
            metadata=H._metadata(route="/agent/v1/tasks", agent_input_type="transcript"),
        )
        job = H.get_job(task_id_value, client_id=client_id)
        return {
            "ok": True,
            "task_id": task_id_value,
            "status": "completed",
            "package_url": f"/agent/v1/tasks/{task_id_value}/package",
            "package": _task_package_response(job or {"task_id": task_id_value, "result": result}),
        }

    raise HTTPException(status_code=400, detail="Provide a video link input or transcript_text")


@router.get("/tasks/{task_id}")
def get_agent_task(request: Request, task_id: str) -> dict[str, Any]:
    job = _job_for_request(request, task_id)
    return {
        "ok": True,
        "task": {
            "task_id": job.get("task_id"),
            "status": job.get("status"),
            "stage": job.get("stage"),
            "progress": job.get("progress"),
            "summary_status": job.get("summary_status"),
        },
        "package_url": f"/agent/v1/tasks/{task_id}/package",
    }


@router.get("/tasks/{task_id}/package")
def get_agent_task_package(request: Request, task_id: str) -> dict[str, Any]:
    return _task_package_response(_job_for_request(request, task_id))


@router.post("/tasks/{task_id}/wait")
async def wait_agent_task(request: Request, task_id: str, payload: Optional[dict[str, Any]] = Body(None)) -> dict[str, Any]:
    payload = payload or {}
    timeout_seconds = min(max(float(payload.get("timeout_seconds") or 30), 0), 60)
    poll_interval = min(max(float(payload.get("poll_interval_seconds") or 2), 0.5), 10)
    deadline = time.monotonic() + timeout_seconds
    while True:
        job = _job_for_request(request, task_id)
        if job.get("status") in {"completed", "failed", "cancelled"}:
            return {"ok": True, "done": True, "package": _task_package_response(job)}
        if time.monotonic() >= deadline:
            return {
                "ok": True,
                "done": False,
                "task": {
                    "task_id": job.get("task_id"),
                    "status": job.get("status"),
                    "stage": job.get("stage"),
                    "progress": job.get("progress"),
                },
                "package_url": f"/agent/v1/tasks/{task_id}/package",
            }
        await asyncio.sleep(poll_interval)


@router.get("/tasks/{task_id}/diagnosis")
def get_agent_task_diagnosis(request: Request, task_id: str) -> dict[str, Any]:
    job = _job_for_request(request, task_id)
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    return {
        "ok": True,
        "task_id": task_id,
        "note": note_generation_diagnosis(job, result),
    }


@router.post("/tasks/{task_id}/note/regenerate")
async def regenerate_agent_task_note(request: Request, task_id: str, payload: Optional[dict[str, Any]] = Body(None)) -> dict[str, Any]:
    payload = payload or {}
    client_id = H._request_client_scope(request)
    job = _job_for_request(request, task_id)
    try:
        updated = await regenerate_agent_note(task_id=task_id, client_id=client_id, job=job, payload=payload)
    except AgentActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc.cause
    return {"ok": True, "task_id": task_id, "package": _task_package_response(updated)}


@router.post("/tasks/{task_id}/exports")
async def export_agent_task(request: Request, task_id: str, payload: Optional[dict[str, Any]] = Body(None)) -> dict[str, Any]:
    payload = payload or {}
    client_id = H._request_client_scope(request)
    job = _job_for_request(request, task_id)
    try:
        updated, export_record = await export_agent_note(task_id=task_id, client_id=client_id, job=job, payload=payload)
    except AgentActionError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc.cause
    return {"ok": True, "task_id": task_id, "export": export_record, "package": _task_package_response(updated)}
