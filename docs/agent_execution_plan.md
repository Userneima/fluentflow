# FluentFlow Agent Execution Plan

本文档记录 FluentFlow Agent 化的落地顺序。目标不是把现有工具包装成概念，而是把「学习资料处理」中的判断、计划、工具调用和失败恢复显性化，让产品同时服务真实自用体验和面试作品集展示。

## Product Decisions

| 决策 | 当前结论 |
| --- | --- |
| 第一服务对象 | 学习资料；第一版只针对课程和讲座笔记 |
| 执行方式 | 默认自动执行，不要求用户先确认计划 |
| 用户可见方式 | `/processing` 作为 Agent 工作流呈现页，展示 Agent 为什么这么处理；长期人工偏好集中到设置页 |
| Demo 优先路线 | 公开产品优先展示高质量云端 STT；ElevenLabs Scribe 作为唯一目标云端 STT，本地 faster-whisper 保留为开发、私有部署和应急能力 |
| Agent 边界 | 先做单 Agent 工作层，不急着做多 Agent 或复杂自治 |

## Current Baseline

| 已有能力 | 当前状态 | 问题 |
| --- | --- | --- |
| `/agent/v1` API | 已有提交、等待、任务包、诊断、重新生成、导出接口 | 更像给外部 Agent 用的数据接口，不是用户可见工作层 |
| Agent Task Package | 已能输出来源、转录、笔记、产物、诊断、下一步动作和 Processing Plan | 后续需要继续丰富工具调用轨迹 |
| 笔记模式规划 | 已有 `note_mode_plan_*`，并已折入 `processing_plan.note_strategy` | 摘要策略仍需继续用真实材料评估 |
| 任务阶段与事件 | 已记录解析、下载、转录、摘要、导出等阶段 | 需要继续产品化成更完整的 Agent 工具调用轨迹 |
| 失败诊断 | 已能区分仅转录、缺转录、额度、登录、任务归属、空笔记等问题 | 需要继续把恢复动作做成更顺手的一键操作 |

## Processing Plan V1 Boundaries

第一版 `Processing Plan` 只服务课程和讲座笔记，不覆盖教程步骤、访谈整理、字幕翻译和知识库归档。后者可以作为未来扩展或输出选项，但不进入第一轮核心目标。

计划采用两段式生成：

1. **初始计划**：任务创建时生成，依据输入类型、用户目标、ElevenLabs 云端 STT 可用性、本地应急能力和少量文件名信息，先确定可执行路径。例如公开产品默认走 ElevenLabs，本地 faster-whisper 只作为私有部署或故障兜底。
2. **补全计划**：转录完成后生成或更新，依据语言、时长、转录长度、内容结构、是否接近课程/讲座，再决定笔记策略、风险提示和预计输出。

材料类型判断的权重必须偏向转录内容。文件名只能作为弱信号，不能主导判断；如果转录内容和文件名冲突，以转录内容为准。第一版可以使用可解释的启发式和结构化 AI 判断，但不能把简单关键词规则包装成强语义理解。

## UI Placement And Settings Consolidation

不新增独立 Agent 页面。Agent 计划展示只放在两个现有位置：

| 位置 | 作用 |
| --- | --- |
| Agent 工作流页 | 从“用户手动选择一堆参数”转为“Agent 将如何处理本次学习资料”的计划、判断链和依据展示 |
| 任务详情 / 编辑器 | 展示完整计划、补全后的判断、工具调用轨迹、失败恢复建议和最终产物 |

Agent 工作流页不再承载长期配置。已经交给 Agent 判断的内容，不应该继续以同等权重暴露给用户；仍需要人维护的偏好，应集中到设置页，并在 Agent 工作流页解释这些偏好如何影响本次计划。

## Execution Table

