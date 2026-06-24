from __future__ import annotations

from pathlib import Path

import backend.core.video_source as video_source


def test_extract_first_url_from_douyin_share_text() -> None:
    text = "复制这条消息，打开抖音看看 https://v.douyin.com/abc123/ 这个视频"

    assert video_source.extract_first_url(text) == "https://v.douyin.com/abc123/"


def test_resolve_direct_video_accepts_douyinvod_url() -> None:
    resolved = video_source.resolve_direct_video(
        "https://v26-dy.douyinvod.com/abc/play/?mime_type=video_mp4&video_id=123456",
    )

    assert resolved is not None
    assert resolved.provider == "direct"
    assert resolved.download_url.startswith("https://v26-dy.douyinvod.com/")


def test_miuistore_link_parser_prefers_mp4_link() -> None:
    html = """
    <a href="https://example.com/not-video">x</a>
    <a href="https://v.douyinvod.com/play/?mime_type=video_mp4">download</a>
    """
    links = video_source.parse_miuistore_links(html)

    assert video_source.choose_miuistore_video_url(links) == "https://v.douyinvod.com/play/?mime_type=video_mp4"


def test_download_video_source_writes_metadata_and_reuses_existing_file(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="direct",
        source_url="https://v.douyinvod.com/play/?video_id=demo123&mime_type=video_mp4",
        download_url="https://v.douyinvod.com/play/?video_id=demo123&mime_type=video_mp4",
        video_id="demo123",
        title="测试视频",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text: resolved)

    def fake_download(url: str, file_path: Path, on_progress=None) -> int:
        file_path.write_bytes(b"video")
        return 5

    monkeypatch.setattr(video_source, "download_file", fake_download)

    saved = video_source.download_video_source("https://v.douyinvod.com/play/?video_id=demo123", video_dir=tmp_path)

    assert saved.filename == "demo123-测试视频.mp4"
    assert saved.raw_title == "测试视频"
    assert saved.display_title == "测试视频"
    assert saved.title == "测试视频"
    assert Path(saved.file_path).is_file()
    assert Path(saved.metadata_path).is_file()
    assert (tmp_path / "视频链接相关信息.md").read_text(encoding="utf-8").strip()


def test_download_video_source_splits_raw_and_display_title(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="direct",
        source_url="https://v.douyinvod.com/play/?video_id=7651613998131006774&mime_type=video_mp4",
        download_url="https://v.douyinvod.com/play/?video_id=7651613998131006774&mime_type=video_mp4",
        video_id="7651613998131006774",
        title="7651613998131006774-四大核心Skill架构与配置指南详解",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text: resolved)
    monkeypatch.setattr(video_source, "download_file", lambda url, file_path, on_progress=None: file_path.write_bytes(b"video") or 5)

    saved = video_source.download_video_source("https://v.douyin.com/demo/", video_dir=tmp_path)

    assert saved.raw_title == "7651613998131006774-四大核心Skill架构与配置指南详解"
    assert saved.display_title == "四大核心Skill架构与配置指南详解"
    assert saved.title == "四大核心Skill架构与配置指南详解"
    assert saved.filename == "7651613998131006774-四大核心Skill架构与配置指南详解.mp4"
