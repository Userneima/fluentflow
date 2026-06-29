# 视频链接爬取测试

这份文档用于验证 FluentFlow 的视频链接下载链路，重点是 YouTube 和 Bilibili。

## Bilibili 支持边界

当前只承诺普通 UP 主投稿公开视频：

- 单个普通公开视频
- 分 P 视频中的指定一 P
- 合集里的单个视频链接
- 带字幕或无字幕的视频
- `www.bilibili.com/video/BV...` 和 `b23.tv` 短链

不把长视频/短视频当成不同下载类型。长度只影响耗时和队列稳定性，不影响解析模型。

明确不支持：

- 番剧
- 课程
- 会员专享内容
- 付费内容
- 版权或地区受限内容
- 直播回放
- 互动视频

## 默认回归测试

默认测试不依赖真实网络，适合每次改代码后跑：

```bash
./venv/bin/python -m pytest tests/test_video_source.py tests/test_video_source_jobs.py -q
```

这层主要防止以下问题回退：

- Bilibili 音视频分离时只拿到视频轨。
- `b23.tv` 短链不被识别为 Bilibili。
- Bilibili 下载没有带正确 Referer。
- Bilibili `yt-dlp` 解析失败后又偷偷走第三方 miuistore 兜底。

## 真实链接解析抽检

这层只解析真实链接，不下载完整视频。需要手动提供公开视频链接：

```bash
export FLUENTFLOW_BILI_SMOKE_URLS='https://www.bilibili.com/video/BVxxxx,https://b23.tv/xxxx'
./venv/bin/python -m pytest tests/test_bilibili_video_source_smoke.py::test_bilibili_smoke_urls_resolve_to_downloadable_media -q
```

通过标准：

- `provider` 必须是 `yt-dlp`。
- 有 `download_url`。
- 有标题或视频 ID。

## 真实下载抽检

这层会真的下载并在需要时合并音视频，只建议用一个较短公开视频做抽检：

```bash
export FLUENTFLOW_BILI_DOWNLOAD_SMOKE_URL='https://www.bilibili.com/video/BVxxxx'
./venv/bin/python -m pytest tests/test_bilibili_video_source_smoke.py::test_bilibili_smoke_url_downloads_media -q
```

通过标准：

- `download_video_source` 返回 `ok: true`。
- 本地生成的视频文件大小大于 0。
- 生成 `.source.json` 元数据。
- 如果是 Bilibili 分离流，能通过 `ffmpeg` 合并。

## 失败判断

如果默认回归测试失败，优先修代码。

如果真实解析失败，先判断链接是否在支持边界内；普通投稿公开视频才算有效失败样本。

如果真实解析成功但下载失败，重点看：

- 资源 URL 是否过期。
- Referer / User-Agent 是否被平台拒绝。
- 是否缺少 `ffmpeg`。
- 文件是否超过 `VIDEO_SOURCE_MAX_BYTES`。
- 是否触发 Bilibili 风控。

如果需要登录态，当前只通过 `yt-dlp` 的通用配置接入：

```bash
export YT_DLP_COOKIES_FROM_BROWSER=chrome
```

Bilibili 不再使用 miuistore 第三方兜底。`yt-dlp` 解析失败时，产品应提示用户上传本地视频，或配置 `YT_DLP_COOKIES_FROM_BROWSER` 后重试。
