"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes:
  GET  /health   – liveness check
  POST /process  – upload video/audio, run STT + summarize, optional Lark export
                   returns Server-Sent Events for real-time progress
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(title="FluentFlow")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5185",
        "http://localhost:5185",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.core.audio_handler import extract_compressed_mp3
    from backend.core.local_stt import transcribe_audio, get_or_load_model
    from backend.core.ai_summarizer import summarize_transcript_to_markdown
    from backend.core.lark_exporter import export_markdown_to_lark
    from backend.core.lark_cli_exporter import export_markdown_via_lark_cli
except ImportError:
    from core.audio_handler import extract_compressed_mp3
    from core.local_stt import transcribe_audio, get_or_load_model
    from core.ai_summarizer import summarize_transcript_to_markdown
    from core.lark_exporter import export_markdown_to_lark
    from core.lark_cli_exporter import export_markdown_via_lark_cli


def _use_lark_cli_export(form_val: Optional[str]) -> bool:
    """True = create doc via local ``lark-cli`` (user OAuth). Explicit false overrides env."""
    v = (form_val or "").strip().lower()
    if v in ("false", "0", "no"):
        return False
    if v in ("true", "1", "yes"):
        return True
    return os.environ.get("FLUENTFLOW_LARK_CLI_EXPORT", "").strip().lower() in ("1", "true", "yes")


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


ALLOWED_SUFFIXES = {
    ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus",
}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/process")
async def process_video(
    file: UploadFile = File(...),
    export_to_lark: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    folder_token: Optional[str] = Form(None),
    deepseek_api_key: Optional[str] = Form(None),
    stt_model: Optional[str] = Form(None),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
) -> StreamingResponse:
    """Upload a file and stream processing progress via SSE."""

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    do_lark = export_to_lark and export_to_lark.lower() in ("true", "1", "yes")
    suffix = Path(file.filename).suffix.lower() or ".mp4"
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")

    td = tempfile.mkdtemp()
    in_path = Path(td) / f"upload{suffix}"
    content = await file.read()
    with open(in_path, "wb") as f:
        f.write(content)

    loop = asyncio.get_event_loop()
    model_size = (stt_model or "").strip() or "small"

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # ── Stage 1: Audio extraction ──────────────────────
            yield _sse({"stage": "audio", "progress": 5})
            out_mp3 = await loop.run_in_executor(
                None, lambda: extract_compressed_mp3(in_path, bitrate="64k")
            )
            yield _sse({"stage": "audio", "progress": 20})

            # ── Stage 2: STT transcription ─────────────────────
            yield _sse({"stage": "stt", "progress": 22})

            progress_queue: asyncio.Queue[dict[str, float]] = asyncio.Queue()
            progress_state: dict[str, float] = {
                "last_sent": 22.0,
                "latest": 22.0,
                "last_push_ts": 0.0,
            }
            progress_lock = threading.Lock()

            def stt_progress_cb(frac: float) -> None:
                # Callback runs in a worker thread; use loop.call_soon_threadsafe to enqueue SSE updates.
                prog = 22.0 + float(frac) * 38.0  # 22–60 range
                if prog < 22.0:
                    prog = 22.0
                if prog > 60.0:
                    prog = 60.0

                now = time.time()
                with progress_lock:
                    # Throttle to avoid flooding the SSE stream.
                    should_send = (
                        (prog - progress_state["last_sent"]) >= 2.0
                        or (now - progress_state["last_push_ts"]) >= 0.6
                        or prog >= 60.0
                    )
                    if not should_send:
                        return

                    progress_state["latest"] = prog
                    progress_state["last_sent"] = prog
                    progress_state["last_push_ts"] = now

                loop.call_soon_threadsafe(
                    progress_queue.put_nowait,
                    {"stage": "stt", "progress": prog},
                )

            tr_future = loop.run_in_executor(
                None,
                lambda: transcribe_audio(
                    out_mp3, model_size=model_size, on_progress=stt_progress_cb
                ),
            )

            # Stream progress updates while STT is running.
            while True:
                if tr_future.done():
                    break
                try:
                    ev = await asyncio.wait_for(progress_queue.get(), timeout=0.5)
                    yield _sse(ev)
                except asyncio.TimeoutError:
                    # No new progress updates in this interval.
                    continue

            # Ensure we also drain any late progress events.
            tr = await tr_future
            while True:
                try:
                    ev = progress_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                yield _sse(ev)

            yield _sse({"stage": "stt", "progress": 60})

            # ── Stage 3: AI summarization ──────────────────────
            yield _sse({"stage": "summary", "progress": 62})

            summary_md = ""
            try:
                kwargs: dict[str, Any] = {}
                api_key = (deepseek_api_key or "").strip()
                if api_key:
                    kwargs["api_key"] = api_key
                if (sp := (system_prompt or "").strip()):
                    kwargs["system_prompt"] = sp
                summary_md = await loop.run_in_executor(
                    None,
                    lambda: summarize_transcript_to_markdown(tr.text, **kwargs),
                )
            except Exception as exc:
                logger.warning("AI summarization failed, using raw transcript: %s", exc)
                summary_md = f"# Transcript\n\n{tr.text}"

            yield _sse({"stage": "summary", "progress": 88})

            # ── Build result ───────────────────────────────────
            duration_sec = tr.duration or (tr.segments[-1].end if tr.segments else 0)
            result: dict[str, Any] = {
                "filename": file.filename,
                "transcript_text": tr.text,
                "transcript_text_preview": tr.text[:200],
                "summary_markdown": summary_md,
                "audio_duration_seconds": round(duration_sec, 1),
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in tr.segments
                ],
            }

            # ── Stage 4: Lark export (optional) ───────────────
            if do_lark:
                yield _sse({"stage": "export", "progress": 90})
                doc_title = title or f"FluentFlow - {Path(file.filename).stem}"
                try:
                    if _use_lark_cli_export(lark_via_cli):
                        resp = await loop.run_in_executor(
                            None,
                            lambda: export_markdown_via_lark_cli(doc_title, summary_md),
                        )
                    else:
                        lark_kwargs: dict[str, Any] = {}
                        if (lark_id := (lark_app_id or "").strip()):
                            lark_kwargs["app_id"] = lark_id
                        if (lark_secret := (lark_app_secret or "").strip()):
                            lark_kwargs["app_secret"] = lark_secret
                        if folder_token:
                            lark_kwargs["folder_token"] = folder_token
                        resp = await loop.run_in_executor(
                            None,
                            lambda: export_markdown_to_lark(doc_title, summary_md, **lark_kwargs),
                        )
                    result["lark_response"] = resp
                except Exception as e:
                    result["lark_error"] = str(e)

            # ── Done ───────────────────────────────────────────
            yield _sse({"stage": "done", "progress": 100, "result": result})

        except Exception as exc:
            logger.exception("Processing failed")
            yield _sse({"stage": "error", "progress": 0, "error": str(exc)})
        finally:
            shutil.rmtree(td, ignore_errors=True)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/export-lark")
