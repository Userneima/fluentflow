const cancelledError = () => Object.assign(new Error('Upload cancelled.'), {aborted: true, name: 'AbortError'});

const checkedJson = async (fetcher, url, init) => {
    if (init?.signal?.aborted) throw cancelledError();
    const response = await fetcher(url, init);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw Object.assign(new Error(payload?.detail || `HTTP ${response.status}`), {status: response.status, payload});
    }
    return payload;
};

const abortSession = async ({fetcher, apiBase, sessionId}) => {
    try {
        await fetcher(`${apiBase}/oss-upload-sessions/${encodeURIComponent(sessionId)}/abort`, {method: 'POST'});
    } catch (_) {
        // The server also expires incomplete sessions; cleanup must not hide the
        // original transfer error from the user.
    }
};

export const uploadSignedOssPart = ({signature, data, onProgress, signal, stallMs=120000, createXhr=() => new XMLHttpRequest()}) => (
    new Promise((resolve, reject) => {
        if (signal?.aborted) {
            reject(cancelledError());
            return;
        }
        const xhr = createXhr();
        let settled = false;
        let lastTick = Date.now();
        const cleanup = () => {
            clearInterval(watchdog);
            signal?.removeEventListener('abort', onAbort);
        };
        const finish = (callback) => {
            if (settled) return;
            settled = true;
            cleanup();
            callback();
        };
        const onAbort = () => {
            try { xhr.abort(); } catch (_) {}
        };
        const watchdog = setInterval(() => {
            if (Date.now() - lastTick <= stallMs) return;
            finish(() => reject(new Error('Upload stalled or timed out. Please try again.')));
            try { xhr.abort(); } catch (_) {}
        }, 5000);

        xhr.open(signature.method || 'PUT', signature.url);
        xhr.withCredentials = false;
        Object.entries(signature.headers || {}).forEach(([key, value]) => xhr.setRequestHeader(key, value));
        xhr.upload.onprogress = (event) => {
            lastTick = Date.now();
            if (event.lengthComputable) onProgress?.(event.loaded);
        };
        xhr.onload = () => {
            if (xhr.status < 200 || xhr.status >= 300) {
                finish(() => reject(Object.assign(new Error(`OSS upload failed: HTTP ${xhr.status}`), {status: xhr.status})));
                return;
            }
            const etag = xhr.getResponseHeader('ETag');
            if (!etag) {
                finish(() => reject(new Error('OSS upload did not return an ETag. Check the bucket CORS expose-header rule.')));
                return;
            }
            finish(() => resolve(etag));
        };
        xhr.onerror = () => finish(() => reject(new Error('Upload failed. Please check the connection and try again.')));
        xhr.onabort = () => finish(() => reject(cancelledError()));
        signal?.addEventListener('abort', onAbort, {once: true});
        xhr.send(data);
    })
);

export const queueOptionsForOssUpload = (options={}, normalizeLarkRoute, isLocalLarkRoute) => {
    const entries = [];
    if (options.exportToLark) {
        const route = normalizeLarkRoute(options.larkExportRoute, !!options.larkViaCli);
        entries.push(['export_to_lark', 'true'], ['lark_export_route', route], ['lark_via_cli', isLocalLarkRoute(route) ? 'true' : 'false']);
    }
    const mapping = [
        ['title', options.title],
        ['folder_token', options.folderToken],
        ['ai_provider', options.aiProvider],
        ['ai_model', options.aiModel],
        ['system_prompt', options.systemPrompt],
        ['note_mode', options.noteMode],
        ['prompt_preset', options.promptPreset],
        ['prompt_preset_label', options.promptPresetLabel],
        ['stt_provider', options.sttProvider],
        ['stt_model', options.sttModel],
        ['stt_speed', options.sttSpeed],
        ['stt_language', options.sttLanguage],
        ['cookies_from_browser', options.cookiesFromBrowser],
    ];
    mapping.forEach(([key, value]) => {
        if (value) entries.push([key, String(value)]);
    });
    if (options.skipSummary) entries.push(['skip_summary', 'true']);
    if (options.generateVisuals) entries.push(['generate_visuals', 'true']);
    if (options.speakerDiarization) entries.push(['speaker_diarization', 'true']);
    return Object.fromEntries(entries);
};

export const uploadFilesToOssAndQueue = async ({
    files,
    options,
    apiBase='',
    fetcher,
    onProgress,
    signal,
    stallMs=120000,
    uploadPart=uploadSignedOssPart,
}) => {
    const queue = [];
    const sourceFiles = Array.from(files || []);
    const totalBytes = sourceFiles.reduce((total, file) => total + Number(file?.size || 0), 0);
    let uploadedBytes = 0;
    const reportProgress = (partBytes=0) => {
        if (totalBytes > 0) onProgress?.(Math.min(100, Math.round(((uploadedBytes + partBytes) / totalBytes) * 100)));
    };

    for (const file of sourceFiles) {
        if (signal?.aborted) throw cancelledError();
        let session = null;
        try {
            const created = await checkedJson(fetcher, `${apiBase}/oss-upload-sessions`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({filename: file.name, content_length: file.size, content_type: file.type || null}),
                signal,
            });
            session = created.session;
            const partSize = Number(session?.part_size_bytes || 0);
            const expectedParts = Number(session?.expected_parts || 0);
            if (!session?.session_id || partSize <= 0 || expectedParts <= 0) throw new Error('OSS upload session response is invalid.');

            const completedParts = [];
            for (let start = 1; start <= expectedParts; start += 32) {
                const partNumbers = Array.from({length: Math.min(32, expectedParts - start + 1)}, (_, index) => start + index);
                const signed = await checkedJson(fetcher, `${apiBase}/oss-upload-sessions/${encodeURIComponent(session.session_id)}/parts`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({part_numbers: partNumbers}),
                    signal,
                });
                for (const part of signed.parts || []) {
                    if (signal?.aborted) throw cancelledError();
                    const partNumber = Number(part.part_number);
                    const offset = (partNumber - 1) * partSize;
                    const data = file.slice(offset, Math.min(offset + partSize, file.size));
                    const etag = await uploadPart({
                        signature: part,
                        data,
                        signal,
                        stallMs,
                        onProgress: reportProgress,
                    });
                    uploadedBytes += data.size;
                    reportProgress();
                    completedParts.push({part_number: partNumber, etag});
                }
            }
            const completed = await checkedJson(fetcher, `${apiBase}/oss-upload-sessions/${encodeURIComponent(session.session_id)}/complete`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({parts: completedParts, options}),
                signal,
            });
            const taskId = completed.session?.task_id;
            if (!taskId) throw new Error('OSS upload completed without a processing task.');
            queue.push({
                task_id: taskId,
                filename: file.name,
                source_file_size_mb: Math.round((file.size / 1024 / 1024) * 1000) / 1000,
                status: 'queued',
                queue_position: queue.length + 1,
                queue_total: sourceFiles.length,
            });
        } catch (error) {
            if (session?.session_id) await abortSession({fetcher, apiBase, sessionId: session.session_id});
            if (queue.length) error.queued = queue;
            throw error;
        }
    }
    return {ok: true, queued: queue, count: queue.length};
};
