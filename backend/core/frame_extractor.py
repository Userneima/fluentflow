"""Extract candidate frames from video for multimodal note generation."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found")
    return path


def _ffprobe_path() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe not found")
    return path


def _video_duration_seconds(video_path: str) -> float:
    result = subprocess.run(
        [
            _ffprobe_path(),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True, capture_output=True, text=True, timeout=15,
    )
    return max(0.0, float((result.stdout or "").strip()))


def _parse_showinfo_timestamps(stderr: str) -> list[float]:
    timestamps: list[float] = []
    for match in re.finditer(r"pts_time:([0-9]+(?:\.[0-9]+)?)", stderr or ""):
        try:
            timestamps.append(float(match.group(1)))
        except ValueError:
            continue
    return timestamps


def _selected_even_indices(total: int, keep: int) -> list[int]:
    if total <= 0 or keep <= 0:
        return []
    if total <= keep:
        return list(range(total))
    if keep == 1:
        return [0]
    return [round(i * (total - 1) / (keep - 1)) for i in range(keep)]


def _extract_scene_frames(
    video_path: str,
    output_dir: Path,
    *,
    threshold: float,
    max_frames: int,
) -> list[dict[str, Any]]:
    """Run ffmpeg scene detection and extract key frames."""
    for stale in output_dir.glob("scene_*.jpg"):
        stale.unlink(missing_ok=True)
    output_pattern = output_dir / "scene_%04d.jpg"
    cmd = [
        _ffmpeg_path(),
        "-y",
        "-i", str(video_path),
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-vsync", "vfr",
        "-q:v", "2",
        str(output_pattern),
    ]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    frames = sorted(output_dir.glob("scene_*.jpg"))
    duration = _video_duration_seconds(video_path)
    timestamps = _parse_showinfo_timestamps(completed.stderr or "")
    frame_records: list[tuple[Path, float]] = []
    for idx, path in enumerate(frames):
        fallback = duration * idx / max(len(frames), 1)
        timestamp = timestamps[idx] if idx < len(timestamps) else fallback
        frame_records.append((path, timestamp))

    selected_indices = set(_selected_even_indices(len(frame_records), max_frames))
    selected_records: list[tuple[Path, float]] = []
    for idx, record in enumerate(frame_records):
        if idx in selected_indices:
            selected_records.append(record)
        else:
            record[0].unlink(missing_ok=True)

    results: list[dict[str, Any]] = []
    for path, timestamp in selected_records:
        if path.is_file():
            results.append({
                "path": str(path),
                "timestamp_seconds": round(timestamp, 1),
                "source": "scene",
            })
    return results


def _extract_timepoint_frames(
    video_path: str,
    output_dir: Path,
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract one frame at each segment start time."""
    results: list[dict[str, Any]] = []
    seen_timestamps: set[float] = set()
    for segment in segments:
        try:
            ts = round(float(segment.get("start") or 0), 1)
        except (TypeError, ValueError):
            continue
        if ts in seen_timestamps:
            continue
        seen_timestamps.add(ts)
        mm = int(ts // 60)
        ss = int(ts % 60)
        filename = f"ts_{mm:02d}{ss:02d}.jpg"
        output = output_dir / filename
        cmd = [
            _ffmpeg_path(),
            "-y",
            "-ss", str(ts),
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            str(output),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        except subprocess.CalledProcessError:
            continue
        if output.is_file():
            results.append({
                "path": str(output),
                "timestamp_seconds": ts,
                "source": "timepoint",
            })
    return results


def _deduplicate_frames(
    scene_frames: list[dict[str, Any]],
    timepoint_frames: list[dict[str, Any]],
    *,
    min_gap_seconds: float = 2.0,
) -> list[dict[str, Any]]:
    """Merge scene and timepoint frames, dropping near-duplicates within min_gap_seconds."""
    merged = sorted(scene_frames + timepoint_frames, key=lambda f: f["timestamp_seconds"])
    if not merged:
        return []
    deduped: list[dict[str, Any]] = [merged[0]]
    for frame in merged[1:]:
        if frame["timestamp_seconds"] - deduped[-1]["timestamp_seconds"] >= min_gap_seconds:
            deduped.append(frame)
        else:
            # Transcript-derived timepoints map better to note sections than raw scene changes.
            if frame["source"] == "timepoint" and deduped[-1]["source"] == "scene":
                deduped[-1] = frame
    return deduped


def extract_candidate_frames(
    video_path: str,
    output_dir: Path,
    segments: list[dict[str, Any]] | None = None,
    *,
    scene_threshold: float = 0.3,
    max_scene_frames: int = 30,
    min_gap_seconds: float = 2.0,
) -> list[dict[str, Any]]:
    """Extract candidate still frames from a video file.

    Uses ffmpeg scene-detection to find significant visual changes, optionally
    supplemented by per-segment timepoint captures. Returns a deduplicated list
    of frame metadata sorted by timestamp.

    Args:
        video_path: Path to the source video file.
        output_dir: Directory to write JPEG frames into.
        segments: Optional transcript segments with ``start`` timestamps.
        scene_threshold: ffmpeg scene change sensitivity (0.0-1.0).
        max_scene_frames: Upper bound on scene frames kept.
        min_gap_seconds: Minimum gap between consecutive output frames.

    Returns:
        List of dicts with keys ``path``, ``timestamp_seconds``, and ``source``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    scene_frames: list[dict[str, Any]] = []
    try:
        scene_frames = _extract_scene_frames(
            video_path, output_dir, threshold=scene_threshold, max_frames=max_scene_frames
        )
    except Exception as exc:
        logger.warning("Scene frame extraction failed: %s", exc)

    timepoint_frames: list[dict[str, Any]] = []
    if segments:
        try:
            timepoint_frames = _extract_timepoint_frames(video_path, output_dir, segments)
        except Exception as exc:
            logger.warning("Timepoint frame extraction failed: %s", exc)

    return _deduplicate_frames(scene_frames, timepoint_frames, min_gap_seconds=min_gap_seconds)


__all__ = ["extract_candidate_frames"]
