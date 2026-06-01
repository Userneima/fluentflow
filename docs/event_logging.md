# FluentFlow 事件日志说明

本文档描述第一阶段最小埋点。目标是记录真实发生的系统链路和已有用户按钮行为，用于分析处理效率、稳定性和飞书导出链路。

## 基本原则

- 事件日志使用本地 SQLite：`data/fluentflow_events.sqlite`。
- 只记录长度、类型、耗时、状态、错误原因和飞书链接，不保存完整转写文本或完整 Markdown 笔记。
- 埋点是 best-effort：写入失败只记录后端 warning，不影响主业务流程。
- 每次处理任务使用一个 `task_id` 串联导入、转写、摘要、导出和下载等事件。
- 历史快照报告不写入事件表，历史 localStorage 数据不伪造成事件。

## 字段含义

| 字段 | 含义 |
| --- | --- |
| `event_id` | 单条事件 ID。 |
| `task_id` | 一次处理任务的 ID，用于串联同一任务的多个事件。 |
| `event_name` | 事件名。 |
| `created_at` | 事件写入时间，ISO 格式。 |
| `source_type` | 来源类型，例如 `video`、`audio`、`transcript_file`。 |
| `source_filename` | 原始文件名。 |
| `source_duration_seconds` | 音视频或字幕推算出的内容时长。 |
| `source_file_size_mb` | 原始文件大小，单位 MB。 |
| `transcript_length` | 转写文本长度。 |
| `summary_length` | Markdown 摘要长度。 |
| `stage` | 事件发生的处理阶段。 |
| `duration_seconds` | 当前阶段耗时。 |
| `success` | 当前事件是否成功，`true`/`false`/空。 |
| `error_reason` | 失败原因。 |
| `export_target` | 导出目标，例如 `lark_cli`、`lark_openapi`。 |
| `feishu_doc_url` | 飞书文档 URL。 |
| `metadata` | 少量补充信息，例如 `trigger: auto/manual`、模型名、下载格式、任务终态字段。 |

## 事件定义

| 事件名 | 真实触发位置 | 含义 |
| --- | --- | --- |
| `source_imported` | `/process`、`/summarize-transcript-file` 收到并读取文件后 | 用户导入音视频或字幕/文本文件。 |
| `audio_extracted` | `/process` 中 FFmpeg 音频处理成功后 | 音视频路径完成音频提取。字幕/文本路径不会记录此事件。 |
| `stt_completed` | `/process` 中 faster-whisper 返回结果后 | 音视频路径完成本地转写。字幕/文本路径不会记录此事件。 |
| `transcript_ready` | `/process` 转写完成后；`/summarize-transcript-file` 解析字幕/文本后 | 系统已有可用转写文本。 |
| `summary_completed` | AI 摘要真实成功并返回非空 Markdown 后 | 摘要生成成功，只记录 `success=true`。 |
| `summary_failed` | AI 摘要调用失败或返回空结果后 | 摘要生成失败，记录 `success=false` 和 `error_reason`。 |
| `summary_fallback_used` | 音视频路径 AI 摘要失败后回退为 transcript 时 | 系统使用原始转写生成 fallback 内容，不代表摘要成功。 |
| `summary_skipped` | 用户开启跳过 AI 摘要时 | 系统进入 transcript-only 模式，`metadata.reason=transcript_only_mode`。 |
| `summary_regenerated` | 用户点击“重新生成”并调用 `/regenerate-summary` 后 | 用户触发重新生成摘要；不代表质量提升。 |
| `lark_export_started` | 自动或手动飞书导出开始前 | 发起飞书导出请求，`success` 为空，`metadata.trigger` 区分 `auto`/`manual`。 |
| `lark_export_completed` | 飞书导出返回或失败后 | 飞书导出完成，使用 `success` 区分成功/失败。 |
| `summary_downloaded` | 用户点击摘要下载按钮后 | 用户下载摘要文件；不代表笔记可用。 |
| `transcript_downloaded` | 用户点击转写下载按钮后 | 用户下载转写文件。 |
| `task_failed` | 处理、摘要、导出等接口发生业务异常时 | 任务在某阶段失败。`/process` HTTP 200 不等同任务成功，业务失败以此事件为准。 |
| `task_cancelled` | 用户点击当前任务的取消按钮后 | 用户主动取消当前任务。 |
| `task_completed` | 一次主处理任务完成、失败或取消时 | 任务终态事件。`duration_seconds` 表示端到端耗时；`metadata.final_status` 为 `completed`、`failed` 或 `cancelled`。 |