| Step | Phase | Action | Output | Validation |
| --- | --- | --- | --- | --- |
| 1 | P0 定义语义 | 定义 FluentFlow Agent 的第一版目标：把学习视频/音频/字幕变成可复用学习资产 | 本文档作为执行基准 | 后续新增 Agent 功能必须能映射到该目标 |
| 2 | P0 目标模型 | 第一版只定义课程笔记和讲座笔记两个学习目标 | `learning_goal` 字段草案 | 不把教程、访谈、翻译、归档提前做成核心目标 |
| 3 | P0 计划结构 | 设计 `Processing Plan` 数据结构：材料类型、用户目标、处理步骤、工具选择、风险提示、预计输出 | `docs/result_schema.md` 或独立 schema 小节 | schema 能覆盖现有本地视频、字幕文件、链接任务 |
| 4 | P1 后端初始计划 | 在任务创建时生成初始计划，基于输入类型、用户目标、本地/云端能力和弱文件名信号 | 后端返回结构化 initial plan，不改变现有执行流程 | 已添加单元测试，覆盖本地视频、字幕导入、链接任务 |
| 5 | P1 任务结果持久化 | 把 `Processing Plan` 写入 job result 和 Agent Task Package | 历史任务可回看当时判断 | Agent package 测试断言包含 plan |
| 6 | P1 转录后补全计划 | 转录完成后依据语言、时长、转录长度和内容结构补全材料判断与笔记策略 | completed plan，包含内容依据和置信边界 | 已测试文件名误导时，计划仍优先听从转录内容 |
| 7 | P1 合并笔记规划 | 将 `note_mode_plan_*` 挂入 Processing Plan 的 `note_strategy`，保留旧字段兼容 | 摘要策略成为完整计划的一部分 | 旧任务仍可打开，新任务能显示完整原因 |
| 8 | P1 自动执行解释 | 保持默认自动执行，但在 Agent 工作流页和任务详情/编辑器展示 Agent 计划，不要求用户确认 | 用户少一步决策，但能看到系统判断 | 不新增页面；Agent 工作流页能显示计划摘要 |
| 9 | P1 设置瘦身 | 删除、合并或迁移已交给 Agent 判断的处理设置 | `/processing` 变成 Agent 工作流呈现页；长期人工偏好进入设置页 | 不牺牲核心任务完成；高级用户仍有必要出口 |
| 10 | P2 工具调用轨迹 | 把现有阶段包装成可读 trace：解析链接、下载、音频预处理、云端 STT、结果标准化、笔记生成、飞书导出 | `tool_trace` 或由事件日志映射出的前端视图 | 用户能看到真实工具调用顺序，不需要理解具体 provider |
| 11 | P2 失败恢复 | 将 diagnosis + next_actions 产品化为“Agent 建议下一步” | 失败任务显示原因、建议和可执行按钮 | 覆盖重新生成、重新导出、等待、重新提交 |
| 12 | P2 ElevenLabs 云端 STT Demo | 打磨一条面试 Demo：上传课程/讲座视频，Agent 自动生成计划，使用 ElevenLabs 云端 STT，标准化转录结果，展示 trace，输出笔记 | 3 分钟可讲清楚的作品集路径 | 不再依赖 Azure 订阅；ElevenLabs 接入前可用本地/历史 provider 临时模拟链路 |
| 13 | P3 评估指标 | 记录计划生成、计划补全、摘要策略、失败恢复动作 | 事件日志新增 Agent plan 口径 | 指标只解释工作流行为，不伪装成笔记质量评分 |
| 14 | P3 文档与作品集 | 补 `docs/result_schema.md`、更新 `docs/product_intro_latest.md` 的 Agent 叙事 | 面试讲述材料与实现一致 | 文档能区分已实现、进行中、未来计划 |

## First Implementation Slice

第一刀只做最小闭环，不重构主处理流程：

1. 新增 `Processing Plan` schema。
2. 后端在任务创建时生成初始计划。
3. 转录完成后基于转录内容补全计划，并降低文件名判断权重。
4. Agent Task Package 返回 plan。
5. Agent 工作流页展示计划摘要和判断链，并把人工长期偏好迁到设置页。
6. 任务详情/编辑器展示完整计划。
7. 任务显示 STT 工具调用轨迹；公开叙事按 ElevenLabs 云端 STT 表达，本地 STT 仅作为开发/应急说明。

完成这一刀后，FluentFlow 就能从“我上传了一个视频，它帮我生成笔记”，升级为：

> 我给 FluentFlow 一个学习资料目标，它自动判断材料类型，选择高质量云端 STT 和笔记策略，执行工具链，并解释每一步为什么发生。

## One-Conversation Multi-Agent Rollout

