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
| `metadata` | 少量补充信息，例如事件口径版本、运行环境、`trigger: auto/manual`、模型名、下载格式、任务终态字段。 |

## 事件定义

| 事件名 | 真实触发位置 | 含义 |
| --- | --- | --- |
| `source_imported` | `/process`、`/summarize-transcript-file` 收到并读取文件后 | 用户导入音视频或字幕/文本文件。 |
| `audio_extracted` | `/process` 中 FFmpeg 音频处理成功后 | 音视频路径完成音频提取。字幕/文本路径不会记录此事件。 |
| `stt_completed` | `/process` 中 faster-whisper 返回结果后 | 音视频路径完成本地转写。字幕/文本路径不会记录此事件。 |
| `transcript_cleanup_completed` | `/process`、`/summarize-transcript-file` 检测到并折叠重复幻觉后 | 机械清洗明显重复片段完成。只在实际发生清洗时记录，不代表人工确认内容正确。 |
| `speaker_diarization_completed` | 用户开启说话人区分且 pyannote 成功返回后 | 字幕段已合并真实说话人标签；不会用启发式猜测 speaker。 |
| `transcript_ready` | `/process` 转写完成后；`/summarize-transcript-file` 解析字幕/文本后 | 系统已有可用转写文本。 |
| `transcript_review_completed` | 已移除，仅历史版本可能存在 | 旧版热词审阅事件。当前主流程不再产生。 |
| `summary_completed` | AI 摘要真实成功并返回非空 Markdown 后 | 摘要生成成功，只记录 `success=true`。 |
| `summary_failed` | AI 摘要调用失败或返回空结果后 | 摘要生成失败，记录 `success=false` 和 `error_reason`。 |
| `summary_fallback_used` | 已移除，仅历史版本可能存在 | 当前版本不再把原始转写伪装成摘要成功；摘要失败会进入失败态。 |
| `summary_skipped` | 用户开启跳过 AI 摘要时 | 系统进入 transcript-only 模式，`metadata.reason=transcript_only_mode`。 |
| `summary_regenerated` | 用户点击“重新生成”并调用 `/regenerate-summary` 后 | 用户触发重新生成摘要；不代表质量提升。 |
| `lark_export_started` | 自动或手动飞书导出开始前 | 发起飞书导出请求，`success` 为空，`metadata.trigger` 区分 `auto`/`manual`。 |
| `lark_export_completed` | 飞书导出返回或失败后 | 飞书导出完成，使用 `success` 区分成功/失败。 |
| `summary_downloaded` | 用户点击摘要下载按钮后 | 用户下载摘要文件；不代表笔记可用。 |
| `transcript_downloaded` | 用户点击转写下载按钮后 | 用户下载转写文件。 |
| `task_failed` | 处理、摘要、导出等接口发生业务异常时 | 任务在某阶段失败。`/process` HTTP 200 不等同任务成功，业务失败以此事件为准。 |
| `task_cancelled` | 用户点击当前任务的取消按钮后 | 用户主动取消当前任务。 |
| `task_completed` | 一次主处理任务完成、失败或取消时 | 任务终态事件。`duration_seconds` 表示端到端耗时；`metadata.final_status` 为 `completed`、`failed` 或 `cancelled`。 |

## 通用 metadata

每条由后端写入的事件都会带上：

| 字段 | 含义 |
| --- | --- |
| `event_schema_version` | 事件口径版本，用于区分历史事件定义。 |
| `app_version` | 应用版本；本地开发环境默认为 `local`。 |

客户端按钮事件也会带上事件口径版本，但只接收白名单 metadata，例如下载格式。

## STT 性能 metadata

`stt_completed` 会记录粗粒度运行环境和归一化性能指标，用于解释“本地转写耗时受设备影响”的口径。`task_completed` 也会带上相同的粗粒度运行环境，方便按设备环境分组看端到端任务耗时。

音视频路径的 STT 运行在独立子进程中。用户点击取消时，后端会取消后台任务并终止 STT 子进程，避免 faster-whisper 在线程池中继续占用 CPU。普通 SSE 连接断开不再等同于取消任务；后台任务会继续运行，前端可通过 `/jobs/{task_id}/events` 重新订阅进度。这个选择牺牲了跨任务复用模型缓存的速度优势；因此主流程里的 `model_cache_hit` 通常只反映子进程内部状态，不应再解读为“整个后端进程是否已经热启动”。

