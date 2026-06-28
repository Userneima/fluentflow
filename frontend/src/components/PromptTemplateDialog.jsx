import {BUILTIN_EXTRA_PROMPT_KEYS, editorPresetKeyOrder} from '../lib/promptPresets.js';
import SvgIcon from '../components/SvgIcon.jsx';

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

    const presetChipClass = (active) => [
        'inline-flex items-center gap-0.5 rounded-[13px] border text-xs font-extrabold transition',
        active
            ? 'border-[#111111] bg-[#111111] text-white dark:border-white dark:bg-white dark:text-[#111111]'
            : 'border-[#dedada] bg-[#fbfbfb] text-[#57585d] hover:bg-[#efeeee] hover:text-[#111111] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/62 dark:hover:bg-white/[0.10] dark:hover:text-white',
    ].join(' ');
    const presetButtonClass = (active, side = '') => [
        'py-2 transition active:translate-y-px',
        side === 'left' ? 'rounded-l-[12px] pl-3 pr-2' : '',
        side === 'right' ? 'rounded-r-[12px] py-2 pl-1 pr-2' : '',
        !side ? 'rounded-[12px] px-3' : '',
        active ? '' : 'hover:bg-[#e8e5e5] dark:hover:bg-white/[0.08]',
    ].join(' ');
    const textAreaClass = 'w-full min-h-[200px] resize-y rounded-[16px] border border-[#dedada] bg-[#fbfbfb] px-4 py-3 font-mono text-sm leading-relaxed text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40';
    const inputClass = 'min-w-[160px] flex-1 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-3 py-2 text-sm font-semibold text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40';

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-5 py-8 backdrop-blur-sm animate-[fadeIn_0.16s_ease-out]" role="dialog" aria-modal="true" onClick={onClose}>
            <div className="flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-[22px] border border-[#dedada] bg-white shadow-[0_28px_90px_-52px_rgba(17,17,17,.72)] dark:border-white/[0.12] dark:bg-[#151515]" onClick={(e)=>e.stopPropagation()}>
                <div className="flex items-start justify-between gap-4 border-b border-[#ece8e8] px-5 py-4 dark:border-white/[0.10]">
                    <div className="min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="flex size-9 items-center justify-center rounded-[13px] bg-[#111111] text-white dark:bg-white dark:text-[#111111]">
                                <SvgIcon name="auto_fix_high" className="text-lg"/>
                            </span>
                            <span className="font-headline text-base font-extrabold text-[#111111] dark:text-white">{t('prompt.label')}</span>
                        </div>
                        <p className="mt-2 text-xs font-semibold text-[#85868c] dark:text-white/45">{t('prompt.editHint')}</p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[13px] bg-[#f4f3f3] text-[#676970] transition hover:bg-[#efeeee] hover:text-[#111111] active:translate-y-px dark:bg-white/[0.08] dark:text-white/55 dark:hover:bg-white/[0.12] dark:hover:text-white"
                        aria-label={lang === 'zh' ? '关闭' : 'Close'}
                    >
                        <SvgIcon name="close" className="text-lg"/>
                    </button>
                </div>
                <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
                    <div className="flex gap-2 flex-wrap">
                        {editorPresetKeyOrder(settings).map((key) => (
                            key.startsWith('user_') ? (
                                <span key={key} className={presetChipClass(promptKey===key)}>
                                    <button type="button" onClick={()=>handlePromptKeyChange(key)}
                                        className={presetButtonClass(promptKey===key, 'left')}>
                                        {presetLabel(key)}
                                    </button>
                                    <button type="button" title={t('set.deletePreset')} onClick={(e)=>handleDeleteUserPreset(key,e)}
                                        className={`${presetButtonClass(promptKey===key, 'right')} flex items-center justify-center ${promptKey===key?'hover:bg-white/10 dark:hover:bg-[#efeeee]':'text-red-600 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-500/10'}`}>
                                        <SvgIcon name="close" className="text-[16px] leading-none"/>
                                    </button>
                                </span>
                            ) : BUILTIN_EXTRA_PROMPT_KEYS.includes(key) ? (
                                <span key={key} className={presetChipClass(promptKey===key)}>
                                    <button type="button" onClick={()=>handlePromptKeyChange(key)}
                                        className={presetButtonClass(promptKey===key, 'left')}>
                                        {presetLabel(key)}
                                    </button>
                                    <button
                                        type="button"
                                        title={t('set.deleteBuiltinPrompt')}
                                        onClick={(e)=>{ e.stopPropagation(); e.preventDefault(); resetBuiltinExtra(key); }}
                                        className={`${presetButtonClass(promptKey===key, 'right')} flex items-center justify-center ${promptKey===key?'hover:bg-white/10 dark:hover:bg-[#efeeee]':'text-red-600 hover:bg-red-50 dark:text-red-300 dark:hover:bg-red-500/10'}`}
                                    >
                                        <SvgIcon name="close" className="text-[16px] leading-none"/>
                                    </button>
                                </span>
                            ) : (
                                <button key={key} onClick={()=>handlePromptKeyChange(key)}
                                    className={presetChipClass(promptKey===key)}>
                                    {presetLabel(key)}
                                </button>
                            )
                        ))}
                    </div>
                    {promptKey === 'default' ? (
                        <div className="space-y-2">
                            <label className="text-xs font-medium text-on-surface-variant">{t('set.editCoursePrompt')}</label>
                            <textarea
                                className={textAreaClass}
                                value={defaultPromptEdit}
                                onChange={(e)=>handleDefaultPromptChange(e.target.value)}
                            />
                        </div>
                    ) : promptKey.startsWith('user_') ? (
                        <div className="space-y-2">
                            <label className="text-xs font-medium text-on-surface-variant">{lang==='zh'?'编辑该预设':'Edit this preset'}</label>
                            <textarea
                                className={textAreaClass}
                                value={userPresetEdit}
                                onChange={(e)=>handleUserPresetChange(e.target.value)}
                            />
                        </div>
                    ) : promptKey === 'custom' ? (
                        <div className="space-y-3">
                            <textarea
                                className={`${textAreaClass} h-32 min-h-[8rem]`}
                                placeholder={t('prompt.customPlaceholder')}
                                value={customText}
                                onChange={e=>handleCustomTextChange(e.target.value)}
                            />
                            <div className="flex flex-wrap items-end gap-2">
                                <input type="text" className={inputClass} placeholder={t('set.presetNamePh')} value={presetNameInput} onChange={e=>setPresetNameInput(e.target.value)} />
                                <button type="button" onClick={saveCustomAsPresetFromEditor} className="h-10 rounded-[14px] bg-[#111111] px-4 text-sm font-extrabold text-white transition hover:bg-[#2a2a2a] active:translate-y-px dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]">
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
                                className={textAreaClass}
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
