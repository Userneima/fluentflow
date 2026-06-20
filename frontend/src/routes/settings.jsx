import {useState,useEffect,useRef,useCallback,useMemo} from 'react';
import {Link,useNavigate} from 'react-router-dom';
import {
    BUILTIN_EXTRA_PROMPT_KEYS,
    DEFAULT_PROMPT_PRESET,
    allPresetSelectKeys,
    getBuiltinExtraPromptBody,
    getDefaultPromptBody,
    isBuiltinPromptPresetHidden,
    normalizeUserPresets,
    presetDisplayLabel,
    resolveSystemPromptFromSettings,
} from '../lib/promptPresets.js';
import {
    azureSpeechMissingMessage,
    compactDisplayFilename,
    createTaskId,
    effectiveSttProvider,
    fmtElapsed,
    fmtFileSize,
    friendlyTaskError,
    isAzureBatchConfigured,
    isAzureCloudProvider,
    isLocalHistoryResult,
    isSttProgressUnmeasured,
    jobToCurrentJob,
    jobToHistoryEntry,
    noteModeLabel,
    normalizeSttModel,
    normalizeSttProvider,
    pickTranscriptSegments,
    timeAgo,
    useApi,
    useApp,
    useAuth,
    useI18n,
    useSettings,
} from '../app/shared.jsx';

