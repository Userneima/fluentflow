import {useEffect, useState} from 'react';
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
    Moon,
    RotateCcw,
    ScanSearch,
    Sun,
} from 'lucide-react';

import HeroProofDemo from './landing/HeroProofDemo.jsx';
import {landingCopy, sourceIconItems} from './landing/content.js';
import {
    bodyType,
    darkGrain,
    darkPageFrost,
    dataType,
    displayType,
    eyebrowClass,
    focusRing,
    interactiveMotion,
    lightGrain,
    lightPageFrost,
    primaryButton,
    secondaryButton,
    sectionShell,
} from './landing/styles.js';

const LogoMark = () => (
    <span className="flex size-10 items-center justify-center rounded-[15px] bg-[#17201b] text-[#fff8ec] shadow-[0_18px_42px_-28px_rgba(23,32,27,.7)] dark:bg-[#f7f1e5] dark:text-[#17201b]">
        <svg viewBox="0 0 64 64" className="size-[29px]" fill="none" aria-hidden="true">
            <rect x="16" y="18" width="30" height="28" rx="10" fill="currentColor"/>
            <rect x="44" y="25" width="8" height="14" rx="4" fill="currentColor"/>
            <path d="M25 29h12M25 36h8" stroke="var(--ff-logo-line, #17201b)" strokeWidth="4.1" strokeLinecap="round" className="[--ff-logo-line:#17201b] dark:[--ff-logo-line:#f7f1e5]"/>
        </svg>
    </span>
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
                    <Link to="/media-text" className={`hidden h-10 touch-manipulation items-center justify-center rounded-full border border-[#dce5d8] bg-white/60 px-4 text-sm font-medium text-[#17201b] ${interactiveMotion} hover:bg-[#f4fbf5] active:translate-y-px dark:border-white/[0.15] dark:bg-white/[0.055] dark:text-white/[0.88] dark:hover:bg-white/[0.10] sm:inline-flex ${focusRing}`}>
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
