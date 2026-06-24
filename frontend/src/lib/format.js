export const fileNameStem = (name) => (name || "").replace(/\.[^/.]+$/, "") || "";
export const stripGeneratedFilenamePrefix = (name) => String(name || '').replace(/^[0-9]{10,24}[-_]+/, '');
export const displayTitleForUser = (value, fallback='') => {
    const clean = stripGeneratedFilenamePrefix(fileNameStem(value)).trim();
    if (clean) return clean;
    return stripGeneratedFilenamePrefix(fileNameStem(fallback)).trim();
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
export const pickTranscriptSegments = (source={}) => {
    for (const key of ['segments', 'cleaned_segments', 'raw_segments']) {
        const segments = normalizeTranscriptSegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    return [];
};
export const pickTranscriptBaselineSegments = (source={}) => {
    for (const key of ['cleaned_segments', 'raw_segments', 'segments']) {
        const segments = normalizeTranscriptSegments(source?.[key]);
        if (segments.length > 0) return segments;
    }
    return [];
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
    if(lower.includes('eof occurred in violation of protocol') || lower.includes('broken pipe')) return lang === 'zh' ? '云端上传中断：通常是网络或 Azure 边缘服务断开连接。请重试；如果文件很大，优先使用 Azure Batch 或减小音频体积。' : 'Cloud upload was interrupted. Retry, or reduce the audio size for very large files.';
    if(lower.includes('queued processing request failed')) return lang === 'zh' ? '后台任务调用转录接口失败。请重试；如果连续出现，请重启后端服务。' : 'The background task could not call the transcription endpoint. Retry or restart the backend.';
    if(lower.includes('no position encodings are defined')) return lang === 'zh' ? '本地说话人区分模型无法处理当前音频长度。请关闭说话人区分，或切换云端转录。' : 'Local diarization cannot handle this audio length. Disable diarization or use cloud transcription.';
    if(lower.includes('downloaded video is too large') || lower.includes('file is too large')) return lang === 'zh' ? '文件超过当前上传限制。请压缩视频、拆分文件，或调高后端上传大小限制。' : 'The file exceeds the current upload limit.';
    return raw;
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
