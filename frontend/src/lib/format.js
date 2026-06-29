export const fileNameStem = (name) => (name || "").replace(/\.[^/.]+$/, "") || "";
export const stripGeneratedFilenamePrefix = (name) => String(name || '').replace(/^(?:[0-9]{10,24}|BV[a-zA-Z0-9]{8,})[-_]+/, '');
export const displayTitleForUser = (value, fallback='') => {
    const clean = stripGeneratedFilenamePrefix(fileNameStem(value)).trim();
    if (clean) return clean;
    return stripGeneratedFilenamePrefix(fileNameStem(fallback)).trim();
};
export const videoLinkDisplayTitle = (value, lang='zh') => {
    const raw = String(value || '').trim();
    const match = raw.match(/https?:\/\/[^\s，。！？、'"“”‘’）)\]】]+/i);
    if (!match) return displayTitleForUser(raw, raw) || (lang === 'zh' ? '视频链接' : 'Video link');
    const url = match[0].replace(/[)）\]】"'“”‘’。，,]+$/g, '');
    try {
        const parsed = new URL(url);
        const host = parsed.hostname.replace(/^www\./, '').toLowerCase();
        const parts = parsed.pathname.split('/').filter(Boolean);
        const bv = parts.find((part) => /^BV[a-zA-Z0-9]+$/.test(part));
        if (host.includes('bilibili.com') || host === 'b23.tv') {
            return bv
                ? (lang === 'zh' ? `Bilibili 视频 ${bv}` : `Bilibili video ${bv}`)
                : (lang === 'zh' ? 'Bilibili 视频' : 'Bilibili video');
        }
        if (host.includes('douyin.com')) return lang === 'zh' ? '抖音视频链接' : 'Douyin video link';
        if (host.includes('youtube.com') || host.includes('youtu.be')) return lang === 'zh' ? 'YouTube 视频' : 'YouTube video';
        if (host) return lang === 'zh' ? `${host} 视频链接` : `${host} video link`;
    } catch(_) {}
    return lang === 'zh' ? '视频链接' : 'Video link';
};
export const compactDisplayFilename = (name, maxChars=42) => {
    const value = displayTitleForUser(name, name) || String(name || '').trim();
    const chars = Array.from(value);
    if (chars.length <= maxChars) return value;
    const extMatch = value.match(/(\.[^./\s]{1,8})$/);
    const ext = extMatch ? extMatch[1] : '';
    const extLength = Array.from(ext).length;
    const keep = Math.max(16, maxChars - extLength - 1);
    return `${chars.slice(0, keep).join('')}…${ext}`;
};

export const fmtTime = (sec) => { const m=Math.floor(sec/60); const s=Math.floor(sec%60); return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; };
export const autoSizeTextarea = (node) => {
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${node.scrollHeight}px`;
};
export const composeTranscriptText = (segments, fallback='') => (
    Array.isArray(segments) && segments.length > 0
        ? segments.map((seg) => (seg?.text || '').trim()).filter(Boolean).join('\n')
        : (fallback || '')
);
export const normalizeTranscriptSegments = (value) => (
    Array.isArray(value)
        ? value
            .filter((seg) => seg && typeof seg === 'object' && String(seg.text || '').trim())
            .map((seg) => ({...seg, text: String(seg.text || '')}))
        : []
);
export const normalizeDisplaySegments = (value) => (
    Array.isArray(value)
        ? value
            .filter((seg) => seg && typeof seg === 'object' && (String(seg.text || '').trim() || String(seg.text_zh || seg.zh || '').trim()))
            .map((seg) => ({
                ...seg,
                text: String(seg.text || seg.text_en || ''),
                ...(String(seg.text_zh || seg.zh || '').trim() ? {text_zh: String(seg.text_zh || seg.zh || '')} : {}),
            }))
        : []
);
export const pickTranscriptSegments = (source={}) => {
    for (const key of ['raw_segments', 'segments', 'cleaned_segments']) {
        const segments = normalizeTranscriptSegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    return [];
};
export const pickTranscriptBaselineSegments = (source={}) => {
    for (const key of ['raw_segments', 'segments', 'cleaned_segments']) {
        const segments = normalizeTranscriptSegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    return [];
};
export const pickDisplayTranscriptSegments = (source={}, rawSegments=[]) => {
    for (const key of ['display_segments', 'bilingual_segments']) {
        const segments = normalizeDisplaySegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    const translated = normalizeDisplaySegments(source?.translated_segments_zh);
    const raw = Array.isArray(rawSegments) && rawSegments.length > 0 ? rawSegments : pickTranscriptSegments(source);
    if (raw.length > 0 && translated.length > 0) {
        return raw.map((segment, index) => {
            const textZh = String(translated[index]?.text_zh || translated[index]?.text || '').trim();
            return textZh ? {...segment, text_zh: textZh} : {...segment};
        }).filter((segment) => String(segment.text || '').trim() || String(segment.text_zh || '').trim());
    }
    return normalizeDisplaySegments(raw);
};
export const buildTranscriptEditRecords = (beforeSegments=[], afterSegments=[], source={}) => {
    if (!Array.isArray(beforeSegments) || !Array.isArray(afterSegments) || beforeSegments.length === 0) return source?.transcript_edit_records || [];
    const now = new Date().toISOString();
    const limit = Math.max(beforeSegments.length, afterSegments.length);
    const records = [];
    for (let i = 0; i < limit; i += 1) {
        const before = beforeSegments[i] || {};
        const after = afterSegments[i] || {};
        const beforeText = String(before.text || '').trim();
        const afterText = String(after.text || '').trim();
        if (!beforeText && !afterText) continue;
        if (beforeText === afterText) continue;
        records.push({
            index: i,
            start: Number(before.start ?? after.start ?? 0) || 0,
            end: Number(before.end ?? after.end ?? before.start ?? after.start ?? 0) || 0,
            before: beforeText,
            after: afterText,
            previous_before: String(beforeSegments[i - 1]?.text || '').trim(),
            next_before: String(beforeSegments[i + 1]?.text || '').trim(),
            previous_after: String(afterSegments[i - 1]?.text || '').trim(),
            next_after: String(afterSegments[i + 1]?.text || '').trim(),
            created_at: now,
        });
    }
    return records;
};
export const fmtElapsed = (sec) => {
    const n = Math.max(0, Number(sec) || 0);
    const h = Math.floor(n / 3600);
    const m = Math.floor((n % 3600) / 60);
    const s = Math.floor(n % 60);
    return h > 0
        ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`
        : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
};
export const fmtDurationCompact = (sec) => {
    const n = Math.max(0, Number(sec) || 0);
    const h = Math.floor(n / 3600);
    const m = Math.floor((n % 3600) / 60);
    const s = Math.floor(n % 60);
    if (h > 0) return `${h}h ${m}m ${s}s`;
    return `${m}m ${s}s`;
};
export const fmtFileSize = (mb) => {
    const n = Number(mb);
    if(!Number.isFinite(n) || n <= 0) return '-';
    if(n >= 1024) return `${(n/1024).toFixed(n >= 10240 ? 0 : 1)} GB`;
    return `${n.toFixed(n >= 10 ? 1 : 2)} MB`;
};
export const totalFileSizeMb = (files=[]) => (
    Math.round(Array.from(files || []).reduce((sum, file) => sum + (Number(file?.size) || 0), 0) / 1024 / 1024 * 1000) / 1000
);
export const fmtBytes = (bytes) => {
    const n = Number(bytes);
    if(!Number.isFinite(n) || n <= 0) return '';
    return fmtFileSize(n / 1024 / 1024);
};
export const fmtDateTime = (value, lang='zh') => {
    const ts = Date.parse(value || '');
    if(!Number.isFinite(ts)) return '-';
    try {
        return new Date(ts).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
        });
    } catch(_) {
        return '-';
    }
};
export const friendlyTaskError = (message, lang='zh') => {
    const raw = String(message || '').trim();
    if(!raw) return lang === 'zh' ? '处理失败，但没有返回具体原因。请重试一次。' : 'The task failed without a specific reason. Try again.';
    const lower = raw.toLowerCase();
    if(lower.includes('only "standard" subscriptions') || lower.includes('only \\"standard\\" subscriptions') || lower.includes('invalidsubscription')) return lang === 'zh' ? '云端转录提交失败：当前区域的 Speech 资源不是 Batch 支持的 Standard 订阅。请检查 Azure Speech 区域和定价层。' : 'Cloud transcription failed: the Speech resource is not a Standard subscription supported for Batch in this region.';
    if(lower.includes('invalidlocale') || lower.includes('specified locale is not supported')) return lang === 'zh' ? '云端转录提交失败：当前音频语言不被 Azure 支持。请切换为中文/英文，或改用本地转录。' : 'Cloud transcription failed: this locale is not supported by Azure.';
    if(lower.includes('invalidmodel') || lower.includes('specified model is not supported')) return lang === 'zh' ? '云端转录提交失败：当前 Azure 资源不支持所选模型。请切换云端默认模型或改用本地转录。' : 'Cloud transcription failed: the selected model is not supported by this Azure resource.';
    if(lower.includes('diarization is currently not supported')) return lang === 'zh' ? '云端转录提交失败：当前 Azure 路线不支持说话人区分。请关闭说话人区分后重试。' : 'Cloud transcription failed: diarization is not supported by this route.';
    if(lower.includes('eof occurred in violation of protocol') || lower.includes('broken pipe')) return lang === 'zh' ? '云端上传中断：通常是网络或云端转录服务断开连接。请重试；如果文件很大，先压缩或拆分音频。' : 'Cloud upload was interrupted. Retry, or reduce/split the audio for very large files.';
    if(lower.includes('queued processing request failed')) return lang === 'zh' ? '后台任务调用转录接口失败。请重试；如果连续出现，请重启后端服务。' : 'The background task could not call the transcription endpoint. Retry or restart the backend.';
    if(lower.includes('http error 403') || raw.includes('视频下载失败：403') || lower.includes('forbidden')) return lang === 'zh' ? '平台拒绝下载当前视频。已尽量优先使用字幕；如果仍失败，请稍后重试、配置浏览器 cookies，或上传本地视频。' : 'The platform refused this video download. FluentFlow will prefer captions when possible; retry later, configure browser cookies, or upload the local video.';
    if(lower.includes('http error 429') || lower.includes('too many requests')) return lang === 'zh' ? '平台请求过于频繁，暂时限制了视频或字幕获取。请稍后重试，或上传本地视频/字幕文件。' : 'The platform is temporarily rate-limiting video or subtitle access. Retry later, or upload the local video/subtitle file.';
    if(raw.includes('视频下载超时') || lower.includes('timed out') || lower.includes('timeout')) return lang === 'zh' ? '视频下载时间过长，可能是视频较大或当前网络较慢。笔记会优先尝试使用字幕；如仍失败，请稍后重试或上传本地视频。' : 'The video download took too long, likely due to a large video or slow network. FluentFlow will prefer captions when possible; retry later or upload the local video.';
    if(lower.includes('no position encodings are defined')) return lang === 'zh' ? '本地说话人区分模型无法处理当前音频长度。请关闭说话人区分，或切换云端转录。' : 'Local diarization cannot handle this audio length. Disable diarization or use cloud transcription.';
    if(lower.includes('downloaded video is too large') || lower.includes('file is too large')) return lang === 'zh' ? '文件超过当前上传限制。请压缩视频、拆分文件，或调高后端上传大小限制。' : 'The file exceeds the current upload limit.';
    return raw;
};

