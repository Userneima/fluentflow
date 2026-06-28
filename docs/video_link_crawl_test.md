# YouTube / Bilibili 视频链接爬取测试

这份文档用于手动验证当前 FluentFlow 是否真的能处理 YouTube 和 Bilibili 链接。

测试分两层：

1. 只测解析和下载：确认 `yt-dlp` 能拿到可下载音频，排除 STT / 摘要干扰。
2. 测完整产品链路：确认链接任务能进入后台队列、转写、产出结果包。

## 测试边界

- 只测试你有权访问的公开视频或已登录账号可访问的视频。
- 不测试批量爬取、播放列表批量下载、付费/私密内容绕过。
- YouTube / Bilibili 都默认优先下载音频流，成功文件通常是 `.m4a`；如果平台当前只给视频格式，系统会回退到可转写的 `.mp4`。
- Bilibili 登录态可用 `BILIBILI_COOKIES_FROM_BROWSER` 或 `BILIBILI_COOKIES_FILE` 提供。
- YouTube 登录态可用 `YT_DLP_COOKIES_FROM_BROWSER` 或 `YT_DLP_COOKIES_FILE` 提供。
- Bilibili 默认会给 `yt-dlp` 添加 `Origin`、`Referer` 和桌面浏览器 `User-Agent`，用于避免常见的 `HTTP Error 412: Precondition Failed`。

## 准备

安装依赖：

```bash
./venv/bin/pip install -r requirements.txt
```

检查 `yt-dlp` 是否可用：

```bash
./venv/bin/python -m yt_dlp --version
```

如果 Bilibili 视频需要登录态，二选一：

```bash
export BILIBILI_COOKIES_FROM_BROWSER=chrome
```

或：

```bash
export BILIBILI_COOKIES_FILE=/absolute/path/to/bilibili-cookies.txt
```

如果 YouTube 视频需要登录态，同理：

```bash
export YT_DLP_COOKIES_FROM_BROWSER=chrome
```

## 测试链接选择

每个平台至少准备 2 条链接：

- 一条短视频，1 到 3 分钟，公开视频。
- 一条普通中长视频，5 到 20 分钟，公开视频。
- Bilibili 建议同时测试 `https://www.bilibili.com/video/BV...` 和 `https://b23.tv/...` 短链。
- YouTube 建议同时测试 `https://www.youtube.com/watch?v=...` 和 `https://youtu.be/...`。

记录模板：

```text
YOUTUBE_SHORT_URL=
YOUTUBE_NORMAL_URL=
BILIBILI_BV_URL=
BILIBILI_SHORT_URL=
```

## 第一层：只测解析和下载

这个测试不会创建 FluentFlow 后台任务，只会调用 `backend.core.video_source.download_video_source`，适合判断“爬取本身是否有效”。

把下面命令里的 URL 换成真实链接：

```bash
TEST_URL='https://www.youtube.com/watch?v=xxxx'
./venv/bin/python - <<'PY'
import json
import os
import tempfile
from pathlib import Path
from backend.core.video_source import download_video_source

url = os.environ["TEST_URL"]
with tempfile.TemporaryDirectory() as tmp:
    saved = download_video_source(url, video_dir=Path(tmp))
    data = saved.to_dict()
    print(json.dumps({
        "ok": data["ok"],
        "provider": data["provider"],
        "video_id": data["video_id"],
        "title": data["title"],
        "filename": data["filename"],
        "media_type": data["media_type"],
        "file_ext": data["file_ext"],
        "size_bytes": data["size_bytes"],
        "duration_seconds": data.get("duration_seconds"),
        "uploader": data.get("uploader"),
        "webpage_url": data.get("webpage_url"),
        "subtitles": data.get("subtitles"),
    }, ensure_ascii=False, indent=2))
PY
```

Bilibili 换成：

```bash
TEST_URL='https://www.bilibili.com/video/BVxxxx'
./venv/bin/python - <<'PY'
import json
import os
import tempfile
from pathlib import Path
from backend.core.video_source import download_video_source

url = os.environ["TEST_URL"]
with tempfile.TemporaryDirectory() as tmp:
    saved = download_video_source(url, video_dir=Path(tmp))
    print(json.dumps(saved.to_dict(), ensure_ascii=False, indent=2))
PY
```

### 第一层通过标准

YouTube 通过标准：

- `provider` 是 `youtube-yt-dlp`。
- `media_type` 优先是 `audio`；如果 YouTube 触发 SABR / PO Token 限制，回退为 `video` 也算爬取有效。
- `file_ext` 通常是 `.m4a`，回退时可能是 `.mp4`。
- `size_bytes` 大于 0。
- `title`、`webpage_url` 有值。

