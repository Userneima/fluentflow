import {simpleMd} from './markdown.js';

export const _dl = (blob, name) => { const u=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=u; a.download=name; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(u); };
export const _baseName = (fn) => (fn||'FluentFlow').replace(/\.[^/.]+$/,'');

export const _fmtSrtTime = (sec) => {
    const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=Math.floor(sec%60), ms=Math.round((sec%1)*1000);
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')},${String(ms).padStart(3,'0')}`;
};
export const _fmtVttTime = (sec) => {
    const h=Math.floor(sec/3600), m=Math.floor((sec%3600)/60), s=Math.floor(sec%60), ms=Math.round((sec%1)*1000);
    return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}.${String(ms).padStart(3,'0')}`;
};

export const dlTranscriptTxt = (text, filename) => {
    _dl(new Blob([text],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'.txt');
};
export const dlTranscriptSrt = (segments, filename) => {
    const lines = segments.map((s,i) => `${i+1}\n${_fmtSrtTime(s.start)} --> ${_fmtSrtTime(s.end)}\n${s.text.trim()}\n`);
    _dl(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'.srt');
};
export const dlTranscriptVtt = (segments, filename) => {
    const lines = ['WEBVTT\n', ...segments.map(s => `${_fmtVttTime(s.start)} --> ${_fmtVttTime(s.end)}\n${s.text.trim()}\n`)];
    _dl(new Blob([lines.join('\n')],{type:'text/vtt;charset=utf-8'}), _baseName(filename)+'.vtt');
};
const bilingualSegments = (segments, translatedSegments) => (
    (segments || []).map((segment, index) => {
        const text = String(segment?.text || '').trim();
        const zh = String(
            segment?.text_zh
            || translatedSegments?.[index]?.text
            || translatedSegments?.[index]?.text_zh
            || ''
        ).trim();
        return {...segment, text: zh ? `${text}\n${zh}` : text};
    }).filter((segment) => String(segment.text || '').trim())
);
export const dlBilingualTranscriptSrt = (segments, translatedSegments, filename) => {
    const merged = bilingualSegments(segments, translatedSegments);
    const lines = merged.map((s,i) => `${i+1}\n${_fmtSrtTime(s.start)} --> ${_fmtSrtTime(s.end)}\n${s.text.trim()}\n`);
    _dl(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'_bilingual_zh.srt');
};
export const dlBilingualTranscriptVtt = (segments, translatedSegments, filename) => {
    const merged = bilingualSegments(segments, translatedSegments);
    const lines = ['WEBVTT\n', ...merged.map(s => `${_fmtVttTime(s.start)} --> ${_fmtVttTime(s.end)}\n${s.text.trim()}\n`)];
    _dl(new Blob([lines.join('\n')],{type:'text/vtt;charset=utf-8'}), _baseName(filename)+'_bilingual_zh.vtt');
};

export const dlSummaryTxt = (md, filename) => {
    _dl(new Blob([md],{type:'text/plain;charset=utf-8'}), _baseName(filename)+'_summary.txt');
};

export const dlSummaryMd = (md, filename) => {
    _dl(new Blob([md],{type:'text/markdown;charset=utf-8'}), _baseName(filename)+'_summary.md');
};

export const dlSummaryWord = (md, filename) => {
    const rendered = simpleMd(md);
    const html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">
<head><meta charset="utf-8"><style>body{font-family:'Microsoft YaHei','Segoe UI',sans-serif;font-size:12pt;line-height:1.8;color:#1a1a1a;max-width:700px;margin:0 auto;padding:40px}h2{font-size:18pt;margin-top:24pt}h3{font-size:15pt;margin-top:18pt}h4{font-size:13pt;margin-top:14pt}ul{margin-left:20pt}li{margin-bottom:4pt}strong{font-weight:bold}</style></head>
<body>${rendered}</body></html>`;
    _dl(new Blob([html],{type:'application/vnd.ms-word;charset=utf-8'}), _baseName(filename)+'_summary.doc');
};

