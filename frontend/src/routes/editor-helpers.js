// Pure helper functions extracted from editor.jsx (formatting, URL/file
// normalization, visual key-moment parsing). No React/JSX dependency.
import {normalizeSttProvider, noteGenerationDiagnosis} from '../app/shared.jsx';


export const jobOptionsForResult = (result) => (
    normalizeSttProvider(result?.stt_provider) === 'local'
    || result?.playback_audio_storage === 'local'
    || result?.source_file_storage === 'local'
        ? {sttProvider: 'local'}
        : {}
);

export const isLikelyVideoFile = (fileOrName) => {
    if (!fileOrName) return false;
    if (typeof fileOrName === 'object' && fileOrName.type) return String(fileOrName.type).startsWith('video/');
    const name = typeof fileOrName === 'string' ? fileOrName : fileOrName.name || '';
    return /\.(mp4|mov|avi|mkv|webm|m4v)$/i.test(name);
};

export const isVideoResultSource = (result, sourceFile) => {
    if (!result) return false;
    if (isLikelyVideoFile(sourceFile || result.filename || result.display_title)) return true;
    const source = String(result.source || result.source_type || '').trim().toLowerCase();
    return ['video', 'video_link', 'youtube', 'douyin'].includes(source);
};

export const localSourceFileMatchesResult = (file, result) => {
    if (!file || !result) return false;
    const fingerprint = result.source_fingerprint || {};
    const expectedName = String(fingerprint.source_filename || result.filename || '').trim();
    const expectedSize = Number(fingerprint.source_size_bytes || 0);
    const nameMatches = expectedName && file.name === expectedName;
    const sizeMatches = expectedSize > 0 && file.size === expectedSize;
    if (nameMatches && sizeMatches) return true;
    if (sizeMatches && !expectedName) return true;
    return false;
};

export const summaryFailureNextStep = (result, lang) => {
    if (!(result?.summary_status === 'failed' || result?.summary_error)) return '';
    const diagnosis = noteGenerationDiagnosis(result, lang);
    const next = diagnosis.nextAction ? ` ${lang === 'zh' ? '下一步：' : 'Next: '}${diagnosis.nextAction}` : '';
    return lang === 'zh'
        ? `${diagnosis.title}：${diagnosis.detail}${next}`
        : `${diagnosis.title}: ${diagnosis.detail}${next}`;
};

export const formatElapsedMinuteSecond = (seconds) => {
    const n = Math.max(0, Math.floor(Number(seconds) || 0));
    const m = Math.floor(n / 60);
    const s = n % 60;
    return `${String(m).padStart(2, '0')}m${String(s).padStart(2, '0')}s`;
};

export const formatSttOriginalRatio = (factor, lang) => {
    const n = Number(factor);
    if (!Number.isFinite(n) || n <= 0) return '';
    const pct = Math.max(1, Math.round(n * 100));
    return lang === 'zh' ? `原 ${pct}%` : `${pct}% of original`;
};

export const firstText = (...values) => {
    for (const value of values) {
        const text = String(value || '').trim();
        if (text) return text;
    }
    return '';
};

export const firstNumber = (...values) => {
    for (const value of values) {
        const n = Number(value);
        if (Number.isFinite(n) && n >= 0) return n;
    }
    return null;
};

export const isSafeVisualArtifactUrl = (url) => {
    const text = String(url || '').trim();
    if (!text) return false;
    if (/^(https?:|data:image\/|blob:)/i.test(text)) return true;
    if (text.startsWith('/jobs/') || text.startsWith('/guest-trial/jobs/')) return true;
    return false;
};

export const normalizeVisualArtifactUrl = (url) => {
    const text = String(url || '').trim();
    if (!text) return '';
    if (/^(https?:|data:image\/|blob:|\/)/i.test(text)) return text;
    if (text.startsWith('jobs/') || text.startsWith('guest-trial/jobs/')) return `/${text}`;
    return '';
};

export const visualArtifactUrlFromMoment = (moment, result) => {
    const direct = firstText(
        moment?.artifact_url,
        moment?.artifactUrl,
        moment?.url,
        moment?.image_url,
        moment?.imageUrl,
        moment?.frame_url,
        moment?.thumbnail_url,
        moment?.src,
    );
    if (isSafeVisualArtifactUrl(direct)) return normalizeVisualArtifactUrl(direct);

    const artifactKey = firstText(moment?.artifact_kind, moment?.artifactKind, moment?.artifact_id, moment?.artifactId);
    const visualArtifact = artifactKey ? result?.visual_artifacts?.[artifactKey] : null;
    const visualArtifactUrl = firstText(visualArtifact?.artifact_url, visualArtifact?.url);
    if (isSafeVisualArtifactUrl(visualArtifactUrl)) return normalizeVisualArtifactUrl(visualArtifactUrl);

    const filename = firstText(moment?.filename);
    if (result?.task_id && filename && !filename.includes('..') && !filename.startsWith('/')) {
        const frameName = filename.split(/[\\/]/).filter(Boolean).pop() || filename;
        return `/jobs/${encodeURIComponent(result.task_id)}/artifacts/frame?file=${encodeURIComponent(frameName)}`;
    }

    return '';
};

export const normalizeVisualKeyMoments = (result) => {
    const direct = Array.isArray(result?.visual_key_moments) ? result.visual_key_moments : [];
    const packaged = Array.isArray(result?.visual?.key_moments) ? result.visual.key_moments : [];
    const source = direct.length ? direct : packaged;
    return source
        .map((moment, index) => {
            const confidence = String(moment?.confidence || '').trim().toLowerCase();
            if (confidence === 'low') return null;
            const timestamp = firstNumber(
                moment?.timestamp_seconds,
                moment?.timestampSeconds,
                moment?.start_seconds,
                moment?.start,
                moment?.time,
            );
            const imageUrl = visualArtifactUrlFromMoment(moment, result);
            const caption = firstText(moment?.caption, moment?.title, moment?.note_section);
            const reason = firstText(moment?.reason, moment?.description);
            if (!imageUrl && !caption && !reason) return null;
            return {
                id: firstText(moment?.id, moment?.request_id, moment?.filename) || `visual-key-moment-${index + 1}`,
                timestamp,
                imageUrl,
                caption,
                reason,
                noteSection: firstText(moment?.note_section),
                confidence,
            };
        })
        .filter(Boolean);
};

export const downloadBrowserFile = (file, fallbackName = 'download') => {
    const url = URL.createObjectURL(file);
    const a = document.createElement('a');
    a.href = url;
    a.download = file?.name || fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
};
