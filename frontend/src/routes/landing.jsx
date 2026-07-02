import {Link} from 'react-router-dom';
import {
    ArrowRight,
    BookOpenText,
    Captions,
    CheckCircle2,
    ChevronRight,
    Download,
    FileText,
    Film,
    Image,
    Languages,
    MonitorPlay,
    Play,
    RotateCcw,
    ScanSearch,
    Sparkles,
    UploadCloud,
} from 'lucide-react';
import {useI18n} from '../app/shared.jsx';

const LogoMark = () => (
    <span className="flex size-10 items-center justify-center rounded-[14px] bg-[#171512] text-[#f8f2e8] shadow-[0_18px_42px_-28px_rgba(37,30,18,.72)] dark:bg-[#f4efe4] dark:text-[#171512]">
        <svg viewBox="0 0 64 64" className="size-[30px]" fill="none" aria-hidden="true">
            <rect x="17" y="19" width="28" height="26" rx="8" fill="currentColor"/>
            <rect x="43" y="25" width="8" height="14" rx="4" fill="currentColor"/>
            <path d="M24 29h13M24 36h9" stroke="var(--ff-logo-line, #171512)" strokeWidth="4.2" strokeLinecap="round" className="[--ff-logo-line:#171512] dark:[--ff-logo-line:#f4efe4]"/>
        </svg>
    </span>
);

