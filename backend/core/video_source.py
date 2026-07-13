"""Resolve and download shared video links for FluentFlow."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.core.title_display import display_title_for_user

SOURCE_INFO_FILE = "视频链接相关信息.md"
DEFAULT_MAX_VIDEO_BYTES = 600 * 1024 * 1024
URL_RE = re.compile(r"https?://[^\s，。！？、'\"“”‘’）)\]】]+", re.I)
MIUISTORE_ORIGIN = "https://sph.miuistore.com"


@dataclass
class VideoSourceProgress:
    stage: str
    message: str
    percent: int | None = None
    loaded_bytes: int | None = None
    total_bytes: int | None = None


@dataclass
class ResolvedVideo:
    provider: str
    source_url: str
    download_url: str
    video_id: str | None = None
    title: str | None = None
    thumbnail_url: str | None = None
    audio_url: str | None = None
    referer: str | None = None
    duration_seconds: float | None = None
    estimated_size_bytes: int | None = None


@dataclass
class SavedVideoSource:
    ok: bool
    provider: str
    source_url: str
    download_url: str
    video_id: str
    raw_title: str
    display_title: str
    title: str
    filename: str
    file_path: str
    file_url: str
    metadata_path: str
    size_bytes: int
    downloaded_at: str
    media_type: str = "video"
    asset_strategy: dict[str, Any] | None = None
    duration_seconds: float | None = None
    estimated_size_bytes: int | None = None
    audio_url: str | None = None
    referer: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


ProgressCallback = Callable[[VideoSourceProgress], None]


def max_video_bytes() -> int:
    try:
        parsed = int(os.environ.get("VIDEO_SOURCE_MAX_BYTES", ""))
        return parsed if parsed > 0 else DEFAULT_MAX_VIDEO_BYTES
    except ValueError:
        return DEFAULT_MAX_VIDEO_BYTES


def trim_url(value: str) -> str:
    return value.strip().rstrip(")）]】\"'“”‘’。，,")


def extract_first_url(input_text: str) -> str | None:
    match = URL_RE.search(input_text or "")
    return trim_url(match.group(0)) if match else None


def parse_http_url(value: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("只支持 http/https 视频链接")
    return parsed


def sanitize_filename_part(value: str) -> str:
    normalized = re.sub(r"[\\/:*?\"<>|#%&{}$!'@+`=]", " ", value or "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized[:72]


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def video_id_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        video_id = (query.get("video_id") or [None])[0]
        if video_id:
            return video_id
        tokens = [token for token in parsed.path.split("/") if token]
        if tokens and re.match(r"^[a-zA-Z0-9_-]{6,}$", tokens[-1]):
            return tokens[-1][:40]
    except Exception:
        pass
    return stable_id(url)


def display_title_for_source_input(input_text: str, fallback: str = "") -> str:
    source_url = extract_first_url(input_text or "")
    if not source_url:
        return display_title_for_user(fallback or input_text, fallback or input_text)
    try:
        parsed = urllib.parse.urlparse(source_url)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        video_id = video_id_from_url(source_url)
        if "bilibili.com" in host or host == "b23.tv":
            return f"Bilibili 视频 {video_id}" if video_id else "Bilibili 视频"
        if "douyin.com" in host:
            return "抖音视频链接"
        if "youtube.com" in host or host == "youtu.be":
            return "YouTube 视频"
        if host:
            return f"{host} 视频链接"
    except Exception:
        pass
    return display_title_for_user(fallback or input_text, fallback or input_text) or "视频链接"


def resolve_filename(video: ResolvedVideo, requested_title: str | None = None, extension: str = ".mp4") -> tuple[str, str, str, str]:
    video_id = sanitize_filename_part(video.video_id or video_id_from_url(video.source_url)) or stable_id(video.source_url)
    raw_title = sanitize_filename_part(requested_title or video.title or f"视频-{video_id}") or f"视频-{video_id}"
    display_title = display_title_for_user(raw_title, raw_title) or raw_title
    filename_title = sanitize_filename_part(display_title) or raw_title
    safe_extension = extension if extension.startswith(".") else f".{extension}"
    return video_id, raw_title, display_title, f"{video_id}-{filename_title}{safe_extension}"


def decode_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def strip_tags(value: str) -> str:
    return decode_html(re.sub(r"<[^>]*>", " ", value or ""))


def parse_miuistore_field(page_html: str, label: str) -> str | None:
    pattern = re.compile(
        rf"{re.escape(label)}：\s*</div>\s*<div[^>]*class=['\"][^'\"]*\bcol-value\b[^'\"]*['\"][^>]*>([\s\S]*?)</div>",
        re.I,
    )
    match = pattern.search(page_html or "")
    return strip_tags(match.group(1)) if match else None


def parse_miuistore_links(page_html: str) -> list[str]:
    links = []
    for match in re.finditer(r'href="([^"]+)"', page_html or "", re.I):
        href = decode_html(match.group(1))
        if href.startswith(("http://", "https://")):
            links.append(href)
    return links


def choose_miuistore_video_url(links: list[str]) -> str | None:
    for needle in ("mime_type=video_mp4", "douyinvod.com", "/aweme/v1/play/"):
        found = next((href for href in links if needle in href), None)
        if found:
            return found
    return None


def is_bilibili_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        return host.endswith("bilibili.com") or host == "b23.tv"
    except Exception:
        return False


def is_youtube_url(url: str) -> bool:
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        return host == "youtu.be" or host.endswith("youtube.com")
    except Exception:
        return False


def fetch_text(url: str, timeout: float = 45) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "user-agent": "Mozilla/5.0 FluentFlow/1.0",
            "accept": "text/html,application/json,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def is_probably_direct_video_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        return (
            parsed.path.lower().endswith(".mp4")
            or (query.get("mime_type") or [None])[0] == "video_mp4"
            or "douyinvod.com" in (parsed.hostname or "")
        )
    except Exception:
        return False


def resolve_direct_video(url: str) -> ResolvedVideo | None:
    if not is_probably_direct_video_url(url):
        return None
    return ResolvedVideo(
        provider="direct",
        source_url=url,
        download_url=url,
        video_id=video_id_from_url(url),
    )


def run_yt_dlp(url: str, cookies_from_browser: str | None = None) -> dict[str, Any]:
    args = [sys.executable, "-m", "yt_dlp", "--dump-single-json", "--skip-download", "--no-playlist", url]
    cookies = (cookies_from_browser or os.environ.get("YT_DLP_COOKIES_FROM_BROWSER", "")).strip()
    if cookies:
        args.insert(3, "--cookies-from-browser")
        args.insert(4, cookies)
    try:
        if is_youtube_url(url):
            url_arg = args.pop()
            args.extend(["--extractor-args", "youtube:player_client=android", url_arg])
    except Exception:
        pass
    if is_bilibili_url(url):
        url_arg = args.pop()
        args.extend([
            "--add-header",
            "Referer:https://www.bilibili.com/",
            "--add-header",
            "Origin:https://www.bilibili.com",
            "--add-header",
            "User-Agent:Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            url_arg,
        ])
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or f"yt-dlp 退出码 {result.returncode}")
    return json.loads(result.stdout)


def choose_yt_dlp_media(info: dict[str, Any]) -> tuple[str | None, str | None]:
    direct_url = info.get("url")
    if direct_url and (info.get("ext") == "mp4" or "mime_type=video_mp4" in direct_url or ".mp4" in direct_url):
        return str(direct_url), None

    combined: list[dict[str, Any]] = []
    videos: list[dict[str, Any]] = []
    audios: list[dict[str, Any]] = []
    for item in info.get("formats") or []:
        if not item.get("url"):
            continue
        has_video = item.get("vcodec") not in {None, "none"}
        has_audio = item.get("acodec") not in {None, "none"}
        if has_video and has_audio:
            combined.append(item)
        elif has_video:
            videos.append(item)
        elif has_audio:
            audios.append(item)

    def video_score(item: dict[str, Any]) -> tuple[int, int, int]:
        return (
            1 if item.get("ext") == "mp4" else 0,
            int(item.get("height") or 0),
            int(item.get("filesize") or item.get("filesize_approx") or 0),
        )

    def audio_score(item: dict[str, Any]) -> tuple[int, int]:
        return (
            int(item.get("abr") or item.get("tbr") or 0),
            int(item.get("filesize") or item.get("filesize_approx") or 0),
        )

    if combined:
        combined.sort(key=video_score, reverse=True)
        return str(combined[0]["url"]), None
    if videos and audios:
        videos.sort(key=video_score, reverse=True)
        audios.sort(key=audio_score, reverse=True)
        return str(videos[0]["url"]), str(audios[0]["url"])
    if audios:
        audios.sort(key=audio_score, reverse=True)
        return str(audios[0]["url"]), None
    if videos:
        videos.sort(key=video_score, reverse=True)
        return str(videos[0]["url"]), None
    return None, None


def _number_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def estimate_yt_dlp_size_bytes(info: dict[str, Any]) -> int | None:
    direct = _number_or_none(info.get("filesize") or info.get("filesize_approx"))
    if direct:
        return int(direct)
    sizes = []
    for item in info.get("formats") or []:
        size = _number_or_none(item.get("filesize") or item.get("filesize_approx"))
        if size:
            sizes.append(int(size))
    return max(sizes) if sizes else None


def resolve_with_yt_dlp(url: str, cookies_from_browser: str | None = None) -> ResolvedVideo | None:
    try:
        info = run_yt_dlp(url, cookies_from_browser)
        download_url, audio_url = choose_yt_dlp_media(info)
        if not download_url:
            return None
        return ResolvedVideo(
            provider="yt-dlp",
            source_url=info.get("webpage_url") or info.get("original_url") or url,
            download_url=download_url,
            video_id=info.get("id"),
            title=info.get("title"),
            thumbnail_url=info.get("thumbnail"),
            audio_url=audio_url,
            referer="https://www.bilibili.com/" if is_bilibili_url(info.get("webpage_url") or url) else None,
            duration_seconds=_number_or_none(info.get("duration")),
            estimated_size_bytes=estimate_yt_dlp_size_bytes(info),
        )
    except Exception:
        return None


def resolve_with_miuistore(input_text: str) -> ResolvedVideo | None:
    try:
        check_url = f"{MIUISTORE_ORIGIN}/sph/public/dy-check?{urllib.parse.urlencode({'data': input_text})}"
        checked = json.loads(fetch_text(check_url))
        if checked.get("error") != 0 or not checked.get("url"):
            return None
        query_url = urllib.parse.urljoin(MIUISTORE_ORIGIN, str(checked["url"]))
        encrypted_url = (urllib.parse.parse_qs(urllib.parse.urlparse(query_url).query).get("url") or [None])[0]
        if not encrypted_url:
            return None
        result_url = f"{MIUISTORE_ORIGIN}/sph/public/dy-r?{urllib.parse.urlencode({'url': encrypted_url})}"
        page_html = fetch_text(result_url)
        links = parse_miuistore_links(page_html)
        download_url = choose_miuistore_video_url(links)
        if not download_url:
            return None
        return ResolvedVideo(
            provider="miuistore",
            source_url=extract_first_url(input_text) or query_url,
            download_url=download_url,
            video_id=parse_miuistore_field(page_html, "视频ID"),
            title=parse_miuistore_field(page_html, "视频标题"),
            thumbnail_url=next((href for href in links if "douyinpic.com" in href), None),
        )
    except Exception:
        return None


def resolve_video(input_text: str, cookies_from_browser: str | None = None) -> ResolvedVideo:
    source_url = extract_first_url(input_text)
    if not source_url:
        raise ValueError("没有识别到视频链接")
    parse_http_url(source_url)
    resolved = resolve_direct_video(source_url) or resolve_with_yt_dlp(source_url, cookies_from_browser)
    if resolved:
        return resolved
    if is_bilibili_url(source_url):
        raise RuntimeError("这个 B 站链接需要登录后才能下载。请在设置里选择“用浏览器登录态下载高清”，或改为上传本地视频。")
    resolved = resolve_with_miuistore(input_text)
    if resolved:
        return resolved
    raise RuntimeError("暂时无法自动解析这个视频链接，请上传视频文件")


def download_referer_for_url(url: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback
    try:
        host = (urllib.parse.urlparse(url).hostname or "").lower()
        if "bilivideo.com" in host or "bilibili.com" in host:
            return "https://www.bilibili.com/"
    except Exception:
        pass
    return "https://www.douyin.com/"


def download_file(
    url: str,
    file_path: Path,
    on_progress: ProgressCallback | None = None,
    *,
    referer: str | None = None,
) -> int:
    parse_http_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "user-agent": "Mozilla/5.0 FluentFlow/1.0",
            "referer": download_referer_for_url(url, referer),
        },
    )
    max_bytes = max_video_bytes()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            content_length = int(response.headers.get("content-length") or 0)
            if content_length > max_bytes:
                raise RuntimeError(f"视频文件过大，当前限制为 {round(max_bytes / 1024 / 1024)}MB")
            on_progress and on_progress(VideoSourceProgress(
                stage="downloading",
                message="正在下载视频" if content_length else "正在下载视频，文件大小未知",
                percent=0 if content_length else None,
                loaded_bytes=0,
                total_bytes=content_length or None,
            ))
            with file_path.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise RuntimeError(f"视频文件过大，当前限制为 {round(max_bytes / 1024 / 1024)}MB")
                    output.write(chunk)
                    percent = min(99, round(downloaded / content_length * 100)) if content_length else None
                    on_progress and on_progress(VideoSourceProgress(
                        stage="downloading",
                        message="正在下载视频",
                        percent=percent,
                        loaded_bytes=downloaded,
                        total_bytes=content_length or None,
                    ))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"视频下载失败：{exc.code}") from exc
    size_bytes = downloaded or file_path.stat().st_size
    on_progress and on_progress(VideoSourceProgress(
        stage="downloading",
        message="视频下载完成",
        percent=100,
        loaded_bytes=size_bytes,
        total_bytes=size_bytes,
    ))
    return size_bytes


def merge_media_parts(video_url: str, audio_url: str, file_path: Path, *, referer: str | None = None) -> int:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("B 站音视频需要合并，但当前环境没有找到 ffmpeg")
    with tempfile.TemporaryDirectory(prefix="fluentflow-bili-") as temp_dir:
        temp_path = Path(temp_dir)
        video_path = temp_path / "video.m4s"
        audio_path = temp_path / "audio.m4s"
        download_file(video_url, video_path, referer=referer)
        download_file(audio_url, audio_path, referer=referer)
        output_path = temp_path / "merged.mp4"
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(video_path),
                "-i",
                str(audio_path),
                "-c",
                "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or "").strip() or "B 站音视频合并失败")
        shutil.move(str(output_path), file_path)
    return file_path.stat().st_size


def _yt_dlp_cookies_args(cookies_from_browser: str | None = None) -> list[str]:
    value = (cookies_from_browser or os.environ.get("YT_DLP_COOKIES_FROM_BROWSER", "")).strip()
    return ["--cookies-from-browser", value] if value else []


def youtube_caption_languages() -> str:
    return (os.environ.get("FLUENTFLOW_YOUTUBE_SUB_LANGS") or "en,zh-Hans,zh-Hant,zh").strip()


def youtube_caption_language_candidates() -> list[str]:
    return [
        item.strip()
        for item in youtube_caption_languages().split(",")
        if item.strip()
    ] or ["en"]


def download_timeout_seconds(
    *,
    duration_seconds: float | None = None,
    estimated_size_bytes: int | None = None,
) -> int:
    override = os.environ.get("FLUENTFLOW_YT_DLP_DOWNLOAD_TIMEOUT_SECONDS")
    if override:
        try:
            return max(int(float(override)), 60)
        except ValueError:
            pass
    try:
        max_timeout = max(int(float(os.environ.get("FLUENTFLOW_YT_DLP_MAX_TIMEOUT_SECONDS", "3600"))), 300)
    except ValueError:
        max_timeout = 3600
    budgets = [900]
    if duration_seconds:
        budgets.append(180 + int(float(duration_seconds) * 0.22))
    if estimated_size_bytes:
        budgets.append(180 + int(int(estimated_size_bytes) / (256 * 1024)))
    return min(max(budgets), max_timeout)


def video_source_failure_reason(error: Any) -> str:
    text = str(error or "").lower()
    if "po token" in text or "sabr streaming" in text or "the page needs to be reloaded" in text:
        return "youtube_media_restricted"
    if "http error 403" in text or "forbidden" in text or "视频下载失败：403" in text:
        return "forbidden"
    if "http error 429" in text or "too many requests" in text:
        return "rate_limited"
    if "timed out" in text or "timeout" in text or "视频下载超时" in text:
        return "timeout"
    if "too large" in text or "文件过大" in text or "file is too large" in text:
        return "too_large"
    if "没有可用字幕" in text or "no subtitles" in text or "no captions" in text:
        return "no_captions"
    return "unknown"


def download_youtube_captions(
    url: str,
    file_path: Path,
    on_progress: ProgressCallback | None = None,
    *,
    cookies_from_browser: str | None = None,
) -> int:
    parse_http_url(url)
    if not is_youtube_url(url):
        raise RuntimeError("YouTube captions are only available for YouTube URLs")
    on_progress and on_progress(VideoSourceProgress(
        stage="downloading",
        message="正在获取 YouTube 字幕",
        percent=None,
        loaded_bytes=None,
        total_bytes=None,
    ))
    file_path.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for language in youtube_caption_language_candidates():
        with tempfile.TemporaryDirectory(prefix="fluentflow-youtube-captions-") as temp_dir:
            output_template = str(Path(temp_dir) / "captions.%(ext)s")
            args = [
                sys.executable,
                "-m",
                "yt_dlp",
                "--skip-download",
                "--no-playlist",
                "--write-subs",
                "--write-auto-subs",
                "--sub-langs",
                language,
                "--sub-format",
                "srt",
                "-o",
                output_template,
                "--extractor-args",
                "youtube:player_client=android",
                *_yt_dlp_cookies_args(cookies_from_browser),
                url,
            ]
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            candidates = sorted(Path(temp_dir).glob("captions*.srt"))
            if result.returncode == 0 and candidates:
                shutil.move(str(candidates[0]), file_path)
                break
            errors.append((result.stderr or result.stdout or f"{language}: yt-dlp 字幕下载失败，退出码 {result.returncode}").strip())
    if not file_path.is_file():
        detail = errors[-1] if errors else "这个 YouTube 视频没有可用字幕"
        raise RuntimeError(detail or "这个 YouTube 视频没有可用字幕")
    size_bytes = file_path.stat().st_size
    on_progress and on_progress(VideoSourceProgress(
        stage="downloading",
        message="YouTube 字幕获取完成",
        percent=100,
        loaded_bytes=size_bytes,
        total_bytes=size_bytes,
    ))
    return size_bytes


def download_yt_dlp_media(
    url: str,
    file_path: Path,
    on_progress: ProgressCallback | None = None,
    *,
    duration_seconds: float | None = None,
    estimated_size_bytes: int | None = None,
    cookies_from_browser: str | None = None,
) -> int:
    parse_http_url(url)
    on_progress and on_progress(VideoSourceProgress(
        stage="downloading",
        message="正在下载视频",
        percent=None,
        loaded_bytes=None,
        total_bytes=None,
    ))
    max_bytes = max_video_bytes()
    args = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--no-part",
        "--force-overwrites",
        "--no-progress",
        "--max-filesize",
        str(max_bytes),
        "-f",
        "best[ext=mp4]/best",
        "-o",
        str(file_path),
        *_yt_dlp_cookies_args(cookies_from_browser),
    ]
    try:
        if is_youtube_url(url):
            args.extend(["--extractor-args", "youtube:player_client=android"])
    except Exception:
        pass
    args.append(url)
    timeout = download_timeout_seconds(
        duration_seconds=duration_seconds,
        estimated_size_bytes=estimated_size_bytes,
    )
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"视频下载超时：视频可能较大或当前网络较慢，已等待 {timeout} 秒。") from exc
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "").strip() or f"yt-dlp 下载失败，退出码 {result.returncode}")
    size_bytes = file_path.stat().st_size
    if size_bytes > max_bytes:
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        raise RuntimeError(f"视频文件过大，当前限制为 {round(max_bytes / 1024 / 1024)}MB")
    on_progress and on_progress(VideoSourceProgress(
        stage="downloading",
        message="视频下载完成",
        percent=100,
        loaded_bytes=size_bytes,
        total_bytes=size_bytes,
    ))
    return size_bytes


def write_source_info(video_dir: Path, title: str, source_url: str) -> None:
    metadata_path = video_dir / SOURCE_INFO_FILE
    try:
        current = metadata_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    if source_url in current:
        return
    prefix = "\n" if current.strip() else ""
    metadata_path.write_text(f"{current}{prefix}{title} {source_url}\n", encoding="utf-8")


def write_json_metadata(file_path: Path, metadata: dict[str, Any]) -> Path:
    metadata_path = file_path.with_suffix(".source.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata_path


def build_asset_strategy(
    *,
    media_type: str,
    source_url: str,
    file_path: Path,
    file_url: str,
    filename: str,
    caption_failure_reason: str | None = None,
) -> dict[str, Any]:
    if media_type == "transcript":
        return {
            "transcript_asset": {
                "status": "completed",
                "kind": "subtitle",
                "source": "youtube_captions",
                "filename": filename,
                "file_path": str(file_path),
                "file_url": file_url,
            },
            "playback_asset": {
                "status": "available",
                "playback_mode": "external_url",
                "source_url": source_url,
            },
            "visual_asset": {
                "status": "unavailable",
                "reason": "local_video_not_downloaded",
            },
            "download_status": "skipped",
            "failure_reason": None,
        }
    return {
        "transcript_asset": {
            "status": "pending",
            "kind": "stt_from_media",
        },
        "playback_asset": {
            "status": "completed",
            "playback_mode": "local_file",
            "filename": filename,
            "file_path": str(file_path),
            "file_url": file_url,
        },
        "visual_asset": {
            "status": "pending",
            "source": "local_video",
        },
        "download_status": "completed",
        "failure_reason": caption_failure_reason,
    }


def download_video_source(
    input_text: str,
    *,
    title: str | None = None,
    video_dir: Path,
    on_progress: ProgressCallback | None = None,
    cookies_from_browser: str | None = None,
) -> SavedVideoSource:
    normalized = (input_text or "").strip()
    if not normalized:
        raise ValueError("缺少视频分享文本或视频链接")
    if len(normalized) > 4000:
        raise ValueError("分享文本过长")

    video_dir.mkdir(parents=True, exist_ok=True)
    on_progress and on_progress(VideoSourceProgress(stage="resolving", message="正在解析分享链接", percent=8))
    resolved = resolve_video(normalized, cookies_from_browser)
    media_type = "transcript" if resolved.provider == "yt-dlp" and is_youtube_url(resolved.source_url) else "video"
    extension = ".srt" if media_type == "transcript" else ".mp4"
    video_id, raw_title, display_title, filename = resolve_filename(resolved, title, extension=extension)
    file_path = video_dir / filename
    caption_failure_reason: str | None = None
    downloaded_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    try:
        size_bytes = file_path.stat().st_size
        on_progress and on_progress(VideoSourceProgress(
            stage="downloading",
            message="本地已有视频文件",
            percent=100,
            loaded_bytes=size_bytes,
            total_bytes=size_bytes,
        ))
    except FileNotFoundError:
        if resolved.audio_url and resolved.download_url:
            on_progress and on_progress(VideoSourceProgress(
                stage="downloading",
                message="正在下载并合并 B 站音视频",
                percent=None,
            ))
            size_bytes = merge_media_parts(
                resolved.download_url,
                resolved.audio_url,
                file_path,
                referer=resolved.referer,
            )
            on_progress and on_progress(VideoSourceProgress(
                stage="downloading",
                message="视频下载完成",
                percent=100,
                loaded_bytes=size_bytes,
                total_bytes=size_bytes,
            ))
        else:
            if media_type == "transcript":
                try:
                    size_bytes = download_youtube_captions(resolved.source_url, file_path, on_progress, cookies_from_browser=cookies_from_browser)
                except Exception as exc:
                    caption_failure_reason = video_source_failure_reason(exc)
                    media_type = "video"
                    video_id, raw_title, display_title, filename = resolve_filename(resolved, title)
                    file_path = video_dir / filename
                    try:
                        size_bytes = download_yt_dlp_media(
                            resolved.source_url,
                            file_path,
                            on_progress,
                            duration_seconds=resolved.duration_seconds,
                            estimated_size_bytes=resolved.estimated_size_bytes,
                            cookies_from_browser=cookies_from_browser,
                        )
                    except Exception as media_exc:
                        raise RuntimeError(
                            f"YouTube 字幕不可用，且原视频下载失败：{media_exc}"
                        ) from media_exc
            elif resolved.provider == "yt-dlp":
                size_bytes = download_yt_dlp_media(
                    resolved.source_url,
                    file_path,
                    on_progress,
                    duration_seconds=resolved.duration_seconds,
                    estimated_size_bytes=resolved.estimated_size_bytes,
                    cookies_from_browser=cookies_from_browser,
                )
            elif resolved.referer:
                size_bytes = download_file(resolved.download_url, file_path, on_progress, referer=resolved.referer)
            else:
                size_bytes = download_file(resolved.download_url, file_path, on_progress)

    on_progress and on_progress(VideoSourceProgress(stage="saving", message="正在保存视频信息", percent=96))
    file_url = f"/video-sources/files/{urllib.parse.quote(filename)}"
    asset_strategy = build_asset_strategy(
        media_type=media_type,
        source_url=resolved.source_url,
        file_path=file_path,
        file_url=file_url,
        filename=filename,
        caption_failure_reason=caption_failure_reason,
    )
    metadata = {
        "provider": resolved.provider,
        "source_url": resolved.source_url,
        "download_url": resolved.download_url,
        "audio_url": resolved.audio_url,
        "referer": resolved.referer,
        "duration_seconds": resolved.duration_seconds,
        "estimated_size_bytes": resolved.estimated_size_bytes,
        "video_id": video_id,
        "raw_title": raw_title,
        "display_title": display_title,
        "title": display_title,
        "filename": filename,
        "file_path": str(file_path),
        "file_url": file_url,
        "size_bytes": size_bytes,
        "downloaded_at": downloaded_at,
        "media_type": media_type,
        "asset_strategy": asset_strategy,
    }
    metadata_path = write_json_metadata(file_path, metadata)
    write_source_info(video_dir, display_title, resolved.source_url)
    return SavedVideoSource(ok=True, metadata_path=str(metadata_path), **metadata)
