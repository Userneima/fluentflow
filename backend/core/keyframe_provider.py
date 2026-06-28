"""Runtime provider boundary for video keyframe extraction."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from backend.core.frame_extractor import extract_candidate_frames

KeyframeProviderName = Literal["local_ffmpeg", "cloud_ffmpeg_worker", "disabled"]


@dataclass(frozen=True)
class KeyframeExtractionResult:
    provider: KeyframeProviderName
    frames: list[dict[str, Any]]
    skipped_reason: str | None = None

    @property
    def enabled(self) -> bool:
        return self.provider != "disabled" and not self.skipped_reason


def keyframe_extraction_enabled() -> bool:
    value = os.environ.get("FLUENTFLOW_KEYFRAME_EXTRACTION", "1").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def configured_keyframe_provider() -> KeyframeProviderName:
    if not keyframe_extraction_enabled():
        return "disabled"
    value = os.environ.get("FLUENTFLOW_KEYFRAME_PROVIDER", "local_ffmpeg").strip().lower()
    if value in {"", "local", "ffmpeg", "local_ffmpeg"}:
        return "local_ffmpeg"
    if value in {"cloud", "worker", "cloud_ffmpeg", "cloud_ffmpeg_worker"}:
        return "cloud_ffmpeg_worker"
    if value in {"0", "false", "no", "off", "disabled", "none"}:
        return "disabled"
    return "disabled"


def _extract_local_ffmpeg(
    video_path: str,
    output_dir: Path,
    *,
    segments: list[dict[str, Any]] | None,
    scene_threshold: float,
    max_scene_frames: int,
    min_gap_seconds: float,
) -> KeyframeExtractionResult:
    frames = extract_candidate_frames(
        video_path,
        output_dir,
        segments=segments,
        scene_threshold=scene_threshold,
        max_scene_frames=max_scene_frames,
        min_gap_seconds=min_gap_seconds,
    )
    for frame in frames:
        frame.setdefault("provider", "local_ffmpeg")
    return KeyframeExtractionResult(provider="local_ffmpeg", frames=frames)


def _extract_cloud_ffmpeg_worker() -> KeyframeExtractionResult:
    worker_url = os.environ.get("FLUENTFLOW_KEYFRAME_WORKER_URL", "").strip()
    if not worker_url:
        return KeyframeExtractionResult(
            provider="cloud_ffmpeg_worker",
            frames=[],
            skipped_reason="cloud_worker_not_configured",
        )
    return KeyframeExtractionResult(
        provider="cloud_ffmpeg_worker",
        frames=[],
        skipped_reason="cloud_worker_adapter_pending",
    )


def extract_keyframes(
    video_path: str,
    output_dir: Path,
    segments: list[dict[str, Any]] | None = None,
    *,
    provider: KeyframeProviderName | None = None,
    scene_threshold: float = 0.3,
    max_scene_frames: int = 30,
    min_gap_seconds: float = 2.0,
) -> KeyframeExtractionResult:
    selected = provider or configured_keyframe_provider()
    if selected == "disabled":
        return KeyframeExtractionResult(provider="disabled", frames=[], skipped_reason="disabled")
    if selected == "cloud_ffmpeg_worker":
        return _extract_cloud_ffmpeg_worker()
    return _extract_local_ffmpeg(
        video_path,
        output_dir,
        segments=segments,
        scene_threshold=scene_threshold,
        max_scene_frames=max_scene_frames,
        min_gap_seconds=min_gap_seconds,
    )


__all__ = [
    "KeyframeExtractionResult",
    "configured_keyframe_provider",
    "extract_keyframes",
    "keyframe_extraction_enabled",
]