const content = {
    zh: {
        nav: {
            product: '笔记质量',
            workflow: '学习方式',
            useCases: '来源',
            app: '进入应用',
            start: '开始处理视频',
        },
        hero: {
            label: '长视频学习笔记',
            title: '把想学的长视频，先变成高质量笔记',
            desc: '把课程、讲座、录屏和视频链接交给 FluentFlow。先得到结构化笔记、字幕和关键画面，再对着视频学习，只改少数不准确处。',
            primary: '开始处理视频',
            secondary: '看学习流程',
            note: '视频仍是学习主线，FluentFlow 先处理笔记整理。',
        },
        preview: {
            source: '课程视频 01:12:44',
            title: '生成后的学习笔记',
            chapter: '03 注意力机制为什么有效',
            bullets: ['先读章节结论，再回到视频验证推导。', '例子、术语和截图都保留来源位置。', '字幕修正会列出原文、改法和原因。'],
            subtitle: '字幕 18:42',
            subtitleText: 'The query and key vectors compare each token against the current context.',
            visual: '关键画面',
            timeline: ['00:00', '18:42', '39:10', '01:12'],
        },
        beforeAfter: {
            eyebrow: '学习方式变化',
            title: '少暂停，少倒回，少做机械整理',
            beforeTitle: '以前边看边记',
            afterTitle: '现在先有笔记再学习',
            before: [
                ['打开长视频', '一小时课程刚开始就要判断怎么记。'],
                ['频繁暂停倒回', '错过一句话就回放，注意力被切碎。'],
                ['手动整理格式', '看完还要重排章节、例子和结论。'],
            ],
            after: [
                ['先生成笔记', '章节、字幕和关键画面先准备好。'],
                ['对着视频学习', '重点看内容，只在不确定处回到原视频。'],
                ['少量修正', '改掉少数识别或理解不准的地方。'],
            ],
        },
        quality: {
            eyebrow: '什么叫高质量',
            title: '不是一段摘要，而是一份可复查的学习资产',
            items: [
                ['结构化章节', '按主题、概念、例子和结论整理，适合先浏览再深入看视频。'],
                ['重要例子和推导', '把课程里的关键步骤留下来，避免只得到泛泛总结。'],
                ['字幕原文保留', '转录和字幕仍可查看，笔记内容能回到来源。'],
                ['保守字幕纠错', '高置信修正会列出原文、修正、原因和时间点。'],
                ['关键画面', '当本地视频可用时，截图作为复查锚点进入笔记。'],
                ['可导出结果', 'Markdown、PDF 和飞书导出让笔记继续沉淀。'],
            ],
        },
        sources: {
            eyebrow: '不同来源都能开始',
            title: '课程、讲座、录屏、本地文件和公开视频链接',
            desc: '公开视频平台可能限制下载或字幕访问，本地上传和字幕文件是最可靠的路线。',
            items: ['课程视频', '讲座回放', '屏幕录制', '本地音视频', '字幕或文本文件', '支持的公开视频链接'],
        },
        outputs: {
            eyebrow: '最后留下什么',
            title: '一份能继续学习、复查和导出的记录',
            items: [
                ['结构化笔记', '先读章节和要点，再带着问题看视频。'],
                ['字幕和转录', '保留原文，便于听不清或识别错误时回查。'],
                ['关键画面', '公式、图表、代码和界面片段可作为复习锚点。'],
                ['处理记录', '运行中、失败、完成、下载和重新处理都集中管理。'],
            ],
        },
        cta: {
            title: '把下一条想学的视频交给 FluentFlow',
            desc: '从一条真实课程或讲座开始。先生成笔记，再对着视频学习和修正。',
            primary: '开始处理视频',
            secondary: '查看处理记录',
        },
    },
    en: {
        nav: {
            product: 'Note quality',
            workflow: 'Study flow',
            useCases: 'Sources',
            app: 'Open app',
            start: 'Start video',
        },
        hero: {
            label: 'Long-video study notes',
            title: 'Turn long learning videos into high-quality notes first',
            desc: 'Give FluentFlow courses, lectures, recordings, and video links. Get notes, subtitles, and key visuals before studying with the video.',
            primary: 'Start video',
            secondary: 'See study flow',
            note: 'The video stays central. FluentFlow removes the note-taking friction first.',
        },
        preview: {
            source: 'Course video 01:12:44',
            title: 'Prepared study note',
            chapter: '03 Why attention works',
            bullets: ['Read the chapter conclusion before replaying the proof.', 'Examples, terms, and screenshots keep source positions.', 'Transcript corrections show original, fix, reason, and time.'],
            subtitle: 'Subtitle 18:42',
            subtitleText: 'The query and key vectors compare each token against the current context.',
            visual: 'Key visual',
            timeline: ['00:00', '18:42', '39:10', '01:12'],
        },
        beforeAfter: {
            eyebrow: 'Study flow',
            title: 'Pause less, rewind less, clean up less',
            beforeTitle: 'Before: note while watching',
            afterTitle: 'After: study with notes ready',
            before: [
                ['Open a long video', 'You must decide what to capture from the first minute.'],
                ['Pause and rewind', 'One missed sentence breaks attention and sends you back.'],
                ['Clean the format', 'After watching, chapters and examples still need manual cleanup.'],
            ],
            after: [
                ['Generate the note first', 'Chapters, subtitles, and key visuals are prepared upfront.'],
                ['Study with the video', 'Focus on the lesson and revisit the source only when needed.'],
                ['Fix a few details', 'Correct the small number of uncertain recognition or wording issues.'],
            ],
        },
        quality: {
            eyebrow: 'What quality means',
            title: 'Not a summary. A reviewable study asset',
            items: [
                ['Structured chapters', 'Themes, concepts, examples, and conclusions are shaped for preview and deep study.'],
                ['Examples and reasoning', 'Important course steps stay visible instead of being flattened into generic summary.'],
                ['Source transcript', 'Transcript and subtitles remain available, so the note can be checked against source.'],
                ['Conservative correction', 'Accepted fixes show original text, corrected text, reason, confidence, and time.'],
                ['Key visuals', 'When local video is available, screenshots become review anchors in the note.'],
                ['Exportable result', 'Markdown, PDF, and Feishu export turn the result into a lasting asset.'],
            ],
        },
        sources: {
            eyebrow: 'Source coverage',
            title: 'Courses, lectures, recordings, local files, and supported public links',
            desc: 'Public platforms may restrict media or caption access. Local upload and subtitle files are the most reliable path.',
            items: ['Course videos', 'Lecture replays', 'Screen recordings', 'Local audio or video', 'Subtitle or text files', 'Supported public links'],
        },
        outputs: {
            eyebrow: 'What you keep',
            title: 'A record you can study, review, and export',
            items: [
                ['Structured note', 'Read the sections first, then study the video with better questions.'],
                ['Subtitles and transcript', 'Keep source text for unclear audio and recognition errors.'],
                ['Key visuals', 'Formulas, charts, code, and screens can become review anchors.'],
                ['Processing records', 'Running, failed, completed, downloads, and retries stay in one place.'],
            ],
        },
        cta: {
            title: 'Give FluentFlow the next video you want to learn',
            desc: 'Start with one real course or lecture. Generate the note first, then study and correct it with the video.',
            primary: 'Start video',
            secondary: 'View records',
        },
    },
};

