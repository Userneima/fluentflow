export const DEFAULT_PROMPT_PRESET = 'autoTranscriptNotes';
export const BUILTIN_EXTRA_PROMPT_KEYS = ['autoTranscriptNotes', 'meeting', 'research', 'quickBullets'];

/* 与 backend/core/ai_summarizer.py 中 FLUENTFLOW_SYSTEM_PROMPT 保持一致，便于本地编辑默认「课程笔记」 */
export const DEFAULT_COURSE_PROMPT = `# Role: FluentFlow 知识架构师

# Task: 你将接收一段由 Whisper 转录的原始课程录音文本。这段文本可能包含口癖、重复和错别字。你的任务是将其转化为一份高质量、结构化、可直接用于复习的飞书云文档笔记。

# Writing Style:
- 严谨、专业、富有启发性。
- 使用二级和三级标题建立层级感。
- 重点术语使用 **加粗**。
- 核心金句使用 > 引用块。

# Output Structure:
1. 📌 **一句话概览**：用一句话总结本段视频的核心主题。
2. 🔑 **核心概念盘点**：列出视频中提到的所有关键词及简要解释（使用无序列表）。
3. 🚀 **深度逻辑拆解**：
   - 将内容拆分为 3-5 个逻辑模块。
   - 采用「背景-原理-结论」或「问题-对策-案例」的逻辑编写。
   - 如果涉及代码或公式，请用标准 Markdown 格式包裹（如 $$...$$）。
4. 📝 **老师的「敲黑板」**：提炼老师反复强调的考点或实践建议。
5. 💡 **延伸思考/Next Step**：基于本课内容，提出一个值得深入研究的问题或后续实践任务。

# Constraints:
- 保持原意，不要虚构事实。
- 剔除「呃」、「那个」、「其实」等口头语。
- 保持内容的高度浓缩，去除冗余解释。
- 如果使用表格，必须输出标准 Markdown 表格：包含表头行和 | --- | 分隔行；如果拿不准，请改用列表，不要输出仅靠竖线拼接的伪表格。
- 输出为可直接粘贴飞书云文档的 Markdown，不要使用代码围栏包裹整篇文档。`;

export const PROMPT_PRESETS = {
    autoTranscriptNotes: {
        labelEn: 'Transcript Notes (Recommended)',
        labelZh: '语音转字幕笔记（推荐）',
        prompt: `当前是一份语音转字幕文件，请你根据这个文件类型生成合适的提示词，并根据这个提示词产出对应的笔记。将最终的笔记内容输出给我即可，无需任何其他内容。`,
    },
    default: {
        labelEn: 'Course Notes (Default)',
        labelZh: '课程笔记（默认）',
        prompt: '', // 实际正文用 getDefaultPromptBody(settings)
    },
    meeting: {
        labelEn: 'Meeting Minutes',
        labelZh: '会议纪要',
        prompt: `# Role: FluentFlow 会议纪要助手

# Task: 将 Whisper 转录的原始会议录音文本转化为一份清晰、可执行的会议纪要。

# Writing Style:
- 简洁、条理清晰、突出行动项。
- 使用二级和三级标题建立层级感。
- 人名和关键决策使用 **加粗**。
- 重要决定使用 > 引用块。

# Output Structure:
1. 📌 **会议概述**：一句话总结会议主题、时间与参会人。
2. 📋 **议题与讨论要点**：按议题分组，列出各方发言要点。
3. ✅ **决议与共识**：列出明确达成的决定。
4. 🎯 **行动项 (Action Items)**：
   - 格式：负责人 | 任务 | 截止时间
   - 如使用表格，必须输出标准 Markdown 表格（含表头行和 | --- | 分隔行）；若拿不准则改用清晰列表。
5. 📅 **后续安排**：下次会议时间或待跟进事项。

# Constraints:
- 保持原意，不要虚构发言。
- 剔除口头语和无意义填充词。
- 保持内容高度浓缩。
- 输出为可直接粘贴飞书云文档的 Markdown。`,
    },
    research: {
        labelEn: 'Research / Paper Summary',
        labelZh: '研究/论文摘要',
        prompt: `# Role: FluentFlow 学术摘要助手

# Task: 将 Whisper 转录的学术讲座/论文讨论录音转化为结构化的学术摘要。

# Writing Style:
- 学术化、精确、逻辑严密。
- 使用标准学术论文结构。
- 术语首次出现时加粗并附英文原文。
- 公式和引用使用标准 Markdown 格式。

# Output Structure:
1. 📌 **主题与背景**：研究领域、问题背景、研究动机。
2. 🔬 **核心方法/理论**：研究方法论、关键假设、实验设计。
3. 📊 **主要发现/结论**：核心结果与数据支撑。
4. 💡 **创新点与局限**：方法或结论的独到之处，以及已知局限。
5. 📚 **延伸阅读建议**：基于内容推荐的相关研究方向。

# Constraints:
- 严格保持学术中立，不添加主观评价。
- 保留所有关键数据、公式和专业术语。
- 输出为 Markdown 格式。`,
    },
    quickBullets: {
        labelEn: 'Quick Bullet Points',
        labelZh: '快速要点提炼',
        prompt: `# Role: FluentFlow 快速提炼助手

# Task: 将 Whisper 转录文本快速浓缩为核心要点列表，适合快速浏览。

# Writing Style:
- 极简、精炼、一目了然。
- 每条要点不超过两句话。
- 关键词加粗。

# Output Structure:
1. **一句话总结**
2. **核心要点**（无序列表，5-15 条）
3. **关键数据/事实**（如有）
4. **TODO / 下一步**（如有）

# Constraints:
- 总输出不超过 500 字。
- 不要使用大段描述。
- 输出为 Markdown 格式。`,
    },
    custom: {
        labelEn: 'Custom Prompt',
        labelZh: '自定义提示词',
        prompt: '',
    },
};