Bilibili 通过标准：

- `provider` 是 `bilibili-yt-dlp`。
- `video_id` 是 `BV...` 或 `av...`。
- `media_type` 是 `audio`。
- `file_ext` 通常是 `.m4a`。
- `size_bytes` 大于 0。
- `uploader`、`duration_seconds` 能拿到最好；拿不到不一定失败，但要记录。

## 第二层：测试完整 FluentFlow 链路

启动后端：

```bash
./venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

另开终端，用 Agent 脚本提交链接。先建议用 `--no-summary` 缩短测试时间，只验证链接下载和转写。

YouTube：

```bash
./venv/bin/python scripts/codex_transcribe_link.py \
  'https://www.youtube.com/watch?v=xxxx' \
  --api-base http://127.0.0.1:8000 \
  --stt-provider auto \
  --no-summary \
  --stdout
```

Bilibili：

```bash
./venv/bin/python scripts/codex_transcribe_link.py \
  'https://www.bilibili.com/video/BVxxxx' \
  --api-base http://127.0.0.1:8000 \
  --stt-provider auto \
  --no-summary \
  --stdout
```

### 第二层通过标准

输出 JSON 里需要看到：

- `ok: true`
- `status: completed`
- `source_type` 是 `audio` 或 `video`；如果第一层回退到 `.mp4`，这里会是 `video`。
- `transcript_text` 长度大于 0
- `task_package.source.video_source.provider` 分别为 `youtube-yt-dlp` 或 `bilibili-yt-dlp`
- `task_package.source.video_source.media_type` 为 `audio` 或平台回退后的 `video`
- `task_package.source.video_source.file_ext` 为 `.m4a`、其他音频扩展名或回退后的 `.mp4`

如果你没有本地 STT，`--stt-provider auto` 可能走云端或失败。只判断爬取能力时，以第一层测试为准。

## 第三层：前端手动测试

启动前端：

```bash
npm run dev:frontend
```

打开前端后：

1. 进入开始处理页。
2. 粘贴 YouTube 或 Bilibili 链接。
3. 提交任务。
4. 到后台任务页查看状态。
5. 完成后打开编辑器。

通过标准：

- 后台任务页能显示解析、下载、排队、转写进度。
- 任务完成后能打开编辑器。
- 编辑器中有转录文本。
- 如果生成摘要，摘要不是空。
- 后台任务或 Agent Package 中能看到 `video_source` metadata。

## 快速定位失败原因

### `No module named yt_dlp`

说明依赖没装：

```bash
./venv/bin/pip install -r requirements.txt
```

### Bilibili 返回登录或权限相关错误

如果错误是 `HTTP Error 412: Precondition Failed`，先确认当前代码已经使用默认 Bilibili headers。需要临时覆盖时可设置：

```bash
export BILIBILI_YT_DLP_ORIGIN=https://www.bilibili.com
export BILIBILI_YT_DLP_REFERER=https://www.bilibili.com
export BILIBILI_YT_DLP_USER_AGENT='Mozilla/5.0 ... Chrome/...'
```

如果仍失败，再配置 cookies。

先配置 cookies：

```bash
export BILIBILI_COOKIES_FROM_BROWSER=chrome
```

如果浏览器 cookie 读取失败，导出 Netscape cookies 文件后：

```bash
export BILIBILI_COOKIES_FILE=/absolute/path/to/bilibili-cookies.txt
```

### YouTube 返回地区、年龄、登录相关错误

尝试：

```bash
export YT_DLP_COOKIES_FROM_BROWSER=chrome
```

或换一个公开视频做基准测试。

### 第一层成功，第二层失败

说明爬取有效，问题在 FluentFlow 后续链路。重点看：

- 后端日志里的任务错误。
- STT provider 是否可用。
- 是否超过上传大小、时长或额度限制。
- `source_type` 是否为 `audio`。
- `metadata.video_source.provider` 是否正确。

### 第一层失败

说明问题在平台解析或下载层。重点看：

- URL 是否真实可访问。
- `yt-dlp` 是否太旧。
- 是否需要 cookies。
- 是否为合集、番剧、会员、区域限制或需要登录的视频。

## 建议记录表

| 平台 | 链接类型 | URL | 第一层结果 | provider | media_type | file_ext | 第二层结果 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| YouTube | watch |  |  |  |  |  |  |  |
| YouTube | youtu.be |  |  |  |  |  |  |  |
| Bilibili | BV |  |  |  |  |  |  |  |
| Bilibili | b23.tv |  |  |  |  |  |  |  |
