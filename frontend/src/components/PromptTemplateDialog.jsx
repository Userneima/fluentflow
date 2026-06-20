import {BUILTIN_EXTRA_PROMPT_KEYS, editorPresetKeyOrder} from '../lib/promptPresets.js';

const builtinPromptValue = ({
    promptKey,
    autoTranscriptNotesEdit,
    meetingEdit,
    researchEdit,
    quickBulletsEdit,
}) => {
    if (promptKey === 'autoTranscriptNotes') return autoTranscriptNotesEdit;
    if (promptKey === 'meeting') return meetingEdit;
    if (promptKey === 'research') return researchEdit;
    return quickBulletsEdit;
};

export default function PromptTemplateDialog({
    open,
    onClose,
    t,
    lang,
    settings,
    promptKey,
    presetLabel,
    handlePromptKeyChange,
    handleDeleteUserPreset,
    resetBuiltinExtra,
    defaultPromptEdit,
    handleDefaultPromptChange,
    userPresetEdit,
    handleUserPresetChange,
    customText,
    handleCustomTextChange,
    presetNameInput,
    setPresetNameInput,
    saveCustomAsPresetFromEditor,
    autoTranscriptNotesEdit,
    meetingEdit,
    researchEdit,
    quickBulletsEdit,
    handleBuiltinExtraChange,
}) {
    if (!open) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-5 py-8 backdrop-blur-sm animate-[fadeIn_0.16s_ease-out]" role="dialog" aria-modal="true" onClick={onClose}>
            <div className="flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-sm border ff-border-muted bg-surface-container-lowest shadow-2xl" onClick={(e)=>e.stopPropagation()}>
                <div className="flex items-start justify-between gap-4 border-b border-surface-container-highest px-5 py-4">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-amber-600 text-lg">auto_fix_high</span>
                            <span className="font-headline font-bold text-base text-on-surface">{t('prompt.label')}</span>
                        </div>
                        <p className="mt-1 text-xs font-medium text-on-surface-variant">{t('prompt.editHint')}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-sm bg-surface-container text-on-surface-variant transition hover:bg-surface-container-high hover:text-on-surface"
                        aria-label={lang === 'zh' ? '关闭' : 'Close'}
                    >
                        <span className="material-symbols-outlined text-lg">close</span>
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
                    <div className="flex gap-2 flex-wrap">
                        {editorPresetKeyOrder(settings).map((key) => (
                            key.startsWith('user_') ? (
                                <span key={key} className={`inline-flex items-center gap-0.5 rounded-full border text-xs font-semibold transition-all ${
                                    promptKey===key
                                    ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                                    : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300 hover:bg-amber-50'
                                }`}>
                                    <button type="button" onClick={()=>handlePromptKeyChange(key)}
                                        className={`px-3 py-1.5 rounded-l-full ${promptKey===key?'':'hover:bg-amber-50/50'}`}>
                                        {presetLabel(key)}
                                    </button>
                                    <button type="button" title={t('set.deletePreset')} onClick={(e)=>handleDeleteUserPreset(key,e)}
                                        className={`pr-1.5 py-1 rounded-r-full flex items-center justify-center ${promptKey===key?'hover:bg-amber-700/30':'hover:bg-red-50 text-red-600'}`}>
                                        <span className="material-symbols-outlined text-[16px] leading-none">close</span>
                                    </button>
                                </span>
                            ) : BUILTIN_EXTRA_PROMPT_KEYS.includes(key) ? (
                                <span key={key} className={`inline-flex items-center gap-0.5 rounded-full border text-xs font-semibold transition-all ${
                                    promptKey===key
                                    ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                                    : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300 hover:bg-amber-50'
                                }`}>
                                    <button type="button" onClick={()=>handlePromptKeyChange(key)}
                                        className={`px-3 py-1.5 rounded-l-full ${promptKey===key?'':'hover:bg-amber-50/50'}`}>
                                        {presetLabel(key)}
                                    </button>
                                    <button
                                        type="button"
                                        title={t('set.deleteBuiltinPrompt')}
                                        onClick={(e)=>{ e.stopPropagation(); e.preventDefault(); resetBuiltinExtra(key); }}
                                        className={`pr-1.5 py-1 rounded-r-full flex items-center justify-center ${promptKey===key?'hover:bg-amber-700/30':'hover:bg-red-50 text-red-600'}`}
                                    >
                                        <span className="material-symbols-outlined text-[16px] leading-none">close</span>
                                    </button>
                                </span>
                            ) : (
                                <button key={key} onClick={()=>handlePromptKeyChange(key)}
                                    className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all border ${
                                        promptKey===key
                                        ? 'bg-amber-600 text-white border-amber-600 shadow-sm'
                                        : 'bg-white text-slate-600 border-slate-200 hover:border-amber-300 hover:bg-amber-50'
                                    }`}>
                                    {presetLabel(key)}
                                </button>
                            )
                        ))}
                    </div>
                    {promptKey === 'default' ? (
                        <div className="space-y-2">
                            <label className="text-xs font-medium text-on-surface-variant">{t('set.editCoursePrompt')}</label>
                            <textarea
                                className="w-full min-h-[200px] bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                value={defaultPromptEdit}
                                onChange={(e)=>handleDefaultPromptChange(e.target.value)}
                            />
                        </div>
                    ) : promptKey.startsWith('user_') ? (
                        <div className="space-y-2">
                            <label className="text-xs font-medium text-on-surface-variant">{lang==='zh'?'编辑该预设':'Edit this preset'}</label>
                            <textarea
                                className="w-full min-h-[200px] bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                value={userPresetEdit}
                                onChange={(e)=>handleUserPresetChange(e.target.value)}
                            />
                        </div>
                    ) : promptKey === 'custom' ? (
                        <div className="space-y-3">
                            <textarea
                                className="w-full h-32 bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface placeholder-slate-400 focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                placeholder={t('prompt.customPlaceholder')}
                                value={customText}
                                onChange={e=>handleCustomTextChange(e.target.value)}
                            />
                            <div className="flex flex-wrap items-end gap-2">
                                <input type="text" className="flex-1 min-w-[160px] bg-white border border-slate-200 rounded-lg px-3 py-2 text-sm" placeholder={t('set.presetNamePh')} value={presetNameInput} onChange={e=>setPresetNameInput(e.target.value)} />
                                <button type="button" onClick={saveCustomAsPresetFromEditor} className="px-4 py-2 bg-amber-600 text-white text-sm font-semibold rounded-lg hover:bg-amber-700 transition">
                                    {t('prompt.saveAsPreset')}
                                </button>
                            </div>
                        </div>
                    ) : BUILTIN_EXTRA_PROMPT_KEYS.includes(promptKey) ? (
                        <div className="space-y-2">
                            <div className="flex flex-wrap justify-between items-center gap-2">
                                <label className="text-xs font-medium text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                <button type="button" onClick={()=>resetBuiltinExtra(promptKey)} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                            </div>
                            <textarea
                                className="w-full min-h-[200px] bg-white border border-slate-200 rounded-lg px-4 py-3 text-sm font-mono text-on-surface focus:ring-2 focus:ring-amber-300/50 focus:border-amber-300 resize-y"
                                value={builtinPromptValue({promptKey, autoTranscriptNotesEdit, meetingEdit, researchEdit, quickBulletsEdit})}
                                onChange={(e)=>handleBuiltinExtraChange(promptKey, e.target.value)}
                            />
                        </div>
                    ) : null}
                </div>
            </div>
        </div>
    );
}