| 字段 | 含义 |
| --- | --- |
| `runtime_os` | 后端运行系统，例如 `Darwin`。 |
| `runtime_machine` | CPU 架构，例如 `arm64`。 |
| `runtime_cpu_count` | CPU 逻辑核心数。 |
| `python_version` | Python 版本。 |
| `faster_whisper_version` | faster-whisper 包版本。 |
| `ctranslate2_version` | ctranslate2 包版本。 |
| `ffmpeg_version` | FFmpeg 版本首行。 |
| `stt_realtime_factor` | `stt_elapsed_seconds / source_duration_seconds`。例如 `0.2` 表示转写耗时约为原音频时长的 20%。该值按本次 STT 阶段耗时计算，冷启动时会包含模型加载时间。 |
| `model_cache_hit` | Whisper 模型是否已在后端进程内缓存。 |
| `model_load_seconds` | 本次加载模型耗时；热启动通常为 `0`。 |
| `model_source` | `local_cache` 或 `model_name`，不记录完整本地路径。 |
| `compute_type` | faster-whisper compute type，例如 `int8`。 |
| `device_requested` | 请求的 faster-whisper 设备，例如 `auto`、`cpu`、`cuda`。 |
| `device_resolved` | faster-whisper 暴露的实际设备；如果当前版本无法读取则为空。 |
| `cpu_threads` | faster-whisper CPU 线程配置，`0` 表示使用默认值。 |
| `num_workers` | faster-whisper worker 数。 |
| `vad_filter` | 是否启用 VAD。 |
| `source_fingerprint` | 原始文件 SHA256、大小和文件名，用于识别同一文件的多次复跑；不包含音频内容或转写正文。 |

报告中比较 STT 性能时，应优先使用 `stt_realtime_factor`，并按 `stt_model`、`stt_speed`、`runtime_os`、`runtime_machine`、`model_cache_hit` 分组或说明口径。若要比较纯转写推理速度，应排除 `model_cache_hit=false` 的冷启动样本，或用 `duration_seconds - model_load_seconds` 单独计算。

## 性能分析命令

- `python3 scripts/report_stt_performance.py --format md`：从 SQLite 事件日志汇总 STT 样本，按设备、模型、速度档和语言分组。
- `python3 scripts/report_stt_performance.py --format json --output reports/stt_performance.json`：导出机器可读报告。
- `python3 scripts/benchmark_stt.py /path/to/media.mp4 --model medium --speed balanced --language auto`：用和应用相同的 FFmpeg + faster-whisper 核心链路跑单文件基准，不写入事件表。

若要比较「应用 vs 命令工具」，应使用同一文件、同一模型、同一速度档、同一语言设置。若要比较不同设备，应保留 `runtime_*`、`device_*`、`compute_type` 和 `model_cache_hit` 口径。

## STT 实时进度口径

`/process` 在语音转录阶段会通过 SSE 推送实时状态：

- `stage="stt"`
- `progress`：整体流水线进度，当前 STT 阶段映射到 22–60。
- `stt_progress`：基于 faster-whisper 已产出 segment 的音频时间戳计算，约等于 `segment.end / audio_duration`。
- `transcribed_seconds`：已转录到的音频时间。
- `duration_seconds`：本次抽取出的 WAV 音频时长。
- `stt_status`：粗粒度内部状态，包括 `starting`、`loading_model`、`preparing_audio`、`waiting_first_segment`、`transcribing_segments`。
- `stt_elapsed_seconds`：当前 STT 阶段已等待时间。

这些 SSE 消息只用于界面反馈，不写入事件表。持久化分析仍以 `stt_completed` 的耗时、模型、设备和文件指纹字段为准。

当前主流程采用质量优先的整段音频转录。第一段 segment 产出前可能只显示状态和等待时间，不强行切块制造进度；底层保留分块转录能力，但不作为默认路径。

## 重复清洗 metadata

`transcript_cleanup_completed` 只处理明显的 STT 重复幻觉，例如同一短语连续循环，或相邻字幕段高度重复。它是机械清洗层，不做语义补全、润色或事实判断。

| 字段 | 含义 |
| --- | --- |
| `cleanup_issue_count` | 本次检测到的重复问题数。 |
| `cleanup_applied_count` | 本次实际折叠的重复问题数。 |
| `cleanup_removed_segment_count` | 因连续重复字幕段被合并移除的 segment 数。 |
| `cleanup_raw_length` | 清洗前转录文本长度。 |
| `cleanup_cleaned_length` | 清洗后转录文本长度。 |

产品结果中仍保留 `raw_transcript_text` 和 `raw_segments`。摘要阶段使用清洗后的文本，避免重复幻觉占用上下文并干扰重点判断。

## 已移除：字幕审阅 metadata

早期版本曾记录 `transcript_review_completed`，用于追踪热词库和保守字幕审阅。当前产品已移除内置热词库和基于热词的字幕审阅入口，主流程不再产生该事件。

