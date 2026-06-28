# FluentFlow 指标口径说明

本文档定义 FluentFlow 后续用于产品判断、简历表达和内部排障的指标口径。它建立在 `docs/event_logging.md` 的事件定义之上，但更关注“能不能写、怎么写、哪些不能误读”。

核心原则：

- 指标必须来自真实事件、真实历史或明确用户反馈。
- 历史快照不能伪造成未来事件日志。
- HTTP 200 不等于任务成功。
- 下载、导出不等于用户认可质量。
- 本地 STT 速度必须带设备、模型和 provider 口径。

## 指标分级

| 分级 | 含义 | 使用方式 |
| --- | --- | --- |
| `resume_ready` | 口径清楚、可信度高，可直接写简历 | 仍建议保留样本量或时间范围 |
| `needs_context` | 可以写，但必须解释分母、来源或限制 | 适合项目复盘，不适合孤立写大数字 |
| `internal_only` | 只适合内部判断和排障 | 不建议写进简历 |
| `unavailable` | 当前没有真实数据入口 | 不能写，除非后续补 UI 或实验 |

## 核心指标

### 完成任务数

- 分级：`resume_ready`
- 事件：`task_completed`
- 计算：`count(task_completed where metadata.final_status="completed")`
- 最小样本量：20 个真实任务起步，50 个以上更适合写简历。
- 说明：代表系统完整处理闭环完成，不等于用户认可笔记质量。
- 可写表达：累计完成 X 个真实音视频/字幕处理任务。

### 累计处理内容时长

- 分级：`resume_ready`
- 事件：`source_imported` 或 `task_completed` metadata 中的时长字段。
- 计算：`sum(source_duration_seconds) / 3600`
- 最小样本量：累计 20 小时以上更有说服力。
- 说明：应区分音视频真实时长和字幕推算时长。
- 可写表达：累计处理约 X 小时课程/讲座/录音材料。

### 音视频 / 字幕来源分布

- 分级：`needs_context`
- 事件：`source_imported`
- 计算：按 `source_type` 分组计数。
- 最小样本量：30 个任务以上。
- 说明：音视频任务会经过 STT，字幕/文本任务跳过 STT，不能混算转录成功率。
- 可写表达：覆盖视频、音频和已有字幕三类输入，其中音视频任务 X 个、字幕/文本任务 X 个。

### STT 成功率

- 分级：`needs_context`
- 事件：`stt_completed`、`task_failed`
- 计算：`stt_completed / 音视频转录尝试数`
- 分母建议：音视频任务中进入 STT 阶段的任务数。
- 最小样本量：20 个音视频 STT 样本。
- 说明：必须按 `stt_provider` 分组，ElevenLabs Scribe、本地 faster-whisper 和 legacy Azure 不能混成一个口径。
- 可写表达：在 X 个音视频样本中，本地/云端 STT 成功率为 X%。

### STT 实时倍率

- 分级：`needs_context`
- 事件：`stt_completed`
- 计算：`stt_completed.metadata.stt_realtime_factor`，或 `duration_seconds / source_duration_seconds`
- 最小样本量：同 provider、同模型至少 10 个样本。
- 说明：本地路径强依赖设备，云端路径包含上传、网络和服务端处理。
- 可写表达：在当前设备/当前 ElevenLabs 配置下，STT 平均耗时约为原音频时长的 X%。

### 摘要生成成功率

- 分级：`resume_ready`
- 事件：`summary_completed`、`summary_failed`
- 计算：`summary_completed / (summary_completed + summary_failed)`
- 最小样本量：20 次摘要尝试。
- 说明：排除 `summary_skipped`；摘要成功只代表模型返回了摘要，不代表质量可用。
- 可写表达：AI 摘要生成链路在 X 次真实任务中成功率 X%。

### Summary fallback 使用率

- 分级：`internal_only`
- 事件：历史 `summary_fallback_used`
- 计算：`summary_fallback_used / summary_failed`
- 当前状态：新口径下不再把 fallback 当摘要成功；如历史存在，只用于排查旧版本。
- 说明：当前版本摘要失败应进入失败态，不建议在简历中强调 fallback。

### Summary skipped 次数

- 分级：`needs_context`
- 事件：`summary_skipped`
- 计算：`count(summary_skipped)`
- 说明：只代表用户选择仅转录，不代表摘要功能失败。
- 可写表达：支持仅转录模式，X 次任务选择跳过 AI 摘要。

### 飞书导出成功率

- 分级：`needs_context`
- 事件：`lark_export_started`、`lark_export_completed`
- 计算：`count(lark_export_completed success=true) / count(lark_export_started)`
- 最小样本量：至少 10 次导出尝试。
- 说明：必须区分自动导出和手动导出，按 `metadata.trigger` 分组更清楚。
- 可写表达：在 X 次飞书导出尝试中成功 X 次，成功率 X%。

### 任务失败率

- 分级：`resume_ready`
- 事件：`task_completed`
- 计算：`failed / (completed + failed + cancelled)`
- 最小样本量：30 个任务以上。
- 说明：取消应单独统计，不应混入系统失败。
- 可写表达：基于任务终态事件统计失败率，并按失败阶段定位问题。

