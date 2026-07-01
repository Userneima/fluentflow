import {useEffect, useState} from 'react';
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
    timeAgo,
    useApi,
    useApp,
    useI18n,
    useSettings,
} from '../app/shared.jsx';

const Section = ({id, title, description, children}) => (
    <section id={id} className="scroll-mt-7 rounded-[18px] border border-[#e4e0e0] bg-white dark:border-white/[0.12] dark:bg-white/[0.06]">
        <div className="border-b border-[#ece8e8] px-5 py-4 dark:border-white/[0.1]">
            <h2 className="font-headline text-base font-extrabold">{title}</h2>
            {description && <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">{description}</p>}
        </div>
        {children}
    </section>
);

const Settings = () => {
    const {t, lang} = useI18n();
    const {loadSettings, saveSettings} = useSettings();
    const {clearHistory, history, larkExports, runtimeConfig} = useApp();
    const {getCredentialsStatus, saveCredentials, getSpeakerDiarizationStatus} = useApi();
    const [settings, setSettings] = useState(() => loadSettings());
    const [cleared, setCleared] = useState(false);
    const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
    const [credentialStatus, setCredentialStatus] = useState(null);
    const [diarizationStatus, setDiarizationStatus] = useState(null);
    const [secretDraft, setSecretDraft] = useState({});
    const [pyannoteTokenEditing, setPyannoteTokenEditing] = useState(false);
    const [secretSaving, setSecretSaving] = useState(false);
    const [secretFeedback, setSecretFeedback] = useState(null);

    useEffect(() => {
        const normalizedSttModel = normalizeSttModel(settings.sttModel);
        if (settings.sttModel !== normalizedSttModel) {
            const next = {...settings, sttModel: normalizedSttModel};
            setSettings(next);
            saveSettings(next);
        }
        getCredentialsStatus().then(setCredentialStatus).catch(() => {});
        getSpeakerDiarizationStatus().then(setDiarizationStatus).catch(() => {});
    }, []);

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

    const secretStatusText = (configured) => (
        configured ? (lang === 'zh' ? '已配置' : 'Configured') : (lang === 'zh' ? '未配置' : 'Not configured')
    );

    const SecretFeedback = ({keyName}) => (
        secretFeedback?.key === keyName ? (
            <p className={`text-[11px] font-semibold ${secretFeedback.ok ? 'text-green-600' : 'text-red-600'}`}>
                {secretFeedback.ok
                    ? (lang === 'zh' ? '已保存' : 'Saved')
                    : `${lang === 'zh' ? '保存失败' : 'Save failed'}: ${secretFeedback.message || ''}`}
            </p>
        ) : null
    );

    const handleClear = () => {
        if (history.length === 0) return;
        setClearConfirmOpen(true);
    };

    const confirmClearHistory = () => {
        setClearConfirmOpen(false);
        clearHistory();
        setCleared(true);
        setTimeout(() => setCleared(false), 2000);
    };

    const inputClass = 'w-full rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 py-3 text-sm font-semibold text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40';
    const fieldLabelClass = 'text-[11px] font-extrabold uppercase tracking-wider text-[#676970] dark:text-white/50';
    const saveButtonClass = 'rounded-[14px] bg-[#111111] px-4 py-3 text-sm font-extrabold text-white transition hover:bg-[#2a2a2a] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]';
    const aiProvider = settings.aiProvider || 'deepseek';
    const aiModel = normalizeAiModel(aiProvider, settings.aiModel);
    const activeAiSecretKey = aiProvider === 'openai' ? 'openai_api_key' : 'deepseek_api_key';
    const activeAiConfigured = aiProvider === 'openai'
        ? credentialStatus?.openai_api_key_configured
        : credentialStatus?.deepseek_api_key_configured;
    const sttProvider = effectiveSttProvider(settings, runtimeConfig);
    const larkExportRoute = larkExportRouteFromSettings(settings);
    const cloudProviderLabel = lang === 'zh' ? '云端转录' : 'Cloud transcription';
    const localProviderLabel = t('set.providerLocal');
    const localRouteAvailable = runtimeConfig.allowedSttProviders.includes('local');
    const pureCloudServer = runtimeConfig.publicMode && !localRouteAvailable;
    const speakerDiarizationAvailable = isCloudSttProvider(sttProvider) || (sttProvider === 'local' && !!diarizationStatus?.available);
    const pyannoteTokenConfigured = !!(credentialStatus?.pyannote_auth_token_configured || diarizationStatus?.auth_configured);
    const showPyannoteTokenInput = !pyannoteTokenConfigured || pyannoteTokenEditing;
    const showMaintainerSettings = runtimeConfig.showMaintainerSettings;

    const routeButtonClass = (active, disabled) => [
        'flex min-h-[74px] flex-1 items-start justify-between gap-3 rounded-[14px] border px-4 py-3 text-left transition',
        active
            ? 'border-primary bg-primary/10 text-[#111111] dark:text-white'
            : 'border-[#dedada] bg-[#f8f7f7] text-[#555] hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/70 dark:hover:bg-white/[0.1]',
        disabled ? 'cursor-not-allowed opacity-45 hover:bg-[#f8f7f7] dark:hover:bg-white/[0.06]' : 'cursor-pointer active:translate-y-px',
    ].join(' ');

    return (
        <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] pb-8 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <main className="mx-auto h-dvh max-w-[820px] overflow-y-auto px-8 py-7 hide-scrollbar">
                <header className="mb-6">
                    <h1 className="font-headline text-2xl font-extrabold tracking-tight text-[#111111] dark:text-white">{t('set.title')}</h1>
                    <p className="mt-2 max-w-[62ch] text-sm font-semibold leading-relaxed text-[#676970] dark:text-white/58">
                        {lang === 'zh'
                            ? '这里只维护长期偏好、凭证和本机数据。单次任务判断放在处理记录里解释。'
                            : 'Long-term preferences, credentials, and local data live here. Per-task decisions are explained in processing records.'}
                    </p>
                </header>

                <div className="space-y-5">
                    <Section
                        id="processing"
                        title={lang === 'zh' ? '处理偏好' : 'Processing preferences'}
                        description={lang === 'zh' ? '这里只保留会影响后续任务的长期偏好。' : 'Only long-term preferences that affect future tasks stay here.'}
                    >
                        <div className="divide-y divide-[#ece8e8] dark:divide-white/[0.1]">
                            <div className="px-5 py-4">
                                <div className="mb-3">
                                    <h3 className="text-sm font-bold">{lang === 'zh' ? '转录路线' : 'Transcription route'}</h3>
                                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                        {pureCloudServer
                                            ? (lang === 'zh' ? '当前是线上云端环境，本地转录不可用。' : 'This cloud deployment cannot run local transcription.')
                                            : (lang === 'zh' ? '本机打开时可以选择本地或云端；线上纯云端环境会锁定云端。' : 'Local desktop can choose local or cloud. Cloud-only deployments stay locked to cloud.')}
                                    </p>
                                </div>
                                <div className="grid gap-3 md:grid-cols-2">
                                    <button
                                        type="button"
                                        className={routeButtonClass(isCloudSttProvider(sttProvider), false)}
                                        onClick={() => updateSettingNow({sttProvider: 'elevenlabs_scribe'})}
                                    >
                                        <span>
                                            <span className="block text-sm font-bold">{cloudProviderLabel}</span>
                                            <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                                {lang === 'zh' ? '适合线上任务和长时间后台处理。' : 'Best for cloud jobs and long background runs.'}
                                            </span>
                                        </span>
                                        {isCloudSttProvider(sttProvider) && <SvgIcon name="check" className="mt-0.5 text-base text-primary"/>}
                                    </button>
                                    <button
                                        type="button"
                                        disabled={!localRouteAvailable}
                                        className={routeButtonClass(sttProvider === 'local', !localRouteAvailable)}
                                        onClick={() => {
                                            if (localRouteAvailable) updateSettingNow({sttProvider: 'local'});
                                        }}
                                    >
                                        <span>
                                            <span className="block text-sm font-bold">{localProviderLabel}</span>
                                            <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                                {localRouteAvailable
                                                    ? (lang === 'zh' ? '本地处理转录；生成笔记仍使用账号和模型服务。' : 'Transcribes locally; note generation still uses your account and model service.')
                                                    : (lang === 'zh' ? '当前环境不可用。' : 'Unavailable in this environment.')}
                                            </span>
                                        </span>
                                        {sttProvider === 'local' && <SvgIcon name="check" className="mt-0.5 text-base text-primary"/>}
                                    </button>
                                </div>
                            </div>

                            <label htmlFor="settingsSpeakerDiarization" className={`grid gap-4 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-start ${speakerDiarizationAvailable ? 'cursor-pointer hover:bg-[#faf9f9] dark:hover:bg-white/[0.04]' : 'cursor-not-allowed opacity-60'}`}>
                                <span>
                                    <span className="block text-sm font-bold">{lang === 'zh' ? '区分不同讲话人' : 'Speaker diarization'}</span>
                                    <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh' ? '适合多人访谈或讲座。不可用时会保持关闭。' : 'Useful for interviews or lectures. It stays off when unavailable.'}
                                    </span>
                                </span>
                                <input id="settingsSpeakerDiarization" type="checkbox" checked={!!settings.speakerDiarization && speakerDiarizationAvailable} disabled={!speakerDiarizationAvailable} onChange={e=>updateSettingNow({speakerDiarization:e.target.checked})} className="h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary disabled:opacity-40"/>
                            </label>

                            {sttProvider === 'local' && localRouteAvailable && (
                                <details className="group px-5 py-4">
                                    <summary className="flex cursor-pointer list-none items-center justify-between gap-4 text-sm font-bold">
                                        <span>{lang === 'zh' ? '本机转录高级选项' : 'Local transcription options'}</span>
                                        <SvgIcon name="expand_less" className="text-sm text-on-surface-variant transition group-open:rotate-180"/>
                                    </summary>
                                    <div className="mt-4 grid gap-4 md:grid-cols-2">
                                        <div className="rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 py-3 text-sm font-semibold text-[#57585d] dark:border-white/[0.12] dark:bg-white/[0.05] dark:text-white/70">
                                            {lang === 'zh'
                                                ? '本地转录固定使用 faster-whisper medium 模型。'
                                                : 'Local transcription always uses the faster-whisper medium model.'}
                                        </div>
                                        <div className="space-y-2">
                                            <label className={fieldLabelClass}>{t('set.sttSpeed')}</label>
                                            <select className={inputClass} value={settings.sttSpeed || 'balanced'} onChange={e=>updateSettingNow({sttSpeed:e.target.value})}>
                                                <option value="fast">{t('set.speedFast')}</option>
                                                <option value="balanced">{t('set.speedBalanced')}</option>
                                                <option value="accurate">{t('set.speedAccurate')}</option>
                                            </select>
                                        </div>
                                    </div>
                                </details>
                            )}
                        </div>
                    </Section>

                    <Section id="export" title={lang === 'zh' ? '导出与集成' : 'Export and integrations'}>
                        <div className="divide-y divide-[#ece8e8] dark:divide-white/[0.1]">
                            <label htmlFor="settingsExportToLark" className="grid cursor-pointer gap-4 px-5 py-4 hover:bg-[#faf9f9] dark:hover:bg-white/[0.04] md:grid-cols-[minmax(0,1fr)_auto] md:items-start">
                                <span>
                                    <span className="block text-sm font-bold">{t('set.autoExport')}</span>
                                    <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh' ? '处理完成后自动创建飞书文档。' : 'Create a Lark document automatically after processing.'}
                                    </span>
                                </span>
                                <input id="settingsExportToLark" type="checkbox" checked={settings.exportToLark || false} onChange={e=>updateSettingNow({exportToLark:e.target.checked})} className="h-4 w-4 rounded border-outline-variant text-primary focus:ring-primary"/>
                            </label>

                            {showMaintainerSettings && (
                                <div className="grid gap-4 px-5 py-4 md:grid-cols-[minmax(0,1fr)_minmax(260px,320px)] md:items-start">
                                    <div>
                                        <h3 className="text-sm font-bold">{t('set.larkExportRoute')}</h3>
                                        <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                            {isLocalLarkExportRoute(larkExportRoute) ? t('set.larkRouteLocalCliHint') : t('set.larkRouteOpenapiHint')}
                                        </p>
                                    </div>
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
                                        <option value={LARK_EXPORT_ROUTE_LOCAL_CLI}>{t('set.larkRouteLocalCli')}</option>
                                    </select>
                                </div>
                            )}

                            {larkExports.length > 0 && (
                                <div className="px-5 py-4">
                                    <div className="mb-3 flex items-center justify-between gap-3">
                                        <h3 className="text-sm font-bold">{t('set.larkHistory')}</h3>
                                        <span className="text-xs font-semibold text-on-surface-variant">{larkExports.length} {t('dash.docUnit')}</span>
                                    </div>
                                    <div className="max-h-64 space-y-2 overflow-y-auto hide-scrollbar">
                                        {larkExports.map((ex, i) => (
                                            <a key={i} href={ex.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 rounded-[12px] bg-[#f4f3f3] p-3 transition hover:bg-[#efeeee] dark:bg-white/[0.08] dark:hover:bg-white/[0.12]">
                                                <SvgIcon name="description" className="text-lg text-primary"/>
                                                <span className="min-w-0 flex-1">
                                                    <span className="block truncate text-sm font-semibold">{ex.title}</span>
                                                    <span className="block text-[10px] text-on-surface-variant">{timeAgo(ex.timestamp, t)}</span>
                                                </span>
                                                <SvgIcon name="open_in_new" className="text-sm text-on-surface-variant"/>
                                            </a>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </Section>

                    <Section id="data" title={lang === 'zh' ? '数据与隐私' : 'Data and privacy'}>
                        <div className="grid gap-4 px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                            <div>
                                <h3 className="text-sm font-bold">{lang === 'zh' ? '本地历史记录' : 'Local browser history'}</h3>
                                <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                    {lang === 'zh' ? '清除当前浏览器保存的本地历史记录，不会删除服务器任务。' : 'Clear history stored in this browser. Server jobs are not deleted.'}
                                </p>
                            </div>
                            <button onClick={handleClear} disabled={history.length === 0} className="inline-flex h-[40px] items-center gap-1.5 rounded-[12px] bg-red-50 px-4 text-xs font-bold text-red-600 transition hover:bg-red-100 disabled:opacity-30 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20">
                                <SvgIcon name="delete_sweep" className="text-sm"/>
                                {cleared ? t('edit.clearConfirm') : `${t('edit.clearHistory')} (${history.length})`}
                            </button>
                        </div>
                    </Section>

                    {showMaintainerSettings && (
                        <Section
                            id="maintenance"
                            title={lang === 'zh' ? '系统维护' : 'System maintenance'}
                            description={lang === 'zh' ? '服务商、密钥和底层能力配置。普通用户不需要理解这里。' : 'Providers, secrets, and low-level capabilities. Regular users do not need this section.'}
                        >
                            <div className="divide-y divide-[#ece8e8] dark:divide-white/[0.1]">
                                <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.provider')}</label>
                                        <select className={inputClass} value={aiProvider} onChange={e=>updateSettingNow({aiProvider:e.target.value, aiModel:e.target.value === 'openai' ? DEFAULT_OPENAI_MODEL : DEFAULT_DEEPSEEK_MODEL})}>
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
                                    <div className="space-y-2 md:col-span-2">
                                        <label className={fieldLabelClass}>{aiProvider === 'openai' ? t('set.openaiKey') : t('set.deepseekKey')}</label>
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={secretStatusText(activeAiConfigured)} type="password" value={secretDraft[activeAiSecretKey] || ''} onChange={e=>setSecretDraft(d=>({...d, [activeAiSecretKey]: e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft[activeAiSecretKey]} onClick={()=>saveSecret(activeAiSecretKey)} className={saveButtonClass}>{lang === 'zh' ? '保存' : 'Save'}</button>
                                        </div>
                                        <SecretFeedback keyName={activeAiSecretKey} />
                                    </div>
                                </div>

                                {!isLocalLarkExportRoute(larkExportRoute) && (
                                    <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
                                        <div className="space-y-2">
                                            <label className={fieldLabelClass}>FEISHU APP ID</label>
                                            <div className="flex gap-2">
                                                <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_id_configured)} value={secretDraft.lark_app_id || ''} onChange={e=>setSecretDraft(d=>({...d, lark_app_id: e.target.value}))}/>
                                                <button type="button" disabled={secretSaving || !secretDraft.lark_app_id} onClick={()=>saveSecret('lark_app_id')} className={saveButtonClass}>{lang === 'zh' ? '保存' : 'Save'}</button>
                                            </div>
                                            <SecretFeedback keyName="lark_app_id" />
                                        </div>
                                        <div className="space-y-2">
                                            <label className={fieldLabelClass}>FEISHU APP SECRET</label>
                                            <div className="flex gap-2">
                                                <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_secret_configured)} type="password" value={secretDraft.lark_app_secret || ''} onChange={e=>setSecretDraft(d=>({...d, lark_app_secret: e.target.value}))}/>
                                                <button type="button" disabled={secretSaving || !secretDraft.lark_app_secret} onClick={()=>saveSecret('lark_app_secret')} className={saveButtonClass}>{lang === 'zh' ? '保存' : 'Save'}</button>
                                            </div>
                                            <SecretFeedback keyName="lark_app_secret" />
                                        </div>
                                    </div>
                                )}

                                {localRouteAvailable && (
                                    <div className="px-5 py-4">
                                        <div className="mb-3 flex items-start justify-between gap-3">
                                            <div>
                                                <label className={fieldLabelClass}>PYANNOTE AUTH TOKEN</label>
                                                <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                                    {pyannoteTokenConfigured
                                                        ? (lang === 'zh' ? '已配置。token 不会显示，需要更换时重新输入。' : 'Configured. The token is hidden. Re-enter it only when replacing it.')
                                                        : (lang === 'zh' ? '用于本机后端获取 pyannote 讲话人区分模型。' : 'Used by the local backend to fetch the pyannote diarization model.')}
                                                </p>
                                            </div>
                                            {pyannoteTokenConfigured && !pyannoteTokenEditing && (
                                                <button type="button" onClick={()=>setPyannoteTokenEditing(true)} className="shrink-0 rounded-[10px] border border-[#dedada] px-3 py-2 text-xs font-bold hover:bg-[#efeeee] dark:border-white/[0.12] dark:hover:bg-white/[0.12]">
                                                    {lang === 'zh' ? '更换' : 'Replace'}
                                                </button>
                                            )}
                                        </div>
                                        {showPyannoteTokenInput && (
                                            <div className="flex flex-col gap-2 md:flex-row">
                                                <input className={inputClass} placeholder={lang === 'zh' ? '粘贴 Hugging Face hf_... token' : 'Paste Hugging Face hf_... token'} type="password" value={secretDraft.pyannote_auth_token || ''} onChange={e=>setSecretDraft(d=>({...d, pyannote_auth_token: e.target.value}))}/>
                                                <button type="button" disabled={secretSaving || !secretDraft.pyannote_auth_token} onClick={()=>saveSecret('pyannote_auth_token')} className={saveButtonClass}>{lang === 'zh' ? '保存' : 'Save'}</button>
                                                {pyannoteTokenConfigured && (
                                                    <button type="button" onClick={()=>{setPyannoteTokenEditing(false); setSecretDraft(d=>({...d, pyannote_auth_token: ''}));}} className="rounded-[14px] border border-[#dedada] px-3 py-3 text-sm font-extrabold text-[#111111] transition hover:bg-[#efeeee] active:translate-y-px dark:border-white/[0.12] dark:text-white dark:hover:bg-white/[0.10]">
                                                        {lang === 'zh' ? '取消' : 'Cancel'}
                                                    </button>
                                                )}
                                            </div>
                                        )}
                                        <SecretFeedback keyName="pyannote_auth_token" />
                                    </div>
                                )}
                            </div>
                        </Section>
                    )}
                </div>
            </main>

            {clearConfirmOpen && (
                <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="clearHistoryTitle">
                    <div className="w-full max-w-[420px] rounded-[22px] border border-[#dedada] bg-white p-5 shadow-[0_28px_90px_-52px_rgba(17,17,17,.72)] dark:border-white/[0.12] dark:bg-[#151515]">
                        <div className="flex items-start gap-3">
                            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300">
                                <SvgIcon name="warning" className="text-xl"/>
                            </span>
                            <div>
                                <h2 id="clearHistoryTitle" className="text-base font-extrabold">
                                    {lang === 'zh' ? '确认清除本地历史？' : 'Clear local history?'}
                                </h2>
                                <p className="mt-2 text-sm leading-relaxed text-on-surface-variant">
                                    {lang === 'zh'
                                        ? '这只会删除当前浏览器保存的历史记录，不会删除服务器任务。删除后无法从本机历史列表恢复。'
                                        : 'This only deletes history stored in this browser. Server jobs are not deleted, and this browser list cannot restore the removed items.'}
                                </p>
                            </div>
                        </div>
                        <div className="mt-5 flex justify-end gap-2">
                            <button type="button" onClick={()=>setClearConfirmOpen(false)} className="inline-flex h-10 items-center rounded-[12px] border border-[#dedada] px-4 text-xs font-bold hover:bg-[#efeeee] dark:border-white/[0.12] dark:hover:bg-white/[0.12]">
                                {t('edit.cancel')}
                            </button>
                            <button type="button" onClick={confirmClearHistory} className="inline-flex h-10 items-center rounded-[12px] bg-red-600 px-4 text-xs font-bold text-white hover:bg-red-700">
                                {lang === 'zh' ? '确认清除' : 'Clear history'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Settings;
