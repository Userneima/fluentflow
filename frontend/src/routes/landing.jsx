import {Link} from 'react-router-dom';
import {
    ArrowRight,
    BookOpenText,
    Brain,
    CheckCircle2,
    ChevronRight,
    Download,
    FileText,
    Film,
    Languages,
    MessageSquareText,
    Play,
    Sparkles,
    UploadCloud,
} from 'lucide-react';
import {useI18n} from '../app/shared.jsx';

const LogoMark = () => (
    <span className="flex size-10 items-center justify-center rounded-[14px] bg-[#111111] text-white shadow-[0_18px_42px_-28px_rgba(17,17,17,.65)] dark:bg-[#f4f0e8] dark:text-[#111111]">
        <svg viewBox="0 0 64 64" className="size-[30px]" fill="none" aria-hidden="true">
            <rect x="17" y="19" width="28" height="26" rx="8" fill="currentColor"/>
            <rect x="43" y="25" width="8" height="14" rx="4" fill="currentColor"/>
            <path d="M24 29h13M24 36h9" stroke="var(--ff-logo-line, #111111)" strokeWidth="4.2" strokeLinecap="round" className="[--ff-logo-line:#111111] dark:[--ff-logo-line:#f4f0e8]"/>
        </svg>
    </span>
);

const content = {
    zh: {
        nav: {
            product: '产品',
            workflow: '工作流',
            useCases: '场景',
            app: '进入应用',
            start: '开始处理视频',
        },
        hero: {
            label: 'FluentFlow Agent',
            title: '把长视频变成可复查的学习笔记',
            desc: '粘贴链接或上传视频，Agent 完成转录、整理、截图锚点和导出。',
            primary: '开始处理视频',
            secondary: '查看工作流',
            note: '适合课程、讲座、录屏和语言学习材料。',
        },
        preview: {
            source: '输入材料',
            sourceTitle: '3 小时课程视频',
            agent: 'Agent 判断',
            agentTitle: '课程型材料，使用高保真笔记',
            transcript: '云端转录',
            transcriptTitle: '识别章节、术语和关键片段',
            note: '笔记产物',
            noteTitle: '结构化笔记 + 复查截图',
            done: '可导出到飞书、Markdown、PDF',
        },
        work: {
            eyebrow: 'Agent 处理链路',
            title: '从转录开始，把学习资料整理成结果',
            desc: 'FluentFlow 把视频处理成可编辑、可复查、可导出的学习笔记。你看到的是每一步判断，核心参数由 Agent 接管。',
            items: [
                ['接收材料', '支持本地视频、音频、字幕文件，也支持公开视频链接。'],
                ['转录与清洗', '优先使用 ElevenLabs 云端转录，并清理重复幻觉和字幕碎片。'],
                ['判断笔记策略', '根据材料类型、时长、语言和转录长度选择笔记结构。'],
                ['生成复查笔记', '输出结构化笔记，并把关键画面作为复习锚点。'],
                ['导出与沉淀', '结果可继续编辑，也可以导出到飞书或本地文件。'],
            ],
        },
        outcome: {
            eyebrow: '最终结果',
            title: '你得到一份可以继续学习的记录',
            cards: [
                ['可编辑转录', '保留原文，支持边听边校对。'],
                ['结构化笔记', '按主题、概念、例子和结论整理。'],
                ['截图锚点', '关键内容配图，点击后可回到对应时间。'],
                ['处理记录', '进度、失败原因、产物下载和重新处理都集中管理。'],
            ],
        },
        scenes: {
            eyebrow: '适合这些材料',
            title: '先把课程和讲座做好',
            items: [
                ['课程视频', '把长课拆成章节、概念和复习要点。'],
                ['讲座回放', '保留论点、例子、结论和可追溯依据。'],
                ['语言学习', '把口语材料转成可修改字幕和学习笔记。'],
            ],
        },
        cta: {
            title: '把下一条视频交给 FluentFlow',
            desc: '先从一个真实学习材料开始。上传视频，等待转录，然后在编辑器里复查笔记。',
            primary: '开始处理视频',
            secondary: '查看处理记录',
        },
    },
    en: {
        nav: {
            product: 'Product',
            workflow: 'Workflow',
            useCases: 'Use cases',
            app: 'Open app',
            start: 'Start video',
        },
        hero: {
            label: 'FluentFlow Agent',
            title: 'Turn long videos into reviewable study notes',
            desc: 'Paste a link or upload a video. The Agent transcribes, structures, anchors screenshots, and exports.',
            primary: 'Start video',
            secondary: 'See workflow',
            note: 'Built for courses, lectures, recordings, and language study.',
        },
        preview: {
            source: 'Source',
            sourceTitle: '3-hour course video',
            agent: 'Agent decision',
            agentTitle: 'Course material, high-fidelity notes',
            transcript: 'Cloud transcript',
            transcriptTitle: 'Chapters, terms, and key segments',
            note: 'Output',
            noteTitle: 'Structured notes + review screenshots',
            done: 'Export to Lark, Markdown, or PDF',
        },
        work: {
            eyebrow: 'Agent workflow',
            title: 'Start with transcription. Finish with study notes',
            desc: 'FluentFlow turns videos into editable, reviewable, exportable study notes. You see the decision path while the Agent handles the core settings.',
            items: [
                ['Receive material', 'Use local video, audio, subtitle files, or supported public video links.'],
                ['Transcribe and clean', 'Prefer ElevenLabs cloud transcription, then clean repetitions and subtitle fragments.'],
                ['Choose note strategy', 'Select structure from material type, duration, language, and transcript length.'],
                ['Generate review notes', 'Create structured notes with key frames as review anchors.'],
                ['Export and keep', 'Keep editing, export to Lark, or download local files.'],
            ],
        },
        outcome: {
            eyebrow: 'Output',
            title: 'You get a record you can keep studying',
            cards: [
                ['Editable transcript', 'Keep the source text and review while listening.'],
                ['Structured notes', 'Organized by themes, concepts, examples, and conclusions.'],
                ['Screenshot anchors', 'Key visuals stay attached to the relevant moment.'],
                ['Processing records', 'Progress, failures, downloads, and retries live in one place.'],
            ],
        },
        scenes: {
            eyebrow: 'Best fit',
            title: 'Start with courses and lectures',
            items: [
                ['Course videos', 'Split long classes into chapters, concepts, and review points.'],
                ['Lecture replays', 'Preserve claims, examples, conclusions, and evidence.'],
                ['Language study', 'Turn spoken materials into editable subtitles and notes.'],
            ],
        },
        cta: {
            title: 'Send the next video to FluentFlow',
            desc: 'Start with one real study material. Upload a video, wait for transcription, then review the note in the editor.',
            primary: 'Start video',
            secondary: 'View history',
        },
    },
};