const Settings = () => {
    const {t, lang} = useI18n();
    const {loadSettings,saveSettings} = useSettings();
    const {clearHistory,history,larkExports} = useApp();
    const [settings,setSettings] = useState(() => loadSettings());
    const [saved,setSaved] = useState(false);
    const [cleared,setCleared] = useState(false);
    const [clearArmed,setClearArmed] = useState(false);
    const templateCount = allPresetSelectKeys(settings).length;

    // 如果当前已被隐藏的内置模板仍被选中，兜底切回 default
    useEffect(() => {
        const pk = (settings && settings.promptPreset) || 'default';
        if (isBuiltinPromptPresetHidden(pk, settings)) {
            const next = { ...settings, promptPreset: 'default' };
            setSettings(next);
            saveSettings(next);
        }
    }, []);

    const isDark = settings.theme === 'dark';
    const applyTheme = (theme) => {
        const next = {...settings, theme};
        setSettings(next);
        saveSettings(next);
        document.documentElement.classList.toggle('dark', theme==='dark');
    };

    const handleSave = () => { saveSettings(settings); setSaved(true); setTimeout(()=>setSaved(false),2000); };
    const updateSettingNow = (patch) => {
        setSettings((s) => {
            const next = {...s, ...patch};
            saveSettings(next);
            return next;
        });
    };

    const resetDefaultPromptInSettings = () => {
        setSettings((s) => {
            const next = { ...s, defaultPromptOverride: '' };
            saveSettings(next);
            return next;
        });
    };

    const resetBuiltinOverrideInSettings = (key) => {
        if (!window.confirm(t('set.deleteBuiltinPromptConfirm'))) return;
        setSettings((s) => {
            const hidden = new Set(Array.isArray(s.hiddenPromptPresets) ? s.hiddenPromptPresets : []);
            hidden.add(key);
            const next = {
                ...s,
                hiddenPromptPresets: Array.from(hidden),
                promptPreset: s.promptPreset === key ? 'default' : s.promptPreset,
            };
            saveSettings(next);
            return next;
        });
        if (templateEditKey === key) setTemplateEditKey('default');
    };

    const [newPresetNameSettings, setNewPresetNameSettings] = useState('');
    const initialTemplateEditKey = (() => {
        const key = settings.promptPreset || DEFAULT_PROMPT_PRESET;
        return isBuiltinPromptPresetHidden(key, settings) ? 'default' : key;
    })();
    const [templateEditKey, setTemplateEditKey] = useState(initialTemplateEditKey);

    const saveCustomAsPresetInSettings = () => {
        const name = newPresetNameSettings.trim();
        if (!name || !(settings.customPromptText || '').trim()) return;
        const id = 'user_' + Date.now();
        setSettings((s) => {
            const next = {
                ...s,
                userPromptPresets: [{ id, nameZh: name, nameEn: name, prompt: s.customPromptText }, ...(s.userPromptPresets || [])],
            };
            saveSettings(next);
            return next;
        });
        setNewPresetNameSettings('');
    };

    const deleteUserPresetInSettings = (id) => {
        if (!window.confirm(t('set.deletePresetConfirm'))) return;
        setSettings((s) => {
            const ups = normalizeUserPresets(s).filter((p) => p.id !== id);
            const next = { ...s, userPromptPresets: ups };
            if (next.promptPreset === id) next.promptPreset = 'default';
            saveSettings(next);
            return next;
        });
    };

    const handleClear = () => {
        if(history.length === 0) return;
        if(!clearArmed){
            setClearArmed(true);
            setTimeout(()=>setClearArmed(false), 5000); // 5秒内二次确认
            return;
        }
        setClearArmed(false);
        clearHistory();
        setCleared(true);
        setTimeout(()=>setCleared(false),2000);
            };

    const preferencesPanel = (
        <section className="bg-surface-container-lowest/95 backdrop-blur-xl rounded-sm p-4 shadow-sm border ff-border-muted w-full xl:w-[420px] flex-shrink-0">
            <div className="flex items-center justify-between gap-3 mb-3">
                <h2 className="text-sm font-bold font-headline text-on-surface">{t('set.prefs')}</h2>
                <div className="grid grid-cols-2 gap-1 p-1 bg-surface-container-low rounded-sm">
                    <button onClick={()=>applyTheme('light')} className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-sm text-xs font-semibold transition ${!isDark?'bg-primary text-white shadow-sm':'text-on-surface-variant hover:bg-surface-container-high'}`}>
                        <span className="material-symbols-outlined text-sm">light_mode</span>{t('set.light')}
                    </button>
                    <button onClick={()=>applyTheme('dark')} className={`flex items-center justify-center gap-1.5 px-3 py-2 rounded-sm text-xs font-semibold transition ${isDark?'bg-primary text-white shadow-sm':'text-on-surface-variant hover:bg-surface-container-high'}`}>
                        <span className="material-symbols-outlined text-sm">dark_mode</span>{t('set.dark')}
                    </button>
                </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
                <button onClick={handleClear} disabled={history.length===0} className={`py-3 px-3 rounded-sm font-semibold text-xs transition disabled:opacity-30 flex items-center justify-center gap-2 ${clearArmed?'bg-red-600 text-white ring-2 ring-red-300/70':'bg-red-50 text-red-600 hover:bg-red-100'}`}>
                    <span className="material-symbols-outlined text-sm">delete_sweep</span>
                    {cleared ? t('edit.clearConfirm') : (clearArmed ? t('edit.clearConfirmAgain') : `${t('edit.clearHistory')} (${history.length})`)}
                </button>
                <button onClick={handleSave} className="py-3 px-3 bg-primary-container text-white rounded-sm font-bold text-xs shadow-lg shadow-primary/20 hover:scale-[1.02] transition-all flex items-center justify-center gap-2">
                    <span className="material-symbols-outlined text-sm">{saved?"check":"save"}</span>
                    {saved ? t('set.saved') : t('set.saveAll')}
                </button>
            </div>
            {clearArmed && (
                <p className="mt-2 text-[11px] font-medium text-red-600 text-center">{t('edit.clearConfirmAgain')}</p>
            )}
        </section>
    );

            return (
            <div className="ml-64 min-h-screen relative pb-8">
                <main className="p-12 max-w-7xl mx-auto h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
                    <header className="mb-8 flex flex-col xl:flex-row xl:items-start justify-between gap-6">
                <div className="min-w-0 pt-2">
                    <h1 className="text-4xl font-extrabold tracking-tight text-on-surface mb-2 font-headline">{t('set.title')}</h1>
                    <p className="text-on-surface-variant font-medium max-w-2xl">{lang==='zh'?'这里保留提示词模板、导出历史和应用偏好；运行凭证已移到工作台。':'Keep prompt templates, export history, and app preferences here; run credentials moved to Workbench.'}</p>
                    <div className="mt-5 flex flex-wrap gap-2">
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm text-primary">auto_fix_high</span>{lang==='zh'?`模板 ${templateCount}`:`Templates ${templateCount}`}
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm text-primary">history</span>{lang==='zh'?`导出 ${larkExports.length}`:`Exports ${larkExports.length}`}
                        </span>
                        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-sm bg-surface-container-low text-xs font-semibold text-on-surface-variant">
                            <span className="material-symbols-outlined text-sm text-primary">folder_open</span>{lang==='zh'?`历史 ${history.length}`:`History ${history.length}`}
                        </span>
                    </div>
                </div>
                {preferencesPanel}
                    </header>
                    <div className="space-y-8">
                    {larkExports.length > 0 && (
                    <section className="bg-surface-container-lowest rounded-sm p-8 shadow-sm">
                        <div className="flex items-center gap-4 mb-6">
                            <div className="w-10 h-10 rounded-sm bg-green-50 flex items-center justify-center text-green-600">
                                <span className="material-symbols-outlined">history</span>
                                    </div>
                            <div>
                                <h2 className="text-lg font-bold tracking-tight font-headline">{t('set.larkHistory')}</h2>
                                <p className="text-xs text-on-surface-variant">{larkExports.length} {t('dash.docUnit')}</p>
                            </div>
                        </div>
                        <div className="space-y-3 max-h-64 overflow-y-auto hide-scrollbar">
                            {larkExports.map((ex,i) => (
                                <a key={i} href={ex.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-4 p-4 rounded-lg bg-surface-container-low hover:bg-blue-50 transition group">
                                    <span className="material-symbols-outlined text-primary text-lg" style={{fontVariationSettings:"'FILL' 1"}}>description</span>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-sm font-semibold text-on-surface truncate group-hover:text-primary">{ex.title}</p>
                                        <p className="text-[10px] text-slate-400">{timeAgo(ex.timestamp, t)}</p>
                                    </div>
                                    <span className="material-symbols-outlined text-slate-300 group-hover:text-primary text-sm">open_in_new</span>
                                </a>
                            ))}
                                </div>
                            </section>
                    )}
                    <section className="bg-surface-container-lowest rounded-sm shadow-sm overflow-hidden">
                        <div className="px-8 py-6 border-b ff-border-muted flex flex-col lg:flex-row lg:items-center justify-between gap-5">
                            <div className="flex items-center gap-4 min-w-0">
                            <div className="w-11 h-11 rounded-sm bg-amber-50 flex items-center justify-center text-amber-600 flex-shrink-0">
                                <span className="material-symbols-outlined text-2xl">auto_fix_high</span>
                            </div>
                            <div className="min-w-0">
                                <h2 className="text-xl font-bold tracking-tight font-headline">{t('set.promptTitle')}</h2>
                                <p className="text-sm text-on-surface-variant">{t('set.promptDesc')}</p>
                            </div>
                        </div>
                            <div className="w-full lg:w-[320px] space-y-2 flex-shrink-0">
                                <label className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">{t('set.templateToEdit')}</label>
                                <select className="w-full bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm focus:ring-2 focus:ring-primary/20" value={templateEditKey} onChange={e=>setTemplateEditKey(e.target.value)}>
                                    {allPresetSelectKeys(settings).map((key) => (
                                        <option key={key} value={key}>{presetDisplayLabel(key, settings, lang)}</option>
                                    ))}
                                </select>
                            </div>
                        </div>
                        <div className="p-8 space-y-5">
                            {templateEditKey==='default' && (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap justify-between items-center gap-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editCoursePrompt')}</label>
                                        <button type="button" onClick={resetDefaultPromptInSettings} className="text-xs font-semibold text-primary hover:underline">{t('set.resetBuiltinPrompt')}</button>
                                    </div>
                                    <textarea className="w-full min-h-[220px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getDefaultPromptBody(settings)} onChange={e=>setSettings(s=>({...s,defaultPromptOverride:e.target.value}))}/>
                                </div>
                            )}
                            {templateEditKey==='custom' && (
                                <div className="space-y-3">
                                    <div className="space-y-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{lang==='zh'?'自定义提示词':'Custom Prompt'}</label>
                                        <textarea className="w-full h-40 bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" placeholder={t('prompt.customPlaceholder')} value={settings.customPromptText||''} onChange={e=>setSettings(s=>({...s,customPromptText:e.target.value}))}/>
                                    </div>
                                    <div className="flex flex-wrap items-end gap-2">
                                        <input type="text" className="flex-1 min-w-[200px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm" placeholder={t('set.presetNamePh')} value={newPresetNameSettings} onChange={e=>setNewPresetNameSettings(e.target.value)} />
                                        <button type="button" onClick={saveCustomAsPresetInSettings} className="px-4 py-3 bg-amber-600 text-white text-sm font-semibold rounded-sm hover:bg-amber-700 transition">{t('set.saveAsPreset')}</button>
                                    </div>
                                </div>
                            )}
                            {BUILTIN_EXTRA_PROMPT_KEYS.includes(templateEditKey) && (
                                <div className="space-y-2">
                                    <div className="flex flex-wrap justify-between items-center gap-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                        <button type="button" onClick={()=>resetBuiltinOverrideInSettings(templateEditKey)} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                                    </div>
                                    <textarea className="w-full min-h-[220px] bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getBuiltinExtraPromptBody(templateEditKey, settings)} onChange={e=>setSettings(s=>({...s,promptOverrides:{...(s.promptOverrides||{}),[templateEditKey]:e.target.value}}))}/>
                                </div>
                            )}
                            {normalizeUserPresets(settings).length > 0 && (
                                <div className="space-y-2">
                                    <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.myPresets')}</label>
                                    <ul className="space-y-2">
                                        {normalizeUserPresets(settings).map((p) => (
                                            <li key={p.id} className="flex items-center justify-between gap-3 p-3 rounded-sm bg-surface-container-low">
                                                <span className="text-sm text-on-surface truncate flex-1" title={lang==='zh'?p.nameZh:p.nameEn}>{lang==='zh'?p.nameZh:p.nameEn}</span>
                                                <button type="button" onClick={()=>deleteUserPresetInSettings(p.id)} className="text-xs font-semibold text-red-600 hover:underline flex-shrink-0">{t('set.deletePreset')}</button>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    </section>
                    </div>
                </main>
            </div>
            );
        };

export default Settings;