export const noteGenerationDiagnosis = (result={}, lang='zh') => {
    const summary = String(result?.summary_markdown || '').trim();
    const status = String(result?.summary_status || '').trim().toLowerCase();
    const stage = String(result?.stage || '').trim().toLowerCase();
    const rawError = String(result?.summary_error || result?.error_reason || '').trim();
    const errorText = rawError.toLowerCase();
    const hasTranscript = !!String(result?.transcript_text || result?.transcript_text_preview || '').trim()
        || (Array.isArray(result?.raw_segments) && result.raw_segments.length > 0)
        || (Array.isArray(result?.display_segments) && result.display_segments.length > 0);
    const zh = lang === 'zh';
    const base = {
        status: 'pending',
        code: 'note_pending',
        severity: 'info',
        title: zh ? '笔记还在生成' : 'Note is still generating',
        detail: zh ? '转录已进入摘要阶段，等待 AI 返回笔记。' : 'The transcript has entered the summary stage and is waiting for the AI note.',
        nextAction: zh ? '稍等片刻；如果长时间没有变化，再刷新任务状态。' : 'Wait a moment; refresh the task status if it does not change.',
        canRegenerate: false,
    };

    if(summary) {
        return {
            ...base,
            status: 'completed',
            code: 'note_completed',
            severity: 'success',
            title: zh ? '笔记已生成' : 'Note generated',
            detail: zh ? '当前结果包含可用的 AI 笔记。' : 'This result contains an AI-generated note.',
            nextAction: '',
            canRegenerate: true,
        };
    }
    if(!hasTranscript) {
        return {
            ...base,
            status: 'unavailable',
            code: 'transcript_missing',
            severity: 'warning',
            title: zh ? '还没有可用于生成笔记的转录' : 'No transcript available for note generation',
            detail: zh ? '需要先完成转录，AI 才能生成笔记。' : 'Transcription must finish before the AI can generate a note.',
            nextAction: zh ? '先等待或重新提交转录任务。' : 'Wait for transcription or submit the task again.',
        };
    }
    if(result?.summary_skipped || status === 'skipped') {
        return {
            ...base,
            status: 'skipped',
            code: 'transcript_only_mode',
            severity: 'neutral',
            title: zh ? '本次开启了仅转录模式' : 'Transcript-only mode was used',
            detail: zh ? '系统按设置跳过了 AI 笔记，转录和字幕已保留。' : 'The system skipped AI note generation by setting; transcript and subtitles are preserved.',
            nextAction: zh ? '需要笔记时，打开结果并点击“重生笔记”。' : 'Open the result and click Regenerate note when you need a note.',
            canRegenerate: true,
        };
    }
    if(status === 'failed' || rawError) {
        let code = 'ai_note_failed';
        let title = zh ? 'AI 笔记生成失败' : 'AI note generation failed';
        let nextAction = zh ? '打开结果后点击“重生笔记”；如果仍失败，换一个笔记模式或缩短材料。' : 'Open the result and click Regenerate note; if it still fails, change the note mode or shorten the material.';
        if(errorText.includes('quota') || errorText.includes('balance') || errorText.includes('额度') || errorText.includes('余额')) {
            code = 'quota_insufficient';
            title = zh ? '额度不足，笔记未生成' : 'Insufficient balance for note generation';
            nextAction = zh ? '补足额度后重生笔记，或降低本次处理成本。' : 'Add balance, then regenerate the note, or lower the processing cost.';
        } else if(errorText.includes('401') || errorText.includes('login') || errorText.includes('auth') || errorText.includes('account')) {
            code = 'auth_required';
            title = zh ? '账号状态阻止了笔记生成' : 'Account state blocked note generation';
            nextAction = zh ? '重新登录后打开结果，再点击“重生笔记”。' : 'Sign in again, reopen the result, then click Regenerate note.';
        } else if(errorText.includes('404') || errorText.includes('job not found') || errorText.includes('not found')) {
            code = 'job_scope_mismatch';
            title = zh ? '任务归属不一致，笔记未生成' : 'Task scope mismatch blocked note generation';
            nextAction = zh ? '刷新任务列表后从同一条记录打开结果；如果仍失败，重新提交任务。' : 'Refresh the task list and open the same record; submit it again if it still fails.';
        } else if(errorText.includes('empty result') || errorText.includes('empty')) {
            code = 'empty_ai_note';
            title = zh ? 'AI 返回了空笔记' : 'AI returned an empty note';
            nextAction = zh ? '点击“重生笔记”；如果重复出现，换用直接生成模式或调整提示词。' : 'Click Regenerate note; if it repeats, use direct mode or adjust the prompt.';
        } else if(errorText.includes('unsupported note generation mode') || errorText.includes('chapter_coverage')) {
            code = 'unsupported_note_mode';
            title = zh ? '笔记模式不受当前版本支持' : 'Note mode is not supported by this version';
            nextAction = zh ? '到设置页选择“自动”或“高保真”，再重新提交任务。' : 'Choose Auto or High fidelity in Settings, then submit again.';
        }
        return {
            ...base,
            status: 'failed',
            code,
            severity: 'error',
            title,
            detail: friendlyTaskError(rawError, lang),
            nextAction,
            canRegenerate: true,
        };
    }
    if(status === 'pending' || stage === 'summary') return base;
    return {
        ...base,
        code: 'note_missing_unknown',
        severity: 'warning',
        title: zh ? '暂时没有可见笔记' : 'No visible note yet',
        detail: zh ? '转录已存在，但结果里没有记录明确的笔记状态。' : 'A transcript exists, but the result does not record a clear note status.',
        nextAction: zh ? '打开结果点击“重生笔记”；如果失败，再查看任务详情。' : 'Open the result and click Regenerate note; check task details if it fails.',
        canRegenerate: true,
    };
};