const workflowIcons = [UploadCloud, Languages, Brain, BookOpenText, Download];
const outcomeIcons = [MessageSquareText, FileText, Film, CheckCircle2];

const landingFocusRing = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#c8873a]/45 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f5f1e9] dark:focus-visible:ring-[#d4a466]/45 dark:focus-visible:ring-offset-[#0f0e0c]';

const WorkflowPreview = ({copy}) => (
    <div className="relative overflow-hidden rounded-[30px] border border-[#ddd8d0] bg-[#f7f3eb] p-4 shadow-[0_28px_90px_-62px_rgba(28,24,18,.78)] dark:border-white/[0.14] dark:bg-[#171511] dark:shadow-none">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_22%_15%,rgba(204,119,42,.16),transparent_30%),radial-gradient(circle_at_80%_20%,rgba(68,104,93,.18),transparent_28%)] dark:opacity-80"/>
        <div className="relative rounded-[24px] border border-[#d8d1c5] bg-[#fffdf8]/85 p-4 dark:border-white/[0.12] dark:bg-[#11100d]/90">
            <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-[14px] bg-[#111111] text-white dark:bg-[#f4f0e8] dark:text-[#111111]">
                        <Play className="size-5" strokeWidth={2.2}/>
                    </span>
                    <div className="min-w-0">
                        <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-[#8a7253] dark:text-[#c8aa78]">{copy.source}</p>
                        <p className="truncate text-sm font-extrabold text-[#191714] dark:text-[#f5f1e9]">{copy.sourceTitle}</p>
                    </div>
                </div>
                <span className="shrink-0 rounded-full border border-[#d8d1c5] px-3 py-1 text-[11px] font-bold text-[#6d655a] dark:border-white/[0.18] dark:bg-white/[0.04] dark:text-white/[0.72]">ElevenLabs</span>
            </div>

            <div className="grid gap-3 sm:grid-cols-[1fr_1.05fr]">
                <div className="space-y-3">
                    <div className="rounded-[20px] border border-[#ded8ce] bg-white/[0.78] p-4 dark:border-white/[0.12] dark:bg-white/[0.07]">
                        <p className="text-xs font-bold text-[#7a7166] dark:text-white/[0.64]">{copy.agent}</p>
                        <p className="mt-2 text-lg font-black leading-tight text-[#181612] dark:text-[#f6f1e8]">{copy.agentTitle}</p>
                    </div>
                    <div className="rounded-[20px] border border-[#ded8ce] bg-white/[0.78] p-4 dark:border-white/[0.12] dark:bg-white/[0.07]">
                        <p className="text-xs font-bold text-[#7a7166] dark:text-white/[0.64]">{copy.transcript}</p>
                        <p className="mt-2 text-sm font-extrabold leading-snug text-[#28241e] dark:text-white/[0.88]">{copy.transcriptTitle}</p>
                        <div className="mt-4 space-y-2">
                            <span className="block h-2 rounded-full bg-[#d8c6aa] dark:bg-white/[0.24]"/>
                            <span className="block h-2 w-4/5 rounded-full bg-[#d8c6aa] dark:bg-white/[0.18]"/>
                            <span className="block h-2 w-3/5 rounded-full bg-[#d8c6aa] dark:bg-white/[0.14]"/>
                        </div>
                    </div>
                </div>
                <div className="rounded-[22px] border border-[#d1c7b8] bg-[#191714] p-4 text-[#f5f1e9] dark:border-white/[0.14] dark:bg-[#211d16] dark:text-[#f8f1e6]">
                    <div className="flex items-center justify-between gap-3">
                        <p className="text-xs font-extrabold uppercase tracking-[0.14em] text-[#d4a466]">{copy.note}</p>
                        <Sparkles className="size-4 text-[#d4a466]" strokeWidth={2.1}/>
                    </div>
                    <h2 className="mt-4 text-2xl font-black leading-tight">{copy.noteTitle}</h2>
                    <div className="mt-5 grid gap-2">
                        {['核心概念', '例子与推导', '复查画面'].map((label) => (
                            <div key={label} className="rounded-[14px] bg-white/[0.08] px-3 py-2 text-xs font-bold dark:bg-white/[0.09] dark:text-white/[0.86]">
                                {label}
                            </div>
                        ))}
                    </div>
                    <p className="mt-5 rounded-[16px] bg-[#c8873a] px-4 py-3 text-sm font-extrabold text-[#16120c]">{copy.done}</p>
                </div>
            </div>
        </div>
    </div>
);

const Landing = () => {
    const {lang} = useI18n();
    const isZh = lang === 'zh';
    const copy = content[isZh ? 'zh' : 'en'];

    return (
        <main className="min-h-dvh bg-[#f5f1e9] text-[#171512] dark:bg-[#0f0e0c] dark:text-[#f5f1e9]">
            <header className="sticky top-0 z-40 border-b border-[#dfd7cb]/80 bg-[#f5f1e9]/88 backdrop-blur-xl dark:border-white/[0.14] dark:bg-[#0f0e0c]/92">
                <div className="mx-auto flex h-[72px] max-w-7xl items-center justify-between gap-5 px-5 sm:px-6 lg:px-8">
                    <Link to="/" className="flex min-w-0 items-center gap-3" aria-label="FluentFlow">
                        <LogoMark/>
                        <span className="truncate text-base font-black tracking-tight">FluentFlow</span>
                    </Link>
                    <nav className="hidden items-center gap-7 text-sm font-bold text-[#6e665c] dark:text-white/[0.72] md:flex">
                        <a href="#product" className="transition hover:text-[#171512] dark:hover:text-white">{copy.nav.product}</a>
                        <a href="#workflow" className="transition hover:text-[#171512] dark:hover:text-white">{copy.nav.workflow}</a>
                        <a href="#use-cases" className="transition hover:text-[#171512] dark:hover:text-white">{copy.nav.useCases}</a>
                    </nav>
                    <div className="flex shrink-0 items-center gap-2">
                        <Link to="/app" className={`hidden h-10 items-center justify-center rounded-full border border-[#d5cabd] px-4 text-sm font-extrabold text-[#171512] transition hover:bg-[#ebe4d9] active:translate-y-px dark:border-white/[0.18] dark:bg-white/[0.04] dark:text-white/[0.88] dark:hover:bg-white/[0.10] sm:inline-flex ${landingFocusRing}`}>
                            {copy.nav.app}
                        </Link>
                        <Link to="/media-text" className={`inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#171512] px-4 text-sm font-extrabold text-[#f5f1e9] transition hover:bg-[#2b261f] active:translate-y-px dark:bg-[#f5f1e9] dark:text-[#171512] dark:hover:bg-[#e8ddcb] ${landingFocusRing}`}>
                            {copy.nav.start}
                            <ArrowRight className="size-4" strokeWidth={2.2}/>
                        </Link>
                    </div>
                </div>
            </header>

            <section className="mx-auto grid min-h-[calc(100dvh-72px)] max-w-7xl items-center gap-12 px-5 py-14 sm:px-6 lg:grid-cols-[0.92fr_1.08fr] lg:px-8 lg:py-20">
                <div className="max-w-3xl">
                    <p className="mb-5 text-sm font-extrabold uppercase tracking-[0.16em] text-[#9a6a32] dark:text-[#d4a466]">{copy.hero.label}</p>
                    <h1 className="font-headline text-5xl font-black leading-[0.98] tracking-normal text-[#171512] dark:text-[#f7f1e7] sm:text-6xl lg:text-7xl">
                        {copy.hero.title}
                    </h1>
                    <p className="mt-6 max-w-[58ch] text-lg font-semibold leading-relaxed text-[#6d655a] dark:text-white/[0.72]">
                        {copy.hero.desc}
                    </p>
                    <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                        <Link to="/media-text" className={`inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#171512] px-6 text-sm font-extrabold text-[#f5f1e9] transition hover:bg-[#2b261f] active:translate-y-px dark:bg-[#f5f1e9] dark:text-[#171512] dark:hover:bg-[#e8ddcb] ${landingFocusRing}`}>
                            {copy.hero.primary}
                            <ArrowRight className="size-4" strokeWidth={2.2}/>
                        </Link>
                        <a href="#workflow" className={`inline-flex h-12 items-center justify-center gap-2 rounded-full border border-[#d5cabd] px-6 text-sm font-extrabold text-[#171512] transition hover:bg-[#ebe4d9] active:translate-y-px dark:border-white/[0.18] dark:bg-white/[0.04] dark:text-white/[0.88] dark:hover:bg-white/[0.10] ${landingFocusRing}`}>
                            {copy.hero.secondary}
                            <ChevronRight className="size-4" strokeWidth={2.2}/>
                        </a>
                    </div>
                    <p className="mt-5 max-w-[48ch] text-sm font-bold text-[#82786b] dark:text-white/[0.58]">{copy.hero.note}</p>
                </div>
                <WorkflowPreview copy={copy.preview}/>
            </section>

            <section id="product" className="border-y border-[#dfd7cb] bg-[#fffaf2] dark:border-white/[0.10] dark:bg-[#15130f]">
                <div className="mx-auto grid max-w-7xl gap-10 px-5 py-16 sm:px-6 lg:grid-cols-[0.85fr_1.15fr] lg:px-8 lg:py-24">
                    <div>
                        <p className="text-sm font-extrabold uppercase tracking-[0.14em] text-[#9a6a32] dark:text-[#d4a466]">{copy.work.eyebrow}</p>
                        <h2 className="mt-4 max-w-[11em] font-headline text-4xl font-black leading-tight text-[#171512] dark:text-[#f7f1e7] sm:text-5xl">{copy.work.title}</h2>
                        <p className="mt-5 max-w-[48ch] text-base font-semibold leading-relaxed text-[#6d655a] dark:text-white/[0.68]">{copy.work.desc}</p>
                    </div>
                    <div className="grid gap-3">
                        {copy.work.items.map(([title, desc], index) => {
                            const Icon = workflowIcons[index] || CheckCircle2;
                            return (
                                <article key={title} className="grid gap-4 rounded-[24px] border border-[#dfd7cb] bg-[#f7f1e7] p-5 sm:grid-cols-[56px_minmax(0,1fr)] dark:border-white/[0.12] dark:bg-white/[0.06]">
                                    <span className="flex size-12 items-center justify-center rounded-[18px] bg-[#171512] text-[#f5f1e9] dark:bg-[#f5f1e9] dark:text-[#171512]">
                                        <Icon className="size-5" strokeWidth={2.1}/>
                                    </span>
                                    <span>
                                        <h3 className="text-xl font-black leading-tight text-[#171512] dark:text-[#f7f1e7]">{title}</h3>
                                        <p className="mt-2 text-sm font-semibold leading-relaxed text-[#6d655a] dark:text-white/[0.68]">{desc}</p>
                                    </span>
                                </article>
                            );
                        })}
                    </div>
                </div>
            </section>

            <section id="workflow" className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
                <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:items-end">
                    <div>
                        <p className="text-sm font-extrabold uppercase tracking-[0.14em] text-[#9a6a32] dark:text-[#d4a466]">{copy.outcome.eyebrow}</p>
                        <h2 className="mt-4 max-w-[12em] font-headline text-4xl font-black leading-tight sm:text-5xl">{copy.outcome.title}</h2>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                        {copy.outcome.cards.map(([title, desc], index) => {
                            const Icon = outcomeIcons[index] || FileText;
                            return (
                                <article key={title} className="rounded-[26px] border border-[#dfd7cb] bg-[#fffaf2] p-5 dark:border-white/[0.12] dark:bg-white/[0.06]">
                                    <Icon className="size-6 text-[#9a6a32] dark:text-[#d4a466]" strokeWidth={2.1}/>
                                    <h3 className="mt-5 text-xl font-black leading-tight">{title}</h3>
                                    <p className="mt-2 text-sm font-semibold leading-relaxed text-[#6d655a] dark:text-white/[0.68]">{desc}</p>
                                </article>
                            );
                        })}
                    </div>
                </div>
            </section>

            <section id="use-cases" className="bg-[#171512] text-[#f5f1e9] dark:bg-[#15130f] dark:text-[#f5f1e9]">
                <div className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
                    <div className="max-w-3xl">
                        <p className="text-sm font-extrabold uppercase tracking-[0.14em] text-[#d4a466] dark:text-[#d4a466]">{copy.scenes.eyebrow}</p>
                        <h2 className="mt-4 font-headline text-4xl font-black leading-tight sm:text-5xl">{copy.scenes.title}</h2>
                    </div>
                    <div className="mt-10 grid gap-4 lg:grid-cols-3">
                        {copy.scenes.items.map(([title, desc]) => (
                            <article key={title} className="rounded-[26px] border border-white/[0.12] bg-white/[0.06] p-6 dark:border-white/[0.12] dark:bg-white/[0.06]">
                                <h3 className="text-2xl font-black leading-tight">{title}</h3>
                                <p className="mt-4 text-sm font-semibold leading-relaxed text-white/[0.62] dark:text-white/[0.68]">{desc}</p>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            <section className="mx-auto max-w-7xl px-5 py-16 sm:px-6 lg:px-8 lg:py-24">
                <div className="rounded-[32px] border border-[#dfd7cb] bg-[#fffaf2] p-6 sm:p-8 lg:flex lg:items-center lg:justify-between lg:gap-10 dark:border-white/[0.12] dark:bg-white/[0.06]">
                    <div className="max-w-2xl">
                        <h2 className="font-headline text-4xl font-black leading-tight sm:text-5xl">{copy.cta.title}</h2>
                        <p className="mt-4 text-base font-semibold leading-relaxed text-[#6d655a] dark:text-white/[0.68]">{copy.cta.desc}</p>
                    </div>
                    <div className="mt-8 flex flex-col gap-3 sm:flex-row lg:mt-0">
                        <Link to="/media-text" className={`inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#171512] px-6 text-sm font-extrabold text-[#f5f1e9] transition hover:bg-[#2b261f] active:translate-y-px dark:bg-[#f5f1e9] dark:text-[#171512] dark:hover:bg-[#e8ddcb] ${landingFocusRing}`}>
                            {copy.cta.primary}
                            <ArrowRight className="size-4" strokeWidth={2.2}/>
                        </Link>
                        <Link to="/agent" className={`inline-flex h-12 items-center justify-center rounded-full border border-[#d5cabd] px-6 text-sm font-extrabold text-[#171512] transition hover:bg-[#ebe4d9] active:translate-y-px dark:border-white/[0.18] dark:bg-white/[0.04] dark:text-white/[0.88] dark:hover:bg-white/[0.10] ${landingFocusRing}`}>
                            {copy.cta.secondary}
                        </Link>
                    </div>
                </div>
            </section>
        </main>
    );
};

export default Landing;
