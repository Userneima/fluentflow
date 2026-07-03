import {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {
    ArrowRight,
    BookOpenText,
    Captions,
    CheckCircle2,
    Download,
    FileText,
    FileVideo2,
    Film,
    Image,
    Link2,
    MicVocal,
    MonitorPlay,
    Moon,
    Play,
    RotateCcw,
    ScanSearch,
    Sun,
    UploadCloud,
} from 'lucide-react';

const LogoMark = () => (
    <span className="flex size-10 items-center justify-center rounded-[15px] bg-[#17201b] text-[#fff8ec] shadow-[0_18px_42px_-28px_rgba(23,32,27,.7)] dark:bg-[#f7f1e5] dark:text-[#17201b]">
        <svg viewBox="0 0 64 64" className="size-[29px]" fill="none" aria-hidden="true">
            <rect x="16" y="18" width="30" height="28" rx="10" fill="currentColor"/>
            <rect x="44" y="25" width="8" height="14" rx="4" fill="currentColor"/>
            <path d="M25 29h12M25 36h8" stroke="var(--ff-logo-line, #17201b)" strokeWidth="4.1" strokeLinecap="round" className="[--ff-logo-line:#17201b] dark:[--ff-logo-line:#f7f1e5]"/>
        </svg>
    </span>
);

const carouselStepMs = 6500;

const sourceIconItems = [
    {key: 'courses', Icon: BookOpenText, tone: 'bg-[#f4d98c] text-[#5c4214] dark:bg-[#f4d98c] dark:text-[#36240b]'},
    {key: 'lectures', Icon: MicVocal, tone: 'bg-[#b9dfd1] text-[#123f33] dark:bg-[#9bd9c2] dark:text-[#0b3026]'},
    {key: 'recordings', Icon: MonitorPlay, tone: 'bg-[#bfd7f3] text-[#183b61] dark:bg-[#a8caef] dark:text-[#102f50]'},
    {key: 'localMedia', Icon: FileVideo2, tone: 'bg-[#f3c2ac] text-[#642d1c] dark:bg-[#efb49a] dark:text-[#51210f]'},
    {key: 'subtitles', Icon: Captions, tone: 'bg-[#d6c7f2] text-[#3e2c68] dark:bg-[#c8b4ee] dark:text-[#2d1d55]'},
    {key: 'links', Icon: Link2, tone: 'bg-[#d0d9bc] text-[#344418] dark:bg-[#c1d49f] dark:text-[#27350f]'},
];

const landingCopy = {
    en: {
        nav: {
            studyFlow: 'Study flow',
            noteQuality: 'Note quality',
            sources: 'Sources',
            openApp: 'Open app',
            startVideo: 'Start a video',
            startShort: 'Start',
        },
        controls: {
            languageLabel: 'Language',
            themeLabel: 'Toggle dark mode',
            switchToEnglish: 'Switch homepage language to English',
            switchToChinese: 'Switch homepage language to Chinese',
            useLight: 'Use light mode',
            useDark: 'Use dark mode',
        },
        hero: {
            eyebrow: 'Long-video study notes',
            title: 'Turn long videos into study-ready notes first.',
            desc: 'Upload a course, lecture, recording, or video link. FluentFlow prepares the note, transcript, and key moments before you study.',
            primary: 'Start processing',
            secondary: 'See the study flow',
            note: '',
        },
        heroVisual: {
            label: 'Animated product walkthrough: input a long video, process source material, study beside the note, and export review assets',
            path: 'fluentflow.app/video-note',
            inputStep: 'Input',
            processingStep: 'Processing',
            studyStep: 'Study / Review',
            exportStep: 'Export',
            upload: 'Upload / paste a long video',
            uploadMeta: 'Paste a course URL',
            uploadSource: 'https://course.example.com/attention-lecture',
            uploadHint: 'Identifying long-video source',
            uploadQueued: 'Notes, transcript, key moments',
            uploadSubtitle: 'URL detected',
            uploadTitle: 'Course lecture: attention mechanisms',
            uploadType: 'Learning material · public link',
            uploadDuration: '1:12:44 video',
            uploadDecision: 'Ready for study-note generation',
            uploadProgress: 'Source check in progress',
            uploadTags: ['Public link', 'Long lecture', 'Transcript', 'Key moments'],
            processing: 'Processing the video',
            processingMeta: 'Course lecture identified',
            processingMaterial: 'Long lecture · note-first route',
            processingStageTranscript: 'Transcript and subtitles',
            processingStageTranscriptStatus: 'Done',
            processingStageFrames: 'Key moments',
            processingStageFramesStatus: 'Running',
            processingStageNotes: 'Study notes',
            processingStageNotesStatus: 'Next',
            processingProgress: 'Processing 64%',
            processingHint: 'Preparing reviewable source material',
            study: 'Study beside the video',
            studyTime: '18:42',
            studyVideoLabel: 'Video',
            studyTranscriptLabel: 'Transcript',
            studyCaption: '"Attention narrows what each token compares."',
            studyNoteArea: 'Note editor',
            studyNoteTitleLabel: 'Note title',
            studyNoteTitle: 'Note title',
            studyChapterLabel: 'Chapter title',
            studyChapterTitle: 'Chapter title',
            studyNoteContentLabel: 'Note content',
            studyConclusion: 'Note content',
            studyAnchorLabel: 'Source anchor',
            studyAnchor: '18:42 source anchor',
            export: 'Export',
            exportFileCount: '4 files',
            exportMediaTitle: 'Video and audio',
            exportMediaVideo: 'Video file',
            exportMediaVideoFormat: '.mp4',
            exportMediaVideoHint: 'source video',
            exportMediaAudio: 'Audio track',
            exportMediaAudioFormat: '.mp3',
            exportMediaAudioHint: 'clean audio',
            exportMediaSubtitles: 'Subtitles',
            exportMediaSubtitlesFormat: '.srt',
            exportMediaSubtitlesHint: 'timed text',
            exportMediaFrames: 'Key frames',
            exportMediaFramesFormat: '.jpg',
            exportMediaFramesHint: 'visual anchors',
            exportNotesTitle: 'Notes and review',
            exportNotesMarkdown: 'Markdown',
            exportNotesMarkdownFormat: '.md',
            exportNotesMarkdownHint: 'editable note',
            exportNotesPdf: 'PDF',
            exportNotesPdfFormat: '.pdf',
            exportNotesPdfHint: 'reading copy',
            exportNotesFeishu: 'Feishu',
            exportNotesFeishuFormat: 'doc',
            exportNotesFeishuHint: 'workspace share',
            exportNotesPackage: 'Study note package',
            exportNotesPackageFormat: '.zip',
            exportNotesPackageHint: 'note bundle',
            finalNote: 'Ready to keep studying later.',
        },
        workflow: {
            eyebrow: 'Before / After',
            title: 'Study with notes ready, not with a pause button under your finger.',
            desc: 'The video stays central. FluentFlow removes the note-taking drag around it.',
            beforeTitle: 'Before',
            afterTitle: 'After',
            beforeItems: [
                ['Open a long video', 'You must decide what to capture from the first minute.'],
                ['Pause and rewind', 'One missed sentence breaks attention and sends you back.'],
                ['Clean the note later', 'After watching, chapters and examples still need manual cleanup.'],
            ],
            afterItems: [
                ['Generate notes first', 'Chapters, subtitles, and key moments are prepared upfront.'],
                ['Study with the video', 'Focus on the lesson and revisit the source only when needed.'],
                ['Fix a few details', 'Correct the small number of uncertain recognition or wording issues.'],
            ],
        },
        quality: {
            eyebrow: 'What quality means',
            title: 'Not a summary. A reviewable study asset.',
            desc: 'Structure, source checks, key moments, export.',
            items: [
                ['Structured chapters', 'Concepts, examples, and conclusions are shaped before you start watching.'],
                ['Important reasoning', 'Key steps stay visible instead of being flattened into a generic summary.'],
                ['Transcript review', 'Subtitles and transcript stay available so the note can be checked against source.'],
                ['Conservative correction', 'Accepted transcript fixes can show original text, corrected text, reason, confidence, and time.'],
                ['Key moments', 'When local video is available, visual anchors help you return to formulas, code, slides, or screens.'],
                ['Exportable result', 'Markdown, PDF, and Feishu exports turn the result into a lasting study asset.'],
            ],
        },
        sources: {
            eyebrow: 'Source coverage',
            title: 'Courses, lectures, recordings, files, and supported public links.',
            desc: 'Local upload and subtitle files are most reliable. Public platforms may restrict access.',
            items: {
                courses: 'Courses',
                lectures: 'Lectures',
                recordings: 'Screen recordings',
                localMedia: 'Local video or audio',
                subtitles: 'Subtitle files',
                links: 'Supported public links',
            },
        },
        output: {
            eyebrow: 'What you keep',
            title: 'A record you can study, review, and export.',
            desc: 'A reusable place for notes, transcript, visuals, records, and exports.',
            items: [
                ['Prepared note', 'Read the structure first, then study the video with better questions.'],
                ['Transcript and subtitles', 'Keep source text for unclear audio and recognition errors.'],
                ['Key visuals', 'Use important frames as review anchors when video evidence is available.'],
                ['Processing record', 'Running, failed, completed, downloads, and retries stay in one place.'],
            ],
        },
        cta: {
            eyebrow: 'Start with one real video',
            title: 'Give FluentFlow the next video you want to learn.',
            desc: 'Generate the note first. Study with the source beside it.',
            primary: 'Start processing',
            secondary: 'View processing records',
        },
    },
    zh: {
        nav: {
            studyFlow: '学习流程',
            noteQuality: '笔记质量',
            sources: '来源类型',
            openApp: '打开应用',
            startVideo: '开始处理',
            startShort: '开始',
        },
        controls: {
            languageLabel: '语言',
            themeLabel: '切换深色模式',
            switchToEnglish: '切换首页语言为英文',
            switchToChinese: '切换首页语言为中文',
            useLight: '使用明亮模式',
            useDark: '使用暗黑模式',
        },
        hero: {
            eyebrow: '长视频学习笔记',
            title: '先把长视频变成可以学习的笔记。',
            desc: '上传课程、讲座、录屏或视频链接。FluentFlow 先准备笔记、字幕/转录和关键画面。',
            primary: '开始处理',
            secondary: '查看学习流程',
            note: '',
        },
        heroVisual: {
            label: '动态产品演示：输入长视频，处理素材，对照笔记学习，再导出复查资产',
            path: 'fluentflow.app/video-note',
            inputStep: '输入',
            processingStep: '处理中',
            studyStep: '学习 / 复查',
            exportStep: '导出',
            upload: '上传或粘贴长视频',
            uploadMeta: '粘贴课程链接',
            uploadSource: 'https://course.example.com/attention-lecture',
            uploadHint: '正在识别长视频来源',
            uploadQueued: '笔记、转录、关键画面',
            uploadSubtitle: '已识别链接',
            uploadTitle: '课程讲座：注意力机制',
            uploadType: '学习材料 · 公开视频链接',
            uploadDuration: '1:12:44 视频',
            uploadDecision: '可生成学习笔记',
            uploadProgress: '正在检查来源',
            uploadTags: ['来源链接', '长视频', '字幕/转录', '关键画面'],
            processing: '正在处理视频',
            processingMeta: '已识别课程讲座',
            processingMaterial: '长讲座 · 先生成笔记路线',
            processingStageTranscript: '转录和字幕',
            processingStageTranscriptStatus: '完成',
            processingStageFrames: '关键画面',
            processingStageFramesStatus: '进行中',
            processingStageNotes: '学习笔记',
            processingStageNotesStatus: '下一步',
            processingProgress: '处理 64%',
            processingHint: '正在准备可复查的来源材料',
            study: '对照视频学习',
            studyTime: '18:42',
            studyVideoLabel: '视频区域',
            studyTranscriptLabel: '字幕',
            studyCaption: '“注意力会收窄每个 token 需要比较的范围。”',
            studyNoteArea: '笔记编辑区',
            studyNoteTitleLabel: '笔记标题',
            studyNoteTitle: '笔记标题',
            studyChapterLabel: '章节标题',
            studyChapterTitle: '章节标题',
            studyNoteContentLabel: '笔记内容',
            studyConclusion: '笔记内容',
            studyAnchorLabel: '来源锚点',
            studyAnchor: '18:42 来源锚点',
            export: '导出',
            exportFileCount: '4 项',
            exportMediaTitle: '视频和音频',
            exportMediaVideo: '视频文件',
            exportMediaVideoFormat: '.mp4',
            exportMediaVideoHint: '原视频',
            exportMediaAudio: '音频轨道',
            exportMediaAudioFormat: '.mp3',
            exportMediaAudioHint: '音频',
            exportMediaSubtitles: '字幕',
            exportMediaSubtitlesFormat: '.srt',
            exportMediaSubtitlesHint: '时间轴字幕',
            exportMediaFrames: '关键画面',
            exportMediaFramesFormat: '.jpg',
            exportMediaFramesHint: '画面锚点',
            exportNotesTitle: '笔记相关',
            exportNotesMarkdown: 'Markdown',
            exportNotesMarkdownFormat: '.md',
            exportNotesMarkdownHint: '可编辑笔记',
            exportNotesPdf: 'PDF',
            exportNotesPdfFormat: '.pdf',
            exportNotesPdfHint: '阅读版',
            exportNotesFeishu: '飞书',
            exportNotesFeishuFormat: 'doc',
            exportNotesFeishuHint: '协作页面',
            exportNotesPackage: '学习笔记包',
            exportNotesPackageFormat: '.zip',
            exportNotesPackageHint: '学习资产包',
            finalNote: '之后可以继续复习。',
        },
        workflow: {
            eyebrow: '前后对比',
            title: '先有笔记再看视频，不再被暂停键牵着走。',
            desc: '视频仍是主线。FluentFlow 先拿掉机械记笔记的拖累。',
            beforeTitle: '以前',
            afterTitle: '现在',
            beforeItems: [
                ['打开一条长视频', '从第一分钟开始就要判断哪些内容值得记。'],
                ['频繁暂停倒回', '漏掉一句话就会打断注意力，再拖回去重听。'],
                ['看完还要整理', '章节、例子和格式仍然需要手动清理。'],
            ],
            afterItems: [
                ['先生成笔记', '章节、字幕和关键画面提前准备好。'],
                ['对着视频学习', '把注意力放回课程，只在需要时回查来源。'],
                ['修少数细节', '只修正少量识别或措辞不确定的地方。'],
            ],
        },
        quality: {
            eyebrow: '什么才算高质量',
            title: '不是摘要，而是可复查的学习资产。',
            desc: '结构、来源、关键画面和导出。',
            items: [
                ['结构化章节', '概念、例子和结论会在你开始看视频前整理出来。'],
                ['关键推理保留', '重要步骤不会被压扁成泛泛总结。'],
                ['字幕/转录可复查', '原始字幕和转录保留，方便核对听不清或识别错误的地方。'],
                ['保守字幕纠错', '已接受的修正可展示原文、修正文、原因、置信度和时间点。'],
                ['关键画面', '本地视频可用时，重要画面会成为公式、代码、幻灯片或屏幕内容的复查锚点。'],
                ['结果可导出', 'Markdown、PDF 和飞书导出可以把结果留下来作为学习资产。'],
            ],
        },
        sources: {
            eyebrow: '来源覆盖',
            title: '课程、讲座、录屏、文件和支持的公开视频链接。',
            desc: '本地上传和字幕文件最稳定。公开视频平台可能限制访问。',
            items: {
                courses: '课程',
                lectures: '讲座',
                recordings: '屏幕录制',
                localMedia: '本地视频或音频',
                subtitles: '字幕文件',
                links: '支持的公开视频链接',
            },
        },
        output: {
            eyebrow: '最后留下什么',
            title: '一份可以学习、复查和导出的记录。',
            desc: '笔记、字幕、画面、处理记录和导出入口都留在一处。',
            items: [
                ['准备好的笔记', '先读结构，再带着更清楚的问题看视频。'],
                ['字幕和转录', '为听不清和识别错误的地方保留来源文本。'],
                ['关键画面', '视频证据可用时，用重要帧作为复习锚点。'],
                ['处理记录', '运行中、失败、完成、下载和重试都在同一个入口。'],
            ],
        },
        cta: {
            eyebrow: '从一条真实视频开始',
            title: '把下一条想学的视频交给 FluentFlow。',
            desc: '先生成笔记，再对着来源学习和修正。',
            primary: '开始处理',
            secondary: '查看处理记录',
        },
    },
};

const displayType = "[font-family:'Techna_Sans','Techna Sans','Avenir_Next','Nunito_Sans','Inter','ui-rounded','SF_Pro_Display',system-ui,sans-serif]";
const bodyType = "[font-family:'Avenir_Next','Inter','ui-rounded','SF_Pro_Text',system-ui,sans-serif]";
const dataType = "[font-family:'SF_Mono','ui-monospace','Menlo','Consolas',monospace]";
const lightGrain = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='96' height='96' viewBox='0 0 96 96'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.92' numOctaves='5' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='96' height='96' filter='url(%23n)' opacity='.62'/%3E%3C/svg%3E\")";
const darkGrain = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='96' height='96' viewBox='0 0 96 96'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.88' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='96' height='96' filter='url(%23n)' fill='white' opacity='.42'/%3E%3C/svg%3E\")";
const lightPageFrost = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.18' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23f)' opacity='.50'/%3E%3C/svg%3E\")";
const darkPageFrost = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160' viewBox='0 0 160 160'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.08' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23f)' fill='white' opacity='.36'/%3E%3C/svg%3E\")";
const interactiveMotion = 'transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200 ease-out';
const focusRing = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2a8f75]/45 focus-visible:ring-offset-2 focus-visible:ring-offset-[#fff8ec] dark:focus-visible:ring-[#8fd9c0]/50 dark:focus-visible:ring-offset-[#111612]';
const sectionShell = 'mx-auto max-w-7xl px-5 sm:px-6 lg:px-8';
const eyebrowClass = `${dataType} text-[11px] font-semibold uppercase tracking-[0.16em] text-[#2f7c66] dark:text-[#8fd9c0]`;
const primaryButton = `inline-flex h-12 touch-manipulation items-center justify-center gap-2 rounded-full bg-[#17201b] px-6 text-sm font-semibold text-[#fff8ec] shadow-[0_18px_46px_-28px_rgba(23,32,27,.82)] ${interactiveMotion} hover:-translate-y-0.5 hover:bg-[#24352d] hover:shadow-[0_24px_58px_-32px_rgba(23,32,27,.88)] active:translate-y-px dark:bg-[#f7f1e5] dark:text-[#17201b] dark:shadow-none dark:hover:bg-[#e9dcc8] ${focusRing}`;
const secondaryButton = `inline-flex h-12 touch-manipulation items-center justify-center gap-2 rounded-full border border-[#d2dfd2] bg-white/72 px-6 text-sm font-semibold text-[#17201b] shadow-[0_16px_38px_-32px_rgba(46,73,58,.45)] ${interactiveMotion} hover:-translate-y-0.5 hover:border-[#9fcab8] hover:bg-[#f4fbf5] active:translate-y-px dark:border-white/[0.16] dark:bg-white/[0.06] dark:text-white/[0.9] dark:hover:border-[#8fd9c0]/45 dark:hover:bg-white/[0.10] ${focusRing}`;

const SectionHeader = ({eyebrow, title, desc}) => (
    <div className="grid gap-5 lg:grid-cols-[0.85fr_1fr] lg:items-end">
        <div>
            <p className={eyebrowClass}>{eyebrow}</p>
            <h2 className={`mt-4 max-w-[12em] ${displayType} text-[34px] font-bold leading-[1.08] tracking-normal text-[#17201b] [text-wrap:balance] dark:text-[#f7f1e5] sm:text-[46px]`}>
                {title}
            </h2>
        </div>
        {desc ? (
            <p className="max-w-[60ch] text-base font-medium leading-relaxed text-[#626d64] dark:text-white/[0.68]">
                {desc}
            </p>
        ) : null}
    </div>
);

const proofViewportHeights = [
    'min-h-[720px] sm:min-h-[540px]',
    'min-h-[720px] sm:min-h-[480px]',
    'min-h-[960px] sm:min-h-[570px]',
    'min-h-[800px] sm:min-h-[480px]',
];
const uploadTagIcons = [Link2, Film, Captions, Image];

const buildProofSteps = (copy) => [
    {id: 'input', marker: '01', label: copy.inputStep, title: copy.upload},
    {id: 'processing', marker: '02', label: copy.processingStep, title: copy.processing},
    {id: 'study', marker: '03', label: copy.studyStep, title: copy.study},
    {id: 'export', marker: '04', label: copy.exportStep, title: copy.export},
];

const buildProcessingStages = (copy) => [
    {name: copy.processingStageTranscript, status: copy.processingStageTranscriptStatus, tone: 'done'},
    {name: copy.processingStageFrames, status: copy.processingStageFramesStatus, tone: 'running'},
    {name: copy.processingStageNotes, status: copy.processingStageNotesStatus, tone: 'next'},
];

const buildHeroExportGroups = (copy) => [
    {
        title: copy.exportMediaTitle,
        items: [
            {label: copy.exportMediaVideo, format: copy.exportMediaVideoFormat, hint: copy.exportMediaVideoHint, Icon: Film},
            {label: copy.exportMediaAudio, format: copy.exportMediaAudioFormat, hint: copy.exportMediaAudioHint, Icon: MicVocal},
            {label: copy.exportMediaSubtitles, format: copy.exportMediaSubtitlesFormat, hint: copy.exportMediaSubtitlesHint, Icon: Captions},
            {label: copy.exportMediaFrames, format: copy.exportMediaFramesFormat, hint: copy.exportMediaFramesHint, Icon: Image},
        ],
    },
    {
        title: copy.exportNotesTitle,
        items: [
            {label: copy.exportNotesMarkdown, format: copy.exportNotesMarkdownFormat, hint: copy.exportNotesMarkdownHint, Icon: FileText},
            {label: copy.exportNotesPdf, format: copy.exportNotesPdfFormat, hint: copy.exportNotesPdfHint, Icon: Download},
            {label: copy.exportNotesFeishu, format: copy.exportNotesFeishuFormat, hint: copy.exportNotesFeishuHint, Icon: BookOpenText},
            {label: copy.exportNotesPackage, format: copy.exportNotesPackageFormat, hint: copy.exportNotesPackageHint, Icon: CheckCircle2},
        ],
    },
];

const proofStageClass = (activeStep, index, extra = '') => `ff-proof-stage absolute inset-x-4 top-4 grid min-h-[306px] content-center rounded-[22px] border p-5 text-[#17201b] shadow-[0_18px_52px_-40px_rgba(46,73,58,.45)] transition-[opacity,transform] duration-500 ease-out dark:text-[#f7f1e5] sm:inset-x-6 sm:min-h-[330px] sm:p-6 ${activeStep === index ? 'z-10 opacity-100 translate-y-0 scale-100 pointer-events-auto' : 'z-0 pointer-events-none translate-y-3 scale-[0.985] opacity-0'} ${extra}`;

const HeroProofMotionStyles = () => (
    <style>{`
        @keyframes ffSceneScan {
            0%, 12% { transform: translateX(0); opacity: .7; }
            48%, 78% { transform: translateX(190px); opacity: 1; }
            100% { transform: translateX(0); opacity: .7; }
        }
        @keyframes ffInputType {
            0%, 14% { clip-path: inset(0 100% 0 0); }
            42%, 100% { clip-path: inset(0 0 0 0); }
        }
        @keyframes ffInputCaret {
            0%, 100% { opacity: 0; }
            45%, 58% { opacity: 1; }
        }
        @keyframes ffCardPop {
            0%, 38% { opacity: 0; transform: translateY(10px) scale(.985); }
            54%, 100% { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes ffProgressGrow {
            0%, 46% { transform: scaleX(.18); }
            78%, 100% { transform: scaleX(.72); }
        }
        @media (prefers-reduced-motion: reduce) {
            .ff-motion-demo .ff-animated {
                animation: none !important;
                transform: none !important;
            }
            .ff-motion-demo .ff-proof-stage {
                transition: none !important;
            }
        }
    `}</style>
);

const ProofStepIndicator = ({steps, activeStep, showStep, clearPreview, selectStep}) => (
    <div className="px-4 pt-4 sm:px-6">
        <div className="grid grid-cols-4 gap-3" role="tablist" aria-label="Homepage product proof steps">
            {steps.map((step, index) => {
                const isActive = activeStep === index;
                return (
                    <button
                        key={step.id}
                        type="button"
                        role="tab"
                        aria-selected={isActive}
                        aria-label={`Select proof step: ${step.marker} ${step.label} ${step.title}`}
                        aria-controls={`ff-proof-panel-${step.id}`}
                        title={`${step.marker} ${step.label}: ${step.title}`}
                        onMouseEnter={() => showStep(index)}
                        onMouseLeave={clearPreview}
                        onFocus={() => showStep(index)}
                        onBlur={clearPreview}
                        onClick={() => selectStep(index)}
                        className={`group flex h-6 min-w-0 items-center rounded-full px-1 ${interactiveMotion} hover:bg-[#e9f1d9]/58 dark:hover:bg-white/[0.06] ${focusRing}`}
                    >
                        <span className="sr-only">{step.marker} {step.label}: {step.title}</span>
                        <span
                            aria-hidden="true"
                            className={`h-2 w-full rounded-full ${interactiveMotion} ${isActive ? 'bg-[linear-gradient(90deg,#2a8f75,#8fd9c0)] shadow-[inset_0_1px_0_rgba(255,255,255,.28),0_10px_24px_-16px_rgba(42,143,117,.92)] dark:bg-[linear-gradient(90deg,#8fd9c0,#d7f8eb)] dark:shadow-[0_0_18px_rgba(143,217,192,.20)]' : 'bg-[#8c9888]/54 group-hover:bg-[#6fa58f]/66 dark:bg-white/[0.22] dark:group-hover:bg-white/[0.34]'}`}
                        />
                    </button>
                );
            })}
        </div>
    </div>
);

const InputStage = ({copy, isActive, stageClass}) => (
    <section id="ff-proof-panel-input" role="tabpanel" aria-hidden={!isActive} className={stageClass(0, 'border-[#d9dfd1] bg-white dark:border-white/[0.13] dark:bg-[#20251f]')}>
        <div className="flex items-start justify-between gap-3">
            <div>
                <p className={`${dataType} text-xs font-bold uppercase tracking-[0.16em] text-[#2f7c66] dark:text-[#8fd9c0]`}>01 {copy.inputStep}</p>
                <h2 className="mt-2 text-[24px] font-semibold leading-tight">{copy.upload}</h2>
            </div>
            <span className="flex size-10 shrink-0 items-center justify-center rounded-[14px] bg-[#17201b] text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]">
                <UploadCloud className="size-[18px]" strokeWidth={2.25} aria-hidden="true"/>
            </span>
        </div>
        <div className="mt-4 grid gap-2.5">
            <div className="rounded-[16px] border border-[#d9dfd1] bg-[#f7faf4] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,.72)] dark:border-white/[0.12] dark:bg-[#111612]">
                <p className={`${dataType} text-[10px] font-bold uppercase tracking-[0.14em] text-[#2f7c66] dark:text-[#8fd9c0]`}>{copy.uploadMeta}</p>
                <div className="mt-2 flex min-w-0 items-center gap-2 rounded-[13px] bg-white px-3 py-1.5 text-xs font-semibold text-[#17201b] shadow-sm dark:bg-white/[0.08] dark:text-[#f7f1e5]">
                    <Link2 className="size-3.5 shrink-0 text-[#2a8f75] dark:text-[#8fd9c0]" strokeWidth={2.25} aria-hidden="true"/>
                    <span className="ff-animated min-w-0 truncate" style={{animation: 'ffInputType 4.8s steps(38,end) infinite'}}>{copy.uploadSource}</span>
                    <span className="ff-animated h-4 w-px shrink-0 bg-[#2a8f75] dark:bg-[#8fd9c0]" style={{animation: 'ffInputCaret 4.8s ease-in-out infinite'}}/>
                </div>
            </div>

            <div className="ff-animated rounded-[17px] bg-[#17201b] p-3.5 text-[#fff8ec] shadow-[0_18px_42px_-34px_rgba(23,32,27,.72)]" style={{animation: 'ffCardPop 4.8s ease-out infinite'}}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <Play className="size-4 shrink-0 fill-current" strokeWidth={2.4} aria-hidden="true"/>
                            <p className="truncate text-sm font-semibold">{copy.uploadTitle}</p>
                        </div>
                        <p className="mt-1 text-xs font-medium text-white/66">{copy.uploadType}</p>
                    </div>
                    <span className={`${dataType} rounded-full bg-white/[0.10] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#f4d98c]`}>
                        {copy.uploadDuration}
                    </span>
                </div>
                <div className="mt-3 grid gap-2 sm:grid-cols-[0.9fr_1.1fr]">
                    <p className="rounded-[12px] bg-white/[0.08] px-3 py-2 text-xs font-semibold text-white/82">{copy.uploadSubtitle}</p>
                    <p className="rounded-[12px] bg-[#20392f] px-3 py-2 text-xs font-semibold text-[#d7f8eb]">{copy.uploadDecision}</p>
                </div>
                <div className="mt-3">
                    <div className="flex items-center justify-between gap-3 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/62">
                        <span>{copy.uploadProgress}</span>
                        <span>{copy.uploadQueued}</span>
                    </div>
                    <div className="relative mt-2 h-2.5 overflow-hidden rounded-full bg-white/18">
                        <span className="ff-animated absolute inset-y-0 left-0 w-full origin-left rounded-full bg-[#f4d98c]" style={{animation: 'ffProgressGrow 4.8s ease-in-out infinite', transform: 'scaleX(.72)'}}/>
                        <span className="ff-animated absolute -top-2 left-2 h-7 w-[3px] rounded-full bg-[#8fd9c0] shadow-[0_0_18px_rgba(143,217,192,.86)]" style={{animation: 'ffSceneScan 4.8s ease-in-out infinite'}}/>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                        {copy.uploadTags.map((tag, index) => {
                            const TagIcon = uploadTagIcons[index];
                            return (
                                <div key={tag} className="flex min-w-0 items-center gap-2 rounded-[12px] border border-white/[0.10] bg-white/[0.08] px-2.5 py-2 text-xs font-semibold text-white/84">
                                    <span className="flex size-7 shrink-0 items-center justify-center rounded-[9px] bg-[#8fd9c0]/16 text-[#a7efd8]">
                                        <TagIcon className="size-3.5" strokeWidth={2.25} aria-hidden="true"/>
                                    </span>
                                    <span className="min-w-0 truncate">{tag}</span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>
    </section>
);

const ProcessingStage = ({copy, isActive, stages, stageClass}) => (
    <section id="ff-proof-panel-processing" role="tabpanel" aria-hidden={!isActive} className={stageClass(1, 'border-[#cfe6d4] bg-[#f3fbf2] dark:border-[#8fd9c0]/24 dark:bg-[#14251b]')}>
        <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
                <p className={`${dataType} text-xs font-bold uppercase tracking-[0.16em] text-[#2f7c66] dark:text-[#8fd9c0]`}>02 {copy.processingStep}</p>
                <h2 className="mt-2 text-[26px] font-semibold leading-tight">{copy.processing}</h2>
            </div>
            <span className="inline-flex items-center gap-2 rounded-[13px] bg-white px-3 py-1.5 text-xs font-semibold text-[#2f7c66] shadow-sm dark:bg-[#8fd9c0]/16 dark:text-[#a7efd8]">
                <ScanSearch className="size-3.5" strokeWidth={2.2} aria-hidden="true"/>
                {copy.processingProgress}
            </span>
        </div>
        <div className="mt-5 rounded-[19px] border border-[#c7dfcc] bg-white p-4 shadow-[inset_0_1px_0_rgba(255,255,255,.72)] dark:border-[#8fd9c0]/22 dark:bg-[#101612]">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <p className="text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">{copy.processingMeta}</p>
                    <p className="mt-1 text-xs font-medium text-[#5f6a61] dark:text-white/[0.66]">{copy.processingMaterial}</p>
                </div>
                <span className={`${dataType} rounded-full bg-[#edf7ee] px-3 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[#2f5940] dark:bg-[#20392f] dark:text-[#d7f8eb]`}>{copy.processingHint}</span>
            </div>
            <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-[#dfe9dc] dark:bg-white/[0.12]">
                <span className="ff-animated block h-full origin-left rounded-full bg-[#2a8f75] dark:bg-[#8fd9c0]" style={{animation: 'ffProgressGrow 6.5s ease-in-out infinite', transform: 'scaleX(.64)'}}/>
            </div>
            <div className="mt-4 grid gap-2.5">
                {stages.map(({name, status, tone}, index) => (
                    <div key={name} className="flex items-center gap-3 rounded-[15px] border border-[#d9e7d6] bg-[#f8fbf5] px-3 py-2.5 dark:border-white/[0.10] dark:bg-white/[0.06]">
                        <span className={`flex size-7 shrink-0 items-center justify-center rounded-[10px] ${tone === 'done' ? 'bg-[#2a8f75] text-white dark:bg-[#8fd9c0] dark:text-[#111612]' : tone === 'running' ? 'bg-[#f4d98c] text-[#5c4214]' : 'bg-[#e8eee2] text-[#5f6a61] dark:bg-white/[0.10] dark:text-white/[0.66]'}`}>
                            {tone === 'done' ? <CheckCircle2 className="size-4" strokeWidth={2.4} aria-hidden="true"/> : <span className={`${dataType} text-[10px] font-bold`}>{index + 1}</span>}
                        </span>
                        <span className="min-w-0 flex-1 text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">{name}</span>
                        <span className="shrink-0 rounded-full bg-white px-2.5 py-1 text-[10px] font-semibold text-[#5f6a61] shadow-sm dark:bg-[#111612] dark:text-white/[0.70]">{status}</span>
                    </div>
                ))}
            </div>
        </div>
    </section>
);

const StudyReviewStage = ({copy, isActive, stageClass}) => (
    <section id="ff-proof-panel-study" role="tabpanel" aria-hidden={!isActive} className={stageClass(2, 'border-[#ecd8b8] bg-[#fff9ec] dark:border-[#f5d19a]/30 dark:bg-[#241d13]')}>
        <div>
            <p className={`${dataType} text-xs font-bold uppercase tracking-[0.16em] text-[#8a5a1f] dark:text-[#f4d98c]`}>03 {copy.studyStep}</p>
            <h2 className="mt-2 text-[26px] font-semibold leading-tight">{copy.study}</h2>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-[0.94fr_1.06fr]">
            <div className="rounded-[18px] bg-[#17201b] p-4 text-[#fff8ec] shadow-[0_16px_40px_-34px_rgba(23,32,27,.72)]">
                <div className="rounded-[15px] bg-white/[0.06] p-3">
                    <div className="flex items-center justify-between gap-3 text-xs font-semibold">
                        <span className={`${dataType} text-[10px] font-bold uppercase tracking-[0.14em] text-[#8fd9c0]`}>{copy.studyVideoLabel}</span>
                        <span className="flex items-center gap-2">
                            <Play className="size-3.5 fill-current" strokeWidth={2.4} aria-hidden="true"/>
                            {copy.studyTime}
                        </span>
                    </div>
                    <div className="mt-3 aspect-video rounded-[13px] bg-[radial-gradient(circle_at_42%_28%,rgba(143,217,192,.34),transparent_28%),linear-gradient(145deg,#31483d,#111612_72%)]">
                        <div className="flex h-full items-end justify-end p-3">
                            <span className="rounded-full bg-[#20392f] px-2.5 py-1 text-[10px] font-semibold text-[#a7efd8]">{copy.uploadDuration}</span>
                        </div>
                    </div>
                    <div className="relative mt-3 h-2 overflow-hidden rounded-full bg-white/18">
                        <span className="block h-full w-[42%] rounded-full bg-[#f4d98c]"/>
                    </div>
                </div>
                <div className="mt-3 rounded-[15px] border border-white/[0.10] bg-white/[0.08] p-3">
                    <p className={`${dataType} text-[10px] font-bold uppercase tracking-[0.14em] text-[#8fd9c0]`}>{copy.studyTranscriptLabel}</p>
                    <p className="mt-2 text-xs font-medium leading-5 text-white/78">{copy.studyCaption}</p>
                </div>
            </div>
            <div className="rounded-[18px] border border-[#e4d4b8] bg-white/84 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,.72)] dark:border-white/[0.13] dark:bg-white/[0.08]">
                <p className={`${dataType} text-[10px] font-bold uppercase tracking-[0.14em] text-[#8a5a1f] dark:text-[#f4d98c]`}>{copy.studyNoteArea}</p>
                <div className="mt-3 rounded-[14px] border border-[#e9d9bd] bg-[#fffdf7] p-3 dark:border-white/[0.10] dark:bg-[#111612]">
                    <p className={`${dataType} text-[10px] font-bold uppercase tracking-[0.12em] text-[#8a5a1f] dark:text-[#f4d98c]`}>{copy.studyNoteTitleLabel}</p>
                    <h3 className="mt-1 text-[19px] font-semibold leading-tight text-[#17201b] dark:text-[#f7f1e5]">{copy.studyNoteTitle}</h3>
                </div>
                <div className="mt-3 rounded-[14px] border border-[#e9d9bd] bg-[#fffdf7] p-3 dark:border-white/[0.10] dark:bg-[#111612]">
                    <p className={`${dataType} text-[10px] font-bold uppercase tracking-[0.12em] text-[#8a5a1f] dark:text-[#f4d98c]`}>{copy.studyChapterLabel}</p>
                    <p className="mt-1 text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">{copy.studyChapterTitle}</p>
                    <p className={`${dataType} mt-3 text-[10px] font-bold uppercase tracking-[0.12em] text-[#8a5a1f] dark:text-[#f4d98c]`}>{copy.studyNoteContentLabel}</p>
                    <p className="mt-1 rounded-[12px] bg-[#f7f1e5] px-3 py-2 text-sm font-semibold leading-6 text-[#4b3e2b] dark:bg-white/[0.06] dark:text-white/[0.82]">{copy.studyConclusion}</p>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                    <span className={`${dataType} rounded-full bg-[#fff3d5] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[#765321] dark:border dark:border-[#8fd9c0]/32 dark:bg-[#123c33] dark:text-[#a7efd8]`}>{copy.studyAnchorLabel}</span>
                    <span className="rounded-full border border-[#f1d093] px-2.5 py-1 text-xs font-semibold text-[#765321] dark:border-[#8fd9c0]/32 dark:bg-[#0e1713] dark:text-[#d7f8eb]">{copy.studyAnchor}</span>
                </div>
            </div>
        </div>
    </section>
);

const ExportStage = ({copy, exportGroups, isActive, stageClass}) => (
    <section id="ff-proof-panel-export" role="tabpanel" aria-hidden={!isActive} className={stageClass(3, 'border-[#d4dfc3] bg-[#f6faed] dark:border-[#d5e6b9]/24 dark:bg-[#1d2414]')}>
        <div>
            <p className={`${dataType} text-xs font-bold uppercase tracking-[0.16em] text-[#5b6d28] dark:text-[#d8e6b9]`}>04 {copy.exportStep}</p>
            <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
                <h2 className="text-[28px] font-semibold leading-tight">{copy.export}</h2>
                <p className="text-xs font-semibold text-[#64704d] dark:text-[#d8e6b9]">{copy.finalNote}</p>
            </div>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2">
            {exportGroups.map(({title, items}) => (
                <div key={title} className="rounded-[18px] border border-[#ccd9b7] bg-white/82 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,.72)] dark:border-white/[0.14] dark:bg-white/[0.08]">
                    <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">{title}</p>
                        <span className={`${dataType} rounded-full border border-transparent bg-[#e9f1d9] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[#52622f] dark:border-[#d5e6b9]/22 dark:bg-[#10160c] dark:text-[#d8e6b9]`}>{copy.exportFileCount}</span>
                    </div>
                    <div className="mt-3 grid gap-2">
                        {items.map(({label, format, hint, Icon}) => (
                            <div key={label} className="flex items-center gap-3 rounded-[14px] border border-[#dde7cf] bg-[#fbfdf7] px-3 py-2.5 dark:border-white/[0.10] dark:bg-white/[0.06]">
                                <span className="flex size-9 shrink-0 items-center justify-center rounded-[12px] bg-[#17201b] text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]">
                                    <Icon className="size-4" strokeWidth={2.2} aria-hidden="true"/>
                                </span>
                                <span className="min-w-0 flex-1">
                                    <span className="block truncate text-xs font-semibold text-[#2e3b21] dark:text-white/[0.84]">{label}</span>
                                    <span className="mt-0.5 block truncate text-[11px] font-medium text-[#66704f] dark:text-white/[0.56]">{hint}</span>
                                </span>
                                <span className={`${dataType} shrink-0 rounded-[10px] border border-[#cbd8b8] bg-white px-2 py-1 text-[10px] font-bold tracking-[0.08em] text-[#52622f] dark:border-[#d5e6b9]/18 dark:bg-[#10160c] dark:text-[#d8e6b9]`}>{format}</span>
                            </div>
                        ))}
                    </div>
                </div>
            ))}
        </div>
    </section>
);

const HeroProofDemo = ({copy}) => {
    const [selectedStep, setSelectedStep] = useState(0);
    const [previewStep, setPreviewStep] = useState(null);
    const [isManual, setIsManual] = useState(false);
    const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
    const activeStep = previewStep ?? selectedStep;
    const proofSteps = buildProofSteps(copy);
    const processingStages = buildProcessingStages(copy);
    const exportGroups = buildHeroExportGroups(copy);

    useEffect(() => {
        if (typeof window === 'undefined') return undefined;
        const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        const updateMotionPreference = () => setPrefersReducedMotion(mediaQuery.matches);
        updateMotionPreference();
        mediaQuery.addEventListener('change', updateMotionPreference);
        return () => mediaQuery.removeEventListener('change', updateMotionPreference);
    }, []);

    useEffect(() => {
        if (prefersReducedMotion || isManual || previewStep !== null) return undefined;
        const timer = window.setInterval(() => {
            setSelectedStep((current) => (current + 1) % proofSteps.length);
        }, carouselStepMs);
        return () => window.clearInterval(timer);
    }, [isManual, previewStep, prefersReducedMotion, proofSteps.length]);

    const showStep = (index) => setPreviewStep(index);
    const clearPreview = () => setPreviewStep(null);
    const selectStep = (index) => {
        setSelectedStep(index);
        setPreviewStep(null);
        setIsManual(true);
    };

    const proofViewportHeight = proofViewportHeights[activeStep] || proofViewportHeights[0];
    const stageClass = (index, extra = '') => proofStageClass(activeStep, index, extra);

    return (
    <div className="ff-motion-demo relative min-h-[520px] self-start lg:min-h-[560px]" aria-label={copy.label}>
        <HeroProofMotionStyles/>
        <div className="absolute left-8 top-12 h-28 w-[72%] rounded-full bg-[linear-gradient(90deg,rgba(42,143,117,.20),rgba(245,176,86,.20),rgba(119,169,230,.16))] blur-2xl"/>
        <article className="relative z-10 overflow-hidden rounded-[26px] border border-white/70 bg-white/84 shadow-[inset_0_1px_0_rgba(255,255,255,.72),0_38px_104px_-70px_rgba(55,73,48,.92)] backdrop-blur-md dark:border-white/[0.16] dark:bg-[#171d18]/88 dark:shadow-[inset_0_1px_0_rgba(255,255,255,.08),0_38px_104px_-72px_rgba(0,0,0,.86)]">
            <div className="flex h-[52px] items-center gap-2 border-b border-[#dce5d8]/86 bg-[#f5f7f1]/76 px-4 backdrop-blur-md dark:border-white/[0.10] dark:bg-white/[0.07] sm:px-5">
                <span className="size-2.5 rounded-full bg-[#d0d5d0] dark:bg-white/[0.26]"/>
                <span className="size-2.5 rounded-full bg-[#d0d5d0] dark:bg-white/[0.26]"/>
                <span className="size-2.5 rounded-full bg-[#d0d5d0] dark:bg-white/[0.26]"/>
                <span className={`ml-2 hidden min-w-0 rounded-[12px] bg-white px-4 py-1.5 text-[11px] font-semibold text-[#5f6a61] shadow-sm dark:bg-white/[0.08] dark:text-white/[0.64] sm:block ${dataType}`}>
                    {copy.path}
                </span>
            </div>

            <ProofStepIndicator
                steps={proofSteps}
                activeStep={activeStep}
                showStep={showStep}
                clearPreview={clearPreview}
                selectStep={selectStep}
            />

            <div className={`relative ${proofViewportHeight} px-4 pb-5 pt-4 sm:px-6`}>
                <InputStage copy={copy} isActive={activeStep === 0} stageClass={stageClass}/>
                <ProcessingStage copy={copy} isActive={activeStep === 1} stages={processingStages} stageClass={stageClass}/>
                <StudyReviewStage copy={copy} isActive={activeStep === 2} stageClass={stageClass}/>
                <ExportStage copy={copy} exportGroups={exportGroups} isActive={activeStep === 3} stageClass={stageClass}/>
            </div>
        </article>
    </div>
    );
};

const WorkflowCard = ({tone, title, items}) => {
    const isAfter = tone === 'after';
    const Icon = isAfter ? CheckCircle2 : RotateCcw;
    return (
        <article className={`rounded-[30px] border p-5 sm:p-6 ${isAfter ? 'border-[#bfe6ca] bg-[#ecfbf1] dark:border-[#8fd9c0]/22 dark:bg-[#8fd9c0]/10' : 'border-[#dbe0d6] bg-white/74 dark:border-white/[0.12] dark:bg-white/[0.055]'}`}>
            <div className="flex items-center gap-3">
                <span className={`flex size-11 items-center justify-center rounded-[16px] ${isAfter ? 'bg-[#2a8f75] text-white' : 'bg-[#17201b] text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]'}`}>
                    <Icon className="size-5" strokeWidth={2.2} aria-hidden="true"/>
                </span>
                <h3 className={`${displayType} text-[24px] font-semibold leading-tight tracking-normal text-[#17201b] dark:text-[#f7f1e5]`}>{title}</h3>
            </div>
            <div className="mt-5 space-y-4">
                {items.map(([itemTitle, desc]) => (
                    <div key={itemTitle} className="grid gap-1 border-t border-[#dbe0d6] pt-4 dark:border-white/[0.10]">
                        <p className="text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">{itemTitle}</p>
                        <p className="text-sm font-medium leading-6 text-[#626d64] dark:text-white/[0.66]">{desc}</p>
                    </div>
                ))}
            </div>
        </article>
    );
};

const Landing = () => {
    const [language, setLanguage] = useState(() => {
        if (typeof window === 'undefined') return 'en';
        return window.localStorage.getItem('fluentflow-landing-language') || 'en';
    });
    const [theme, setTheme] = useState(() => {
        if (typeof window === 'undefined') return 'light';
        const savedTheme = window.localStorage.getItem('fluentflow-landing-theme');
        if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    });
    const copy = landingCopy[language] || landingCopy.en;
    const ThemeIcon = theme === 'dark' ? Sun : Moon;

    useEffect(() => {
        if (typeof window === 'undefined') return;
        window.localStorage.setItem('fluentflow-landing-language', language);
    }, [language]);

    useEffect(() => {
        if (typeof document === 'undefined' || typeof window === 'undefined') return;
        document.documentElement.classList.toggle('dark', theme === 'dark');
        window.localStorage.setItem('fluentflow-landing-theme', theme);
    }, [theme]);

    return (
    <main
        id="main-content"
        className={`relative h-dvh overflow-y-auto scroll-smooth bg-[#fff8ec] text-[#17201b] motion-reduce:scroll-auto dark:bg-[#111612] dark:text-[#f7f1e5] ${bodyType}`}
    >
        <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(circle_at_18%_10%,rgba(42,143,117,.16),transparent_28rem),radial-gradient(circle_at_84%_12%,rgba(245,176,86,.18),transparent_30rem),linear-gradient(180deg,#fff8ec_0%,#f6fbf2_52%,#fffaf0_100%)] dark:bg-[radial-gradient(circle_at_18%_10%,rgba(143,217,192,.12),transparent_28rem),radial-gradient(circle_at_84%_12%,rgba(245,176,86,.10),transparent_30rem),linear-gradient(180deg,#111612_0%,#161d18_55%,#111612_100%)]"/>
        <div className="pointer-events-none fixed inset-0 z-0 opacity-[0.16] mix-blend-multiply dark:hidden" style={{backgroundImage: lightGrain}}/>
        <div className="pointer-events-none fixed inset-0 z-0 hidden opacity-[0.085] mix-blend-screen dark:block" style={{backgroundImage: darkGrain}}/>
        <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(circle_at_52%_0%,rgba(255,255,255,.42),transparent_25rem),linear-gradient(135deg,rgba(255,255,255,.24),rgba(255,255,255,0)_44%)] opacity-[0.38] dark:bg-[radial-gradient(circle_at_52%_0%,rgba(255,255,255,.10),transparent_25rem),linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,255,255,0)_46%)] dark:opacity-[0.16]"/>
        <div
            className="pointer-events-none fixed inset-0 z-0 opacity-[0.24] mix-blend-multiply dark:hidden"
            style={{
                backgroundImage: `${lightPageFrost}, radial-gradient(circle, rgba(23,32,27,.18) 0 0.55px, transparent 0.7px)`,
                backgroundSize: '160px 160px, 5px 5px',
            }}
        />
        <div
            className="pointer-events-none fixed inset-0 z-0 hidden opacity-[0.12] mix-blend-screen dark:block"
            style={{
                backgroundImage: `${darkPageFrost}, radial-gradient(circle, rgba(255,255,255,.26) 0 0.55px, transparent 0.75px)`,
                backgroundSize: '160px 160px, 6px 6px',
            }}
        />
        <a href="#homepage-hero" className={`sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-[#17201b] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[#fff8ec] dark:focus:bg-[#f7f1e5] dark:focus:text-[#17201b] ${focusRing}`}>
            Skip to main content
        </a>

        <header className="sticky top-0 z-40 border-b border-[#dce5d8]/90 bg-[#fff8ec]/72 shadow-[inset_0_1px_0_rgba(255,255,255,.68)] backdrop-blur-xl dark:border-white/[0.11] dark:bg-[#111612]/82 dark:shadow-[inset_0_1px_0_rgba(255,255,255,.06)]">
            <div className="mx-auto flex h-[70px] max-w-7xl items-center justify-between gap-5 px-5 sm:px-6 lg:px-8">
                <Link to="/" className={`flex min-w-0 items-center gap-3 rounded-[16px] ${focusRing}`} aria-label="FluentFlow">
                    <LogoMark/>
                    <span className={`truncate text-base font-semibold tracking-normal ${displayType}`}>FluentFlow</span>
                </Link>
                <nav className="hidden items-center gap-7 text-sm font-medium text-[#5f6a61] dark:text-white/[0.68] md:flex">
                    <a href="#workflow" className={`${interactiveMotion} rounded-full px-1 hover:text-[#17201b] dark:hover:text-white ${focusRing}`}>{copy.nav.studyFlow}</a>
                    <a href="#quality" className={`${interactiveMotion} rounded-full px-1 hover:text-[#17201b] dark:hover:text-white ${focusRing}`}>{copy.nav.noteQuality}</a>
                    <a href="#sources" className={`${interactiveMotion} rounded-full px-1 hover:text-[#17201b] dark:hover:text-white ${focusRing}`}>{copy.nav.sources}</a>
                </nav>
                <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
                    <div className="flex h-10 items-center rounded-full border border-[#dce5d8] bg-white/62 p-1 shadow-[0_12px_30px_-28px_rgba(46,73,58,.42)] dark:border-white/[0.15] dark:bg-white/[0.055]" aria-label={copy.controls.languageLabel}>
                        {[
                            ['en', 'EN', copy.controls.switchToEnglish],
                            ['zh', '中', copy.controls.switchToChinese],
                        ].map(([value, label, ariaLabel]) => (
                            <button
                                key={value}
                                type="button"
                                aria-label={ariaLabel}
                                title={ariaLabel}
                                onClick={() => setLanguage(value)}
                                className={`h-8 min-w-8 rounded-full px-2 text-xs font-semibold ${interactiveMotion} ${language === value ? 'bg-[#17201b] text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]' : 'text-[#5f6a61] hover:bg-[#f4fbf5] hover:text-[#17201b] dark:text-white/[0.68] dark:hover:bg-white/[0.10] dark:hover:text-white'} ${focusRing}`}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                    <button
                        type="button"
                        aria-label={theme === 'dark' ? copy.controls.useLight : copy.controls.useDark}
                        title={theme === 'dark' ? copy.controls.useLight : copy.controls.useDark}
                        onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}
                        className={`flex size-10 touch-manipulation items-center justify-center rounded-full border border-[#dce5d8] bg-white/62 text-[#17201b] ${interactiveMotion} hover:bg-[#f4fbf5] active:translate-y-px dark:border-white/[0.15] dark:bg-white/[0.055] dark:text-white/[0.88] dark:hover:bg-white/[0.10] ${focusRing}`}
                    >
                        <ThemeIcon className="size-4" strokeWidth={2.2} aria-hidden="true"/>
                    </button>
                    <Link to="/app" className={`hidden h-10 touch-manipulation items-center justify-center rounded-full border border-[#dce5d8] bg-white/60 px-4 text-sm font-medium text-[#17201b] ${interactiveMotion} hover:bg-[#f4fbf5] active:translate-y-px dark:border-white/[0.15] dark:bg-white/[0.055] dark:text-white/[0.88] dark:hover:bg-white/[0.10] sm:inline-flex ${focusRing}`}>
                        {copy.nav.openApp}
                    </Link>
                    <Link to="/media-text" className={`inline-flex h-10 touch-manipulation items-center justify-center gap-2 rounded-full bg-[#17201b] px-4 text-sm font-semibold text-[#fff8ec] ${interactiveMotion} hover:bg-[#24352d] active:translate-y-px dark:bg-[#f7f1e5] dark:text-[#17201b] dark:hover:bg-[#e9dcc8] ${focusRing}`}>
                        <span className="hidden sm:inline">{copy.nav.startVideo}</span>
                        <span className="sm:hidden">{copy.nav.startShort}</span>
                        <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden="true"/>
                    </Link>
                </div>
            </div>
        </header>

        <section id="homepage-hero" className={`${sectionShell} relative z-10 grid min-h-[calc(100dvh-70px)] scroll-mt-24 items-start gap-10 py-10 sm:py-12 lg:grid-cols-[0.9fr_1.1fr] lg:py-14`}>
            <div className="max-w-3xl">
                <p className={eyebrowClass}>{copy.hero.eyebrow}</p>
                <h1 className={`mt-5 max-w-[10.8em] ${displayType} text-[42px] font-bold leading-[1.06] tracking-normal text-[#17201b] [text-wrap:balance] dark:text-[#f7f1e5] sm:text-[56px] lg:text-[68px]`}>
                    {copy.hero.title}
                </h1>
                <p className="mt-6 max-w-[62ch] text-[17px] font-medium leading-8 text-[#5f6a61] [text-wrap:pretty] dark:text-white/[0.70] sm:text-[18px]">
                    {copy.hero.desc}
                </p>
                <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                    <Link to="/media-text" className={primaryButton}>
                        {copy.hero.primary}
                        <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden="true"/>
                    </Link>
                    <a href="#workflow" className={secondaryButton}>
                        {copy.hero.secondary}
                    </a>
                </div>
                {copy.hero.note ? (
                    <p className={`${dataType} mt-5 max-w-[54ch] text-[12px] font-medium leading-6 text-[#6f7b70] dark:text-white/[0.54]`}>
                        {copy.hero.note}
                    </p>
                ) : null}
            </div>
            <HeroProofDemo copy={copy.heroVisual}/>
        </section>

        <section id="workflow" className="relative z-10 scroll-mt-24 border-y border-[#dce5d8] bg-white/64 shadow-[inset_0_1px_0_rgba(255,255,255,.58)] backdrop-blur-md dark:border-white/[0.10] dark:bg-white/[0.045] dark:shadow-[inset_0_1px_0_rgba(255,255,255,.06)]">
            <div className={`${sectionShell} py-16 lg:py-24`}>
                <SectionHeader
                    eyebrow={copy.workflow.eyebrow}
                    title={copy.workflow.title}
                    desc={copy.workflow.desc}
                />
                <div className="mt-10 grid gap-4 lg:grid-cols-2">
                    <WorkflowCard
                        tone="before"
                        title={copy.workflow.beforeTitle}
                        items={copy.workflow.beforeItems}
                    />
                    <WorkflowCard
                        tone="after"
                        title={copy.workflow.afterTitle}
                        items={copy.workflow.afterItems}
                    />
                </div>
            </div>
        </section>

        <section id="quality" className={`${sectionShell} relative z-10 scroll-mt-24 py-16 lg:py-24`}>
                <SectionHeader
                eyebrow={copy.quality.eyebrow}
                title={copy.quality.title}
                desc={copy.quality.desc}
            />
            <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {copy.quality.items.map(([title, desc], index) => {
                    const icons = [BookOpenText, ScanSearch, Captions, FileText, Image, Download];
                    const Icon = icons[index] || BookOpenText;
                    return (
                        <article key={title} className={`rounded-[28px] border border-white/68 bg-white/68 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,.62),0_20px_58px_-46px_rgba(46,73,58,.45)] backdrop-blur-md ${interactiveMotion} hover:-translate-y-0.5 hover:border-[#9fcab8] hover:bg-white/82 dark:border-white/[0.12] dark:bg-white/[0.065] dark:shadow-[inset_0_1px_0_rgba(255,255,255,.06)] dark:hover:border-[#8fd9c0]/45`}>
                            <Icon className="size-6 text-[#2f7c66] dark:text-[#8fd9c0]" strokeWidth={2.05} aria-hidden="true"/>
                            <h3 className={`mt-5 ${displayType} text-xl font-semibold leading-tight tracking-normal text-[#17201b] dark:text-[#f7f1e5]`}>{title}</h3>
                            <p className="mt-3 text-sm font-medium leading-6 text-[#626d64] dark:text-white/[0.66]">{desc}</p>
                        </article>
                    );
                })}
            </div>
        </section>

        <section id="sources" className="relative z-10 scroll-mt-24 border-y border-[#dce5d8] bg-[#f3fbf2]/72 shadow-[inset_0_1px_0_rgba(255,255,255,.58)] backdrop-blur-md dark:border-white/[0.10] dark:bg-[#8fd9c0]/6 dark:shadow-[inset_0_1px_0_rgba(255,255,255,.06)]">
            <div className={`${sectionShell} grid gap-10 py-16 lg:grid-cols-[0.86fr_1.14fr] lg:items-center lg:py-24`}>
                <div>
                    <p className={eyebrowClass}>{copy.sources.eyebrow}</p>
                    <h2 className={`mt-4 max-w-[12em] ${displayType} text-[34px] font-bold leading-[1.08] tracking-normal text-[#17201b] [text-wrap:balance] dark:text-[#f7f1e5] sm:text-[46px]`}>
                        {copy.sources.title}
                    </h2>
                    <p className="mt-5 max-w-[60ch] text-base font-medium leading-relaxed text-[#626d64] dark:text-white/[0.66]">
                        {copy.sources.desc}
                    </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                    {sourceIconItems.map(({key, Icon, tone}) => (
                        <div key={key} className="flex min-h-[76px] items-center gap-3 rounded-[24px] border border-white/68 bg-white/70 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,.58),0_16px_42px_-38px_rgba(46,73,58,.35)] backdrop-blur-md dark:border-white/[0.12] dark:bg-white/[0.065] dark:shadow-[inset_0_1px_0_rgba(255,255,255,.06)]">
                            <span className={`flex size-10 shrink-0 items-center justify-center rounded-[15px] shadow-[inset_0_0_0_1px_rgba(23,32,27,.10)] ${tone}`}>
                                <Icon className="size-5" strokeWidth={2.25} aria-hidden="true"/>
                            </span>
                            <p className="text-sm font-semibold leading-tight text-[#17201b] dark:text-[#f7f1e5]">{copy.sources.items[key]}</p>
                        </div>
                    ))}
                </div>
            </div>
        </section>

        <section className={`${sectionShell} relative z-10 py-16 lg:py-24`}>
            <SectionHeader
                eyebrow={copy.output.eyebrow}
                title={copy.output.title}
                desc={copy.output.desc}
            />
            <div className="mt-10 grid gap-4 lg:grid-cols-4">
                {copy.output.items.map(([title, desc], index) => {
                    const icons = [FileText, Captions, Film, CheckCircle2];
                    const Icon = icons[index] || FileText;
                    return (
                        <article key={title} className="rounded-[28px] border border-white/68 bg-white/68 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,.62),0_18px_52px_-44px_rgba(46,73,58,.42)] backdrop-blur-md dark:border-white/[0.11] dark:bg-white/[0.065] dark:shadow-[inset_0_1px_0_rgba(255,255,255,.06)]">
                            <Icon className="size-6 text-[#2f7c66] dark:text-[#8fd9c0]" strokeWidth={2.05} aria-hidden="true"/>
                            <h3 className={`mt-5 ${displayType} text-xl font-semibold leading-tight tracking-normal text-[#17201b] dark:text-[#f7f1e5]`}>{title}</h3>
                            <p className="mt-3 text-sm font-medium leading-6 text-[#626d64] dark:text-white/[0.66]">{desc}</p>
                        </article>
                    );
                })}
            </div>
        </section>

        <section className={`${sectionShell} relative z-10 pb-16 lg:pb-24`}>
            <div className="overflow-hidden rounded-[36px] border border-[#21362c] bg-[#17201b] p-6 text-[#fff8ec] shadow-[0_28px_80px_-48px_rgba(23,32,27,.82)] sm:p-8 lg:flex lg:items-center lg:justify-between lg:gap-10 dark:border-white/[0.12]">
                <div className="pointer-events-none absolute inset-x-0 h-24 bg-[linear-gradient(90deg,rgba(143,217,192,.22),rgba(245,176,86,.18),rgba(119,169,230,.16))] blur-3xl"/>
                <div className="relative max-w-2xl">
                    <p className={`${dataType} text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8fd9c0]`}>{copy.cta.eyebrow}</p>
                    <h2 className={`mt-3 ${displayType} text-[34px] font-bold leading-[1.08] tracking-normal [text-wrap:balance] sm:text-[48px]`}>
                        {copy.cta.title}
                    </h2>
                    <p className="mt-4 text-base font-medium leading-relaxed text-white/[0.72]">
                        {copy.cta.desc}
                    </p>
                </div>
                <div className="relative mt-8 flex flex-col gap-3 sm:flex-row lg:mt-0">
                    <Link to="/media-text" className="inline-flex h-12 touch-manipulation items-center justify-center gap-2 rounded-full bg-[#fff8ec] px-6 text-sm font-semibold text-[#17201b] transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200 ease-out hover:-translate-y-0.5 hover:bg-[#e9dcc8] active:translate-y-px">
                        {copy.cta.primary}
                        <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden="true"/>
                    </Link>
                    <Link to="/agent" className="inline-flex h-12 touch-manipulation items-center justify-center rounded-full border border-white/[0.18] bg-white/[0.06] px-6 text-sm font-semibold text-white transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200 ease-out hover:-translate-y-0.5 hover:bg-white/[0.12] active:translate-y-px">
                        {copy.cta.secondary}
                    </Link>
                </div>
            </div>
        </section>
    </main>
    );
};

export default Landing;
