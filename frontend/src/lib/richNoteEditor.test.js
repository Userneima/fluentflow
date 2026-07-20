// @vitest-environment jsdom

import {describe, expect, it} from 'vitest';
import {editableHtmlToMarkdown, markdownToEditableHtml} from './richNoteEditor.js';

describe('rich note editor conversion', () => {
    it('presents markdown as formatted HTML instead of source symbols', () => {
        const html = markdownToEditableHtml('# 课程笔记\n\n- **重点**\n- *复习*');

        expect(html).toContain('<h2');
        expect(html).toContain('<strong>重点</strong>');
        expect(html).toContain('<em>复习</em>');
        expect(html).not.toContain('**重点**');
    });

    it('returns headings, lists, emphasis, tables, code, and images to markdown', () => {
        const markdown = editableHtmlToMarkdown(`
            <h2>课程笔记</h2>
            <ul><li><strong>重点</strong></li><li><em>复习</em></li></ul>
            <table><thead><tr><th>概念</th><th>说明</th></tr></thead><tbody><tr><td>术语</td><td>解释</td></tr></tbody></table>
            <pre><code>const note = true;</code></pre>
            <figure><img alt="流程图" src="/jobs/task/artifacts/frame.png"></figure>
        `);

        expect(markdown).toContain('# 课程笔记');
        expect(markdown).toContain('- **重点**');
        expect(markdown).toContain('- *复习*');
        expect(markdown).toContain('| 概念 | 说明 |\n| --- | --- |\n| 术语 | 解释 |');
        expect(markdown).toContain('```\nconst note = true;\n```');
        expect(markdown).toContain('![流程图](/jobs/task/artifacts/frame.png)');
    });

    it('keeps a table when it was wrapped by the markdown renderer', () => {
        const markdown = editableHtmlToMarkdown(markdownToEditableHtml('| 概念 | 说明 |\n| --- | --- |\n| 术语 | 解释 |'));

        expect(markdown).toBe('| 概念 | 说明 |\n| --- | --- |\n| 术语 | 解释 |');
    });
});
