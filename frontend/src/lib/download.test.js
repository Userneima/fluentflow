// Regression guards for the browser export pipeline (docx / print-PDF / subtitles).
//
// Export formatting is a repeat-regression area: fixing one path (Word, PDF,
// screenshots) has historically broken another because nothing locked the
// output shape. These tests assert the *structure* of what download.js emits so
// each previously-fixed format bug stays fixed.
//
// The vitest environment is `node` (see vitest.config.mjs), and download.js
// imports apiConfig.js, which touches `window`/`localStorage` at module load.
// So we shim minimal browser globals BEFORE dynamically importing the module,
// and drive the screenshot fetch path with a controllable global `fetch`. docx
// output is a binary zip; we unzip and assert on word/document.xml, never bytes.

import {afterEach, beforeAll, describe, expect, it} from 'vitest';

// --- browser global shims (must exist before download.js / apiConfig.js load) ---
globalThis.window = globalThis.window || {
    location: {hostname: '127.0.0.1', port: '5173', origin: 'http://127.0.0.1:5173'},
    FLUENTFLOW_CONFIG: {},
    crypto: {},
};
globalThis.localStorage = globalThis.localStorage || {
    _s: {},
    getItem(k) { return this._s[k] ?? null; },
    setItem(k, v) { this._s[k] = String(v); },
    removeItem(k) { delete this._s[k]; },
};

let dl;
let Packer;
let JSZip;

beforeAll(async () => {
    dl = await import('./download.js');
    ({Packer} = await import('docx'));
    JSZip = (await import('jszip')).default;
});

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

// fetch stub that fails every image request → exercises the caption fallback.
const failingFetch = () => { globalThis.fetch = async () => ({ok: false, headers: {get: () => ''}, arrayBuffer: async () => new ArrayBuffer(0)}); };

// fetch stub that returns a tiny PNG → exercises the embedded-image path.
const imageFetch = () => {
    const calls = [];
    const png = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]).buffer;
    globalThis.fetch = async (url) => {
        calls.push(String(url));
        return {ok: true, headers: {get: (h) => (String(h).toLowerCase() === 'content-type' ? 'image/png' : '')}, arrayBuffer: async () => png};
    };
    return calls;
};

// Build a .docx and return its word/document.xml plus the zip for media checks.
const docxArtifacts = async (md) => {
    const doc = await dl.buildSummaryDocxDocument(md);
    const zip = await JSZip.loadAsync(await Packer.toBuffer(doc));
    return {xml: await zip.file('word/document.xml').async('string'), zip};
};

const SAMPLE_NOTE = [
    '# 学习笔记 Study Note 2024',
    '',
    '正文含中文、English 和数字 123。',
    '',
    '## 要点 Key Points',
    '- 第一点 with **bold** and `code`',
    '- 第二点',
    '',
    '1. 步骤一',
    '2. 步骤二',
    '',
    '| 概念 Concept | 说明 Note |',
    '| --- | --- |',
    '| Agent | 智能体 |',
    '| Tool | 工具 |',
    '',
    '> 一句引用 quote',
    '',
    '---',
    '',
    '![板书截图](/jobs/task-1/artifacts/frame?file=frame_001.jpg)',
].join('\n');

describe('Word .docx export structure', () => {
    it('applies PingFang SC to every font slot (CJK / latin / digits share one font)', async () => {
        failingFetch();
        const {xml} = await docxArtifacts(SAMPLE_NOTE);
        // Regression: Chinese text falling back to a system font because the
        // eastAsia slot was not set. Every rFonts must pin all four slots.
        const fonts = [...xml.matchAll(/<w:rFonts\b[^>]*\/>/g)].map((m) => m[0]);
        expect(fonts.length).toBeGreaterThan(0);
        for (const tag of fonts) {
            expect(tag).toContain('w:ascii="PingFang SC"');
            expect(tag).toContain('w:eastAsia="PingFang SC"');
            expect(tag).toContain('w:hAnsi="PingFang SC"');
            expect(tag).toContain('w:cs="PingFang SC"');
        }
    });

    it('renders lists via native Word numbering, not a literal bullet glyph', async () => {
        failingFetch();
        const {xml} = await docxArtifacts(SAMPLE_NOTE);
        // Regression: duplicate bullets — a manual "•" span PLUS Word's own
        // list marker. Native numbering must be used and no "•" may leak in.
        expect(xml).not.toContain('•');
        expect(xml).toMatch(/<w:numPr>/);
        // bullet list (numId 1) and ordered list (numId 2) both present
        const numIds = [...xml.matchAll(/<w:numId w:val="(\d+)"/g)].map((m) => m[1]);
        expect(new Set(numIds).size).toBeGreaterThanOrEqual(2);
    });

    it('renders headings as Word heading styles', async () => {
        failingFetch();
        const {xml} = await docxArtifacts(SAMPLE_NOTE);
        expect(xml).toContain('<w:pStyle w:val="Heading1"/>');
        expect(xml).toContain('<w:pStyle w:val="Heading2"/>');
    });

    it('renders a pipe table as a fixed full-width table without clipping the first column', async () => {
        failingFetch();
        const {xml} = await docxArtifacts(SAMPLE_NOTE);
        // Regression: left column clipped to zero width. Fixed layout + explicit
        // percentage table width keeps every column, including the first.
        expect(xml).toContain('<w:tblLayout w:type="fixed"/>');
        expect(xml).toMatch(/<w:tblW\b[^>]*w:type="pct"/);
        // header + both body rows, first column values must survive
        expect(xml).toContain('概念 Concept');
        expect(xml).toContain('说明 Note');
        expect(xml).toContain('Agent');
        expect(xml).toContain('智能体');
        expect(xml).toContain('Tool');
    });

    it('renders code blocks, blockquotes and dividers as document paragraphs', async () => {
        failingFetch();
        const {xml} = await docxArtifacts('```\nconst x = 1;\n```\n\n> 引用块\n\n---');
        expect(xml).toContain('const x = 1;');
        expect(xml).toContain('引用块');
        // divider + quote left border are drawn with paragraph borders
        expect(xml).toContain('<w:pBdr>');
    });

    it('keeps bold and code inline styling inside a run', async () => {
        failingFetch();
        const {xml} = await docxArtifacts('普通文字 **加粗** 和 `code` 收尾。');
        expect(xml).toContain('加粗');
        expect(xml).toContain('<w:b/>');
        // markdown markers themselves must not leak into the text
        expect(xml).not.toContain('**');
        expect(xml).not.toContain('`code`');
    });

    it('produces a valid document even when markdown is empty', async () => {
        failingFetch();
        const {xml} = await docxArtifacts('');
        expect(xml).toContain('<w:body>');
    });
});