历史数据中如出现该事件，可按旧口径理解：

| 字段 | 含义 |
| --- | --- |
| `review_mode` | 审阅模式：`suggest` 只给建议，`conservative` 只自动应用高置信明显错误。 |
| `review_use_ai` | 是否启用大模型参与候选判断。 |
| `review_suggestion_count` | 本次发现的候选建议数。 |
| `review_applied_count` | 本次实际自动应用的修改数。 |
| `hotword_libraries` | 旧版本启用的热词库列表。 |

## AI 笔记生成模式 metadata

`summary_completed` 和 `summary_regenerated` 会记录笔记生成模式，方便后续比较不同长度字幕下的质量和耗时。

| 字段 | 含义 |
| --- | --- |
| `requested_note_mode` | 用户或前端请求的模式：`auto`、`direct`、`high_fidelity`。 |
| `resolved_note_mode` | 后端实际采用的模式。`auto` 会按转录长度自动解析为 `direct` 或 `high_fidelity`。 |
| `note_mode_chunk_count` | 本次摘要阶段使用的转录分段数；`direct` 通常为 `1`。 |
| `note_mode_transcript_length` | 本次输入摘要阶段的转录文本长度。 |
| `coverage_checked` | 高保真模式下是否执行了覆盖率检查。输入过长时可能跳过覆盖检查。 |
| `coverage_revision_used` | 覆盖率检查发现遗漏后，是否执行了修订。 |

当前自动阈值为：转录文本不超过约 `20,000` 字符时使用 `direct`；超过后使用 `high_fidelity`。这个阈值不是模型上下文极限，而是质量策略起点：先保守避免长课程被过度概括，后续用真实样本再调。

三种模式的口径：

- `auto`：默认推荐。用户不用判断长度，后端自动选择。
- `direct`：整段转录一次发送给模型，速度更快，适合较短材料；用户强制选择时不代表一定不会超过模型上下文。
- `high_fidelity`：先分段提取证据，再生成终稿，并在条件允许时做覆盖率检查；耗时更久，适合长课程和信息密度高的字幕。

## 任务终态 metadata

`task_completed` 不新增表字段，以下口径放在 `metadata` 中：

| 字段 | 含义 |
| --- | --- |
| `final_status` | `completed` / `failed` / `cancelled`。 |
| `total_duration_seconds` | 端到端任务耗时，与该事件的 `duration_seconds` 一致。 |
| `summary_status` | `completed` / `failed` / `skipped`。 |
| `lark_requested` | 本次主处理任务是否请求自动飞书导出。 |
| `lark_success` | 自动飞书导出是否成功；未请求时为空。 |
| `source_type` | 来源类型，冗余写入便于分析。 |
| `pipeline_mode` | `audio_video` 或 `transcript_file`。 |
| `completion_reason` | 可选，说明跳过、失败或取消原因。 |

取消口径：

- 前端取消按钮会记录 `task_cancelled`，表示用户明确点击取消。
- 后端检测到请求断开时，会终止 STT 子进程并记录 `task_completed(metadata.final_status="cancelled")`。
- 报表统计取消任务时优先按 `task_completed.final_status="cancelled"` 去重；统计用户取消按钮点击时再看 `task_cancelled`。

## 可计算指标

- 导入任务数：`source_imported` 数量。
- 音视频处理数：`source_imported` 且 `source_type in ("video", "audio")`。
- 字幕/文本处理数：`source_imported` 且 `source_type="transcript_file"`。
- 平均内容时长：`source_duration_seconds` 的均值。
- FFmpeg 平均耗时：`audio_extracted.duration_seconds`。
- STT 耗时比：优先使用 `stt_completed.metadata.stt_realtime_factor`，也可按 `stt_completed.duration_seconds / source_duration_seconds` 复算。
- 摘要生成成功率：`summary_completed / (summary_completed + summary_failed)`，排除 `summary_skipped`。
- 摘要跳过次数：`summary_skipped` 数量。
- 任务完成数：`task_completed(metadata.final_status="completed")`。
- 任务失败数：`task_completed(metadata.final_status="failed")`。
- 端到端平均任务耗时：`task_completed.duration_seconds` 的均值。
- 平均转写长度：`transcript_ready.transcript_length` 的均值。
- 平均摘要长度：`summary_completed.summary_length` 的均值。
- 直接/高保真模式分布：按 `summary_completed.metadata.resolved_note_mode` 聚合。
- 高保真覆盖修订率：`coverage_revision_used=true / coverage_checked=true`，只适合内部观察，不等同最终笔记质量。
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
