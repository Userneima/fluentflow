from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import backend.core.video_source as video_source


def _env_urls(name: str) -> list[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        pytest.skip(f"{name} is not set")
    urls = [item.strip() for item in re.split(r"[\n,]", raw) if item.strip()]
    if not urls:
        pytest.skip(f"{name} has no usable URLs")
    return urls


def test_bilibili_smoke_urls_resolve_to_downloadable_media() -> None:
    for url in _env_urls("FLUENTFLOW_BILI_SMOKE_URLS"):
        resolved = video_source.resolve_video(url)

        assert resolved.provider == "yt-dlp"
        assert resolved.download_url
        assert resolved.title or resolved.video_id
        assert resolved.referer in {None, "https://www.bilibili.com/"}


def test_bilibili_smoke_url_downloads_media(tmp_path: Path) -> None:
    url = (os.environ.get("FLUENTFLOW_BILI_DOWNLOAD_SMOKE_URL") or "").strip()
    if not url:
        pytest.skip("FLUENTFLOW_BILI_DOWNLOAD_SMOKE_URL is not set")

    saved = video_source.download_video_source(url, video_dir=tmp_path)

    assert saved.ok is True
    assert saved.provider == "yt-dlp"
    assert Path(saved.file_path).is_file()
    assert Path(saved.file_path).stat().st_size > 0
    assert Path(saved.metadata_path).is_file()