const qualityIcons = [BookOpenText, ScanSearch, Captions, Languages, Image, Download];
const outputIcons = [FileText, Captions, Film, CheckCircle2];

const focusRing = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#bb7a2d]/45 focus-visible:ring-offset-2 focus-visible:ring-offset-[#f6f0e6] dark:focus-visible:ring-[#d6a466]/45 dark:focus-visible:ring-offset-[#0f0e0c]';
const primaryButton = `inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#171512] px-6 text-sm font-extrabold text-[#f8f2e8] transition hover:bg-[#2d261e] active:translate-y-px dark:bg-[#f4efe4] dark:text-[#171512] dark:hover:bg-[#e7dcc9] ${focusRing}`;
const secondaryButton = `inline-flex h-12 items-center justify-center gap-2 rounded-full border border-[#d7cbbb] bg-[#f9f4eb]/70 px-6 text-sm font-extrabold text-[#171512] transition hover:bg-[#efe4d5] active:translate-y-px dark:border-white/[0.18] dark:bg-white/[0.055] dark:text-white/[0.9] dark:hover:bg-white/[0.10] ${focusRing}`;
const sectionShell = 'mx-auto max-w-7xl px-5 sm:px-6 lg:px-8';
const eyebrowClass = 'text-[12px] font-extrabold uppercase tracking-[0.16em] text-[#9a6428] dark:text-[#d6a466]';

const SectionHeader = ({eyebrow, title, desc, narrow=false}) => (
    <div className={narrow ? 'max-w-3xl' : 'grid gap-5 lg:grid-cols-[0.85fr_1fr] lg:items-end'}>
        <div>
            <p className={eyebrowClass}>{eyebrow}</p>
            <h2 className="mt-4 max-w-[13em] font-headline text-[34px] font-black leading-[1.02] text-[#171512] dark:text-[#f7f1e8] sm:text-[44px]">
                {title}
            </h2>
        </div>
        {desc ? (
            <p className="max-w-[58ch] text-base font-semibold leading-relaxed text-[#6f6558] dark:text-white/[0.68]">
                {desc}
            </p>
        ) : null}
    </div>
);

