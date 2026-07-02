import {Link} from 'react-router-dom';
import {
    ArrowRight,
    BookOpenText,
    Captions,
    CheckCircle2,
    Download,
    FileText,
    Film,
    Image,
    Play,
    RotateCcw,
    ScanSearch,
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

const sourceItems = [
    'Courses',
    'Lectures',
    'Screen recordings',
    'Local video or audio',
    'Subtitle files',
    'Supported public links',
];

const qualityItems = [
    ['Structured chapters', 'Concepts, examples, and conclusions are shaped before you start watching.'],
    ['Important reasoning', 'Key steps stay visible instead of being flattened into a generic summary.'],
    ['Transcript review', 'Subtitles and transcript stay available so the note can be checked against source.'],
    ['Conservative correction', 'Accepted transcript fixes can show original text, corrected text, reason, confidence, and time.'],
    ['Key moments', 'When local video is available, visual anchors help you return to formulas, code, slides, or screens.'],
    ['Exportable result', 'Markdown, PDF, and Feishu exports turn the result into a lasting study asset.'],
];

const outputItems = [
    ['Prepared note', 'Read the structure first, then study the video with better questions.'],
    ['Transcript and subtitles', 'Keep source text for unclear audio and recognition errors.'],
    ['Key visuals', 'Use important frames as review anchors when video evidence is available.'],
    ['Processing record', 'Running, failed, completed, downloads, and retries stay in one place.'],
];

const displayType = "[font-family:'Techna_Sans','Techna Sans','Avenir_Next','Nunito_Sans','Inter','ui-rounded','SF_Pro_Display',system-ui,sans-serif]";
const bodyType = "[font-family:'Avenir_Next','Inter','ui-rounded','SF_Pro_Text',system-ui,sans-serif]";
const dataType = "[font-family:'SF_Mono','ui-monospace','Menlo','Consolas',monospace]";
const lightGrain = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140' viewBox='0 0 140 140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.78' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' opacity='.48'/%3E%3C/svg%3E\")";
const darkGrain = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140' viewBox='0 0 140 140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.74' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)' fill='white' opacity='.30'/%3E%3C/svg%3E\")";
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

const HeroVisual = () => (
    <div className="ff-motion-demo relative min-h-[620px] lg:min-h-[640px]" aria-label="Animated demo: FluentFlow scans a long video and prepares reviewable study notes">
        <style>{`
            @keyframes ffScan {
                0%, 11% { transform: translateX(0); opacity: .55; }
                36% { transform: translateX(250px); opacity: 1; }
                54% { transform: translateX(250px); opacity: .9; }
                78%, 100% { transform: translateX(0); opacity: .55; }
            }
            @keyframes ffPulseRibbon {
                0%, 18%, 100% { transform: scaleX(.7); opacity: .42; }
                30%, 54% { transform: scaleX(1); opacity: 1; }
                72% { transform: scaleX(.85); opacity: .58; }
            }
            @keyframes ffGenerate {
                0%, 20% { opacity: 0; transform: translateY(12px) scale(.98); }
                31%, 100% { opacity: 1; transform: translateY(0) scale(1); }
            }
            @keyframes ffHighlight {
                0%, 48%, 100% { box-shadow: inset 0 0 0 1px rgba(42,143,117,.18); background: rgba(242,251,244,.92); }
                58%, 78% { box-shadow: inset 0 0 0 2px rgba(42,143,117,.6), 0 14px 28px rgba(42,143,117,.16); background: rgba(231,247,237,.98); }
            }
            @keyframes ffFix {
                0%, 62% { opacity: .28; transform: translateY(8px); }
                74%, 100% { opacity: 1; transform: translateY(0); }
            }
            @keyframes ffCursor {
                0%, 66% { opacity: 0; transform: translate(18px, -8px) rotate(-8deg); }
                78%, 88% { opacity: 1; transform: translate(0, 0) rotate(-8deg); }
                100% { opacity: 0; transform: translate(0, 0) rotate(-8deg); }
            }
            @media (prefers-reduced-motion: reduce) {
                .ff-motion-demo .ff-animated {
                    animation: none !important;
                    opacity: 1 !important;
                    transform: none !important;
                }
            }
        `}</style>
        <div className="absolute left-2 top-12 h-24 w-[74%] rounded-full bg-[linear-gradient(90deg,rgba(42,143,117,.18),rgba(245,176,86,.18),rgba(119,169,230,.14))] blur-2xl"/>
        <div className="absolute left-0 top-24 z-10 w-[320px] rotate-[-3deg] overflow-hidden rounded-[32px] border border-[#d6dfd2] bg-[#17201b] p-4 text-[#fff8ec] shadow-[0_34px_92px_-62px_rgba(23,32,27,.88)] dark:border-white/[0.14]">
            <div className="relative aspect-[16/10] overflow-hidden rounded-[24px] bg-[radial-gradient(circle_at_30%_25%,rgba(255,255,255,.35),transparent_17%),linear-gradient(145deg,rgba(245,176,86,.5),transparent_45%),linear-gradient(155deg,#365143,#131714_70%)]">
                <span className="absolute inset-x-5 bottom-5 h-2 rounded-full bg-white/18"/>
                <span className="ff-animated absolute bottom-5 left-5 h-2 w-16 origin-left rounded-full bg-[#8fd9c0]" style={{animation: 'ffPulseRibbon 6.4s ease-in-out infinite'}}/>
                <span className="ff-animated absolute bottom-1 left-5 h-[92%] w-[3px] rounded-full bg-[#fff8ec]/90 shadow-[0_0_20px_rgba(143,217,192,.8)]" style={{animation: 'ffScan 6.4s ease-in-out infinite'}}/>
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
                <div>
                    <p className={`${dataType} text-[11px] font-semibold uppercase tracking-[0.12em] text-[#b9dccd]`}>Scanning timeline</p>
                    <p className="mt-1 text-sm font-semibold">Course lecture · 1:12:44</p>
                </div>
                <span className="flex size-10 items-center justify-center rounded-full bg-white text-[#17201b]">
                    <Play className="size-4 fill-current" strokeWidth={2.4} aria-hidden="true"/>
                </span>
            </div>
        </div>

        <article className="absolute right-0 top-0 z-20 w-[min(540px,88%)] rounded-[34px] border border-[#d8e0d2] bg-white/92 p-5 shadow-[0_38px_104px_-70px_rgba(55,73,48,.92)] backdrop-blur dark:border-white/[0.13] dark:bg-[#182018]/92">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <span className={`${dataType} rounded-full bg-[#e7f7ed] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2f7c66] dark:bg-[#8fd9c0]/12 dark:text-[#8fd9c0]`}>Generating notes</span>
                <span className={`${dataType} text-[11px] font-medium text-[#7b867c] dark:text-white/[0.52]`}>18:42 source anchor</span>
            </div>
            <h2 className={`ff-animated mt-5 ${displayType} text-[32px] font-bold leading-[1.1] tracking-normal text-[#17201b] [text-wrap:balance] dark:text-[#f7f1e5] sm:text-[38px]`} style={{animation: 'ffGenerate 6.4s ease-in-out infinite'}}>
                03 Why attention works
            </h2>
            <div className="ff-animated mt-5 rounded-[24px] border border-[#d7eadb] bg-[#f2fbf4] p-4 dark:border-[#8fd9c0]/18 dark:bg-[#8fd9c0]/8" style={{animation: 'ffGenerate 6.4s ease-in-out infinite 360ms'}}>
                <p className="text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">Read the chapter conclusion first.</p>
                <p className="mt-2 text-sm font-medium leading-6 text-[#5f6a61] dark:text-white/[0.66]">
                    Query and key vectors compare each token against the current context. Examples, terms, and frames keep source positions.
                </p>
            </div>
            <div className="ff-animated mt-4 rounded-[24px] border border-[#d4e6f4] bg-[#eef7ff] p-4 dark:border-[#77a9e6]/20 dark:bg-[#77a9e6]/10" style={{animation: 'ffHighlight 6.4s ease-in-out infinite'}}>
                <p className="text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">Transcript and key moment highlighted.</p>
                <p className="mt-2 text-sm font-medium leading-6 text-[#526476] dark:text-white/[0.66]">
                    18:42 · “compare each token against the current context”
                </p>
            </div>
            <div className="ff-animated relative mt-4 rounded-[24px] border border-[#eadfca] bg-[#fff7e8] p-4 dark:border-[#f5b056]/18 dark:bg-[#f5b056]/10" style={{animation: 'ffFix 6.4s ease-in-out infinite'}}>
                <span className="ff-animated absolute right-5 top-4 rounded-full bg-[#17201b] px-3 py-1 text-[11px] font-semibold text-[#fff8ec] dark:bg-[#f7f1e5] dark:text-[#17201b]" style={{animation: 'ffCursor 6.4s ease-in-out infinite'}}>
                    Fix accepted
                </span>
                <p className="text-sm font-semibold text-[#17201b] dark:text-[#f7f1e5]">User fixes one uncertain detail.</p>
                <p className="mt-2 text-sm font-medium leading-6 text-[#6d614f] dark:text-white/[0.66]">
                    Original transcript stays traceable, while the study note uses the corrected wording.
                </p>
            </div>
            <div className={`mt-5 grid grid-cols-4 gap-2 text-[10px] font-medium tabular-nums text-[#768278] dark:text-white/[0.44] ${dataType}`}>
                {timeline.map((item) => <span key={item}>{item}</span>)}
            </div>
            <div className="mt-2 grid grid-cols-4 gap-1">
                {timeline.map((item, index) => (
                    <span key={`${item}-ribbon`} className={`h-2 origin-left rounded-full ${index === 1 ? 'ff-animated bg-[#2a8f75]' : 'bg-[#dbe7dc] dark:bg-white/[0.14]'}`} style={index === 1 ? {animation: 'ffPulseRibbon 6.4s ease-in-out infinite'} : undefined}/>
                ))}
            </div>
        </article>

        <aside className="absolute bottom-6 left-4 z-10 w-[min(330px,72%)] rounded-[30px] border border-[#c9ead4] bg-[#dbf6e4]/92 p-5 shadow-[0_26px_70px_-52px_rgba(45,100,65,.7)] backdrop-blur dark:border-[#8fd9c0]/18 dark:bg-[#8fd9c0]/12">
            <p className={`${dataType} text-[11px] font-semibold uppercase tracking-[0.12em] text-[#2f7c66] dark:text-[#8fd9c0]`}>Study with the video</p>
            <p className="mt-2 text-lg font-bold leading-snug text-[#17201b] dark:text-[#f7f1e5]">Pause less. Rewind less. Clean up less.</p>
            <p className="mt-2 text-sm font-medium leading-6 text-[#4d6658] dark:text-white/[0.66]">The video stays central. FluentFlow prepares the note before you study.</p>
        </aside>
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

const Landing = () => (
    <main
        id="main-content"
        className={`relative h-dvh overflow-y-auto scroll-smooth bg-[#fff8ec] text-[#17201b] motion-reduce:scroll-auto dark:bg-[#111612] dark:text-[#f7f1e5] ${bodyType}`}
    >
        <div className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(circle_at_18%_10%,rgba(42,143,117,.16),transparent_28rem),radial-gradient(circle_at_84%_12%,rgba(245,176,86,.18),transparent_30rem),linear-gradient(180deg,#fff8ec_0%,#f6fbf2_52%,#fffaf0_100%)] dark:bg-[radial-gradient(circle_at_18%_10%,rgba(143,217,192,.12),transparent_28rem),radial-gradient(circle_at_84%_12%,rgba(245,176,86,.10),transparent_30rem),linear-gradient(180deg,#111612_0%,#161d18_55%,#111612_100%)]"/>
        <div className="pointer-events-none fixed inset-0 z-0 opacity-[0.10] mix-blend-multiply dark:hidden" style={{backgroundImage: lightGrain}}/>
        <div className="pointer-events-none fixed inset-0 z-0 hidden opacity-[0.055] mix-blend-screen dark:block" style={{backgroundImage: darkGrain}}/>
        <a href="#homepage-hero" className={`sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:bg-[#17201b] focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-[#fff8ec] dark:focus:bg-[#f7f1e5] dark:focus:text-[#17201b] ${focusRing}`}>
            Skip to main content
        </a>

        <header className="sticky top-0 z-40 border-b border-[#dce5d8]/90 bg-[#fff8ec]/78 backdrop-blur-xl dark:border-white/[0.11] dark:bg-[#111612]/86">
            <div className="mx-auto flex h-[70px] max-w-7xl items-center justify-between gap-5 px-5 sm:px-6 lg:px-8">
                <Link to="/" className={`flex min-w-0 items-center gap-3 rounded-[16px] ${focusRing}`} aria-label="FluentFlow">
                    <LogoMark/>
                    <span className={`truncate text-base font-semibold tracking-normal ${displayType}`}>FluentFlow</span>
                </Link>
                <nav className="hidden items-center gap-7 text-sm font-medium text-[#5f6a61] dark:text-white/[0.68] md:flex">
                    <a href="#workflow" className={`${interactiveMotion} rounded-full px-1 hover:text-[#17201b] dark:hover:text-white ${focusRing}`}>Study flow</a>
                    <a href="#quality" className={`${interactiveMotion} rounded-full px-1 hover:text-[#17201b] dark:hover:text-white ${focusRing}`}>Note quality</a>
                    <a href="#sources" className={`${interactiveMotion} rounded-full px-1 hover:text-[#17201b] dark:hover:text-white ${focusRing}`}>Sources</a>
                </nav>
                <div className="flex shrink-0 items-center gap-2">
                    <Link to="/app" className={`hidden h-10 touch-manipulation items-center justify-center rounded-full border border-[#dce5d8] bg-white/60 px-4 text-sm font-medium text-[#17201b] ${interactiveMotion} hover:bg-[#f4fbf5] active:translate-y-px dark:border-white/[0.15] dark:bg-white/[0.055] dark:text-white/[0.88] dark:hover:bg-white/[0.10] sm:inline-flex ${focusRing}`}>
                        Open app
                    </Link>
                    <Link to="/media-text" className={`inline-flex h-10 touch-manipulation items-center justify-center gap-2 rounded-full bg-[#17201b] px-4 text-sm font-semibold text-[#fff8ec] ${interactiveMotion} hover:bg-[#24352d] active:translate-y-px dark:bg-[#f7f1e5] dark:text-[#17201b] dark:hover:bg-[#e9dcc8] ${focusRing}`}>
                        Start a video
                        <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden="true"/>
                    </Link>
                </div>
            </div>
        </header>

        <section id="homepage-hero" className={`${sectionShell} relative z-10 grid min-h-[calc(100dvh-70px)] scroll-mt-24 items-center gap-10 py-10 sm:py-12 lg:grid-cols-[0.9fr_1.1fr] lg:py-14`}>
            <div className="max-w-3xl">
                <p className={eyebrowClass}>Long-video study notes</p>
                <h1 className={`mt-5 max-w-[10.8em] ${displayType} text-[42px] font-bold leading-[1.06] tracking-normal text-[#17201b] [text-wrap:balance] dark:text-[#f7f1e5] sm:text-[56px] lg:text-[68px]`}>
                    Turn long videos into study-ready notes first.
                </h1>
                <p className="mt-6 max-w-[62ch] text-[17px] font-medium leading-8 text-[#5f6a61] [text-wrap:pretty] dark:text-white/[0.70] sm:text-[18px]">
                    Give FluentFlow courses, lectures, screen recordings, and video links. Get structured notes, transcript and subtitles, and key moments before you study with the video. Then fix only the few uncertain details.
                </p>
                <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                    <Link to="/media-text" className={primaryButton}>
                        Start processing
                        <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden="true"/>
                    </Link>
                    <a href="#workflow" className={secondaryButton}>
                        See the study flow
                    </a>
                </div>
                <p className={`${dataType} mt-5 max-w-[54ch] text-[12px] font-medium leading-6 text-[#6f7b70] dark:text-white/[0.54]`}>
                    FluentFlow does not replace watching. It removes the note-taking drag before you begin.
                </p>
            </div>
            <HeroVisual/>
        </section>

        <section id="workflow" className="relative z-10 scroll-mt-24 border-y border-[#dce5d8] bg-white/58 backdrop-blur-sm dark:border-white/[0.10] dark:bg-white/[0.035]">
            <div className={`${sectionShell} py-16 lg:py-24`}>
                <SectionHeader
                    eyebrow="Before / After"
                    title="Study with notes ready, not with a pause button under your finger."
                    desc="The learning path still runs through the video. FluentFlow simply prepares the note, transcript, and review anchors first."
                />
                <div className="mt-10 grid gap-4 lg:grid-cols-2">
                    <WorkflowCard
                        tone="before"
                        title="Before"
                        items={[
                            ['Open a long video', 'You must decide what to capture from the first minute.'],
                            ['Pause and rewind', 'One missed sentence breaks attention and sends you back.'],
                            ['Clean the note later', 'After watching, chapters and examples still need manual cleanup.'],
                        ]}
                    />
                    <WorkflowCard
                        tone="after"
                        title="After"
                        items={[
                            ['Generate notes first', 'Chapters, subtitles, and key moments are prepared upfront.'],
                            ['Study with the video', 'Focus on the lesson and revisit the source only when needed.'],
                            ['Fix a few details', 'Correct the small number of uncertain recognition or wording issues.'],
                        ]}
                    />
                </div>
            </div>
        </section>

        <section id="quality" className={`${sectionShell} relative z-10 scroll-mt-24 py-16 lg:py-24`}>
            <SectionHeader
                eyebrow="What quality means"
                title="Not a summary. A reviewable study asset."
                desc="High-quality notes are structured, source-grounded, and useful after the first read."
            />
            <div className="mt-10 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {qualityItems.map(([title, desc], index) => {
                    const icons = [BookOpenText, ScanSearch, Captions, FileText, Image, Download];
                    const Icon = icons[index] || BookOpenText;
                    return (
                        <article key={title} className={`rounded-[28px] border border-[#dce5d8] bg-white/72 p-5 shadow-[0_20px_58px_-46px_rgba(46,73,58,.45)] backdrop-blur ${interactiveMotion} hover:-translate-y-0.5 hover:border-[#9fcab8] hover:bg-white dark:border-white/[0.11] dark:bg-white/[0.055] dark:hover:border-[#8fd9c0]/45`}>
                            <Icon className="size-6 text-[#2f7c66] dark:text-[#8fd9c0]" strokeWidth={2.05} aria-hidden="true"/>
                            <h3 className={`mt-5 ${displayType} text-xl font-semibold leading-tight tracking-normal text-[#17201b] dark:text-[#f7f1e5]`}>{title}</h3>
                            <p className="mt-3 text-sm font-medium leading-6 text-[#626d64] dark:text-white/[0.66]">{desc}</p>
                        </article>
                    );
                })}
            </div>
        </section>

        <section id="sources" className="relative z-10 scroll-mt-24 border-y border-[#dce5d8] bg-[#f3fbf2]/70 backdrop-blur-sm dark:border-white/[0.10] dark:bg-[#8fd9c0]/5">
            <div className={`${sectionShell} grid gap-10 py-16 lg:grid-cols-[0.86fr_1.14fr] lg:items-center lg:py-24`}>
                <div>
                    <p className={eyebrowClass}>Source coverage</p>
                    <h2 className={`mt-4 max-w-[12em] ${displayType} text-[34px] font-bold leading-[1.08] tracking-normal text-[#17201b] [text-wrap:balance] dark:text-[#f7f1e5] sm:text-[46px]`}>
                        Courses, lectures, recordings, files, and supported public links.
                    </h2>
                    <p className="mt-5 max-w-[60ch] text-base font-medium leading-relaxed text-[#626d64] dark:text-white/[0.66]">
                        Public video platforms may restrict media or caption access. Local upload and subtitle files are the most reliable path.
                    </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                    {sourceItems.map((item) => (
                        <div key={item} className="flex min-h-[76px] items-center gap-3 rounded-[24px] border border-[#d2dfd2] bg-white/78 px-4 py-3 shadow-[0_16px_42px_-38px_rgba(46,73,58,.35)] dark:border-white/[0.12] dark:bg-white/[0.055]">
                            <span className="flex size-10 shrink-0 items-center justify-center rounded-[15px] bg-[#dff7e8] text-[#2f7c66] dark:bg-[#8fd9c0]/13 dark:text-[#8fd9c0]">
                                <UploadCloud className="size-5" strokeWidth={2.1} aria-hidden="true"/>
                            </span>
                            <p className="text-sm font-semibold leading-tight text-[#17201b] dark:text-[#f7f1e5]">{item}</p>
                        </div>
                    ))}
                </div>
            </div>
        </section>

        <section className={`${sectionShell} relative z-10 py-16 lg:py-24`}>
            <SectionHeader
                eyebrow="What you keep"
                title="A record you can study, review, and export."
                desc="The output is not a disposable chat answer. It becomes a place to revisit the video, check the transcript, and keep the result."
            />
            <div className="mt-10 grid gap-4 lg:grid-cols-4">
                {outputItems.map(([title, desc], index) => {
                    const icons = [FileText, Captions, Film, CheckCircle2];
                    const Icon = icons[index] || FileText;
                    return (
                        <article key={title} className="rounded-[28px] border border-[#dce5d8] bg-white/72 p-5 shadow-[0_18px_52px_-44px_rgba(46,73,58,.42)] dark:border-white/[0.11] dark:bg-white/[0.055]">
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
                    <p className={`${dataType} text-[11px] font-semibold uppercase tracking-[0.16em] text-[#8fd9c0]`}>Start with one real video</p>
                    <h2 className={`mt-3 ${displayType} text-[34px] font-bold leading-[1.08] tracking-normal [text-wrap:balance] sm:text-[48px]`}>
                        Give FluentFlow the next video you want to learn.
                    </h2>
                    <p className="mt-4 text-base font-medium leading-relaxed text-white/[0.72]">
                        Start with a real course, lecture, or recording. Generate the note first, then study and correct it with the video.
                    </p>
                </div>
                <div className="relative mt-8 flex flex-col gap-3 sm:flex-row lg:mt-0">
                    <Link to="/media-text" className="inline-flex h-12 touch-manipulation items-center justify-center gap-2 rounded-full bg-[#fff8ec] px-6 text-sm font-semibold text-[#17201b] transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200 ease-out hover:-translate-y-0.5 hover:bg-[#e9dcc8] active:translate-y-px">
                        Start processing
                        <ArrowRight className="size-4" strokeWidth={2.25} aria-hidden="true"/>
                    </Link>
                    <Link to="/agent" className="inline-flex h-12 touch-manipulation items-center justify-center rounded-full border border-white/[0.18] bg-white/[0.06] px-6 text-sm font-semibold text-white transition-[color,background-color,border-color,box-shadow,transform,opacity] duration-200 ease-out hover:-translate-y-0.5 hover:bg-white/[0.12] active:translate-y-px">
                        View processing records
                    </Link>
                </div>
            </div>
        </section>
    </main>
);

export default Landing;
