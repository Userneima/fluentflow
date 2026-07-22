from __future__ import annotations

from pathlib import Path

import pytest

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


def test_choose_yt_dlp_media_pairs_bilibili_video_and_audio() -> None:
    info = {
        "formats": [
            {
                "url": "https://upos.example/video-low.m4s",
                "vcodec": "avc1",
                "acodec": "none",
                "ext": "mp4",
                "height": 360,
                "filesize": 1_000,
            },
            {
                "url": "https://upos.example/video-high.m4s",
                "vcodec": "avc1",
                "acodec": "none",
                "ext": "mp4",
                "height": 720,
                "filesize": 2_000,
            },
            {
                "url": "https://upos.example/audio.m4s",
                "vcodec": "none",
                "acodec": "mp4a",
                "ext": "m4a",
                "abr": 128,
            },
        ],
    }

    video_url, audio_url = video_source.choose_yt_dlp_media(info)

    assert video_url == "https://upos.example/video-high.m4s"
    assert audio_url == "https://upos.example/audio.m4s"


def test_choose_yt_dlp_media_prefers_combined_stream_when_available() -> None:
    info = {
        "formats": [
            {
                "url": "https://upos.example/video-only.m4s",
                "vcodec": "avc1",
                "acodec": "none",
                "ext": "mp4",
                "height": 1080,
            },
            {
                "url": "https://upos.example/combined.mp4",
                "vcodec": "avc1",
                "acodec": "mp4a",
                "ext": "mp4",
                "height": 720,
            },
            {
                "url": "https://upos.example/audio.m4s",
                "vcodec": "none",
                "acodec": "mp4a",
                "ext": "m4a",
            },
        ],
    }

    video_url, audio_url = video_source.choose_yt_dlp_media(info)

    assert video_url == "https://upos.example/combined.mp4"
    assert audio_url is None


def test_download_timeout_scales_with_duration_and_size(monkeypatch) -> None:
    monkeypatch.delenv("FLUENTFLOW_YT_DLP_DOWNLOAD_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("FLUENTFLOW_YT_DLP_MAX_TIMEOUT_SECONDS", "3600")

    short_budget = video_source.download_timeout_seconds(duration_seconds=120, estimated_size_bytes=20 * 1024 * 1024)
    long_budget = video_source.download_timeout_seconds(duration_seconds=5400, estimated_size_bytes=250 * 1024 * 1024)

    assert short_budget == 900
    assert long_budget > short_budget
    assert long_budget <= 3600


def test_estimate_yt_dlp_size_uses_largest_available_format() -> None:
    assert video_source.estimate_yt_dlp_size_bytes({
        "formats": [
            {"filesize_approx": 100},
            {"filesize": 250},
        ],
    }) == 250


def test_bilibili_url_detection_covers_public_submission_shapes() -> None:
    assert video_source.is_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD/")
    assert video_source.is_bilibili_url("https://www.bilibili.com/video/BV1xx411c7mD/?p=2")
    assert video_source.is_bilibili_url("https://b23.tv/abc123")
    assert not video_source.is_bilibili_url("https://www.youtube.com/watch?v=demo")


def test_run_yt_dlp_adds_bilibili_headers(monkeypatch) -> None:
    captured = {}

    class FakeResult:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(args, capture_output=True, text=True, timeout=90):
        captured["args"] = args
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        return FakeResult()

    monkeypatch.setattr(video_source.subprocess, "run", fake_run)

    video_source.run_yt_dlp("https://www.bilibili.com/video/BVdemo/")

    args = captured["args"]
    assert "Referer:https://www.bilibili.com/" in args
    assert "Origin:https://www.bilibili.com" in args
    assert any(value.startswith("User-Agent:Mozilla/5.0") for value in args)
    assert args[-1] == "https://www.bilibili.com/video/BVdemo/"


def test_run_yt_dlp_adds_youtube_android_client(monkeypatch) -> None:
    captured = {}

    class FakeResult:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(args, capture_output=True, text=True, timeout=90):
        captured["args"] = args
        return FakeResult()

    monkeypatch.setattr(video_source.subprocess, "run", fake_run)

    video_source.run_yt_dlp("https://youtu.be/demo123")

    args = captured["args"]
    assert args[0] == video_source.sys.executable
    assert "--extractor-args" in args
    assert "youtube:player_client=android" in args
    assert args[-1] == "https://youtu.be/demo123"


def test_download_youtube_captions_uses_auto_srt_subtitles(tmp_path, monkeypatch) -> None:
    captured = {}

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, capture_output=True, text=True, timeout=120):
        captured["args"] = args
        captured["timeout"] = timeout
        output_template = args[args.index("-o") + 1]
        Path(output_template.replace("%(ext)s", "en.srt")).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        return FakeResult()

    monkeypatch.setenv("FLUENTFLOW_YOUTUBE_SUB_LANGS", "en")
    monkeypatch.setattr(video_source.subprocess, "run", fake_run)

    size = video_source.download_youtube_captions(
        "https://youtu.be/demo123",
        tmp_path / "demo123.srt",
    )

    args = captured["args"]
    assert size > 0
    assert "--write-auto-subs" in args
    assert "--write-subs" in args
    assert args[args.index("--sub-langs") + 1] == "en"
    assert args[args.index("--sub-format") + 1] == "srt"
    assert "youtube:player_client=android" in args
    assert (tmp_path / "demo123.srt").read_text(encoding="utf-8").startswith("1\n")