const StudyAssetPreview = ({copy}) => (
    <div className="relative">
        <div className="absolute -left-5 top-8 hidden h-44 w-24 rounded-[28px] bg-[#dcc49d]/55 blur-2xl dark:bg-[#8f5f24]/28 lg:block"/>
        <div className="relative overflow-hidden rounded-[30px] border border-[#d9cdbc] bg-[#fffaf2] shadow-[0_34px_110px_-72px_rgba(39,31,20,.82)] dark:border-white/[0.12] dark:bg-[#171510] dark:shadow-none">
            <div className="grid gap-0 lg:grid-cols-[1fr_0.74fr]">
                <div className="p-4 sm:p-5">
                    <div className="rounded-[22px] border border-[#ded2c1] bg-[#f9f4eb] p-4 dark:border-white/[0.11] dark:bg-white/[0.055]">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-[#9a6428] dark:text-[#d6a466]">{copy.source}</p>
                            <span className="rounded-full border border-[#d7cbbb] px-3 py-1 text-[11px] font-extrabold text-[#5f5649] dark:border-white/[0.16] dark:text-white/[0.68]">ElevenLabs</span>
                        </div>
                        <h2 className="mt-5 font-headline text-[28px] font-black leading-tight text-[#171512] dark:text-[#f7f1e8]">{copy.title}</h2>
                        <div className="mt-5 rounded-[20px] bg-[#171512] p-4 text-[#f7f1e8] dark:bg-[#211d16]">
                            <p className="text-[11px] font-extrabold uppercase tracking-[0.14em] text-[#d6a466]">{copy.chapter}</p>
                            <div className="mt-4 space-y-3">
                                {copy.bullets.map((item) => (
                                    <p key={item} className="rounded-[14px] bg-white/[0.08] px-3 py-2 text-sm font-bold leading-6 text-white/[0.88]">
                                        {item}
                                    </p>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
                <div className="border-t border-[#e2d7c7] bg-[#f4eadb] p-4 dark:border-white/[0.10] dark:bg-[#120f0b] lg:border-l lg:border-t-0">
                    <div className="rounded-[22px] border border-[#d9cdbc] bg-[#fffaf2] p-4 dark:border-white/[0.11] dark:bg-white/[0.06]">
                        <div className="flex items-center gap-3">
                            <span className="flex size-10 items-center justify-center rounded-[14px] bg-[#171512] text-[#f8f2e8] dark:bg-[#f4efe4] dark:text-[#171512]">
                                <Play className="size-5" strokeWidth={2.15}/>
                            </span>
                            <div>
                                <p className="text-[11px] font-extrabold text-[#8a765a] dark:text-white/[0.56]">{copy.subtitle}</p>
                                <p className="text-sm font-black text-[#171512] dark:text-[#f7f1e8]">Transformer lecture</p>
                            </div>
                        </div>
                        <p className="mt-4 text-sm font-semibold leading-6 text-[#5f5649] dark:text-white/[0.68]">{copy.subtitleText}</p>
                        <div className="mt-5 grid grid-cols-4 gap-2 text-[10px] font-extrabold text-[#7a6b58] dark:text-white/[0.48]">
                            {copy.timeline.map((item) => <span key={item}>{item}</span>)}
                        </div>
                        <div className="mt-2 grid grid-cols-4 gap-1">
                            {copy.timeline.map((item, index) => (
                                <span key={`${item}-segment`} className={`h-2 rounded-full ${index === 1 ? 'bg-[#bb7a2d]' : 'bg-[#dccdb8] dark:bg-white/[0.14]'}`}/>
                            ))}
                        </div>
                    </div>
                    <div className="mt-3 overflow-hidden rounded-[22px] border border-[#d9cdbc] bg-[#201a12] dark:border-white/[0.11]">
                        <div className="aspect-[16/10] bg-[linear-gradient(135deg,rgba(214,164,102,.32),transparent_42%),radial-gradient(circle_at_24%_24%,rgba(255,255,255,.28),transparent_18%),linear-gradient(160deg,#2b241a,#15110d_58%,#5a3a19)]"/>
                        <div className="flex items-center justify-between gap-3 border-t border-white/[0.10] px-4 py-3">
                            <span className="text-xs font-extrabold text-[#f7f1e8]">{copy.visual}</span>
                            <MonitorPlay className="size-4 text-[#d6a466]" strokeWidth={2.15}/>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
);

const StepList = ({title, items, tone}) => {
    const isAfter = tone === 'after';
    const Icon = isAfter ? CheckCircle2 : RotateCcw;
    return (
        <article className={`rounded-[28px] border p-5 sm:p-6 ${isAfter ? 'border-[#d5b987] bg-[#fff7e9] dark:border-[#d6a466]/28 dark:bg-[#d6a466]/10' : 'border-[#dfd4c4] bg-[#fbf5ec] dark:border-white/[0.12] dark:bg-white/[0.055]'}`}>
            <div className="flex items-center gap-3">
                <span className={`flex size-11 items-center justify-center rounded-[16px] ${isAfter ? 'bg-[#bb7a2d] text-[#171512]' : 'bg-[#171512] text-[#f8f2e8] dark:bg-[#f4efe4] dark:text-[#171512]'}`}>
                    <Icon className="size-5" strokeWidth={2.15}/>
                </span>
                <h3 className="font-headline text-[22px] font-black text-[#171512] dark:text-[#f7f1e8]">{title}</h3>
            </div>
            <div className="mt-5 space-y-4">
                {items.map(([itemTitle, desc]) => (
                    <div key={itemTitle} className="grid gap-1 border-t border-[#dfd4c4] pt-4 dark:border-white/[0.10]">
                        <p className="text-sm font-black text-[#171512] dark:text-[#f7f1e8]">{itemTitle}</p>
                        <p className="text-sm font-semibold leading-6 text-[#6f6558] dark:text-white/[0.66]">{desc}</p>
                    </div>
                ))}
            </div>
        </article>
    );
};

const Landing = () => {
    const {lang} = useI18n();
    const isZh = lang === 'zh';
    const copy = content[isZh ? 'zh' : 'en'];

    return (
        <main className="min-h-dvh bg-[#f6f0e6] text-[#171512] dark:bg-[#0f0e0c] dark:text-[#f7f1e8]">
            <header className="sticky top-0 z-40 border-b border-[#dfd4c4]/85 bg-[#f6f0e6]/88 backdrop-blur-xl dark:border-white/[0.12] dark:bg-[#0f0e0c]/92">
                <div className="mx-auto flex h-[68px] max-w-7xl items-center justify-between gap-5 px-5 sm:px-6 lg:px-8">
                    <Link to="/" className={`flex min-w-0 items-center gap-3 rounded-[16px] ${focusRing}`} aria-label="FluentFlow">
                        <LogoMark/>
                        <span className="truncate text-base font-black tracking-normal">FluentFlow</span>
                    </Link>
                    <nav className="hidden items-center gap-7 text-sm font-bold text-[#6f6558] dark:text-white/[0.70] md:flex">
                        <a href="#product" className="transition hover:text-[#171512] dark:hover:text-white">{copy.nav.product}</a>
                        <a href="#workflow" className="transition hover:text-[#171512] dark:hover:text-white">{copy.nav.workflow}</a>
                        <a href="#use-cases" className="transition hover:text-[#171512] dark:hover:text-white">{copy.nav.useCases}</a>
                    </nav>
                    <div className="flex shrink-0 items-center gap-2">
                        <Link to="/app" className={`hidden h-10 items-center justify-center rounded-full border border-[#d7cbbb] bg-[#f9f4eb]/65 px-4 text-sm font-extrabold text-[#171512] transition hover:bg-[#efe4d5] active:translate-y-px dark:border-white/[0.18] dark:bg-white/[0.055] dark:text-white/[0.88] dark:hover:bg-white/[0.10] sm:inline-flex ${focusRing}`}>
                            {copy.nav.app}
                        </Link>
                        <Link to="/media-text" className={`inline-flex h-10 items-center justify-center gap-2 rounded-full bg-[#171512] px-4 text-sm font-extrabold text-[#f8f2e8] transition hover:bg-[#2d261e] active:translate-y-px dark:bg-[#f4efe4] dark:text-[#171512] dark:hover:bg-[#e7dcc9] ${focusRing}`}>
                            {copy.nav.start}
                            <ArrowRight className="size-4" strokeWidth={2.2}/>
                        </Link>
                    </div>
                </div>
            </header>

            <section className={`${sectionShell} grid min-h-[calc(100dvh-68px)] items-center gap-10 py-10 sm:py-12 lg:grid-cols-[0.88fr_1.12fr] lg:py-14`}>
                <div className="max-w-3xl">
                    <p className={eyebrowClass}>{copy.hero.label}</p>
                    <h1 className="mt-5 max-w-[11em] font-headline text-[42px] font-black leading-[1.02] tracking-normal text-[#171512] dark:text-[#f7f1e8] sm:text-[56px] lg:text-[68px]">
                        {copy.hero.title}
                    </h1>
                    <p className="mt-6 max-w-[60ch] text-[17px] font-semibold leading-8 text-[#665d51] dark:text-white/[0.72]">
                        {copy.hero.desc}
                    </p>
                    <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                        <Link to="/media-text" className={primaryButton}>
                            {copy.hero.primary}
                            <ArrowRight className="size-4" strokeWidth={2.2}/>
                        </Link>
                        <a href="#workflow" className={secondaryButton}>
                            {copy.hero.secondary}
                            <ChevronRight className="size-4" strokeWidth={2.2}/>
                        </a>
                    </div>
                    <p className="mt-5 max-w-[46ch] text-sm font-bold text-[#806f5a] dark:text-white/[0.58]">{copy.hero.note}</p>
                </div>
                <StudyAssetPreview copy={copy.preview}/>
            </section>

            <section id="workflow" className="border-y border-[#dfd4c4] bg-[#fff8ee] dark:border-white/[0.10] dark:bg-[#15130f]">
                <div className={`${sectionShell} py-16 lg:py-24`}>
                    <SectionHeader eyebrow={copy.beforeAfter.eyebrow} title={copy.beforeAfter.title}/>
                    <div className="mt-10 grid gap-4 lg:grid-cols-2">
                        <StepList title={copy.beforeAfter.beforeTitle} items={copy.beforeAfter.before} tone="before"/>
                        <StepList title={copy.beforeAfter.afterTitle} items={copy.beforeAfter.after} tone="after"/>
                    </div>
                </div>
            </section>

            <section id="product" className={`${sectionShell} py-16 lg:py-24`}>
                <SectionHeader eyebrow={copy.quality.eyebrow} title={copy.quality.title}/>
                <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {copy.quality.items.map(([title, desc], index) => {
                        const Icon = qualityIcons[index] || Sparkles;
                        return (
                            <article key={title} className="rounded-[26px] border border-[#dfd4c4] bg-[#fffaf3] p-5 transition hover:-translate-y-0.5 hover:border-[#c6a16a] dark:border-white/[0.11] dark:bg-white/[0.055] dark:hover:border-[#d6a466]/45">
                                <Icon className="size-6 text-[#9a6428] dark:text-[#d6a466]" strokeWidth={2.05}/>
                                <h3 className="mt-5 text-xl font-black leading-tight text-[#171512] dark:text-[#f7f1e8]">{title}</h3>
                                <p className="mt-3 text-sm font-semibold leading-6 text-[#6f6558] dark:text-white/[0.66]">{desc}</p>
                            </article>
                        );
                    })}
                </div>
            </section>

            <section id="use-cases" className="border-y border-[#dfd4c4] bg-[#fff8ee] dark:border-white/[0.10] dark:bg-[#15130f]">
                <div className={`${sectionShell} grid gap-10 py-16 lg:grid-cols-[0.86fr_1.14fr] lg:items-center lg:py-24`}>
                    <div>
                        <p className="text-[12px] font-extrabold uppercase tracking-[0.16em] text-[#d6a466]">{copy.sources.eyebrow}</p>
                        <h2 className="mt-4 max-w-[13em] font-headline text-[34px] font-black leading-[1.02] text-[#171512] dark:text-[#f7f1e8] sm:text-[44px]">{copy.sources.title}</h2>
                        <p className="mt-5 max-w-[58ch] text-base font-semibold leading-relaxed text-[#6f6558] dark:text-white/[0.66]">{copy.sources.desc}</p>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                        {copy.sources.items.map((item) => (
                            <div key={item} className="flex min-h-[74px] items-center gap-3 rounded-[22px] border border-[#dfd4c4] bg-[#fffaf3] px-4 py-3 dark:border-white/[0.12] dark:bg-white/[0.06]">
                                <span className="flex size-10 shrink-0 items-center justify-center rounded-[14px] bg-[#bb7a2d] text-[#171512] dark:bg-[#d6a466]">
                                    <UploadCloud className="size-5" strokeWidth={2.1}/>
                                </span>
                                <p className="text-sm font-black leading-tight text-[#171512] dark:text-[#f7f1e8]">{item}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            <section className={`${sectionShell} py-16 lg:py-24`}>
                <SectionHeader eyebrow={copy.outputs.eyebrow} title={copy.outputs.title} narrow/>
                <div className="mt-10 grid gap-4 lg:grid-cols-4">
                    {copy.outputs.items.map(([title, desc], index) => {
                        const Icon = outputIcons[index] || FileText;
                        return (
                            <article key={title} className="rounded-[26px] border border-[#dfd4c4] bg-[#fffaf3] p-5 dark:border-white/[0.11] dark:bg-white/[0.055]">
                                <Icon className="size-6 text-[#9a6428] dark:text-[#d6a466]" strokeWidth={2.05}/>
                                <h3 className="mt-5 text-xl font-black leading-tight text-[#171512] dark:text-[#f7f1e8]">{title}</h3>
                                <p className="mt-3 text-sm font-semibold leading-6 text-[#6f6558] dark:text-white/[0.66]">{desc}</p>
                            </article>
                        );
                    })}
                </div>
            </section>

            <section className={`${sectionShell} pb-16 lg:pb-24`}>
                <div className="rounded-[32px] border border-[#dfd4c4] bg-[#fff8ee] p-6 sm:p-8 lg:flex lg:items-center lg:justify-between lg:gap-10 dark:border-white/[0.12] dark:bg-white/[0.055]">
                    <div className="max-w-2xl">
                        <p className={eyebrowClass}>{copy.cta.primary}</p>
                        <h2 className="mt-3 font-headline text-[34px] font-black leading-[1.04] text-[#171512] dark:text-[#f7f1e8] sm:text-[44px]">{copy.cta.title}</h2>
                        <p className="mt-4 text-base font-semibold leading-relaxed text-[#6f6558] dark:text-white/[0.68]">{copy.cta.desc}</p>
                    </div>
                    <div className="mt-8 flex flex-col gap-3 sm:flex-row lg:mt-0">
                        <Link to="/media-text" className={primaryButton}>
                            {copy.cta.primary}
                            <ArrowRight className="size-4" strokeWidth={2.2}/>
                        </Link>
                        <Link to="/agent" className={secondaryButton}>
                            {copy.cta.secondary}
                        </Link>
                    </div>
                </div>
            </section>
        </main>
    );
};

export default Landing;