export const sttStatusLabel = (status, t) => {
    const key = {
        starting: 'dash.sttStarting',
        loading_model: 'dash.sttLoadingModel',
        chunking_audio: 'dash.sttChunking',
        preparing_audio: 'dash.sttPreparingAudio',
        waiting_first_segment: 'dash.sttWaitingFirst',
        transcribing_chunks: 'dash.sttChunks',
        transcribing_segments: 'dash.sttSegments',
        azure_transcribing: 'dash.sttAzure',
        azure_batch_uploading: 'dash.sttAzureUpload',
        azure_batch_submitting: 'dash.sttAzureSubmit',
        azure_batch_waiting: 'dash.sttAzureWait',
        azure_batch_downloading: 'dash.sttAzureDownload',
        elevenlabs_uploading: 'dash.sttAzureUpload',
        elevenlabs_processing: 'dash.sttAzureWait',
        elevenlabs_normalizing: 'dash.sttAzureDownload',
    }[status || ''];
    return key ? t(key) : t('dash.waitingSegment');
};
export const sttProgressFraction = (job) => Math.max(0, Math.min(1, Number(job?.sttProgress) || 0));
export const isSttProgressUnmeasured = (job) => (
    job?.stage === 'stt'
    && sttProgressFraction(job) <= 0
    && job?.sttStatus !== 'transcribing_segments'
);
export const jobProgressLabel = (job, t) => isSttProgressUnmeasured(job)
    ? t('dash.progressUnknown')
    : `${Math.round(Math.max(0, Math.min(100, Number(job?.progress) || 0)))}%`;

export const fmtSttRelative = (factor, lang) => {
    const n = Number(factor);
    if(!Number.isFinite(n) || n <= 0) return '';
    if(n * 100 < 1) return lang === 'zh' ? '低于原时长 1%' : '<1% of media duration';
    const pct = Math.round(n * 100);
    return lang === 'zh' ? `约为原时长 ${pct}%` : `${pct}% of media duration`;
};

export const timeAgo = (ts, t) => {
    const d = Date.now()-ts, m=Math.floor(d/60000), h=Math.floor(d/3600000), dy=Math.floor(d/86400000);
    if(m<1) return t('dash.justNow');
    if(m<60) return `${m} ${t('dash.mAgo')}`;
    if(h<24) return `${h} ${t('dash.hAgo')}`;
    return `${dy} ${t('dash.dAgo')}`;
};
