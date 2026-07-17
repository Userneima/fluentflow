"""Safely materialize an OSS source object into the existing task source store."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Protocol

from backend.core.storage_paths import _source_storage_dir


class OssSourceDownloader(Protocol):
    def download_to_file(self, *, object_key: str, target_path: Path) -> int: ...


def materialize_oss_source(
    downloader: OssSourceDownloader,
    *,
    task_id: str,
    object_key: str,
    suffix: str,
    expected_size_bytes: int,
) -> Path:
    """Stream an OSS object into a task-local file and verify its exact size.

    The final path appears only after the full source is written, so a failed
    download cannot be mistaken for a usable task source by the queue.
    """

    if not task_id:
        raise ValueError("task_id is required")
    if expected_size_bytes <= 0:
        raise ValueError("expected_size_bytes must be positive")
    safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    target_dir = _source_storage_dir() / task_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"source{safe_suffix}"
    temporary = target_dir / f".source.{uuid.uuid4().hex}.part"
    try:
        downloaded_size = downloader.download_to_file(object_key=object_key, target_path=temporary)
        actual_size = temporary.stat().st_size
        if downloaded_size != actual_size or actual_size != expected_size_bytes:
            raise RuntimeError("OSS source size verification failed")
        os.replace(temporary, target)
        return target
    finally:
        if temporary.exists():
            temporary.unlink()


__all__ = ["OssSourceDownloader", "materialize_oss_source"]
