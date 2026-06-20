"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes are organized in backend/routers/ and import shared helpers
from backend.core.server_helpers.
"""

from __future__ import annotations

import urllib  # noqa: F401 — re-export for test compatibility
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.server_helpers import (
    APP_VERSION,
    EVENT_SCHEMA_VERSION,
    FRONTEND_DIR,
    FRONTEND_INDEX,
    FRONTEND_DIST_DIR,
    FRONTEND_ROOT,
    API_ROUTE_PREFIXES,
    beta_access_middleware,
    _startup_resume_queue,
    # ── Re-exports for backward compatibility (tests, legacy imports) ──
    GUEST_TRIAL_TOKEN_HEADER,
    HTTPException,
    JSONResponse,
    JOB_EVENTS,
    _SUBMISSION_RATE_EVENTS,
    _allowed_stt_providers,
    _duration_limit_error,
    _enforce_active_job_limit,
    _enforce_daily_quota,
    _enforce_global_active_job_limit,
    _enforce_global_daily_quota,
    _enforce_guest_daily_ip_limit,
    _enforce_history_retention,
    _enforce_submission_rate_limit,
    _friendly_error_message,
    _is_public_request,
    _job_metadata_for_update,
    _normalize_stt_provider,
    _ops_status_payload,
    _request_client_scope,
    _request_is_local_execution,
    _resume_queued_transcription_jobs,
    _run_queued_transcription,
    _run_video_source_job,
    _should_proxy_cloud_workspace,
    _write_edited_transcript_backup,
    get_job,
    upsert_job,
    delete_jobs,
    list_jobs,
    log_event,
    update_job_result,
    job_has_transcript_result,
    list_job_summaries,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    await _startup_resume_queue()
    yield

app = FastAPI(title="FluentFlow", lifespan=lifespan)

# ── Middleware ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(beta_access_middleware)

# ── API Routers ────────────────────────────────────────────────
from backend.routers.health import router as health_router
from backend.routers.auth import router as auth_router
from backend.routers.admin import router as admin_router
from backend.routers.guest_trial import router as guest_trial_router
from backend.routers.jobs import router as jobs_router
from backend.routers.video_sources import router as video_sources_router
from backend.routers.processing import router as processing_router
from backend.routers.config import router as config_router
from backend.routers.events import router as events_router
from backend.routers.spa import router as spa_router
from backend.routers.misc import router as misc_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(guest_trial_router)
app.include_router(jobs_router)
app.include_router(video_sources_router)
app.include_router(processing_router)
app.include_router(config_router)
app.include_router(events_router)
app.include_router(misc_router)

# ── Static Files (SPA fallback is handled by routers/spa.py) ───
if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="assets")

app.include_router(spa_router)
