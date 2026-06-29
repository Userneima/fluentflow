"""Resolve and download shared video links for FluentFlow."""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
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


def resolve_filename(video: ResolvedVideo, requested_title: str | None = None) -> tuple[str, str, str, str]:
    video_id = sanitize_filename_part(video.video_id or video_id_from_url(video.source_url)) or stable_id(video.source_url)
    raw_title = sanitize_filename_part(requested_title or video.title or f"视频-{video_id}") or f"视频-{video_id}"
    display_title = display_title_for_user(raw_title, raw_title) or raw_title
    filename_title = sanitize_filename_part(display_title) or raw_title
    return video_id, raw_title, display_title, f"{video_id}-{filename_title}.mp4"


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


def run_yt_dlp(url: str) -> dict[str, Any]:
    args = ["python3", "-m", "yt_dlp", "--dump-single-json", "--skip-download", "--no-playlist", url]
    cookies_from_browser = os.environ.get("YT_DLP_COOKIES_FROM_BROWSER", "").strip()
    if cookies_from_browser:
        args.insert(3, "--cookies-from-browser")
        args.insert(4, cookies_from_browser)
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


def resolve_with_yt_dlp(url: str) -> ResolvedVideo | None:
    try:
        info = run_yt_dlp(url)
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


def resolve_video(input_text: str) -> ResolvedVideo:
    source_url = extract_first_url(input_text)
    if not source_url:
        raise ValueError("没有识别到视频链接")
    parse_http_url(source_url)
    for resolver in (resolve_direct_video, resolve_with_yt_dlp):
        resolved = resolver(source_url)
        if resolved:
            return resolved
    if is_bilibili_url(source_url):
        raise RuntimeError("B 站链接暂时只能通过 yt-dlp 解析。请上传本地视频，或配置 YT_DLP_COOKIES_FROM_BROWSER 后重试。")
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


def download_video_source(
    input_text: str,
    *,
    title: str | None = None,
    video_dir: Path,
    on_progress: ProgressCallback | None = None,
) -> SavedVideoSource:
    normalized = (input_text or "").strip()
    if not normalized:
        raise ValueError("缺少视频分享文本或视频链接")
    if len(normalized) > 4000:
        raise ValueError("分享文本过长")

    video_dir.mkdir(parents=True, exist_ok=True)
    on_progress and on_progress(VideoSourceProgress(stage="resolving", message="正在解析分享链接", percent=8))
    resolved = resolve_video(normalized)
    video_id, raw_title, display_title, filename = resolve_filename(resolved, title)
    file_path = video_dir / filename
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
            if resolved.referer:
                size_bytes = download_file(resolved.download_url, file_path, on_progress, referer=resolved.referer)
            else:
                size_bytes = download_file(resolved.download_url, file_path, on_progress)

    on_progress and on_progress(VideoSourceProgress(stage="saving", message="正在保存视频信息", percent=96))
    metadata = {
        "provider": resolved.provider,
        "source_url": resolved.source_url,
        "download_url": resolved.download_url,
        "audio_url": resolved.audio_url,
        "referer": resolved.referer,
        "video_id": video_id,
        "raw_title": raw_title,
        "display_title": display_title,
        "title": display_title,
        "filename": filename,
        "file_path": str(file_path),
        "file_url": f"/video-sources/files/{urllib.parse.quote(filename)}",
        "size_bytes": size_bytes,
        "downloaded_at": downloaded_at,
    }
    metadata_path = write_json_metadata(file_path, metadata)
    write_source_info(video_dir, display_title, resolved.source_url)
    return SavedVideoSource(ok=True, metadata_path=str(metadata_path), **metadata)