async def export_lark(
    markdown: str = Form(...),
    title: str = Form("FluentFlow Export"),
    lark_app_id: Optional[str] = Form(None),
    lark_app_secret: Optional[str] = Form(None),
    lark_via_cli: Optional[str] = Form(None),
):
    """Standalone endpoint: export existing markdown to a Lark document."""
    loop = asyncio.get_event_loop()
    try:
        if _use_lark_cli_export(lark_via_cli):
            resp = await loop.run_in_executor(
                None, lambda: export_markdown_via_lark_cli(title, markdown)
            )
            return resp
        kwargs: dict[str, Any] = {}
        if (v := (lark_app_id or "").strip()):
            kwargs["app_id"] = v
        if (v := (lark_app_secret or "").strip()):
            kwargs["app_secret"] = v
        resp = await loop.run_in_executor(
            None, lambda: export_markdown_to_lark(title, markdown, **kwargs)
        )
        return resp
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/regenerate-summary")
async def regenerate_summary(
    transcript: str = Form(...),
    deepseek_api_key: Optional[str] = Form(None),
    system_prompt: Optional[str] = Form(None),
):
    """Re-run AI summarization on an existing transcript with optional custom prompt."""
    loop = asyncio.get_event_loop()
    kwargs: dict[str, Any] = {}
    if (k := (deepseek_api_key or "").strip()):
        kwargs["api_key"] = k
    if (p := (system_prompt or "").strip()):
        kwargs["system_prompt"] = p
    try:
        md = await loop.run_in_executor(
            None, lambda: summarize_transcript_to_markdown(transcript, **kwargs)
        )
        return {"summary_markdown": md}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# Mount frontend static files last so API routes take precedence
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to local video file")
    parser.add_argument("--export-to-lark", action="store_true")
    parser.add_argument("--title", default=None)
    parser.add_argument("--folder-token", default=None)
    args = parser.parse_args()

    vp = Path(args.video)
    if not vp.is_file():
        raise SystemExit(f"video not found: {vp}")

    mp3 = extract_compressed_mp3(vp)
    tr = transcribe_audio(mp3)
    try:
        md = summarize_transcript_to_markdown(tr.text)
    except Exception:
        md = f"# Transcript\n\n{tr.text}"

    print("SUMMARY:\n", md[:2000])
    if args.export_to_lark:
        print("Exporting to Lark...")
        try:
            out = export_markdown_to_lark(args.title or vp.stem, md, folder_token=args.folder_token)
            print("Export result:", out)
        except Exception as e:
            print("Export failed:", e)