## 任务终态 metadata

`task_completed` 不新增表字段，以下口径放在 `metadata` 中：

| 字段 | 含义 |
| --- | --- |
| `final_status` | `completed` / `failed` / `cancelled`。 |
| `total_duration_seconds` | 端到端任务耗时，与该事件的 `duration_seconds` 一致。 |
| `summary_status` | `completed` / `failed` / `skipped` / `fallback_used`。 |
| `lark_requested` | 本次主处理任务是否请求自动飞书导出。 |
| `lark_success` | 自动飞书导出是否成功；未请求时为空。 |
| `source_type` | 来源类型，冗余写入便于分析。 |
| `pipeline_mode` | `audio_video` 或 `transcript_file`。 |
| `completion_reason` | 可选，说明跳过、失败或取消原因。 |

## 可计算指标

- 导入任务数：`source_imported` 数量。
- 音视频处理数：`source_imported` 且 `source_type in ("video", "audio")`。
- 字幕/文本处理数：`source_imported` 且 `source_type="transcript_file"`。
- 平均内容时长：`source_duration_seconds` 的均值。
- FFmpeg 平均耗时：`audio_extracted.duration_seconds`。
- STT 耗时比：`stt_completed.duration_seconds / source_duration_seconds`。
- 摘要生成成功率：`summary_completed / (summary_completed + summary_failed)`，排除 `summary_skipped`。
- 摘要跳过次数：`summary_skipped` 数量。
- 摘要 fallback 次数：`summary_fallback_used` 数量。
- 任务完成数：`task_completed(metadata.final_status="completed")`。
- 任务失败数：`task_completed(metadata.final_status="failed")`。
- 端到端平均任务耗时：`task_completed.duration_seconds` 的均值。
- 平均转写长度：`transcript_ready.transcript_length` 的均值。
- 平均摘要长度：`summary_completed.summary_length` 的均值。
- 飞书导出成功率：`lark_export_completed(success=true) / lark_export_started`。
- 自动/手动导出数量：按 `metadata.trigger` 聚合 `lark_export_started`。
- 失败原因分布：按 `task_failed.error_reason` 或失败事件聚合。
- 下载次数：`summary_downloaded`、`transcript_downloaded` 数量。

## 本阶段明确不做

| 不做事件 | 原因 |
| --- | --- |
| `note_copied` | 当前没有复制 Markdown 按钮。 |
| `manual_review_started` | 当前没有“开始校对”入口。 |
| `manual_review_completed` | 当前没有“完成校对”入口，也没有校对计时。 |
| `note_marked_usable` | 当前没有“这篇笔记可直接使用”入口。 |
| `note_marked_needs_edit` | 当前没有“需要我再改”入口。 |
| `user_rating_submitted` | 当前没有 1-5 分评分入口。 |
| `manual_edit_completed` | 当前没有正文编辑器，不能把提示词编辑或重新生成包装成笔记编辑。 |

这些事件应留到第二阶段，在补充明确 UI 选择权后再记录。

## 导出事件日志

```bash
python3 scripts/export_events.py --format json
python3 scripts/export_events.py --format csv
```

可以写入文件：

```bash
python3 scripts/export_events.py --format json --output reports/fluentflow_events.json
python3 scripts/export_events.py --format csv --output reports/fluentflow_events.csv
```
