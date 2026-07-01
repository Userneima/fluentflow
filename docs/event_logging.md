# FluentFlow 事件日志说明

本文档描述 FluentFlow 的长期事件日志口径。目标是记录真实发生的系统链路和用户动作，用于分析处理效率、稳定性、失败原因和外部同步链路。

## 基本原则

- 事件日志使用本地 SQLite：`data/fluentflow_events.sqlite`。
- 只记录长度、类型、耗时、状态、错误原因和外部同步结果，不保存完整转写文本或完整 Markdown 笔记。
- 事件日志是诊断和统计数据，不是结果存储；完整结果、字幕、笔记和产物归属看任务结果和 artifact。
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
| `export_target` | 外部导出或同步目标。当前飞书/Lark 路线使用 `lark_cli`、`lark_openapi`。 |
| `feishu_doc_url` | 飞书/Lark 文档 URL；仅飞书/Lark 导出事件使用。 |
| `metadata` | 少量补充信息，例如事件口径版本、运行环境、`trigger: auto/manual`、模型名、下载格式、任务终态字段。 |

## 事件定义

| 事件名 | 真实触发位置 | 含义 |
| --- | --- | --- |
| `source_imported` | `/process`、`/summarize-transcript-file` 收到并读取文件后 | 用户导入音视频或字幕/文本文件。 |
| `audio_extracted` | `/process` 中 FFmpeg 音频处理成功后 | 音视频路径完成音频提取。字幕/文本路径不会记录此事件。 |
| `stt_completed` | `/process` 中选定 STT 服务返回结果后 | 音视频路径完成真实转写。`metadata.stt_provider` 区分具体转录 provider；字幕/文本路径不会记录此事件。 |
| `transcript_cleanup_completed` | `/process`、`/summarize-transcript-file` 检测到并折叠重复幻觉后 | 机械清洗明显重复片段完成。只在实际发生清洗时记录，不代表人工确认内容正确。 |
| `speaker_diarization_completed` | 用户开启说话人区分且真实 diarization 后端成功返回后 | 字幕段已合并真实说话人标签。不会用启发式猜测 speaker。 |
| `transcript_ready` | `/process` 转写完成后；`/summarize-transcript-file` 解析字幕/文本后 | 系统已有可用转写文本。 |
| `transcript_review_completed` | 已移除，仅历史版本可能存在 | 旧版热词审阅事件。当前主流程不再产生。 |
| `summary_completed` | AI 摘要真实成功并返回非空 Markdown 后 | 摘要生成成功，只记录 `success=true`。 |
| `summary_failed` | AI 摘要调用失败或返回空结果后 | 摘要生成失败，记录 `success=false` 和 `error_reason`。 |
| `summary_fallback_used` | 已移除，仅历史版本可能存在 | 当前版本不再把原始转写伪装成摘要成功；摘要失败会进入失败态。 |
| `summary_skipped` | 用户开启跳过 AI 摘要时 | 系统进入 transcript-only 模式，`metadata.reason=transcript_only_mode`。 |
| `summary_regenerated` | 用户点击“重新生成”并调用 `/regenerate-summary` 后 | 用户触发重新生成摘要；不代表质量提升。 |
| `lark_export_started` | 自动或手动飞书/Lark 导出开始前 | 发起当前外部同步请求，`success` 为空，`metadata.trigger` 区分 `auto`/`manual`。 |
| `lark_export_completed` | 飞书/Lark 导出返回或失败后 | 当前外部同步完成，使用 `success` 区分成功/失败。 |
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

`stt_completed` 会记录粗粒度运行环境、转录服务和归一化性能指标，用于解释“本地转写耗时受设备影响”和“云端转写耗时受网络与服务端影响”的口径。`task_completed` 也会带上相同的粗粒度运行环境，方便按设备环境分组看端到端任务耗时。

不同 STT provider 的进度和取消能力不同。事件日志只记录真实完成后的 `stt_completed` 指标；进行中状态属于任务进度流，不应伪造成持久化事件。

本地转录、云端转录和 legacy provider 的性能不能直接混算。报告必须按 `stt_provider` 分组，并说明是否包含上传、网络等待、模型加载或外部服务处理时间。

外部 provider 请求可能无法像本地子进程一样被强制中断。用户取消任务时可以更新任务状态并停止后续处理，但已发出的外部请求是否真正停止取决于 provider 能力。

| 字段 | 含义 |
| --- | --- |
| `runtime_os` | 后端运行系统，例如 `Darwin`。 |
| `runtime_machine` | CPU 架构，例如 `arm64`。 |
| `runtime_cpu_count` | CPU 逻辑核心数。 |
| `python_version` | Python 版本。 |
| `faster_whisper_version` | faster-whisper 包版本。 |
| `ctranslate2_version` | ctranslate2 包版本。 |
| `ffmpeg_version` | FFmpeg 版本首行。 |
| `stt_provider` | `elevenlabs_scribe`、`local` 或 legacy `azure_batch`。报告必须按 provider 分组比较。 |
| `stt_provider_label` | 面向阅读的转录服务名称。 |
| `stt_language` | 用户选择的语言配置；`auto` 表示交给 STT provider 自动识别。 |
| `detected_language` | STT 服务返回的检测语言。 |
| `provider_audio_size_mb` | Provider 上传前的音频大小。旧事件可能使用 provider-specific 字段，例如 `elevenlabs_audio_size_mb` 或 `azure_batch_audio_size_mb`。 |
| `provider_duration_seconds` | Provider 上传前的音频时长估计。旧事件可能使用 provider-specific 字段，例如 `elevenlabs_duration_seconds` 或 `azure_batch_duration_seconds`。 |
| `legacy_provider_status` | Legacy provider 轮询状态；仅历史或兼容路径可能存在。 |
| `audio_output_format` | `audio_extracted` 事件中的 STT 音频格式。本地路径为 `wav`，云端路径为 `mp3`。 |
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

