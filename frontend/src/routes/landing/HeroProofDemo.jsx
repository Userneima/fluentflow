import {useEffect, useState} from 'react';
import {
    BookOpenText,
    Captions,
    CheckCircle2,
    Download,
    FileText,
    Film,
    Image,
    Link2,
    MicVocal,
    Play,
    ScanSearch,
    UploadCloud,
} from 'lucide-react';

import {dataType, focusRing, interactiveMotion} from './styles.js';

const carouselStepMs = 6500;

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


export default HeroProofDemo;