def test_download_youtube_captions_stops_after_first_success(tmp_path, monkeypatch) -> None:
    calls = []

    class FakeResult:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(args, capture_output=True, text=True, timeout=120):
        calls.append(args[args.index("--sub-langs") + 1])
        output_template = args[args.index("-o") + 1]
        Path(output_template.replace("%(ext)s", "en.srt")).write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
            encoding="utf-8",
        )
        return FakeResult()

    monkeypatch.setenv("FLUENTFLOW_YOUTUBE_SUB_LANGS", "en,zh-Hant")
    monkeypatch.setattr(video_source.subprocess, "run", fake_run)

    video_source.download_youtube_captions("https://youtu.be/demo123", tmp_path / "demo123.srt")

    assert calls == ["en"]


def test_miuistore_field_parser_accepts_extra_value_classes() -> None:
    html = """
    <div class='col text-md-end col-label'>视频标题：</div>
    <div class='col col-value col-title'>测试 B 站视频</div>
    """

    assert video_source.parse_miuistore_field(html, "视频标题") == "测试 B 站视频"


def test_resolve_video_stops_bilibili_after_yt_dlp_failure(monkeypatch) -> None:
    def fail_if_called(url: str, timeout: float = 45) -> str:
        raise AssertionError(f"miuistore should not be called for Bilibili: {url}")

    monkeypatch.setattr(video_source, "_resolve_with_yt_dlp_attempt", lambda url, cookies_from_browser=None: (None, "unavailable"))
    monkeypatch.setattr(video_source, "fetch_text", fail_if_called)

    with pytest.raises(RuntimeError, match="需要登录后才能下载"):
        video_source.resolve_video("https://www.bilibili.com/video/BVdemo/?p=2")


def test_resolve_video_records_yt_dlp_fallback_to_miuistore(monkeypatch) -> None:
    fallback = video_source.ResolvedVideo(
        provider="miuistore",
        source_url="https://v.douyin.com/demo/",
        download_url="https://v.douyinvod.com/play/?mime_type=video_mp4",
    )
    monkeypatch.setattr(video_source, "_resolve_with_yt_dlp_attempt", lambda url, cookies_from_browser=None: (None, "unavailable"))
    monkeypatch.setattr(video_source, "_resolve_with_miuistore_attempt", lambda input_text: (fallback, None))

    resolved = video_source.resolve_video("https://v.douyin.com/demo/")

    assert resolved.resolution_trace == [
        {"provider": "yt-dlp", "status": "failed", "reason": "unavailable"},
        {"provider": "miuistore", "status": "selected"},
    ]


def test_resolve_video_keeps_trace_when_all_resolvers_fail(monkeypatch) -> None:
    monkeypatch.setattr(video_source, "_resolve_with_yt_dlp_attempt", lambda url, cookies_from_browser=None: (None, "rate_limited"))
    monkeypatch.setattr(video_source, "_resolve_with_miuistore_attempt", lambda input_text: (None, "unavailable"))

    with pytest.raises(video_source.VideoSourceResolutionError) as captured:
        video_source.resolve_video("https://v.douyin.com/demo/")

    assert captured.value.resolution_trace == [
        {"provider": "yt-dlp", "status": "failed", "reason": "rate_limited"},
        {"provider": "miuistore", "status": "failed", "reason": "unavailable"},
    ]


