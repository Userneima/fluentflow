"""Storage-directory path helpers, extracted from server_helpers.py.
Thin wrappers over runtime_paths — re-imported by server_helpers so
H._artifact_storage_dir etc. keep working. No server_helpers imports."""

from __future__ import annotations

from pathlib import Path

from backend.core.runtime_paths import (
    default_artifact_dir,
    default_edited_transcript_dir,
    default_source_dir,
    default_transcript_edit_records_dir,
    default_video_source_dir,
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_storage_dir() -> Path:
    return default_source_dir()


def _video_source_storage_dir() -> Path:
    return default_video_source_dir()


def _edited_transcript_dir() -> Path:
    return default_edited_transcript_dir()


def _artifact_storage_dir() -> Path:
    return default_artifact_dir()


def _transcript_edit_records_dir() -> Path:
    return default_transcript_edit_records_dir()
