import { describe, expect, it, vi } from 'vitest';

import { queueOptionsForOssUpload, uploadFilesToOssAndQueue } from './ossDirectUpload.js';

const jsonResponse = (payload, status=200) => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
});

const sourceFile = (name='lesson.mp4', size=8) => ({
    name,
    size,
    type: 'video/mp4',
    slice: (start, end) => ({size: end - start, start, end}),
});

describe('OSS direct upload client', () => {
    it('uploads signed parts, reports aggregate progress, and creates a normal queue item', async () => {
        const fetcher = vi.fn(async (url, init={}) => {
            if (url.endsWith('/oss-upload-sessions')) {
                expect(JSON.parse(init.body)).toMatchObject({filename: 'lesson.mp4', content_length: 8});
                return jsonResponse({session: {session_id: 'session-1', part_size_bytes: 4, expected_parts: 2}});
            }
            if (url.endsWith('/parts')) {
                return jsonResponse({parts: [
                    {part_number: 1, method: 'PUT', url: 'https://oss.example/1', headers: {}},
                    {part_number: 2, method: 'PUT', url: 'https://oss.example/2', headers: {}},
                ]});
            }
            if (url.endsWith('/complete')) {
                expect(JSON.parse(init.body)).toEqual({
                    parts: [{part_number: 1, etag: 'etag-1'}, {part_number: 2, etag: 'etag-2'}],
                    options: {stt_provider: 'elevenlabs_scribe'},
                });
                return jsonResponse({session: {task_id: 'task-1'}});
            }
            throw new Error(`Unexpected request: ${url}`);
        });
        const progress = [];
        const uploadPart = vi.fn(async ({data, onProgress}) => {
            onProgress(data.size);
            return `etag-${data.start / 4 + 1}`;
        });

        const result = await uploadFilesToOssAndQueue({
            files: [sourceFile()],
            options: {stt_provider: 'elevenlabs_scribe'},
            apiBase: '/api',
            fetcher,
            uploadPart,
            onProgress: (value) => progress.push(value),
        });

        expect(result.queued).toEqual([expect.objectContaining({task_id: 'task-1', filename: 'lesson.mp4', queue_total: 1})]);
        expect(uploadPart).toHaveBeenCalledTimes(2);
        expect(progress.at(-1)).toBe(100);
        expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
            '/api/oss-upload-sessions',
            '/api/oss-upload-sessions/session-1/parts',
            '/api/oss-upload-sessions/session-1/complete',
        ]);
    });

    it('aborts an unfinished session when a signed part fails', async () => {
        const fetcher = vi.fn(async (url) => {
            if (url.endsWith('/oss-upload-sessions')) {
                return jsonResponse({session: {session_id: 'session-1', part_size_bytes: 8, expected_parts: 1}});
            }
            if (url.endsWith('/parts')) {
                return jsonResponse({parts: [{part_number: 1, method: 'PUT', url: 'https://oss.example/1', headers: {}}]});
            }
            if (url.endsWith('/abort')) return jsonResponse({ok: true});
            throw new Error(`Unexpected request: ${url}`);
        });

        await expect(uploadFilesToOssAndQueue({
            files: [sourceFile()],
            options: {},
            fetcher,
            uploadPart: async () => { throw new Error('connection dropped'); },
        })).rejects.toThrow('connection dropped');

        expect(fetcher.mock.calls.map(([url]) => url)).toContain('/oss-upload-sessions/session-1/abort');
    });

    it('maps existing run preferences to the server queue contract', () => {
        expect(queueOptionsForOssUpload(
            {
                exportToLark: true,
                larkExportRoute: 'local_cli',
                aiProvider: 'deepseek',
                skipSummary: true,
                speakerDiarization: true,
            },
            (route) => route,
            (route) => route === 'local_cli',
        )).toEqual({
            export_to_lark: 'true',
            lark_export_route: 'local_cli',
            lark_via_cli: 'true',
            ai_provider: 'deepseek',
            skip_summary: 'true',
            speaker_diarization: 'true',
        });
    });
});