def test_video_source_pending_title_ignores_bilibili_tracking_query() -> None:
    title = video_source.display_title_for_source_input(
        "https://www.bilibili.com/video/BV1JBoEBbEH7/?spm_id_from=333.337.search-card.all.click&vd_source=demo"
    )

    assert title == "Bilibili 视频 BV1JBoEBbEH7"
    assert "spm_id_from" not in title
    assert "vd_source" not in title


def test_bilibili_download_uses_bilibili_referer_for_upos_stream(monkeypatch, tmp_path) -> None:
    captured = {}

    class FakeResponse:
        headers = {"content-length": "5"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def read(self, size: int = -1) -> bytes:
            if captured.get("read"):
                return b""
            captured["read"] = True
            return b"video"

    def fake_urlopen(request, timeout: float = 120):
        captured["referer"] = request.headers.get("Referer")
        return FakeResponse()

    monkeypatch.setattr(video_source.urllib.request, "urlopen", fake_urlopen)

    size = video_source.download_file("https://upos-sz-mirrorcos.bilivideo.com/video.m4s", tmp_path / "video.m4s")

    assert size == 5
    assert captured["referer"] == "https://www.bilibili.com/"


def test_download_video_source_writes_metadata_and_reuses_existing_file(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="direct",
        source_url="https://v.douyinvod.com/play/?video_id=demo123&mime_type=video_mp4",
        download_url="https://v.douyinvod.com/play/?video_id=demo123&mime_type=video_mp4",
        video_id="demo123",
        title="测试视频",
        resolution_trace=[{"provider": "direct", "status": "selected"}],
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)

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
    assert saved.resolution_trace == [{"provider": "direct", "status": "selected"}]
    assert (tmp_path / "视频链接相关信息.md").read_text(encoding="utf-8").strip()


def test_download_video_source_uses_yt_dlp_for_yt_dlp_provider(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="yt-dlp",
        source_url="https://video.example/watch/demo123",
        download_url="https://cdn.example/video.mp4",
        video_id="demo123",
        title="Video Demo",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)
    monkeypatch.setattr(video_source, "download_file", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("download_file should not be used")))

    def fake_download_yt_dlp_media(url, file_path, on_progress=None, **kwargs):
        assert url == "https://video.example/watch/demo123"
        file_path.write_bytes(b"video")
        return 5

    monkeypatch.setattr(video_source, "download_yt_dlp_media", fake_download_yt_dlp_media)

    saved = video_source.download_video_source("https://video.example/watch/demo123", video_dir=tmp_path)

    assert saved.filename == "demo123-Video Demo.mp4"
    assert saved.media_type == "video"
    assert Path(saved.file_path).read_bytes() == b"video"


def test_download_video_source_prefers_youtube_captions(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="yt-dlp",
        source_url="https://www.youtube.com/watch?v=demo123",
        download_url="https://googlevideo.example/video.mp4",
        video_id="demo123",
        title="YouTube Demo",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)
    monkeypatch.setattr(video_source, "download_yt_dlp_media", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("media download should not be used")))

    def fake_download_captions(url, file_path, on_progress=None, **kwargs):
        assert url == "https://www.youtube.com/watch?v=demo123"
        file_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
        return file_path.stat().st_size

    monkeypatch.setattr(video_source, "download_youtube_captions", fake_download_captions)

    saved = video_source.download_video_source("https://youtu.be/demo123", video_dir=tmp_path)

    assert saved.provider == "yt-dlp"
    assert saved.media_type == "transcript"
    assert saved.filename == "demo123-YouTube Demo.srt"
    assert saved.asset_strategy["transcript_asset"]["source"] == "youtube_captions"
    assert saved.asset_strategy["playback_asset"]["playback_mode"] == "external_url"
    assert saved.asset_strategy["download_status"] == "skipped"
    assert Path(saved.file_path).suffix == ".srt"
    assert saved.size_bytes > 0