const buildPrintableSummaryElement = (md) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'ff-print-summary-export';
    wrapper.innerHTML = `
        <style>
            .ff-print-summary-export {
                box-sizing: border-box;
                width: 760px;
                padding: 42px 48px;
                background: #ffffff;
                color: #171717;
                font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", Arial, sans-serif;
                font-size: 14px;
                font-weight: 400;
                line-height: 1.72;
                letter-spacing: 0;
            }
            .ff-print-summary-export * {
                box-sizing: border-box;
                color: inherit !important;
                opacity: 1 !important;
                text-shadow: none !important;
            }
            .ff-print-summary-export h2,
            .ff-print-summary-export h3,
            .ff-print-summary-export h4,
            .ff-print-summary-export h5 {
                break-after: avoid;
                page-break-after: avoid;
                margin: 22px 0 10px;
                color: #111111 !important;
                font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", Arial, sans-serif;
                font-weight: 750;
                line-height: 1.35;
            }
            .ff-print-summary-export h2 { font-size: 24px; margin-top: 0; }
            .ff-print-summary-export h3 { font-size: 20px; }
            .ff-print-summary-export h4 { font-size: 17px; }
            .ff-print-summary-export h5 { font-size: 15px; }
            .ff-print-summary-export p {
                margin: 0 0 10px;
                color: #252525 !important;
            }
            .ff-print-summary-export ul,
            .ff-print-summary-export ol {
                margin: 8px 0 14px 24px;
                padding: 0;
            }
            .ff-print-summary-export li {
                display: list-item !important;
                margin: 0 0 7px;
                padding-left: 2px;
                color: #252525 !important;
                break-inside: avoid;
                page-break-inside: avoid;
            }
            .ff-print-summary-export li > span:first-child {
                display: none !important;
            }
            .ff-print-summary-export li > span {
                display: inline !important;
            }
            .ff-print-summary-export strong {
                font-weight: 750;
                color: #111111 !important;
            }
            .ff-print-summary-export code {
                display: inline;
                padding: 1px 4px;
                border-radius: 4px;
                background: #f1f3f5 !important;
                color: #111111 !important;
                font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
                font-size: 0.92em;
            }
            .ff-print-summary-export pre,
            .ff-print-summary-export blockquote,
            .ff-print-summary-export figure,
            .ff-print-summary-export table {
                break-inside: avoid;
                page-break-inside: avoid;
            }
            .ff-print-summary-export pre {
                overflow-wrap: anywhere;
                white-space: pre-wrap;
                margin: 12px 0 16px;
                padding: 12px 14px;
                border-radius: 8px;
                background: #f6f8fa !important;
                color: #171717 !important;
                font-size: 12px;
                line-height: 1.55;
            }
            .ff-print-summary-export blockquote {
                margin: 12px 0 16px;
                padding: 10px 14px;
                border-left: 4px solid #7c3aed;
                background: #f7f3ff !important;
                color: #2d2540 !important;
            }
            .ff-print-summary-export hr {
                margin: 18px 0;
                border: 0;
                border-top: 1px solid #dedede;
            }
            .ff-print-summary-export img {
                display: block;
                max-width: 100%;
                height: auto;
                margin: 8px 0;
                border-radius: 8px;
            }
            .ff-print-summary-export figcaption {
                margin-top: 4px;
                color: #666666 !important;
                font-size: 11px;
                line-height: 1.45;
            }
            .ff-print-summary-export table {
                width: 100%;
                border-collapse: collapse;
                margin: 12px 0 16px;
                font-size: 12px;
            }
            .ff-print-summary-export th,
            .ff-print-summary-export td {
                border: 1px solid #dedede;
                padding: 7px 9px;
                vertical-align: top;
                color: #222222 !important;
            }
            .ff-print-summary-export th {
                background: #f5f5f5 !important;
                color: #111111 !important;
                font-weight: 750;
            }
            .ff-print-summary-export br + br {
                display: none;
            }
        </style>
        <div class="ff-print-summary-body">${simpleMd(md, {renderImages: true})}</div>
    `;
    wrapper.style.position = 'fixed';
    wrapper.style.left = '-10000px';
    wrapper.style.top = '0';
    wrapper.style.zIndex = '-1';
    return wrapper;
};

export const dlSummaryPdf = async (summaryMdOrRef, filename) => {
    if(!window.html2pdf) throw new Error('html2pdf not loaded');
    const sourceEl = summaryMdOrRef?.current || null;
    const printable = typeof summaryMdOrRef === 'string'
        ? buildPrintableSummaryElement(summaryMdOrRef)
        : sourceEl?.cloneNode(true);
    if(!printable) return;
    if(sourceEl) {
        printable.classList.add('ff-print-summary-export');
        printable.style.background = '#ffffff';
        printable.style.color = '#171717';
        printable.style.width = '760px';
        printable.style.padding = '42px 48px';
        printable.style.position = 'fixed';
        printable.style.left = '-10000px';
        printable.style.top = '0';
        printable.style.zIndex = '-1';
    }
    document.body.appendChild(printable);
    try {
        await window.html2pdf().set({
            margin: [12,12,12,12],
            filename: _baseName(filename)+'_summary.pdf',
            image: {type:'jpeg', quality:0.98},
            html2canvas: {
                scale: 2,
                useCORS: true,
                backgroundColor: '#ffffff',
                scrollY: 0,
                windowWidth: 840,
                windowHeight: Math.max(printable.scrollHeight, 1120),
            },
            jsPDF: {unit:'mm', format:'a4', orientation:'portrait'},
            pagebreak: {mode: ['css', 'legacy'], avoid: ['figure', 'table', 'pre', 'blockquote', 'li']},
        }).from(printable).save();
    } finally {
        printable.remove();
    }
};

export const dlSummaryImage = async (summaryElRef, filename) => {
    throw new Error('PNG export disabled');
};