### 失败阶段分布

- 分级：`internal_only`
- 事件：`task_failed`
- 计算：按 `stage`、`error_reason`、`metadata.stt_provider` 聚合。
- 说明：适合排障和下一轮优化，不适合作为简历数字单独展示。
- 可写表达：如果用于简历，应写成“基于失败阶段分布定位并修复 X 类问题”，而不是列失败数。

### 重新生成率

- 分级：`needs_context`
- 事件：`summary_regenerated`、`summary_completed`
- 计算：`summary_regenerated / summary_completed`
- 说明：重新生成只代表用户点击重跑，不能直接解释为首版质量差，也不能解释为质量提升。
- 可写表达：支持结果页重新生成摘要，并记录重生成行为用于提示词和模式对比。

### 摘要下载次数

- 分级：`needs_context`
- 事件：`summary_downloaded`
- 计算：`count(summary_downloaded)`
- 说明：下载代表用户取走文件，不代表笔记可用。
- 可写表达：生成摘要支持本地下载，累计下载 X 次。不要写成“X 篇笔记被采纳”。

### 转写下载次数

- 分级：`needs_context`
- 事件：`transcript_downloaded`
- 计算：`count(transcript_downloaded)`
- 说明：可作为用户是否需要保留原始转录的行为信号。
- 可写表达：转写产物支持 TXT/SRT/VTT 下载，累计下载 X 次。

### 取消率

- 分级：`needs_context`
- 事件：`task_cancelled`、`task_completed`
- 计算：`task_completed(final_status="cancelled") / all task_completed`
- 说明：取消可能是用户主动放弃、上传错文件、等待太久或测试行为，需要结合日志和反馈解释。
- 可写表达：记录长任务取消行为，用于优化等待提示和任务控制。

## 质量指标

当前不建议直接写质量指标，除非补足用户反馈或测试口径。

### 笔记可用率

- 分级：`unavailable`
- 当前缺口：没有“这篇笔记可直接使用 / 需要我再改”的明确入口。
- 未来做法：结果页补最小反馈按钮，事件记录 `note_marked_usable` / `note_marked_needs_edit`。

### 用户评分

- 分级：`unavailable`
- 当前缺口：没有 1-5 分评分入口。
- 未来做法：只在真实用户试用阶段加入，避免打断单人本地使用。

### 人工校对耗时

- 分级：`unavailable`
- 当前缺口：没有“开始校对 / 完成校对”两个明确动作。
- 当前已有：转录编辑记录可以证明用户修改了哪些句子，但不能证明总校对耗时。

### STT 质量

- 分级：`needs_context`
- 数据：人工修正后的参考转录、`scripts/evaluate_stt.py` 评估结果。
- 指标：CER、char accuracy、segment exact rate、glossary recall、active confusion count。
- 说明：适合按样本集说明模型/配置优化，不适合从一两个样本泛化。

## 推荐简历表达模板

### 可以直接写

- 累计处理 X 个真实音视频/字幕任务，覆盖约 X 小时课程、讲座和录音材料。
- 基于 SQLite 事件日志记录导入、转写、摘要、导出、失败和取消等阶段，支持按任务回溯端到端耗时与失败原因。
- 将 ElevenLabs Scribe 云转录与本地 faster-whisper 纳入同一处理链路，并按 provider、设备和模型记录 STT 性能口径。

### 必须带口径写

- 在当前设备 / ElevenLabs 配置下，STT 平均耗时约为原音频时长的 X%。
- 在 X 次飞书导出尝试中，成功 X 次；其中自动导出 X 次、手动导出 X 次。
- 在 X 次摘要尝试中，AI 摘要生成成功率为 X%，不含仅转录模式。

### 暂时不要写

- 笔记可用率 X%。
- 用户满意度 X 分。
- 人工校对耗时下降 X%。
- 用户采纳率 X%。
- 自动节省 X 小时人工成本，除非有明确对照或用户反馈。

## 样本量建议

| 指标 | 最小样本量 | 更适合写简历的样本量 |
| --- | --- | --- |
| 完成任务数 | 20 | 50+ |
| 累计内容时长 | 10 小时 | 30 小时+ |
| STT 成功率 | 20 个音视频任务 | 50+ |
| STT 实时倍率 | 同 provider 10 个 | 同 provider 30+ |
| 摘要成功率 | 20 次摘要尝试 | 50+ |
| 飞书导出成功率 | 10 次导出尝试 | 30+ |
| 用户反馈 | 3 名用户 | 5-10 名用户 |

## 报告生成建议

优先使用：

```bash
python3 scripts/export_events.py --format json --output reports/fluentflow_events.json
python3 scripts/report_stt_performance.py --format md --output reports/stt_performance.md
python3 scripts/history_snapshot.py
```

报告中必须写清：

- 数据时间范围。
- 样本数量。
- 是否来自历史快照还是事件日志。
- 本地还是云端 STT。
- 设备和模型口径。
- 哪些指标只是行为记录，不代表质量认可。