def test_download_video_source_falls_back_when_youtube_captions_missing(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="yt-dlp",
        source_url="https://www.youtube.com/watch?v=demo123",
        download_url="https://googlevideo.example/video.mp4",
        video_id="demo123",
        title="YouTube Demo",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)
    monkeypatch.setattr(video_source, "download_youtube_captions", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no captions")))

    def fake_download_yt_dlp_media(url, file_path, on_progress=None, **kwargs):
        assert file_path.suffix == ".mp4"
        file_path.write_bytes(b"video")
        return 5

    monkeypatch.setattr(video_source, "download_yt_dlp_media", fake_download_yt_dlp_media)

    saved = video_source.download_video_source("https://youtu.be/demo123", video_dir=tmp_path)

    assert saved.media_type == "video"
    assert saved.filename == "demo123-YouTube Demo.mp4"
    assert saved.asset_strategy["playback_asset"]["playback_mode"] == "local_file"
    assert saved.asset_strategy["failure_reason"] == "no_captions"
    assert Path(saved.file_path).read_bytes() == b"video"


def test_download_video_source_explains_youtube_caption_and_media_failure(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="yt-dlp",
        source_url="https://www.youtube.com/watch?v=demo123",
        download_url="https://googlevideo.example/video.mp4",
        video_id="demo123",
        title="YouTube Demo",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)
    monkeypatch.setattr(video_source, "download_youtube_captions", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("no captions")))
    monkeypatch.setattr(video_source, "download_yt_dlp_media", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("missing a GVS PO Token")))

    with pytest.raises(RuntimeError, match="YouTube 字幕不可用，且原视频下载失败"):
        video_source.download_video_source("https://youtu.be/demo123", video_dir=tmp_path)


def test_video_source_failure_reason_classifies_youtube_media_restriction() -> None:
    assert video_source.video_source_failure_reason("missing a GVS PO Token") == "youtube_media_restricted"


def test_download_video_source_merges_split_bilibili_streams(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="yt-dlp",
        source_url="https://www.bilibili.com/video/BVdemo/",
        download_url="https://upos.example/video.m4s",
        audio_url="https://upos.example/audio.m4s",
        referer="https://www.bilibili.com/",
        video_id="BVdemo",
        title="B 站视频",
    )
    merged = {}
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)

    def fake_merge(video_url: str, audio_url: str, file_path: Path, *, referer=None) -> int:
        merged["video_url"] = video_url
        merged["audio_url"] = audio_url
        merged["referer"] = referer
        file_path.write_bytes(b"merged")
        return 6

    monkeypatch.setattr(video_source, "merge_media_parts", fake_merge)

    saved = video_source.download_video_source("https://www.bilibili.com/video/BVdemo/", video_dir=tmp_path)

    assert merged == {
        "video_url": "https://upos.example/video.m4s",
        "audio_url": "https://upos.example/audio.m4s",
        "referer": "https://www.bilibili.com/",
    }
    assert saved.provider == "yt-dlp"
    assert saved.audio_url == "https://upos.example/audio.m4s"
    assert Path(saved.file_path).read_bytes() == b"merged"


def test_download_video_source_splits_raw_and_display_title(tmp_path, monkeypatch) -> None:
    resolved = video_source.ResolvedVideo(
        provider="direct",
        source_url="https://v.douyinvod.com/play/?video_id=7651613998131006774&mime_type=video_mp4",
        download_url="https://v.douyinvod.com/play/?video_id=7651613998131006774&mime_type=video_mp4",
        video_id="7651613998131006774",
        title="7651613998131006774-四大核心Skill架构与配置指南详解",
    )
    monkeypatch.setattr(video_source, "resolve_video", lambda input_text, cookies_from_browser=None: resolved)
    monkeypatch.setattr(video_source, "download_file", lambda url, file_path, on_progress=None: file_path.write_bytes(b"video") or 5)

    saved = video_source.download_video_source("https://v.douyin.com/demo/", video_dir=tmp_path)

    assert saved.raw_title == "7651613998131006774-四大核心Skill架构与配置指南详解"
    assert saved.display_title == "四大核心Skill架构与配置指南详解"
    assert saved.title == "四大核心Skill架构与配置指南详解"
    assert saved.filename == "7651613998131006774-四大核心Skill架构与配置指南详解.mp4"
