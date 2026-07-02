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

const timeline = ['00:00', '18:42', '39:10', '1:12:44'];

const sourceIconItems = [
    ['courses', BookOpenText, 'bg-[#f4d98c] text-[#5c4214] dark:bg-[#f4d98c] dark:text-[#36240b]'],
    ['lectures', MicVocal, 'bg-[#b9dfd1] text-[#123f33] dark:bg-[#9bd9c2] dark:text-[#0b3026]'],
    ['recordings', MonitorPlay, 'bg-[#bfd7f3] text-[#183b61] dark:bg-[#a8caef] dark:text-[#102f50]'],
    ['localMedia', FileVideo2, 'bg-[#f3c2ac] text-[#642d1c] dark:bg-[#efb49a] dark:text-[#51210f]'],
    ['subtitles', Captions, 'bg-[#d6c7f2] text-[#3e2c68] dark:bg-[#c8b4ee] dark:text-[#2d1d55]'],
    ['links', Link2, 'bg-[#d0d9bc] text-[#344418] dark:bg-[#c1d49f] dark:text-[#27350f]'],
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
            label: 'Animated product proof scene: upload a long video, generate notes, compare uncertain details, and export the study asset',
            eyebrow: 'Study workspace',
            path: 'fluentflow.app/video-note',
            upload: 'Upload / paste a long video',
            uploadMeta: 'Course lecture · 1:12:44',
            uploadHint: 'video link + local file',
            notes: 'Notes generated first',
            noteTitle: '03 Why attention works',
            noteBulletOne: 'Structured chapter and conclusion',
            noteBulletTwo: 'Transcript line and key moment anchor',
            anchor: '18:42 source anchor',
            compare: 'Compare and correct',
            compareHint: 'Watch beside the note',
            original: 'Original: "context windows"',
            corrected: 'Corrected: "attention window"',
            accepted: 'Fix accepted',
            export: 'Export study asset',
            exportHint: 'Markdown · PDF · Feishu',
            finalNote: 'Ready to study with the video.',
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
            label: '动态产品证明场景：上传长视频，生成笔记，对照修正，再导出学习资产',
            eyebrow: '学习工作区',
            path: 'fluentflow.app/video-note',
            upload: '上传或粘贴长视频',
            uploadMeta: '课程讲座 · 1:12:44',
            uploadHint: '视频链接 + 本地文件',
            notes: '先生成学习笔记',
            noteTitle: '03 注意力机制为什么有效',
            noteBulletOne: '结构化章节和结论先出现',
            noteBulletTwo: '字幕行和关键画面可回查',
            anchor: '18:42 来源锚点',
            compare: '对照视频修正',
            compareHint: '视频和笔记并排复查',
            original: '原文："上下文窗口"',
            corrected: '修正："注意力窗口"',
            accepted: '已接受修正',
            export: '导出学习资产',
            exportHint: 'Markdown · PDF · 飞书',
            finalNote: '准备好对着视频学习。',
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

const HeroVisual = ({copy}) => (
    <div className="ff-motion-demo relative min-h-[500px] lg:min-h-[540px]" aria-label={copy.label}>
        <style>{`
            @keyframes ffCarouselSlide {
                0%, 22% { opacity: 1; transform: translateY(0) scale(1); pointer-events: auto; }
                27%, 100% { opacity: 0; transform: translateY(12px) scale(.985); pointer-events: none; }
            }
            @keyframes ffSceneScan {
                0%, 12% { transform: translateX(0); opacity: .7; }
                48%, 78% { transform: translateX(190px); opacity: 1; }
                100% { transform: translateX(0); opacity: .7; }
            }
            @keyframes ffBrowserProgress {
                0% { transform: scaleX(.12); }
                100% { transform: scaleX(1); }
            }
            @keyframes ffNoteLine {
                0%, 18% { transform: scaleX(.22); opacity: .52; }
                46%, 100% { transform: scaleX(1); opacity: 1; }
            }
            @media (prefers-reduced-motion: reduce) {
                .ff-motion-demo .ff-animated {
                    animation: none !important;
                    transform: none !important;
                }
                .ff-motion-demo .ff-carousel-slide {
                    display: none !important;
                    opacity: 1 !important;
                }
                .ff-motion-demo .ff-carousel-slide:last-child {
                    display: grid !important;
                }
            }
        `}</style>
        <div className="absolute left-8 top-12 h-28 w-[72%] rounded-full bg-[linear-gradient(90deg,rgba(42,143,117,.20),rgba(245,176,86,.20),rgba(119,169,230,.16))] blur-2xl"/>
        <article className="relative z-10 overflow-hidden rounded-[34px] border border-white/70 bg-white/84 shadow-[inset_0_1px_0_rgba(255,255,255,.72),0_38px_104px_-70px_rgba(55,73,48,.92)] backdrop-blur-md dark:border-white/[0.16] dark:bg-[#171d18]/88 dark:shadow-[inset_0_1px_0_rgba(255,255,255,.08),0_38px_104px_-72px_rgba(0,0,0,.86)]">
            <div className="flex h-14 items-center gap-2 border-b border-[#dce5d8]/86 bg-[#f5f7f1]/76 px-5 backdrop-blur-md dark:border-white/[0.10] dark:bg-white/[0.07]">
                <span className="size-3 rounded-full bg-[#d0d5d0] dark:bg-white/[0.26]"/>
                <span className="size-3 rounded-full bg-[#d0d5d0] dark:bg-white/[0.26]"/>
                <span className="size-3 rounded-full bg-[#d0d5d0] dark:bg-white/[0.26]"/>
                <span className={`ml-3 hidden min-w-0 rounded-full bg-white px-4 py-1.5 text-[11px] font-semibold text-[#5f6a61] shadow-sm dark:bg-white/[0.08] dark:text-white/[0.64] sm:block ${dataType}`}>
                    {copy.path}
                </span>
            </div>

            <div className="px-5 pt-5 sm:px-7">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className={`${dataType} rounded-full bg-[#e7f7ed] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#276f5b] dark:bg-[#8fd9c0]/16 dark:text-[#a7efd8]`}>
                        {copy.eyebrow}
                    </span>
                    <span className={`${dataType} text-[11px] font-medium text-[#5f6a61] dark:text-white/[0.62]`}>{copy.anchor}</span>
                </div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-[#dce5d8] dark:bg-white/[0.12]">
                    <span className="ff-animated block h-full origin-left rounded-full bg-[linear-gradient(90deg,#2a8f75,#f4d98c,#77a9e6)]" style={{animation: 'ffBrowserProgress 12s linear infinite'}}/>
                </div>
            </div>

            <div className="relative min-h-[365px] px-5 pb-6 pt-5 sm:min-h-[390px] sm:px-7">
                <section className="ff-proof-stage ff-carousel-slide ff-animated absolute inset-x-5 top-5 grid min-h-[320px] content-center rounded-[28px] border border-[#d9dfd1] bg-white p-5 text-[#17201b] shadow-[0_20px_58px_-42px_rgba(46,73,58,.45)] dark:border-white/[0.13] dark:bg-[#20251f] dark:text-[#f7f1e5] sm:inset-x-7 sm:min-h-[345px] sm:p-7" style={{animation: 'ffCarouselSlide 12s ease-in-out infinite'}}>
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <p className={`${dataType} text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f7c66] dark:text-[#8fd9c0]`}>01 Input</p>
                            <h2 className="mt-3 text-2xl font-semibold leading-tight">{copy.upload}</h2>
                            <p className="mt-2 text-sm font-medium text-[#5f6a61] dark:text-white/[0.68]">{copy.uploadMeta}</p>
                        </div>
                        <span className="flex size-12 shrink-0 items-center justify-center rounded-[18px] bg-[#17201b] text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]">
                            <UploadCloud className="size-5" strokeWidth={2.25} aria-hidden="true"/>
                        </span>
                    </div>
                    <div className="mt-8 rounded-[22px] bg-[#17201b] p-4 text-[#fff8ec]">
                        <div className="flex items-center gap-2 text-sm font-semibold">
                            <Play className="size-4 fill-current" strokeWidth={2.4} aria-hidden="true"/>
                            <span>{copy.uploadHint}</span>
                        </div>
                        <div className="relative mt-4 h-2.5 rounded-full bg-white/20">
                            <span className="absolute inset-y-0 left-0 w-[64%] rounded-full bg-[#f4d98c]"/>
                            <span className="ff-animated absolute -top-2 left-2 h-7 w-[3px] rounded-full bg-[#8fd9c0] shadow-[0_0_18px_rgba(143,217,192,.86)]" style={{animation: 'ffSceneScan 3s ease-in-out infinite'}}/>
                        </div>
                        <div className={`mt-3 grid grid-cols-4 gap-2 text-[10px] font-medium tabular-nums text-white/64 ${dataType}`}>
                            {timeline.map((item) => <span key={item}>{item}</span>)}
                        </div>
                    </div>
                </section>

                <section className="ff-proof-stage ff-carousel-slide ff-animated absolute inset-x-5 top-5 grid min-h-[320px] content-center rounded-[28px] border border-[#cfe6d4] bg-[#f3fbf2] p-5 text-[#17201b] opacity-0 shadow-[0_20px_58px_-42px_rgba(46,73,58,.45)] dark:border-[#8fd9c0]/24 dark:bg-[#14251b] dark:text-[#f7f1e5] sm:inset-x-7 sm:min-h-[345px] sm:p-7" style={{animation: 'ffCarouselSlide 12s ease-in-out infinite 3s'}}>
                    <p className={`${dataType} text-[10px] font-semibold uppercase tracking-[0.16em] text-[#2f7c66] dark:text-[#8fd9c0]`}>02 Notes</p>
                    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                        <h2 className="text-2xl font-semibold leading-tight">{copy.notes}</h2>
                        <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#2f7c66] shadow-sm dark:bg-[#8fd9c0]/16 dark:text-[#a7efd8]">{copy.anchor}</span>
                    </div>
                    <div className="mt-7 rounded-[24px] border border-[#c7dfcc] bg-white p-5 dark:border-[#8fd9c0]/22 dark:bg-[#101612]">
                        <p className={`${displayType} text-2xl font-semibold leading-tight text-[#17201b] dark:text-[#f7f1e5]`}>{copy.noteTitle}</p>
                        {[copy.noteBulletOne, copy.noteBulletTwo].map((item, index) => (
                            <div key={item} className="mt-4 flex items-center gap-3">
                                <span className="size-2 rounded-full bg-[#2a8f75]"/>
                                <span className="text-sm font-medium text-[#4f5f53] dark:text-white/[0.72]">{item}</span>
                                <span className="ff-animated h-1.5 origin-left flex-1 rounded-full bg-[#b6d9c0] dark:bg-[#467d65]" style={{animation: `ffNoteLine 3s ease-in-out infinite ${index * 0.35}s`}}/>
                            </div>
                        ))}
                    </div>
                </section>

                <section className="ff-proof-stage ff-carousel-slide ff-animated absolute inset-x-5 top-5 grid min-h-[320px] content-center rounded-[28px] border border-[#ecd8b8] bg-[#fff9ec] p-5 text-[#17201b] opacity-0 shadow-[0_20px_58px_-42px_rgba(46,73,58,.45)] dark:border-[#f5d19a]/30 dark:bg-[#241d13] dark:text-[#f7f1e5] sm:inset-x-7 sm:min-h-[345px] sm:p-7" style={{animation: 'ffCarouselSlide 12s ease-in-out infinite 6s'}}>
                    <div className="grid gap-5 sm:grid-cols-[0.9fr_1.1fr] sm:items-center">
                        <div className="rounded-[24px] bg-[#17201b] p-4 text-[#fff8ec]">
                            <div className="flex items-center gap-2 text-xs font-semibold">
                                <Play className="size-3.5 fill-current" strokeWidth={2.4} aria-hidden="true"/>
                                <span>{copy.compareHint}</span>
                            </div>
                            <div className="mt-4 aspect-video rounded-[18px] bg-[radial-gradient(circle_at_42%_28%,rgba(143,217,192,.34),transparent_28%),linear-gradient(145deg,#31483d,#111612_72%)]"/>
                        </div>
                        <div>
                            <p className={`${dataType} text-[10px] font-semibold uppercase tracking-[0.16em] text-[#8a5a1f] dark:text-[#f4d98c]`}>03 Review</p>
                            <h2 className="mt-3 text-2xl font-semibold leading-tight">{copy.compare}</h2>
                            <div className="mt-5 grid gap-2">
                                <p className="rounded-[14px] bg-white px-3 py-2 text-xs font-medium text-[#76664e] dark:bg-white/[0.10] dark:text-white/[0.70]">{copy.original}</p>
                                <p className="rounded-[14px] bg-[#e7f7ed] px-3 py-2 text-xs font-semibold text-[#246b57] dark:bg-[#8fd9c0]/16 dark:text-[#a7efd8]">{copy.corrected}</p>
                            </div>
                            <p className="mt-4 inline-flex rounded-full bg-[#17201b] px-3 py-1 text-xs font-semibold text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]">{copy.accepted}</p>
                        </div>
                    </div>
                </section>

                <section className="ff-proof-stage ff-carousel-slide ff-animated absolute inset-x-5 top-5 grid min-h-[320px] content-center rounded-[28px] border border-[#d4dfc3] bg-[#f6faed] p-5 text-[#17201b] opacity-0 shadow-[0_20px_58px_-42px_rgba(46,73,58,.45)] dark:border-[#d5e6b9]/24 dark:bg-[#1d2414] dark:text-[#f7f1e5] sm:inset-x-7 sm:min-h-[345px] sm:p-7" style={{animation: 'ffCarouselSlide 12s ease-in-out infinite 9s'}}>
                    <div className="mx-auto max-w-sm text-center">
                        <span className="mx-auto flex size-14 items-center justify-center rounded-[20px] bg-[#17201b] text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]">
                            <Download className="size-6" strokeWidth={2.2} aria-hidden="true"/>
                        </span>
                        <p className={`${dataType} mt-6 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#5b6d28] dark:text-[#d8e6b9]`}>04 Export</p>
                        <h2 className="mt-3 text-3xl font-semibold leading-tight">{copy.export}</h2>
                        <p className="mt-3 text-sm font-medium text-[#64704d] dark:text-[#d8e6b9]">{copy.finalNote}</p>
                        <div className="mt-7 flex flex-wrap justify-center gap-2">
                            {copy.exportHint.split(' · ').map((item) => (
                                <span key={item} className="rounded-full border border-[#ccd9b7] bg-white px-4 py-2 text-xs font-semibold text-[#46552a] dark:border-white/[0.16] dark:bg-white/[0.10] dark:text-white/[0.78]">{item}</span>
                            ))}
                        </div>
                    </div>
                </section>
            </div>
        </article>
    </div>
);

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

        <section id="homepage-hero" className={`${sectionShell} relative z-10 grid min-h-[calc(100dvh-70px)] scroll-mt-24 items-center gap-10 py-10 sm:py-12 lg:grid-cols-[0.9fr_1.1fr] lg:py-14`}>
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
            <HeroVisual copy={copy.heroVisual}/>
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
                    {sourceIconItems.map(([key, Icon, tone]) => (
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