开发执行可以采用“一个主对话 + 多个子 Agent”的模式。主控 Agent 负责产品判断、接口契约、共享文件集成和最终验证；子 Agent 只负责被分配的清晰边界，避免在不同对话里丢失产品口径。

### Execution Order

| 顺序 | 子 Agent / 角色 | 目标 | 主要文件 | 不碰范围 |
| --- | --- | --- | --- | --- |
| 1 | 后端链路 | 让 ElevenLabs Scribe 真正进入 `/process`、队列、凭证、speaker 和 trace 主链路 | `backend/core/server_helpers.py`, `backend/routers/processing.py`, `backend/core/local_config.py`, `backend/routers/config.py`, `tests/test_queue_process.py` | 不改前端页面和产品文档 |
| 2 | 主控集成 | 统一 STT provider 契约，消除 `azure_batch` 默认口径残留 | `frontend/src/app/shared.jsx`, `frontend/src/app/jobMorph.js`, `scripts/check_deployment_readiness.py`, `scripts/codex_transcribe_link.py` | 不重做页面视觉 |
| 3 | 前端体验 | 把 `/processing` 从运行参数面板改成 Agent 工作流呈现页 | `frontend/src/routes/processing.jsx`, 必要时抽取 `agent-trace` 展示组件 | 不改后端执行分支，不抢共享 provider helper |
| 4 | 设置收口 | 把长期人工偏好集中到设置页，移走 Agent 已自动判断的运行参数 | `frontend/src/routes/settings.jsx` | 不改变任务执行语义 |
| 5 | Demo / 文档 | 把面试叙事、部署变量、运维手册和架构图统一到 ElevenLabs + Agent 路线 | `README.md`, `docs/product_intro_latest.md`, `docs/architecture.md`, `docs/beta_deployment_checklist.md`, `deploy/README.md` | 不写新的 schema，除非代码字段变化 |

### Shared-File Rules

- `frontend/src/app/shared.jsx`, `frontend/src/app/jobMorph.js`, `frontend/src/app/i18n.jsx`, `backend/routers/processing.py`, `backend/core/server_helpers.py`, `docs/changelog.md` 只能由主控或单一指定 Agent 改。
- 子 Agent 可以指出共享文件需要怎么改，但不要并行修改同一共享文件。
- 前端页面 Agent 优先在页面内部完成展示层，不先抽公共 helper；公共 helper 由主控在集成时统一抽。
- 文档 Agent 只更新当前路线和验收口径，不删除历史 changelog 中真实发生过的 Azure 记录。

### Current First Batch

第一批任务不再继续扩展功能，先消除三类断层：

1. 后端断层：页面和文档说 ElevenLabs，但主 `/process` 链路仍可能回到 Azure 或 local。
2. 前端断层：`/processing` 还是运行参数面板，且页面入口、provider 口径和 Agent trace 分散。
3. 文档断层：README、架构、部署和运维文档如果还以 Azure 为默认，会直接误导 Demo 准备。

## Non-Goals For Now

- 不把 Azure 云端链路作为第一版 Agent Demo 核心；默认云端 STT 使用 ElevenLabs Scribe，Azure 只作为 legacy 兼容代码保留。
- 产品内第一版不做多 Agent 协作；开发执行可以使用本文档定义的主控 + 子 Agent 模式。
- 不要求用户在执行前审批每一步。
- 不把教程步骤、访谈整理、字幕翻译、知识库归档作为第一版核心目标。
- 不新增独立 Agent 页面。
- 不为了展示 Agent 感而增加无意义动画或长篇解释。
- 不把启发式分类伪装成真正语义智能；计划生成需要明确说明依据与置信边界。

## Interview Storyline

1. 用户上传一个课程或讲座视频。
2. Agent 先生成初始计划，选择高质量云端 STT 路线。
3. Agent 自动规划：云端转录、结果标准化、段落整理、高保真或直接笔记、可选飞书归档。
4. 转录完成后，Agent 根据内容补全材料判断和笔记策略。
5. 系统执行真实工具链：音频预处理、云端 STT、结果标准化、AI 笔记生成、产物保存。
6. UI 在 Agent 工作流页和任务详情/编辑器展示计划、工具调用轨迹、失败恢复建议和最终学习笔记。
7. 面试讲述重点：这不是单次模型调用，而是一个带计划、工具、状态、诊断和恢复能力的学习资料处理 Agent。
