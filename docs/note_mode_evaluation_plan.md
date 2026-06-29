# 笔记生成模式阈值评测方案

本文档记录如何用自动化实验和模型评审，校准 FluentFlow 笔记生成模式的默认切换边界。

它回答的问题是：

- `direct`、`high_fidelity`、`chapter_coverage` 分别适合什么长度和内容类型？
- 2 万、8 万这类阈值应该如何被验证，而不是凭感觉写死？
- 哪些评测可以自动化，哪些必须保留人工判断？

## 基本结论

阈值不能只按模型上下文上限定，也不能只按字符数定。

第一版可以用字符数作为启发式边界，但最终应该通过真实字幕样本评测来校准：

```text
候选默认策略：
- 短字幕：direct
- 普通长字幕：high_fidelity
- 超长或高价值字幕：chapter_coverage
```

其中 `20,000` 和 `80,000` 只能作为初始候选值：

- `20,000`：来自当前 direct / high_fidelity 的自动切换阈值，是质量风险阈值，不是模型能力边界。
- `80,000`：来自当前约 8000 字符证据分段下，约 10 个证据批次的复杂度拐点，尚未经过样本验证。

## 目标

建立一个离线评测流程，自动比较不同笔记模式在真实字幕上的表现，输出候选阈值和失败案例。

目标不是让脚本自动宣布“最优策略”，而是让维护者看到：

- 哪个长度段 direct 开始明显漏点。
- 哪个长度段 high_fidelity 开始吃力。
- chapter_coverage 从哪里开始值得付出额外成本。
- 哪些内容类型不适合单纯按长度判断。

## 非目标

第一版不做：

- 不用自动分数直接替代人工判断。
- 不把模型评审当作绝对真理。
- 不要求一次覆盖所有内容类型。
- 不在生产链路中实时跑评测。
- 不把评测样本中的完整字幕提交到 Git。

## 样本设计

评测样本应覆盖不同长度和不同内容密度。

建议目录：

```text
data/eval_samples/
  short_01.txt
  mid_01.txt
  long_01.txt
  extra_long_01.txt
```

样本范围：

| 长度段 | 目的 |
| --- | --- |
| 1 万字以内 | 验证 direct 是否足够。 |
| 1 万到 3 万字 | 找 direct 开始不稳的边界。 |
| 3 万到 6 万字 | 验证 high_fidelity 是否明显优于 direct。 |
| 6 万到 10 万字 | 找 high_fidelity 的风险边界。 |
| 10 万字以上 | 验证 chapter_coverage 是否值得。 |

内容类型：

| 类型 | 关注点 |
| --- | --- |
| 课程 | 概念、框架、例子、步骤是否完整。 |
| 会议 | 决策、行动项、风险、责任人是否完整。 |
| 访谈 | 人物观点、故事、转折是否完整。 |
| 播客/口播 | 冗余压缩后是否保留主线。 |

样本不宜只看字符数。同样 5 万字，流水账会议和高密度课程的质量风险完全不同。

## 自动化角色

可以用 subagent 或同等的批处理任务来分工。这里的 “subagent” 是执行角色，不要求必须使用某个特定框架。

### 1. Runner

职责：批量跑不同模式。

输入：

- 样本字幕。
- 模式列表：`direct`、`high_fidelity`、`chapter_coverage`。
- 固定模型、提示词和运行配置。

输出：

```json
{
  "sample_id": "long_01",
  "mode": "high_fidelity",
  "transcript_chars": 73520,
  "elapsed_seconds": 182.4,
  "model_call_count": 13,
  "output_chars": 12680,
  "status": "completed",
  "metadata": {
    "chunk_count": 10,
    "coverage_checked": true,
    "coverage_revision_used": false
  }
}
```

### 2. Evidence Builder

职责：从原字幕中抽取评测用关键点清单。

要求：

- 不看各模式输出，避免被候选笔记污染。
- 输出结构化关键点。
- 标记重要性和来源片段。

示例：

```json
{
  "point_id": "P017",
  "importance": 5,
  "type": "method",
  "text": "讲者提出用户访谈要先问行为事实，而不是直接问偏好。",
  "source_hint": "约第 34 分钟"
}
```

注意：这仍然是模型生成的临时 gold set，不等于绝对标准。边界样本仍需人工抽查。

### 3. Judge

职责：对照关键点清单评估每种模式输出。

评估维度：

| 维度 | 含义 |
| --- | --- |
| `coverage` | 重要点是否被覆盖。 |
| `faithfulness` | 是否忠实原文，是否幻觉。 |
| `specificity` | 是否保留例子、数字、限制条件、步骤。 |
| `structure` | 章节结构是否自然。 |
| `redundancy` | 是否重复啰嗦。 |
| `readability` | 是否适合复习或归档。 |

输出：

```json
{
  "sample_id": "long_01",
  "mode": "direct",
  "covered_points": ["P001", "P002"],
  "missed_important_points": ["P017", "P021"],
  "hallucination_risk": "low",
  "structure_score": 3,
  "notes": "中后段案例被明显压缩。"
}
```

### 4. Boundary Analyzer

职责：汇总所有样本并提出候选边界。

关注问题：

- direct 从哪个长度/密度开始重要点覆盖率下降？
- high_fidelity 在多少证据批次后开始遗漏或覆盖检查不稳定？
- chapter_coverage 额外耗时和成本从哪里开始值得？
- 是否存在“短但信息密度高”的例外样本？

