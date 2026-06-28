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
import SvgIcon from '../components/SvgIcon.jsx';
import {
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    LARK_EXPORT_ROUTE_LOCAL_CLI,
    LARK_EXPORT_ROUTE_OPENAPI,
    effectiveSttProvider,
    isCloudSttProvider,
    isLocalLarkExportRoute,
    larkExportRouteFromSettings,
    normalizeAiModel,
    normalizeSttModel,
    normalizeSttProvider,
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
    const {clearHistory,history,larkExports,runtimeConfig} = useApp();
    const {getCredentialsStatus, saveCredentials, getSpeakerDiarizationStatus} = useApi();
    const [settings,setSettings] = useState(() => loadSettings());
    const [saved,setSaved] = useState(false);
    const [cleared,setCleared] = useState(false);
    const [clearArmed,setClearArmed] = useState(false);
    const [credentialStatus, setCredentialStatus] = useState(null);
    const [diarizationStatus, setDiarizationStatus] = useState(null);
    const [secretDraft, setSecretDraft] = useState({});
    const [pyannoteTokenEditing, setPyannoteTokenEditing] = useState(false);
    const [secretSaving, setSecretSaving] = useState(false);
    const [secretFeedback, setSecretFeedback] = useState(null);
    const templateCount = allPresetSelectKeys(settings).length;

    useEffect(() => {
        const pk = (settings && settings.promptPreset) || 'default';
        if (isBuiltinPromptPresetHidden(pk, settings)) {
            const next = { ...settings, promptPreset: 'default' };
            setSettings(next);
            saveSettings(next);
        }
        const normalizedSttModel = normalizeSttModel(settings.sttModel);
        if (settings.sttModel !== normalizedSttModel) {
            const next = { ...settings, sttModel: normalizedSttModel };
            setSettings(next);
            saveSettings(next);
        }
        getCredentialsStatus().then(setCredentialStatus).catch(() => {});
        getSpeakerDiarizationStatus().then(setDiarizationStatus).catch(() => {});
    }, []);

    const handleSave = () => { saveSettings(settings); setSaved(true); setTimeout(()=>setSaved(false),2000); };
    const updateSettingNow = (patch) => {
        setSettings((s) => {
            const next = {...s, ...patch};
            saveSettings(next);
            return next;
        });
    };

    const saveSecret = async (key) => {
        const value = secretDraft[key];
        if (value === undefined) return;
        setSecretSaving(true);
        setSecretFeedback(null);
        try {
            const next = await saveCredentials({[key]: value});
            const fresh = await getCredentialsStatus().catch(() => next);
            setCredentialStatus(fresh);
            if (key === 'pyannote_auth_token') {
                const status = await getSpeakerDiarizationStatus();
                setDiarizationStatus(status);
                setPyannoteTokenEditing(false);
            }
            setSecretDraft((draft) => ({...draft, [key]: ''}));
            setSecretFeedback({key, ok: true});
        } catch (err) {
            setSecretFeedback({key, ok: false, message: err.message || String(err)});
        } finally {
            setSecretSaving(false);
        }
    };

    const secretStatusText = (configured) => configured
        ? (lang === 'zh' ? '已配置' : 'Configured')
        : (lang === 'zh' ? '未配置' : 'Not configured');

    const SecretFeedback = ({keyName}) => (
        secretFeedback?.key === keyName ? (
            <p className={`text-[11px] font-semibold ${secretFeedback.ok ? 'text-green-600' : 'text-red-600'}`}>
                {secretFeedback.ok
                    ? (lang === 'zh' ? '已保存' : 'Saved')
                    : `${lang === 'zh' ? '保存失败' : 'Save failed'}：${secretFeedback.message || ''}`}
            </p>
        ) : null
    );

    const inputClass = "w-full bg-surface-container-low border-none rounded-sm px-4 py-3 text-sm text-on-surface focus:ring-2 focus:ring-primary/20";
    const fieldLabelClass = "text-[11px] font-bold uppercase tracking-wider text-on-surface-variant";
    const aiProvider = settings.aiProvider || 'deepseek';
    const aiModel = normalizeAiModel(aiProvider, settings.aiModel);
    const activeAiSecretKey = aiProvider === 'openai' ? 'openai_api_key' : 'deepseek_api_key';
    const activeAiConfigured = aiProvider === 'openai'
        ? credentialStatus?.openai_api_key_configured
        : credentialStatus?.deepseek_api_key_configured;
    const sttProvider = effectiveSttProvider(settings, runtimeConfig);
    const canChooseSttProvider = runtimeConfig.allowedSttProviders.length > 1;
    const larkExportRoute = larkExportRouteFromSettings(settings);
    const speakerDiarizationAvailable = isCloudSttProvider(sttProvider) || (sttProvider === 'local' && !!diarizationStatus?.available);
    const pyannoteTokenConfigured = !!(credentialStatus?.pyannote_auth_token_configured || diarizationStatus?.auth_configured);
    const showPyannoteTokenInput = !pyannoteTokenConfigured || pyannoteTokenEditing;
    const showMaintainerSettings = runtimeConfig.showMaintainerSettings;
    const [promptAdvanced, setPromptAdvanced] = useState(false);

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
            setTimeout(()=>setClearArmed(false), 5000);
            return;
        }
        setClearArmed(false);
        clearHistory();
        setCleared(true);
        setTimeout(()=>setCleared(false),2000);
    };

    const isDark = settings.theme === 'dark';
    const applyTheme = (theme) => {
        const next = {...settings, theme};
        setSettings(next);
        saveSettings(next);
        document.documentElement.classList.toggle('dark', theme==='dark');
    };

    return (
        <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] pb-8 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <main className="mx-auto h-dvh max-w-[900px] overflow-y-auto px-8 py-7 hide-scrollbar">
                <header className="mb-7">
                    <h1 className="text-2xl font-extrabold tracking-tight text-[#111111] dark:text-white font-headline">{t('set.title')}</h1>
                    <p className="mt-1 text-sm font-medium text-[#777] dark:text-white/55">{lang==='zh'?'这里保留长期偏好、凭证和模板维护；每次任务的处理策略由 Agent 判断。':'Long-term preferences, credentials, and templates live here. Per-task processing strategy is handled by the Agent.'}</p>
                </header>

                <div className="space-y-6">

                    {/* ── Credentials ── */}
                    <section className="rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="flex items-center gap-3 mb-5">
                            <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-purple-50 text-purple-600 dark:bg-purple-500/10 dark:text-purple-300">
                                <SvgIcon name="key" className="text-lg"/>
                            </span>
                            <div>
                                <h2 className="text-base font-extrabold text-[#111111] dark:text-white font-headline">{lang==='zh'?'运行凭证':'Credentials'}</h2>
                                <p className="text-xs text-[#8a8a8a] dark:text-white/40">{lang==='zh'?'API 密钥和访问令牌，保存在服务端。':'API keys and access tokens, stored server-side.'}</p>
                            </div>
                        </div>

                        <div className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.provider')}</label>
                                    <select className={inputClass} value={aiProvider} onChange={e=>updateSettingNow({aiProvider:e.target.value,aiModel:e.target.value==='openai'?DEFAULT_OPENAI_MODEL:DEFAULT_DEEPSEEK_MODEL})}>
                                        <option value="deepseek">DeepSeek</option>
                                        <option value="openai">OpenAI</option>
                                    </select>
                                </div>
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.aiModel')}</label>
                                    {aiProvider === 'openai' ? (
                                        <select className={inputClass} value={aiModel} onChange={e=>updateSettingNow({aiModel:e.target.value})}>
                                            <option value="gpt-5.4-mini">gpt-5.4-mini</option>
                                            <option value="gpt-5.4">gpt-5.4</option>
                                            <option value="gpt-5.5">gpt-5.5</option>
                                        </select>
                                    ) : (
                                        <select className={inputClass} value={aiModel} onChange={e=>updateSettingNow({aiModel:e.target.value})}>
                                            <option value="deepseek-reasoner">deepseek-reasoner</option>
                                        </select>
                                    )}
                                </div>
                            </div>
                            {showMaintainerSettings && (
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{aiProvider==='openai'?t('set.openaiKey'):t('set.deepseekKey')}</label>
                                    <div className="flex gap-2">
                                        <input className={inputClass} placeholder={secretStatusText(activeAiConfigured)} type="password" value={secretDraft[activeAiSecretKey]||""} onChange={e=>setSecretDraft(d=>({...d,[activeAiSecretKey]:e.target.value}))}/>
                                        <button type="button" disabled={secretSaving || !secretDraft[activeAiSecretKey]} onClick={()=>saveSecret(activeAiSecretKey)} className="px-4 py-3 rounded-sm bg-primary text-on-primary text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                    </div>
                                    <SecretFeedback keyName={activeAiSecretKey} />
                                </div>
                            )}
                        </div>
                    </section>

                    {/* ── Transcription ── */}
                    <section className="rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="flex items-center gap-3 mb-5">
                            <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-primary/10 text-primary">
                                <SvgIcon name="mic" className="text-lg"/>
                            </span>
                            <div>
                                <h2 className="text-base font-extrabold text-[#111111] dark:text-white font-headline">{t('work.transcription')}</h2>
                                <p className="text-xs text-[#8a8a8a] dark:text-white/40">{lang==='zh'?'语音识别和讲话人区分设置。':'Speech recognition and speaker diarization.'}</p>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                            <div className="space-y-2">
                                <label className={fieldLabelClass}>{t('set.sttProvider')}</label>
                                {canChooseSttProvider ? (
                                    <select className={inputClass} value={sttProvider} onChange={e=>updateSettingNow({sttProvider:e.target.value})}>
                                        {runtimeConfig.allowedSttProviders.includes('elevenlabs_scribe') && <option value="elevenlabs_scribe">{t('set.providerCloud')}</option>}
                                        {runtimeConfig.allowedSttProviders.includes('azure_batch') && <option value="azure_batch">{t('set.providerAzureBatch')}</option>}
                                        {runtimeConfig.allowedSttProviders.includes('local') && <option value="local">{t('set.providerLocal')}</option>}
                                    </select>
                                ) : (
                                    <div className={`${inputClass} flex items-center justify-between`}>
                                        <span>{isCloudSttProvider(sttProvider) ? t('set.providerCloud') : t('set.providerLocal')}</span>
                                        <SvgIcon name="lock" className="text-base text-primary"/>
                                    </div>
                                )}
                            </div>
                            {sttProvider === 'local' && (
                                <>
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.modelSel')}</label>
                                        <select className={inputClass} value={normalizeSttModel(settings.sttModel)} onChange={e=>updateSettingNow({sttModel:e.target.value})}>
                                            <option value="medium">{t('set.optMedium')}</option>
                                            <option value="large-v3">{t('set.optLarge')}</option>
                                        </select>
                                    </div>
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.sttSpeed')}</label>
                                        <select className={inputClass} value={settings.sttSpeed||"balanced"} onChange={e=>updateSettingNow({sttSpeed:e.target.value})}>
                                            <option value="fast">{t('set.speedFast')}</option>
                                            <option value="balanced">{t('set.speedBalanced')}</option>
                                            <option value="accurate">{t('set.speedAccurate')}</option>
                                        </select>
                                    </div>
                                </>
                            )}
                        </div>

                        <label htmlFor="settingsSpeakerDiarization" className={`flex items-start gap-3 rounded-[14px] bg-[#f4f3f3] dark:bg-white/[0.08] p-4 ${speakerDiarizationAvailable?'cursor-pointer hover:bg-[#efeeee] dark:hover:bg-white/[0.12]':'cursor-not-allowed opacity-60'}`}>
                            <SvgIcon name="record_voice_over" className="mt-0.5 text-primary text-lg"/>
                            <span className="flex-1 min-w-0">
                                <span className="block text-sm font-bold text-[#111111] dark:text-white">{lang==='zh'?'区分不同讲话人':'Speaker diarization'}</span>
                                <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                    {sttProvider === 'local'
                                        ? (lang==='zh'?'本机路径使用 pyannote 标记 SPEAKER；更适合多人讲座或访谈。':'Local mode uses pyannote to label SPEAKER for multi-speaker material.')
                                        : (lang==='zh'?'云端转录可请求说话人区分，效果取决于音频质量。':'Cloud transcription can request speaker labels; quality depends on audio.')}
                                </span>
                            </span>
                            <input id="settingsSpeakerDiarization" type="checkbox" checked={!!settings.speakerDiarization && speakerDiarizationAvailable} disabled={!speakerDiarizationAvailable} onChange={e=>updateSettingNow({speakerDiarization:e.target.checked})} className="w-4 h-4 mt-1 rounded border-outline-variant text-primary focus:ring-primary disabled:opacity-40"/>
                        </label>

                        {showMaintainerSettings && sttProvider === 'local' && (
                            <div className="mt-4 rounded-[14px] bg-[#f4f3f3] dark:bg-white/[0.08] p-4">
                                <div className="flex items-start justify-between gap-3 mb-3">
                                    <div className="space-y-1">
                                        <label className={fieldLabelClass}>PYANNOTE AUTH TOKEN</label>
                                        <p className="text-xs text-on-surface-variant leading-relaxed">
                                            {pyannoteTokenConfigured
                                                ? (lang==='zh'?'已配置。token 不会显示在前端；需要更换时再重新输入。':'Configured. The token is not shown in the frontend; re-enter it only when replacing it.')
                                                : (lang==='zh'?'用于本机后端从 Hugging Face 获取 pyannote 讲话人区分模型。':'Used by the local backend to fetch the pyannote model from Hugging Face.')}
                                        </p>
                                    </div>
                                    {pyannoteTokenConfigured && !pyannoteTokenEditing && (
                                        <button type="button" onClick={()=>setPyannoteTokenEditing(true)} className="shrink-0 px-3 py-2 rounded-[10px] border border-[#dedada] dark:border-white/[0.12] text-xs font-bold text-[#111111] dark:text-white hover:bg-[#efeeee] dark:hover:bg-white/[0.12]">
                                            {lang==='zh'?'更换':'Replace'}
                                        </button>
                                    )}
                                </div>
                                {showPyannoteTokenInput && (
                                    <div className="flex flex-col gap-2 md:flex-row">
                                        <input className={inputClass} placeholder={lang==='zh'?'粘贴 Hugging Face hf_... token':'Paste Hugging Face hf_... token'} type="password" value={secretDraft.pyannote_auth_token||""} onChange={e=>setSecretDraft(d=>({...d,pyannote_auth_token:e.target.value}))}/>
                                        <button type="button" disabled={secretSaving || !secretDraft.pyannote_auth_token} onClick={()=>saveSecret('pyannote_auth_token')} className="px-4 py-3 rounded-sm bg-primary text-on-primary text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                        {pyannoteTokenConfigured && (
                                            <button type="button" onClick={()=>{setPyannoteTokenEditing(false); setSecretDraft(d=>({...d,pyannote_auth_token:''}));}} className="px-3 py-3 rounded-sm border ff-border-control text-sm font-bold text-on-surface hover:bg-surface-container-high">
                                                {lang==='zh'?'取消':'Cancel'}
                                            </button>
                                        )}
                                    </div>
                                )}
                                <SecretFeedback keyName="pyannote_auth_token" />
                            </div>
                        )}
                    </section>

                    {/* ── Feishu Export ── */}
                    <section className="rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="flex items-center gap-3 mb-5">
                            <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-primary/10 text-primary">
                                <SvgIcon name="ios_share" className="text-lg"/>
                            </span>
                            <div>
                                <h2 className="text-base font-extrabold text-[#111111] dark:text-white font-headline">{t('work.export')}</h2>
                                <p className="text-xs text-[#8a8a8a] dark:text-white/40">{lang==='zh'?'处理完成后自动创建飞书文档。':'Automatically create a Feishu doc after processing.'}</p>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                            <label htmlFor="settingsExportToLark" className="flex cursor-pointer items-start gap-3 rounded-[14px] bg-[#f4f3f3] dark:bg-white/[0.08] p-4 hover:bg-[#efeeee] dark:hover:bg-white/[0.12]">
                                <SvgIcon name="ios_share" className="mt-0.5 text-primary text-lg"/>
                                <span className="flex-1 min-w-0">
                                    <span className="block text-sm font-bold text-[#111111] dark:text-white">{t('set.autoExport')}</span>
                                    <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">{lang==='zh'?'处理完成后自动创建飞书文档。':'Create a Lark document automatically after processing.'}</span>
                                </span>
                                <input id="settingsExportToLark" type="checkbox" checked={settings.exportToLark||false} onChange={e=>updateSettingNow({exportToLark:e.target.checked})} className="w-4 h-4 mt-1 rounded border-outline-variant text-primary focus:ring-primary"/>
                            </label>
                            <div className="space-y-2">
                                <label className={fieldLabelClass}>{t('set.larkExportRoute')}</label>
                                <select
                                    className={inputClass}
                                    value={larkExportRoute}
                                    onChange={e=>{
                                        const route = e.target.value;
                                        updateSettingNow({
                                            larkExportRoute: route,
                                            larkViaCli: isLocalLarkExportRoute(route),
                                        });
                                    }}
                                >
                                    <option value={LARK_EXPORT_ROUTE_OPENAPI}>{t('set.larkRouteOpenapi')}</option>
                                    {showMaintainerSettings && <option value={LARK_EXPORT_ROUTE_LOCAL_CLI}>{t('set.larkRouteLocalCli')}</option>}
                                </select>
                                <p className="text-[11px] text-on-surface-variant leading-snug">
                                    {isLocalLarkExportRoute(larkExportRoute) ? t('set.larkRouteLocalCliHint') : t('set.larkRouteOpenapiHint')}
                                </p>
                            </div>
                        </div>
                        {showMaintainerSettings && !isLocalLarkExportRoute(larkExportRoute) && (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 pt-4 border-t border-[#e4e0e0] dark:border-white/[0.12]">
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>App ID</label>
                                    <div className="flex gap-2">
                                        <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_id_configured)} value={secretDraft.lark_app_id||""} onChange={e=>setSecretDraft(d=>({...d,lark_app_id:e.target.value}))}/>
                                        <button type="button" disabled={secretSaving || !secretDraft.lark_app_id} onClick={()=>saveSecret('lark_app_id')} className="px-4 py-3 rounded-sm bg-primary text-on-primary text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                    </div>
                                    <SecretFeedback keyName="lark_app_id" />
                                </div>
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>App Secret</label>
                                    <div className="flex gap-2">
                                        <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_secret_configured)} type="password" value={secretDraft.lark_app_secret||""} onChange={e=>setSecretDraft(d=>({...d,lark_app_secret:e.target.value}))}/>
                                        <button type="button" disabled={secretSaving || !secretDraft.lark_app_secret} onClick={()=>saveSecret('lark_app_secret')} className="px-4 py-3 rounded-sm bg-primary text-on-primary text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                    </div>
                                    <SecretFeedback keyName="lark_app_secret" />
                                </div>
                            </div>
                        )}
                    </section>

                    {/* ── Prompt Templates ── */}
                    <section className="rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="flex items-center gap-3 mb-5">
                            <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-purple-50 text-purple-600 dark:bg-purple-500/10 dark:text-purple-300">
                                <SvgIcon name="auto_fix_high" className="text-lg"/>
                            </span>
                            <div>
                                <h2 className="text-base font-extrabold text-[#111111] dark:text-white font-headline">{t('set.promptTitle')}</h2>
                                <p className="text-xs text-[#8a8a8a] dark:text-white/40">{lang==='zh'?`${templateCount} 个可用模板。这里维护模板偏好，Agent 负责决定本次处理方式。`:`${templateCount} templates available. Maintain template preferences here; the Agent decides the per-task route.`}</p>
                            </div>
                        </div>

                        <div className="space-y-3">
                            <div className="flex flex-wrap items-end gap-3">
                                <div className="space-y-1.5 min-w-0 flex-1">
                                    <label className="text-[10px] font-bold uppercase tracking-wider text-[#8a8a8a] dark:text-white/40">{t('set.templateToEdit')}</label>
                                    <select className="w-full bg-[#f4f3f3] dark:bg-white/[0.08] border-none rounded-[12px] px-4 py-2.5 text-sm font-semibold text-[#111111] dark:text-white focus:ring-2 focus:ring-primary/20" value={templateEditKey} onChange={e=>setTemplateEditKey(e.target.value)}>
                                        {allPresetSelectKeys(settings).map((key) => (
                                            <option key={key} value={key}>{presetDisplayLabel(key, settings, lang)}</option>
                                        ))}
                                    </select>
                                </div>
                                <button type="button" onClick={() => setPromptAdvanced(v => !v)} className="inline-flex h-[42px] items-center gap-1.5 rounded-[12px] border border-[#dedada] dark:border-white/[0.12] bg-white dark:bg-white/[0.06] px-4 text-xs font-bold text-[#666] dark:text-white/55 hover:bg-[#efeeee] dark:hover:bg-white/[0.12] hover:text-[#111111] dark:hover:text-white">
                                    <SvgIcon name={promptAdvanced ? 'expand_less' : 'code'} className="text-sm"/>
                                    {lang==='zh'?'编辑正文':'Edit body'}
                                </button>
                            </div>

                            {promptAdvanced && (
                                <div className="space-y-4 pt-2 border-t border-[#e4e0e0] dark:border-white/[0.12]">
                                    {templateEditKey==='default' && (
                                        <div className="space-y-2">
                                            <div className="flex flex-wrap justify-between items-center gap-2">
                                                <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editCoursePrompt')}</label>
                                                <button type="button" onClick={resetDefaultPromptInSettings} className="text-xs font-semibold text-primary hover:underline">{t('set.resetBuiltinPrompt')}</button>
                                            </div>
                                            <textarea className="w-full min-h-[220px] bg-[#f4f3f3] dark:bg-white/[0.08] border-none rounded-[12px] px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getDefaultPromptBody(settings)} onChange={e=>setSettings(s=>({...s,defaultPromptOverride:e.target.value}))}/>
                                        </div>
                                    )}
                                    {templateEditKey==='custom' && (
                                        <div className="space-y-3">
                                            <div className="space-y-2">
                                                <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{lang==='zh'?'自定义提示词':'Custom Prompt'}</label>
                                                <textarea className="w-full h-40 bg-[#f4f3f3] dark:bg-white/[0.08] border-none rounded-[12px] px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" placeholder={t('prompt.customPlaceholder')} value={settings.customPromptText||''} onChange={e=>setSettings(s=>({...s,customPromptText:e.target.value}))}/>
                                            </div>
                                            <div className="flex flex-wrap items-end gap-2">
                                                <input type="text" className="flex-1 min-w-[200px] bg-[#f4f3f3] dark:bg-white/[0.08] border-none rounded-[12px] px-4 py-3 text-sm" placeholder={t('set.presetNamePh')} value={newPresetNameSettings} onChange={e=>setNewPresetNameSettings(e.target.value)} />
                                                <button type="button" onClick={saveCustomAsPresetInSettings} className="px-4 py-3 bg-purple-600 text-white text-sm font-semibold rounded-[12px] hover:bg-purple-700 transition">{t('set.saveAsPreset')}</button>
                                            </div>
                                        </div>
                                    )}
                                    {BUILTIN_EXTRA_PROMPT_KEYS.includes(templateEditKey) && (
                                        <div className="space-y-2">
                                            <div className="flex flex-wrap justify-between items-center gap-2">
                                                <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.editBuiltinTemplate')}</label>
                                                <button type="button" onClick={()=>resetBuiltinOverrideInSettings(templateEditKey)} className="text-xs font-semibold text-primary hover:underline">{t('set.deleteBuiltinPrompt')}</button>
                                            </div>
                                            <textarea className="w-full min-h-[220px] bg-[#f4f3f3] dark:bg-white/[0.08] border-none rounded-[12px] px-4 py-3 text-sm font-mono focus:ring-2 focus:ring-primary/20 resize-y" value={getBuiltinExtraPromptBody(templateEditKey, settings)} onChange={e=>setSettings(s=>({...s,promptOverrides:{...(s.promptOverrides||{}),[templateEditKey]:e.target.value}}))}/>
                                        </div>
                                    )}
                                    {normalizeUserPresets(settings).length > 0 && (
                                        <div className="space-y-2">
                                            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">{t('set.myPresets')}</label>
                                            <ul className="space-y-2">
                                                {normalizeUserPresets(settings).map((p) => (
                                                    <li key={p.id} className="flex items-center justify-between gap-3 p-3 rounded-[12px] bg-[#f4f3f3] dark:bg-white/[0.08]">
                                                        <span className="text-sm text-on-surface truncate flex-1" title={lang==='zh'?p.nameZh:p.nameEn}>{lang==='zh'?p.nameZh:p.nameEn}</span>
                                                        <button type="button" onClick={()=>deleteUserPresetInSettings(p.id)} className="text-xs font-semibold text-red-600 hover:underline flex-shrink-0">{t('set.deletePreset')}</button>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </section>

                    {/* ── Feishu Export History ── */}
                    {larkExports.length > 0 && (
                        <section className="rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                            <div className="flex items-center gap-3 mb-4">
                                <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-green-50 text-green-600 dark:bg-green-500/10 dark:text-green-300">
                                    <SvgIcon name="history" className="text-lg"/>
                                </span>
                                <div>
                                    <h2 className="text-base font-extrabold text-[#111111] dark:text-white font-headline">{t('set.larkHistory')}</h2>
                                    <p className="text-xs text-[#8a8a8a] dark:text-white/40">{larkExports.length} {t('dash.docUnit')}</p>
                                </div>
                            </div>
                            <div className="space-y-2 max-h-64 overflow-y-auto hide-scrollbar">
                                {larkExports.map((ex,i) => (
                                    <a key={i} href={ex.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 p-3 rounded-[12px] bg-[#f4f3f3] dark:bg-white/[0.08] hover:bg-blue-50 dark:hover:bg-white/[0.12] transition group">
                                        <SvgIcon name="description" className="text-primary text-lg"/>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-semibold text-[#111111] dark:text-white truncate group-hover:text-primary">{ex.title}</p>
                                            <p className="text-[10px] text-[#8a8a8a] dark:text-white/40">{timeAgo(ex.timestamp, t)}</p>
                                        </div>
                                        <SvgIcon name="open_in_new" className="text-[#8a8a8a] dark:text-white/40 group-hover:text-primary text-sm"/>
                                    </a>
                                ))}
                            </div>
                        </section>
                    )}

                    {/* ── App ── */}
                    <section className="rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="flex items-center gap-3 mb-5">
                            <span className="flex h-9 w-9 items-center justify-center rounded-[12px] bg-primary/10 text-primary">
                                <SvgIcon name="palette" className="text-lg"/>
                            </span>
                            <div>
                                <h2 className="text-base font-extrabold text-[#111111] dark:text-white font-headline">{t('set.prefs')}</h2>
                                <p className="text-xs text-[#8a8a8a] dark:text-white/40">{lang==='zh'?'外观和历史记录。':'Appearance and history.'}</p>
                            </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-3">
                            <div className="inline-flex rounded-[14px] border border-[#dedada] dark:border-white/[0.12] bg-[#f4f3f3] dark:bg-white/[0.08] p-1">
                                <button onClick={()=>applyTheme('light')} className={`flex items-center gap-1.5 rounded-[12px] px-4 py-2 text-xs font-bold transition ${!isDark?'bg-white text-[#111111] shadow-sm dark:bg-white/[0.16] dark:text-white':'text-[#777] hover:text-[#111111] dark:text-white/55 dark:hover:text-white'}`}>
                                    <SvgIcon name="light_mode" className="text-sm"/>{t('set.light')}
                                </button>
                                <button onClick={()=>applyTheme('dark')} className={`flex items-center gap-1.5 rounded-[12px] px-4 py-2 text-xs font-bold transition ${isDark?'bg-white text-[#111111] shadow-sm dark:bg-white/[0.16] dark:text-white':'text-[#777] hover:text-[#111111] dark:text-white/55 dark:hover:text-white'}`}>
                                    <SvgIcon name="dark_mode" className="text-sm"/>{t('set.dark')}
                                </button>
                            </div>
                            <button onClick={handleSave} className={`inline-flex h-[38px] items-center gap-1.5 rounded-[12px] px-4 text-xs font-bold transition ${saved?'bg-green-50 text-green-600 dark:bg-green-500/10 dark:text-green-300':'bg-primary/10 text-primary hover:bg-primary/20'}`}>
                                <SvgIcon name={saved ? 'check' : 'save'} className="text-sm"/>
                                {saved ? t('set.saved') : t('set.saveAll')}
                            </button>
                            <button onClick={handleClear} disabled={history.length===0} className={`inline-flex h-[38px] items-center gap-1.5 rounded-[12px] px-4 text-xs font-bold transition disabled:opacity-30 ${clearArmed?'bg-red-600 text-white':'bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20'}`}>
                                <SvgIcon name="delete_sweep" className="text-sm"/>
                                {cleared ? t('edit.clearConfirm') : (clearArmed ? t('edit.clearConfirmAgain') : `${t('edit.clearHistory')} (${history.length})`)}
                            </button>
                        </div>
                        {clearArmed && (
                            <p className="mt-2 text-[11px] font-medium text-red-600">{t('edit.clearConfirmAgain')}</p>
                        )}
                    </section>

                </div>
            </main>
        </div>
    );
};

export default Settings;