describe('Word .docx screenshot embedding', () => {
    it('embeds a real image when the artifact fetch succeeds, resolving the API base', async () => {
        const calls = imageFetch();
        const {xml, zip} = await docxArtifacts('![截图](/jobs/task-1/artifacts/frame?file=f.png)');
        expect(xml).toContain('<w:drawing>');
        const media = Object.keys(zip.files).filter((n) => n.startsWith('word/media/') && n.endsWith('.png'));
        expect(media.length).toBe(1);
        // artifact path is fetched through the resolved API base, not the raw path
        expect(calls[0]).toContain('/jobs/task-1/artifacts/frame');
        expect(calls[0]).toMatch(/^https?:\/\//);
    });

    it('degrades to a readable caption when the image cannot be fetched, without failing the export', async () => {
        failingFetch();
        // A broken image sits between real content; the whole doc must still build.
        const {xml, zip} = await docxArtifacts('# 标题\n\n![丢失的截图](/jobs/x/artifacts/frame?file=missing.png)\n\n结尾段落。');
        expect(xml).toContain('标题');
        expect(xml).toContain('结尾段落。');
        // fallback keeps the caption + source, and embeds no image
        expect(xml).toContain('丢失的截图');
        expect(xml).not.toContain('<w:drawing>');
        expect(Object.keys(zip.files).some((n) => n.startsWith('word/media/') && /\.(png|jpg|jpeg|gif|bmp)$/.test(n))).toBe(false);
    });
});

describe('PDF print HTML', () => {
    it('renders a self-contained white print document', () => {
        const html = dl.buildPrintableSummaryHtml('# 标题\n\n正文。', 'note');
        expect(html).toContain('<!DOCTYPE html>');
        expect(html).toContain('ff-print-summary-export');
        expect(html).toContain('@page');
        expect(html).toContain('background: #ffffff');
    });

    it('does not emit manual list-marker glyphs into list items', () => {
        // Regression: PDF list items showing a literal "•" next to the native
        // list marker. The print path renders lists without manual markers.
        const html = dl.buildPrintableSummaryHtml('- 第一点\n- 第二点\n\n1. 步骤一\n2. 步骤二');
        const items = [...html.matchAll(/<li[^>]*>[\s\S]*?<\/li>/g)].map((m) => m[0]);
        expect(items.length).toBeGreaterThan(0);
        for (const li of items) expect(li).not.toContain('•');
    });

    it('renders pipe tables as an HTML table, never raw markdown source', () => {
        const html = dl.buildPrintableSummaryHtml('| A | B |\n| --- | --- |\n| 1 | 2 |');
        expect(html).toContain('<table');
        expect(html).not.toContain('| --- |');
        expect(html).not.toContain('|---|');
    });

    it('rewrites artifact image references through the API base before printing', () => {
        const html = dl.buildPrintableSummaryHtml('![截图](/jobs/task-1/artifacts/frame?file=f.png)');
        expect(html).toContain('<img');
        // the src must be an absolute resolved URL, not the bare app-relative path
        expect(html).toMatch(/src="https?:\/\/[^"]*\/jobs\/task-1\/artifacts\/frame/);
    });
});

describe('rewriteExportImageSources', () => {
    it('resolves app-relative artifact paths to an absolute URL', () => {
        const out = dl.rewriteExportImageSources('![a](/jobs/x/artifacts/frame?file=f.png)');
        expect(out).toMatch(/!\[a\]\(https?:\/\/[^)]*\/jobs\/x\/artifacts\/frame\?file=f\.png\)/);
    });

    it('leaves already-absolute image URLs untouched', () => {
        const url = 'https://cdn.example.com/pic.png';
        expect(dl.rewriteExportImageSources(`![p](${url})`)).toContain(`(${url})`);
    });

    it('ignores markdown without image references', () => {
        expect(dl.rewriteExportImageSources('# 标题\n\n正文没有图片。')).toBe('# 标题\n\n正文没有图片。');
    });
});

describe('subtitle exports', () => {
    it('formats SRT timestamps as HH:MM:SS,mmm', () => {
        expect(dl._fmtSrtTime(3661.5)).toBe('01:01:01,500');
    });

    it('formats VTT timestamps as HH:MM:SS.mmm', () => {
        expect(dl._fmtVttTime(3661.5)).toBe('01:01:01.500');
    });

    it('derives the export base name by stripping the extension', () => {
        expect(dl._baseName('lecture.mp4')).toBe('lecture');
        expect(dl._baseName('')).toBe('FluentFlow');
    });
});