输出：

```text
候选边界：
- direct：≤ 28,000 字符
- high_fidelity：28,001 到 76,000 字符
- chapter_coverage：> 76,000 字符

置信度：中
原因：7 万字符以上样本中 high_fidelity 开始出现重要案例遗漏，chapter_coverage 在结构和覆盖率上更稳定，但耗时约增加 2.1 倍。
```

### 5. Reporter

职责：生成维护者可读报告。

输出文件：

```text
reports/note_mode_eval/
  runs.json
  point_sets.json
  judge_scores.json
  boundary_recommendation.md
  sample_failures.md
```

## 推荐命令形态

当前已落地第一版结果报告工具。它读取已经生成好的任务结果 JSON，汇总模式、转录长度、摘要长度、覆盖 metadata、耗时、token 和可选外部评审，不负责自动宣布哪种模式质量最好：

```bash
npm run note:quality -- \
  --input data/local_eval_results/long_01_chapter.json \
  --review data/local_eval_reviews/long_01_review.json \
  --output-dir reports/note_quality_eval/long_01
```

输出文件：

```text
reports/note_quality_eval/
  runs.json
  report.md
```

完整的跨模式 runner 仍是下一阶段：

```bash
venv/bin/python scripts/evaluate_note_modes.py \
  --samples data/eval_samples \
  --modes direct,high_fidelity,chapter_coverage \
  --output reports/note_mode_eval
```

评测脚本不需要接入生产任务队列。它只作为离线评测工具。

## 评测指标

### 质量指标

| 指标 | 说明 |
| --- | --- |
| 重要点覆盖率 | `covered_important_points / total_important_points`。 |
| 总覆盖率 | `covered_points / total_points`。 |
| 幻觉风险 | 模型评审 + 人工抽查。 |
| 结构稳定性 | 是否章节自然、层级清晰、顺序合理。 |
| 细节保留率 | 例子、数字、步骤、限制条件是否保留。 |

### 成本指标

| 指标 | 说明 |
| --- | --- |
| 运行耗时 | 从开始生成到完成的时间。 |
| 模型调用次数 | 不同模式的调用复杂度。 |
| 输出长度 | 避免“更完整”只是更长。 |
| 失败率 | JSON 解析失败、模型调用失败、空输出等。 |

### 边界指标

| 指标 | 说明 |
| --- | --- |
| direct 失稳点 | direct 重要点覆盖率明显下降的长度/密度。 |
| high_fidelity 失稳点 | 高保真开始遗漏、压缩过度或覆盖检查跳过的区间。 |
| chapter_coverage 收益点 | 完整覆盖模式质量收益超过额外成本的区间。 |

## 人工校准

自动评审完成后，必须人工抽查边界样本。

建议人工检查：

- direct 和 high_fidelity 分界附近 3 到 5 个样本。
- high_fidelity 和 chapter_coverage 分界附近 3 到 5 个样本。
- 模型评审认为差异最大的失败样本。

人工判断重点：

- 漏掉的点是否真的重要。
- chapter_coverage 是否只是写得更长，而不是真正更完整。
- 高保真是否已经足够好，没必要切到更重模式。
- 用户目标是否影响模式选择。

最终阈值应是：

```text
自动评测候选 + 人工边界样本校准
```

而不是单纯的脚本输出。

## 第一版执行计划

### Phase 1：准备样本

- 收集 10 到 20 份真实字幕。
- 按长度和内容类型标记 metadata。
- 样本放在本地 data 目录，不提交 Git。

### Phase 2：手动跑小样本

- 先选 3 份样本。
- 人工分别跑 direct、high_fidelity、chapter_coverage。
- 检查输出差异，确认评测维度是否合理。

### Phase 3：实现离线评测脚本

- 已完成：保存并汇总已生成结果的运行 metadata。
- 已完成：生成 Markdown / JSON 报告。
- 待完成：批量运行不同模式。
- 待完成：调用模型生成关键点清单。
- 待完成：调用模型做 judge。

### Phase 4：人工校准阈值

- 阅读 `boundary_recommendation.md`。
- 抽查边界样本。
- 形成第一版产品默认策略。

### Phase 5：回写产品文档

- 更新 `docs/long_transcript_coverage_notes_plan.md`。
- 更新 `docs/usage_guide_cn.md` 中模式说明。
- 必要时更新 `docs/event_logging.md` 的 metadata 口径。

## 风险

| 风险 | 处理 |
| --- | --- |
| 模型评审偏向更长输出 | 把“输出长度”单独记录，人工抽查高分长文。 |
| Evidence Builder 漏标关键点 | 边界样本人工校准，不把 gold set 当绝对真理。 |
| 样本太少导致阈值偶然 | 阈值标注为候选，积累更多真实样本后再改。 |
| API 成本过高 | 先小样本，缓存中间结果。 |
| 内容类型差异过大 | 阈值之外保留用户手动选择“快速优先 / 完整优先”。 |

## 当前建议

在没有评测数据前，不要把 `20,000` 和 `80,000` 写成产品事实。

更准确的表述是：

```text
20,000 是当前 direct/high_fidelity 的初始质量阈值。
80,000 是基于当前 8000 字符证据分段和约 10 批证据复杂度推导的候选阈值。
两者都需要通过 note_mode_evaluation 评测校准。
```

最终产品默认策略应来自评测报告，而不是当前直觉。
