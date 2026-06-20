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
        const zh = String(translatedSegments?.[index]?.text || translatedSegments?.[index]?.text_zh || '').trim();
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

export const dlSummaryPdf = async (summaryElRef, filename) => {
    if(!window.html2pdf) throw new Error('html2pdf not loaded');
    const el = summaryElRef.current;
    if(!el) return;
    await window.html2pdf().set({
        margin: [12,12,12,12],
        filename: _baseName(filename)+'_summary.pdf',
        image: {type:'jpeg', quality:0.95},
        html2canvas: {scale:2, useCORS:true, scrollY:0, windowHeight:el.scrollHeight},
        jsPDF: {unit:'mm', format:'a4', orientation:'portrait'},
    }).from(el).save();
};

export const dlSummaryImage = async (summaryElRef, filename) => {
    // Disabled by user request (remove PNG export feature).
    throw new Error('PNG export disabled');
    const el = summaryElRef.current;
    if(!el) return;

    const isDark = document.documentElement.classList.contains('dark');
    const bg = isDark ? '#0c0e11' : '#ffffff';
    const fg = isDark ? '#e2e2e6' : '#171c1f';

    const temp = document.createElement('div');
    temp.style.position = 'fixed';
    temp.style.left = '0';
    temp.style.top = '0';
    temp.style.zIndex = '9999';
    temp.style.visibility = 'visible';
    temp.style.opacity = '0';
    temp.style.pointerEvents = 'none';
    temp.style.background = bg;
    temp.style.color = fg;
    temp.style.padding = '32px';
    temp.style.boxSizing = 'border-box';
    temp.style.width = (el.getBoundingClientRect().width || 800) + 'px';
    temp.innerHTML = el.innerHTML;

    document.body.appendChild(temp);

    await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

    try {
        if(window.html2canvas){
            const canvas = await window.html2canvas(temp, {
                scale: 2,
                useCORS: true,
                backgroundColor: bg,
                scrollX: 0,
                scrollY: 0,
                windowWidth: temp.scrollWidth,
                windowHeight: temp.scrollHeight,
            });
            const canvasObj = canvas?.canvas || canvas;
            if(canvasObj){
                if(typeof canvasObj.toBlob === 'function'){
                    canvasObj.toBlob(blob => { if(blob) _dl(blob, _baseName(filename)+'_summary.png'); }, 'image/png');
                    return;
                }
                if(typeof canvasObj.toDataURL === 'function'){
                    const dataUrl = canvasObj.toDataURL('image/png');
                    const blob = await (await fetch(dataUrl)).blob();
                    _dl(blob, _baseName(filename)+'_summary.png');
                    return;
                }
            }
        }

        const canvasResult = await window.html2pdf()
            .set({
                html2canvas: {scale:2, useCORS:true, scrollY:0, backgroundColor: bg, windowHeight: temp.scrollHeight},
            })
            .from(temp)
            .toCanvas();
        const canvas = canvasResult?.canvas || canvasResult;
        if(!canvas) throw new Error('Image export failed: canvas is empty');

        if(typeof canvas.toBlob === 'function'){
            canvas.toBlob(blob => { if(blob) _dl(blob, _baseName(filename)+'_summary.png'); }, 'image/png');
            return;
        }
        if(typeof canvas.toDataURL === 'function'){
            const dataUrl = canvas.toDataURL('image/png');
            const blob = await (await fetch(dataUrl)).blob();
            _dl(blob, _baseName(filename)+'_summary.png');
            return;
        }
        throw new Error('Image export failed: canvas has no toBlob/toDataURL');
    } finally {
        document.body.removeChild(temp);
    }
};