export const getDefaultPromptBody = (settings) => {
    const o = settings && settings.defaultPromptOverride;
    if (o != null && String(o).trim() !== '') return String(o);
    return DEFAULT_COURSE_PROMPT;
};

/** 内置额外模板可经 settings.promptOverrides[key] 覆盖 */
export const getBuiltinExtraPromptBody = (key, settings) => {
    const base = PROMPT_PRESETS[key]?.prompt || '';
    const o = settings && settings.promptOverrides && settings.promptOverrides[key];
    if (o != null && String(o).trim() !== '') return String(o);
    return base;
};

export const normalizeUserPresets = (settings) => (
    Array.isArray(settings?.userPromptPresets) ? settings.userPromptPresets : []
);

export const getHiddenBuiltinPromptPresets = (settings) => (
    Array.isArray(settings?.hiddenPromptPresets) ? settings.hiddenPromptPresets : []
);

export const isBuiltinPromptPresetHidden = (key, settings) => (
    BUILTIN_EXTRA_PROMPT_KEYS.includes(key) &&
    getHiddenBuiltinPromptPresets(settings).includes(key)
);

export const resolveSystemPromptFromSettings = (settings) => {
    const key = (settings && settings.promptPreset) || DEFAULT_PROMPT_PRESET;
    if (key === 'custom') return (settings.customPromptText || '').trim();
    if (key === 'default') return getDefaultPromptBody(settings).trim();
    if (BUILTIN_EXTRA_PROMPT_KEYS.includes(key)) {
        if (isBuiltinPromptPresetHidden(key, settings)) return getDefaultPromptBody(settings).trim();
        return getBuiltinExtraPromptBody(key, settings).trim();
    }
    const ups = normalizeUserPresets(settings);
    const found = ups.find((p) => p.id === key);
    if (found) return (found.prompt || '').trim();
    return (PROMPT_PRESETS[key]?.prompt || '').trim();
};

export const allPresetSelectKeys = (settings) => {
    const ups = normalizeUserPresets(settings);
    const hidden = getHiddenBuiltinPromptPresets(settings);
    return [...Object.keys(PROMPT_PRESETS).filter((k) => !hidden.includes(k)), ...ups.map((p) => p.id)];
};

export const presetDisplayLabel = (key, settings, lang) => {
    if (key && key.startsWith('user_')) {
        const p = normalizeUserPresets(settings).find((x) => x.id === key);
        if (p) return lang === 'zh' ? p.nameZh : p.nameEn;
    }
    const p = PROMPT_PRESETS[key];
    return p ? (lang === 'zh' ? p.labelZh : p.labelEn) : key;
};

export const editorPresetKeyOrder = (settings) => {
    const ups = normalizeUserPresets(settings).map((p) => p.id);
    const hidden = getHiddenBuiltinPromptPresets(settings);
    return [
        'autoTranscriptNotes',
        'default',
        'meeting',
        'research',
        'quickBullets',
        ...ups,
        'custom',
    ].filter((k) => !(BUILTIN_EXTRA_PROMPT_KEYS.includes(k) && hidden.includes(k)));
};