报告中比较 STT 性能时，应优先使用 `stt_realtime_factor`，并按 `stt_provider`、`stt_model`、`stt_speed`、`runtime_os`、`runtime_machine`、`model_cache_hit` 分组或说明口径。本地路径若要比较纯转写推理速度，应排除 `model_cache_hit=false` 的冷启动样本，或用 `duration_seconds - model_load_seconds` 单独计算；云端路径则应说明包含上传、网络等待和云端处理时间。

`scripts/report_stt_performance.py` 会额外汇总云端上传音频平均体积、平均时长和 `detected_language` 分布。报告中 `stt_language` 表示用户请求配置，`detected_language` 才表示 STT 服务返回的识别结果。

当同一个 `source_fingerprint` 同时出现本地和云端的 `stt_completed` 事件时，报告会生成 `Same-Source Comparisons`，列出同一文件下不同 provider 的耗时、倍率和最快/最慢差异。这个指标适合比较同一材料的 provider 表现，但不能泛化成所有材料的平均速度差；简历或报告中应保留“同源文件复测”口径。

## 性能分析命令

- `venv/bin/python scripts/report_stt_performance.py --format md`：从 SQLite 事件日志汇总 STT 样本，按转录服务、设备、模型、速度档和语言分组。
- `venv/bin/python scripts/report_stt_performance.py --format json --output reports/stt_performance.json`：导出机器可读报告。
- `venv/bin/python scripts/benchmark_stt.py /path/to/media.mp4 --model medium --speed balanced --language auto`：用和应用相同的 FFmpeg + faster-whisper 核心链路跑单文件基准，不写入事件表。
- `venv/bin/python scripts/check_deployment_readiness.py`：检查公开部署所需的 ElevenLabs、LLM、上传限制、队列和飞书配置。

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
| `requested_note_mode` | 用户或前端请求的模式：`auto`、`direct`、`high_fidelity`、`chapter_coverage`。 |
| `resolved_note_mode` | 后端实际采用的模式。`auto` 会由策略 Agent 或长度兜底解析为具体模式。 |
| `note_mode_chunk_count` | 本次摘要阶段使用的转录分段数；`direct` 通常为 `1`。 |
| `note_mode_transcript_length` | 本次输入摘要阶段的转录文本长度。 |
| `coverage_checked` | 高保真模式下是否执行了覆盖率检查。输入过长时可能跳过覆盖检查。 |
| `coverage_revision_used` | 覆盖率检查发现遗漏后，是否执行了修订。 |
| `note_mode_segment_count` | `chapter_coverage` 稳定切片数。 |
| `note_mode_evidence_count` | `chapter_coverage` 抽取出的证据数。 |
| `note_mode_chapter_count` | `chapter_coverage` 生成的章节数。 |
| `note_mode_important_evidence_count` | `chapter_coverage` 中 importance >= 4 的证据数。 |
| `note_mode_covered_important_evidence_count` | 程序章节分配已覆盖的重要证据数。 |
| `note_mode_coverage_missing_count` | 覆盖检查发现或推断仍需补入的重要遗漏数量。 |

事件日志只记录请求模式、实际模式和可计算元数据；具体自动选择阈值属于笔记策略，不在事件口径中硬编码。

三种模式的口径：

- `auto`：默认推荐。用户不用判断长度，后端自动选择。
- `direct`：整段转录一次发送给模型，速度更快，适合较短材料；用户强制选择时不代表一定不会超过模型上下文。
- `high_fidelity`：先分段提取证据，再生成终稿，并在条件允许时做覆盖率检查；耗时更久，适合长课程和信息密度高的字幕。
- `chapter_coverage`：先稳定切片、抽取证据、规划章节，再逐章生成和覆盖检查；最慢，适合超长或高价值材料。

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
- 队列/后台任务的进度订阅断开不等于取消；用户可重新订阅任务事件。
- 旧的直接流式处理请求如果在完成前被客户端断开，可能记录 `task_completed(metadata.final_status="cancelled", completion_reason="client_disconnect")`。
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
- 笔记模式分布：按 `summary_completed.metadata.resolved_note_mode` 聚合。
- 高保真覆盖修订率：`coverage_revision_used=true / coverage_checked=true`，只适合内部观察，不等同最终笔记质量。
- 飞书导出成功率：`lark_export_completed(success=true) / lark_export_started`。
- 自动/手动导出数量：按 `metadata.trigger` 聚合 `lark_export_started`。
- 失败原因分布：按 `task_failed.error_reason` 或失败事件聚合。
- 下载次数：`summary_downloaded`、`transcript_downloaded` 数量。

## 不记录的事件类型

不要为不存在的用户动作或不可验证的系统判断预留事件。新增事件前先确认：

- 用户是否真的触发了一个明确动作，或系统是否真的进入了一个可验证状态。
- 事件是否能帮助诊断、统计或恢复，而不是只为了“看起来更完整”。
- 是否会诱导系统记录正文、字幕、笔记或其他生成内容。
- 是否已有结果字段、任务状态或 artifact 能表达同一事实。

示例：如果界面没有明确的评分、标记可用、开始校对或完成校对动作，就不要记录 `user_rating_submitted`、`note_marked_usable`、`manual_review_started` 这类意图事件。

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
