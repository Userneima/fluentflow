"""FluentFlow: local video → structured notes pipeline (FastAPI backend).

Routes are organized in backend/routers/ and import shared helpers
from backend.core.server_helpers.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.core.server_helpers import (
    FRONTEND_DIST_DIR,
    beta_access_middleware,
    _startup_resume_queue,
)
from backend.core.desktop_sync_client import flush_desktop_sync_outbox

@asynccontextmanager
async def lifespan(app: FastAPI):
    await _startup_resume_queue()
    asyncio.create_task(asyncio.to_thread(flush_desktop_sync_outbox))
    yield

app = FastAPI(title="FluentFlow", lifespan=lifespan)

# ── Middleware ─────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
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
from backend.routers.oss_uploads import router as oss_uploads_router
from backend.routers.config import router as config_router
from backend.routers.events import router as events_router
from backend.routers.agent import router as agent_router
from backend.routers.desktop_sync import router as desktop_sync_router
from backend.routers.desktop_pairing import cloud_router as desktop_pairing_cloud_router, local_router as desktop_pairing_local_router
from backend.routers.spa import router as spa_router
from backend.routers.misc import router as misc_router

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(guest_trial_router)
app.include_router(jobs_router)
app.include_router(video_sources_router)
app.include_router(processing_router)
app.include_router(oss_uploads_router)
app.include_router(config_router)
app.include_router(events_router)
app.include_router(agent_router)
app.include_router(desktop_sync_router)
app.include_router(desktop_pairing_cloud_router)
app.include_router(desktop_pairing_local_router)
app.include_router(misc_router)

# ── Static Files (SPA fallback is handled by routers/spa.py) ───
if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST_DIR / "assets")), name="assets")

app.include_router(spa_router)
