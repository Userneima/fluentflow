import {useEffect, useState} from 'react';
import SvgIcon from '../components/SvgIcon.jsx';
import {
    API_BASE,
    apiFetch,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_QWEN_MODEL,
    LARK_EXPORT_ROUTE_LOCAL_CLI,
    LARK_EXPORT_ROUTE_OPENAPI,
    LARK_EXPORT_ROUTE_USER_OAUTH,
    effectiveSttProvider,
    isCloudSttProvider,
    isLocalLarkExportRoute,
    isUserOAuthLarkExportRoute,
    larkExportRouteFromSettings,
    normalizeAiModel,
    normalizeSttModel,
    timeAgo,
    useApi,
    useApp,
    useAuth,
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

const SettingCheckbox = ({id, checked, disabled, onChange}) => (
    <span className="flex justify-end pt-0.5">
        <input
            id={id}
            type="checkbox"
            checked={checked}
            disabled={disabled}
            onChange={onChange}
            className="peer sr-only"
        />
        <span
            aria-hidden="true"
            className="flex size-5 items-center justify-center rounded-[6px] border border-outline-variant bg-surface-container-lowest text-transparent transition peer-checked:border-primary peer-checked:bg-primary peer-checked:text-on-primary peer-focus-visible:ring-2 peer-focus-visible:ring-primary/30 peer-disabled:opacity-40 dark:border-white/30 dark:bg-white/[0.04] dark:peer-checked:border-primary dark:peer-checked:bg-primary"
        >
            <SvgIcon name="check" className="text-[15px]"/>
        </span>
    </span>
);

const Settings = () => {
    const {t, lang} = useI18n();
    const {loadSettings, saveSettings} = useSettings();
    const {clearHistory, history, larkExports, runtimeConfig} = useApp();
    const {authMode, user, guestMode} = useAuth();
    const {getCredentialsStatus, saveCredentials, getSpeakerDiarizationStatus, checkVideoCookies, getDesktopSyncStatus, startDesktopPairing, flushDesktopSync} = useApi();
    const [settings, setSettings] = useState(() => loadSettings());
    const [cleared, setCleared] = useState(false);
    const [clearConfirmOpen, setClearConfirmOpen] = useState(false);
    const [credentialStatus, setCredentialStatus] = useState(null);
    const [diarizationStatus, setDiarizationStatus] = useState(null);
    const [cookieCheck, setCookieCheck] = useState(null);
    const [cookieChecking, setCookieChecking] = useState(false);
    const [secretDraft, setSecretDraft] = useState({});
    const [pyannoteTokenEditing, setPyannoteTokenEditing] = useState(false);
    const [secretSaving, setSecretSaving] = useState(false);
    const [secretFeedback, setSecretFeedback] = useState(null);
    const [desktopSync, setDesktopSync] = useState(undefined);
    const [desktopSyncCloudUrl, setDesktopSyncCloudUrl] = useState('');
    const [desktopSyncBusy, setDesktopSyncBusy] = useState(false);
    const [desktopSyncFeedback, setDesktopSyncFeedback] = useState(null);
    const [accountDeletionConfirmOpen, setAccountDeletionConfirmOpen] = useState(false);
    const [accountDeletionBusy, setAccountDeletionBusy] = useState(false);
    const [accountDeletionError, setAccountDeletionError] = useState('');

    const refreshDesktopSync = async () => {
        try {
            const next = await getDesktopSyncStatus();
            setDesktopSync(next);
            setDesktopSyncCloudUrl((current) => current || next?.sync?.cloud_url || next?.default_cloud_url || '');
            return next;
        } catch (_) {
            setDesktopSync((current) => current || null);
            return null;
        }
    };

    const credentialConfigured = (status, key) => {
        if (key === 'dashscope_api_key' || key === 'qwen_api_key') {
            return !!(status?.dashscope_api_key_configured || status?.qwen_api_key_configured);
        }
        return !!status?.[`${key}_configured`];
    };

    const credentialStatusKey = (key) => (
        key === 'dashscope_api_key' || key === 'qwen_api_key'
            ? 'dashscope_api_key_configured'
            : `${key}_configured`
    );

    useEffect(() => {
        const normalizedSttModel = normalizeSttModel(settings.sttModel);
        if (settings.sttModel !== normalizedSttModel) {
            const next = {...settings, sttModel: normalizedSttModel};
            setSettings(next);
            saveSettings(next);
        }
        getCredentialsStatus().then(setCredentialStatus).catch(() => {});
        getSpeakerDiarizationStatus().then(setDiarizationStatus).catch(() => {});
        refreshDesktopSync();
    }, []);

    useEffect(() => {
        if (!desktopSync?.sync?.pairing_pending) return undefined;
        const poll = window.setInterval(() => { refreshDesktopSync(); }, 2000);
        return () => window.clearInterval(poll);
    }, [desktopSync?.sync?.pairing_pending]);

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
            const statusKey = credentialStatusKey(key);
            if (value && statusKey) {
                fresh[statusKey] = true;
                if (key === 'dashscope_api_key' || key === 'qwen_api_key') {
                    fresh.qwen_api_key_configured = true;
                    fresh.dashscope_api_key_configured = true;
                }
            }
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

    const secretRetentionText = (configured) => (
        configured
            ? (lang === 'zh' ? '已配置，留空则保留' : 'Configured. Leave blank to keep it.')
            : (lang === 'zh' ? '未配置' : 'Not configured')
    );

    const secretInputPlaceholder = (configured) => (
        configured
            ? (lang === 'zh' ? '已配置，输入新 Key 可替换' : 'Configured. Enter a new key to replace it.')
            : (lang === 'zh' ? '粘贴 API Key' : 'Paste API key')
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

    const requestAccountDeletion = async () => {
        setAccountDeletionBusy(true);
        setAccountDeletionError('');
        try {
            const response = await apiFetch(`${API_BASE}/account/deletion`, {method: 'POST'});
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || (lang === 'zh' ? '无法提交删除请求' : 'Unable to request account deletion'));
            window.location.assign('/?account_deletion=requested');
        } catch (err) {
            setAccountDeletionError(err.message || String(err));
            setAccountDeletionConfirmOpen(false);
        } finally {
            setAccountDeletionBusy(false);
        }
    };

    const connectDesktopSync = async () => {
        const cloudUrl = desktopSyncCloudUrl.trim();
        if (!cloudUrl) {
            setDesktopSyncFeedback({ok: false, message: lang === 'zh' ? '填写云端地址后再连接。' : 'Enter the cloud address first.'});
            return;
        }
        const pairWindow = window.open('', 'fluentflow-desktop-pair', 'popup,width=560,height=720');
        setDesktopSyncBusy(true);
        setDesktopSyncFeedback(null);
        try {
            const next = await startDesktopPairing({cloud_url: cloudUrl});
            setDesktopSync({sync: next, outbox: desktopSync?.outbox || {pending_count: 0}});
            if (pairWindow) {
                try { pairWindow.opener = null; } catch (_) {}
                pairWindow.location.assign(next.pair_url);
            } else {
                window.open(next.pair_url, '_blank', 'noopener,noreferrer');
            }
        } catch (err) {
            pairWindow?.close();
            setDesktopSyncFeedback({ok: false, message: err.message || String(err)});
        } finally {
            setDesktopSyncBusy(false);
        }
    };

    const retryDesktopSync = async () => {
        setDesktopSyncBusy(true);
        setDesktopSyncFeedback(null);
        try {
            const next = await flushDesktopSync();
            setDesktopSync(next);
            setDesktopSyncFeedback({ok: true, message: lang === 'zh' ? '已检查待同步内容。' : 'Checked pending sync items.'});
        } catch (err) {
            setDesktopSyncFeedback({ok: false, message: err.message || String(err)});
        } finally {
            setDesktopSyncBusy(false);
        }
    };


    const inputClass = 'w-full rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 py-3 text-sm font-semibold text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40';
    const fieldLabelClass = 'text-[11px] font-extrabold uppercase tracking-wider text-[#676970] dark:text-white/50';
    const saveButtonClass = 'rounded-[14px] bg-[#111111] px-4 py-3 text-sm font-extrabold text-white transition hover:bg-[#2a2a2a] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]';
    const cellBase = 'rounded-[14px] border border-[#ece8e8] bg-[#fbfbfb] px-4 py-3.5 dark:border-white/[0.1] dark:bg-white/[0.02]';
    const radioClass = (active) => [
        'mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-full border-2 transition',
        active ? 'border-primary' : 'border-[#c9c9c9] dark:border-white/30',
    ].join(' ');
    const aiProvider = settings.aiProvider || 'deepseek';
    const aiModel = normalizeAiModel(aiProvider, settings.aiModel);
    const aiProviderDefaults = {
        deepseek: DEFAULT_DEEPSEEK_MODEL,
        openai: DEFAULT_OPENAI_MODEL,
        qwen: DEFAULT_QWEN_MODEL,
    };
    const activeAiSecretKey = aiProvider === 'openai' ? 'openai_api_key' : (aiProvider === 'qwen' ? 'dashscope_api_key' : 'deepseek_api_key');
    const activeAiConfigured = aiProvider === 'openai'
        ? credentialStatus?.openai_api_key_configured
        : (aiProvider === 'qwen' ? credentialConfigured(credentialStatus, 'dashscope_api_key') : credentialStatus?.deepseek_api_key_configured);
    const sttProvider = effectiveSttProvider(settings, runtimeConfig);
    const larkExportRoute = larkExportRouteFromSettings(settings);
    const feishuUserOAuthSelected = isUserOAuthLarkExportRoute(larkExportRoute);
    const larkRouteHint = feishuUserOAuthSelected
        ? (lang === 'zh' ? '导出会写入你连接的飞书账号空间，不需要在这里输入 App Secret。' : 'Exports go to the connected Feishu account. No app secret is entered here.')
        : (isLocalLarkExportRoute(larkExportRoute) ? t('set.larkRouteLocalCliHint') : t('set.larkRouteOpenapiHint'));
    const cloudProviderLabel = lang === 'zh' ? '云端转录' : 'Cloud transcription';
    const localProviderLabel = t('set.providerLocal');
    const localRouteAvailable = runtimeConfig.allowedSttProviders.includes('local');
    const pureCloudServer = runtimeConfig.publicMode && !localRouteAvailable;
    const speakerDiarizationAvailable = isCloudSttProvider(sttProvider) || (sttProvider === 'local' && !!diarizationStatus?.available);
    const pyannoteTokenConfigured = !!(credentialStatus?.pyannote_auth_token_configured || diarizationStatus?.auth_configured);
    const showPyannoteTokenInput = !pyannoteTokenConfigured || pyannoteTokenEditing;
    const showMaintainerSettings = runtimeConfig.showMaintainerSettings;
    const desktopSyncConnected = !!desktopSync?.sync?.connected;
    const desktopSyncPendingCount = Number(desktopSync?.outbox?.pending_count || 0);

    const routeButtonClass = (active, disabled) => [
        'flex min-h-[74px] flex-1 items-start gap-3 rounded-[14px] border px-4 py-3 text-left transition',
        active
            ? 'border-primary bg-primary/10 text-[#111111] dark:text-white'
            : 'border-[#dedada] bg-[#f8f7f7] text-[#555] hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/70 dark:hover:bg-white/[0.1]',
        disabled ? 'cursor-not-allowed opacity-45 hover:bg-[#f8f7f7] dark:hover:bg-white/[0.06]' : 'cursor-pointer active:translate-y-px',
    ].join(' ');

    return (
        <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] pb-8 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <main className="mx-auto h-dvh max-w-[1040px] overflow-y-auto px-8 py-7 hide-scrollbar">
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
                        id="transcription"
                        title={lang === 'zh' ? '转录' : 'Transcription'}
                        description={lang === 'zh'
                            ? (pureCloudServer ? '把音视频变成文字的方式。当前是线上云端环境，本地转录不可用。' : '把音视频变成文字的方式。云端与本地转录二选一。')
                            : (pureCloudServer ? 'How media becomes text. This cloud deployment cannot run local transcription.' : 'How media becomes text. Choose cloud or local transcription.')}
                    >
                        <div className="grid gap-3 p-5 md:grid-cols-2">
                            <div className="md:col-span-2">
                                <label className={`${fieldLabelClass} mb-2.5 block`}>{lang === 'zh' ? '转录路线' : 'Transcription route'}</label>
                                <div className="grid gap-3 md:grid-cols-2">
                                    <button
                                        type="button"
                                        className={routeButtonClass(isCloudSttProvider(sttProvider), false)}
                                        onClick={() => updateSettingNow({sttProvider: 'elevenlabs_scribe'})}
                                    >
                                        <span className={radioClass(isCloudSttProvider(sttProvider))} aria-hidden="true">
                                            {isCloudSttProvider(sttProvider) && <span className="size-2.5 rounded-full bg-primary"/>}
                                        </span>
                                        <span>
                                            <span className="block text-sm font-bold">{cloudProviderLabel}</span>
                                            <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                                {lang === 'zh' ? '适合线上任务和长时间后台处理。' : 'Best for cloud jobs and long background runs.'}
                                            </span>
                                        </span>
                                    </button>
                                    <button
                                        type="button"
                                        disabled={!localRouteAvailable}
                                        className={routeButtonClass(sttProvider === 'local', !localRouteAvailable)}
                                        onClick={() => {
                                            if (localRouteAvailable) updateSettingNow({sttProvider: 'local'});
                                        }}
                                    >
                                        <span className={radioClass(sttProvider === 'local')} aria-hidden="true">
                                            {sttProvider === 'local' && <span className="size-2.5 rounded-full bg-primary"/>}
                                        </span>
                                        <span>
                                            <span className="block text-sm font-bold">{localProviderLabel}</span>
                                            <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                                {localRouteAvailable
                                                    ? (lang === 'zh' ? '本地处理转录；生成笔记仍使用账号和模型服务。' : 'Transcribes locally; note generation still uses your account and model service.')
                                                    : (lang === 'zh' ? '当前环境不可用。' : 'Unavailable in this environment.')}
                                            </span>
                                        </span>
                                    </button>
                                </div>
                            </div>

                            <label htmlFor="settingsSpeakerDiarization" className={`flex items-start justify-between gap-3 ${cellBase} ${speakerDiarizationAvailable ? 'cursor-pointer hover:bg-[#f4f3f3] dark:hover:bg-white/[0.04]' : 'cursor-not-allowed opacity-60'}`}>
                                <span>
                                    <span className="block text-sm font-bold">{lang === 'zh' ? '区分不同讲话人' : 'Speaker diarization'}</span>
                                    <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh' ? '适合多人访谈或讲座。不可用时会保持关闭。' : 'Useful for interviews or lectures. It stays off when unavailable.'}
                                    </span>
                                </span>
                                <SettingCheckbox
                                    id="settingsSpeakerDiarization"
                                    checked={!!settings.speakerDiarization && speakerDiarizationAvailable}
                                    disabled={!speakerDiarizationAvailable}
                                    onChange={e=>updateSettingNow({speakerDiarization:e.target.checked})}
                                />
                            </label>

                            {sttProvider === 'local' && localRouteAvailable && (
                                <div className={`flex items-center justify-between gap-3 ${cellBase}`}>
                                    <span className="text-sm font-bold">{t('set.sttSpeed')}</span>
                                    <select className="h-10 shrink-0 rounded-[12px] border border-[#dedada] bg-[#fbfbfb] px-3 text-sm font-bold text-[#111111] outline-none transition focus:border-[#111111] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white" value={settings.sttSpeed || 'balanced'} onChange={e=>updateSettingNow({sttSpeed:e.target.value})}>
                                        <option value="fast">{t('set.speedFast')}</option>
                                        <option value="balanced">{t('set.speedBalanced')}</option>
                                        <option value="accurate">{t('set.speedAccurate')}</option>
                                    </select>
                                </div>
                            )}

                            {localRouteAvailable && (
                                <div className={`md:col-span-2 ${cellBase}`}>
                                    <label className="block text-sm font-bold">{lang === 'zh' ? '视频链接下载登录态' : 'Video link login'}</label>
                                    <div className="mt-2.5 flex flex-wrap items-center gap-2.5">
                                        <select
                                            className="h-10 w-[220px] rounded-[12px] border border-[#dedada] bg-[#fbfbfb] px-3 text-sm font-bold text-[#111111] outline-none transition focus:border-[#111111] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white"
                                            value={settings.videoCookiesBrowser || ''}
                                            onChange={e=>{ updateSettingNow({videoCookiesBrowser:e.target.value}); setCookieCheck(null); }}
                                        >
                                            <option value="">{lang === 'zh' ? '关闭（不读取浏览器登录态）' : 'Off (no browser login)'}</option>
                                            <option value="chrome">Chrome</option>
                                            <option value="edge">Edge</option>
                                            <option value="firefox">Firefox</option>
                                            <option value="safari">Safari</option>
                                            <option value="brave">Brave</option>
                                        </select>
                                        {settings.videoCookiesBrowser && (
                                            <button
                                                type="button"
                                                disabled={cookieChecking}
                                                onClick={async () => {
                                                    setCookieChecking(true); setCookieCheck(null);
                                                    try { setCookieCheck(await checkVideoCookies(settings.videoCookiesBrowser)); }
                                                    catch (err) { setCookieCheck({ok:false, message: err.message || String(err)}); }
                                                    finally { setCookieChecking(false); }
                                                }}
                                                className="inline-flex h-10 shrink-0 items-center gap-2 rounded-[12px] border border-[#dedada] bg-white px-4 text-xs font-bold text-[#111111] transition hover:bg-[#f4f3f3] disabled:opacity-50 dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.10]"
                                            >
                                                {cookieChecking ? (lang === 'zh' ? '检测中…' : 'Checking…') : (lang === 'zh' ? '检测登录态' : 'Check login')}
                                            </button>
                                        )}
                                        {cookieCheck && (
                                            <span className={`text-xs font-semibold ${cookieCheck.ok ? (cookieCheck.bilibili_logged_in ? 'text-emerald-600 dark:text-emerald-300' : 'text-amber-600 dark:text-amber-300') : 'text-red-600 dark:text-red-300'}`}>
                                                {cookieCheck.ok
                                                    ? (cookieCheck.bilibili_logged_in
                                                        ? (lang === 'zh' ? '已读取到登录态，且已登录 B 站，可下高清。' : 'Cookies read; logged into Bilibili — HD available.')
                                                        : (lang === 'zh' ? '已读取到浏览器 cookie，但未检测到 B 站登录（B 站最高约 480p）。B 站高清请先在该浏览器登录；YouTube 受限视频不受影响。' : 'Cookies read, but not logged into Bilibili (Bilibili max ~480p). Log into Bilibili for HD; YouTube restricted videos still work.'))
                                                    : cookieCheck.message}
                                            </span>
                                        )}
                                    </div>
                                    <p className="mt-2.5 text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh'
                                            ? '从所选浏览器复用你的登录 cookie，下载需要登录才能看的视频。仅在本机读取、不会上传；B 站高清和 YouTube 受限视频需要它。'
                                            : 'Reuse your login cookies from the chosen browser to download videos that need sign-in. Read locally only, never uploaded; needed for Bilibili HD and restricted YouTube videos.'}
                                    </p>
                                </div>
                            )}
                        </div>
                    </Section>

                    <Section
                        id="notes"
                        title={lang === 'zh' ? '笔记' : 'Notes'}
                        description={lang === 'zh' ? 'AI 生成笔记时的偏好。' : 'Preferences for AI-generated notes.'}
                    >
                        <div className="p-5">
                            <label htmlFor="settingsAutoIllustrate" className={`flex items-start justify-between gap-3 ${cellBase} cursor-pointer hover:bg-[#f4f3f3] dark:hover:bg-white/[0.04]`}>
                                <span>
                                    <span className="block text-sm font-bold">{lang === 'zh' ? '给笔记自动配图' : 'Auto-illustrate notes'}</span>
                                    <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh'
                                            ? '视频笔记自动截取关键画面配图；需配置通义千问（DashScope）视觉密钥，会产生额外费用。纯口播视频通常无可配图。'
                                            : 'Capture key frames into video notes. Needs a Qwen (DashScope) vision key and adds cost. Talking-head videos usually have nothing to illustrate.'}
                                    </span>
                                </span>
                                <SettingCheckbox
                                    id="settingsAutoIllustrate"
                                    checked={!!settings.autoIllustrate}
                                    onChange={e=>updateSettingNow({autoIllustrate:e.target.checked})}
                                />
                            </label>
                        </div>
                    </Section>

                    <Section id="export" title={lang === 'zh' ? '导出' : 'Export'} description={lang === 'zh' ? '把笔记同步到飞书云文档。' : 'Sync notes to Feishu cloud docs.'}>
                        <div className="grid gap-3 p-5 md:grid-cols-2">
                            <label htmlFor="settingsExportToLark" className={`flex items-start justify-between gap-3 ${cellBase} cursor-pointer hover:bg-[#f4f3f3] dark:hover:bg-white/[0.04]`}>
                                <span>
                                    <span className="block text-sm font-bold">{t('set.autoExport')}</span>
                                    <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh' ? '处理完成后自动创建飞书文档。' : 'Create a Lark document automatically after processing.'}
                                    </span>
                                </span>
                                <SettingCheckbox
                                    id="settingsExportToLark"
                                    checked={settings.exportToLark || false}
                                    onChange={e=>updateSettingNow({exportToLark:e.target.checked})}
                                />
                            </label>

                            {showMaintainerSettings && (
                                <div className={`flex items-start justify-between gap-3 ${cellBase}`}>
                                    <span className="min-w-0">
                                        <span className="block text-sm font-bold">{t('set.larkExportRoute')}</span>
                                        <span className="mt-1 block text-xs leading-relaxed text-on-surface-variant">{larkRouteHint}</span>
                                    </span>
                                    <select
                                        className="h-10 w-[168px] shrink-0 rounded-[12px] border border-[#dedada] bg-[#fbfbfb] px-3 text-sm font-bold text-[#111111] outline-none transition focus:border-[#111111] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white"
                                        value={larkExportRoute}
                                        onChange={e=>{
                                            const route = e.target.value;
                                            updateSettingNow({
                                                larkExportRoute: route,
                                                larkViaCli: isLocalLarkExportRoute(route),
                                            });
                                        }}
                                    >
                                        <option value={LARK_EXPORT_ROUTE_USER_OAUTH}>{lang === 'zh' ? '连接自己的飞书账号' : 'Connected Feishu account'}</option>
                                        <option value={LARK_EXPORT_ROUTE_OPENAPI}>{t('set.larkRouteOpenapi')}</option>
                                        <option value={LARK_EXPORT_ROUTE_LOCAL_CLI}>{t('set.larkRouteLocalCli')}</option>
                                    </select>
                                </div>
                            )}

                            {larkExports.length > 0 && (
                                <div className={`md:col-span-2 ${cellBase}`}>
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

                    {desktopSync && (
                        <Section
                            id="desktop-sync"
                            title={lang === 'zh' ? '设备与云端' : 'Device and cloud'}
                            description={lang === 'zh' ? '本机转录的字幕和笔记会同步到同一账号；原视频保留在这台设备。' : 'Local transcripts and notes sync to the same account. Source videos stay on this device.'}
                        >
                            <div className="m-5 space-y-3">
                                {desktopSyncConnected ? (
                                    <div className={`${cellBase} flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between`}>
                                        <div className="flex min-w-0 items-start gap-3">
                                            <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[10px] bg-primary/10 text-primary"><SvgIcon name="cloud_done" className="text-lg"/></span>
                                            <div className="min-w-0">
                                                <h3 className="text-sm font-bold">{lang === 'zh' ? '云端账号已连接' : 'Cloud account connected'}</h3>
                                                <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                                    {desktopSyncPendingCount > 0
                                                        ? (lang === 'zh' ? `${desktopSyncPendingCount} 项等待同步` : `${desktopSyncPendingCount} item${desktopSyncPendingCount === 1 ? '' : 's'} pending`)
                                                        : (lang === 'zh' ? '当前没有待同步内容' : 'No pending sync items')}
                                                </p>
                                            </div>
                                        </div>
                                        <button type="button" aria-label={lang === 'zh' ? '立即重试同步' : 'Retry sync now'} title={lang === 'zh' ? '立即重试同步' : 'Retry sync now'} disabled={desktopSyncBusy || desktopSyncPendingCount === 0} onClick={retryDesktopSync} className="inline-flex size-10 shrink-0 items-center justify-center rounded-[12px] border border-outline-variant text-on-surface transition hover:bg-surface-container-low disabled:cursor-not-allowed disabled:opacity-40">
                                            <SvgIcon name="refresh" className={`text-base ${desktopSyncBusy ? 'animate-spin' : ''}`}/>
                                        </button>
                                    </div>
                                ) : (
                                    <div className={`${cellBase} space-y-3`}>
                                        <label className={`${fieldLabelClass} block`} htmlFor="desktopSyncCloudUrl">{lang === 'zh' ? '云端地址' : 'Cloud address'}</label>
                                        <div className="flex flex-col gap-2 sm:flex-row">
                                            <input id="desktopSyncCloudUrl" className={inputClass} value={desktopSyncCloudUrl} onChange={e=>setDesktopSyncCloudUrl(e.target.value)} placeholder="https://" inputMode="url" autoComplete="url"/>
                                            <button type="button" disabled={desktopSyncBusy} onClick={connectDesktopSync} className="inline-flex h-[46px] shrink-0 items-center justify-center gap-2 rounded-[14px] bg-primary px-4 text-sm font-extrabold text-on-primary transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50">
                                                <SvgIcon name={desktopSyncBusy ? 'sync' : 'cloud_upload'} className={`text-base ${desktopSyncBusy ? 'animate-spin' : ''}`}/>
                                                {desktopSync?.sync?.pairing_pending ? (lang === 'zh' ? '等待浏览器完成' : 'Waiting for browser') : (lang === 'zh' ? '连接云端账号' : 'Connect cloud account')}
                                            </button>
                                        </div>
                                    </div>
                                )}
                                {desktopSyncFeedback && <p className={`text-xs font-semibold ${desktopSyncFeedback.ok ? 'text-primary' : 'text-error'}`}>{desktopSyncFeedback.message}</p>}
                            </div>
                        </Section>
                    )}

                    <Section id="data" title={lang === 'zh' ? '数据' : 'Data'} description={lang === 'zh' ? '本机保存的记录。' : 'Records stored on this device.'}>
                        <div className={`m-5 grid gap-4 ${cellBase} md:grid-cols-[minmax(0,1fr)_auto] md:items-center`}>
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

                    {authMode === 'accounts' && user && !guestMode && (
                        <Section id="account" title={lang === 'zh' ? '账号' : 'Account'} description={lang === 'zh' ? '跨设备登录和云端数据的管理。' : 'Manage cross-device access and cloud data.'}>
                            <div className="p-5">
                                <div className={`flex flex-col gap-4 ${cellBase} sm:flex-row sm:items-center sm:justify-between`}>
                                    <div className="min-w-0">
                                        <h3 className="text-sm font-bold text-red-700 dark:text-red-300">{lang === 'zh' ? '删除账号' : 'Delete account'}</h3>
                                        <p className="mt-1 max-w-[62ch] text-xs leading-relaxed text-on-surface-variant">
                                            {lang === 'zh'
                                                ? '申请后会立即停止任务、退出所有设备并撤销桌面同步和 API 凭证。云端字幕、笔记和任务数据保留 7 天；在期限内用同一 Google 账号重新登录可取消删除。'
                                                : 'This immediately stops jobs, signs out devices, and revokes desktop sync and API credentials. Cloud transcripts, notes, and jobs are retained for 7 days; sign in again with the same Google account during that period to cancel.'}
                                        </p>
                                        {accountDeletionError && <p className="mt-2 text-xs font-semibold text-red-600 dark:text-red-300">{accountDeletionError}</p>}
                                    </div>
                                    <button type="button" onClick={()=>setAccountDeletionConfirmOpen(true)} className="h-10 shrink-0 rounded-[12px] border border-red-300 px-4 text-xs font-bold text-red-700 transition hover:bg-red-50 dark:border-red-400/40 dark:text-red-300 dark:hover:bg-red-500/10">
                                        {lang === 'zh' ? '申请删除' : 'Request deletion'}
                                    </button>
                                </div>
                            </div>
                        </Section>
                    )}

                    {showMaintainerSettings && (
                        <details id="advanced" className="group scroll-mt-7 rounded-[18px] border border-[#e4e0e0] bg-white dark:border-white/[0.12] dark:bg-white/[0.06]">
                            <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4">
                                <div>
                                    <h2 className="font-headline text-base font-extrabold">{lang === 'zh' ? '高级 · 模型密钥' : 'Advanced · Model keys'}</h2>
                                    <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                        {lang === 'zh' ? '服务商、模型和 API 密钥，进阶才需要展开。普通用户可忽略。' : 'Providers, models, and API keys. Open only if you know you need it.'}
                                    </p>
                                </div>
                                <SvgIcon name="expand_less" className="shrink-0 text-lg text-on-surface-variant transition group-open:rotate-180"/>
                            </summary>
                            <div className="divide-y divide-[#ece8e8] border-t border-[#ece8e8] dark:divide-white/[0.1] dark:border-white/[0.1]">
                                <div className="grid gap-4 px-5 py-4 md:grid-cols-2">
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.provider')}</label>
                                        <select className={inputClass} value={aiProvider} onChange={e=>updateSettingNow({aiProvider:e.target.value, aiModel: aiProviderDefaults[e.target.value] || DEFAULT_DEEPSEEK_MODEL})}>
                                            <option value="deepseek">DeepSeek</option>
                                            <option value="openai">OpenAI</option>
                                            <option value="qwen">Qwen</option>
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
                                        ) : aiProvider === 'qwen' ? (
                                            <select className={inputClass} value={aiModel} onChange={e=>updateSettingNow({aiModel:e.target.value})}>
                                                <option value={DEFAULT_QWEN_MODEL}>{DEFAULT_QWEN_MODEL}</option>
                                            </select>
                                        ) : (
                                            <select className={inputClass} value={aiModel} onChange={e=>updateSettingNow({aiModel:e.target.value})}>
                                                <option value="deepseek-reasoner">deepseek-reasoner</option>
                                            </select>
                                        )}
                                    </div>
                                    <div className="space-y-2 md:col-span-2">
                                        <label className={fieldLabelClass}>{aiProvider === 'openai' ? t('set.openaiKey') : (aiProvider === 'qwen' ? t('set.dashscopeKey') : t('set.deepseekKey'))}</label>
                                        <p className="text-xs leading-relaxed text-on-surface-variant">{secretRetentionText(activeAiConfigured)}</p>
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={secretInputPlaceholder(activeAiConfigured)} type="password" value={secretDraft[activeAiSecretKey] || ''} onChange={e=>setSecretDraft(d=>({...d, [activeAiSecretKey]: e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft[activeAiSecretKey]} onClick={()=>saveSecret(activeAiSecretKey)} className={saveButtonClass}>{lang === 'zh' ? '保存' : 'Save'}</button>
                                        </div>
                                        <SecretFeedback keyName={activeAiSecretKey} />
                                    </div>
                                    {aiProvider !== 'qwen' && (
                                        <div className="space-y-2 md:col-span-2">
                                            <label className={fieldLabelClass}>{t('set.dashscopeKey')}</label>
                                            <p className="text-xs leading-relaxed text-on-surface-variant">
                                                {lang === 'zh'
                                                    ? '用于 Qwen 视觉模型选择视频截图；摘要仍可使用 DeepSeek 或 OpenAI。'
                                                    : 'Used by the Qwen vision model to select video screenshots. Summaries can still use DeepSeek or OpenAI.'}
                                            </p>
                                            <p className="text-xs leading-relaxed text-on-surface-variant">{secretRetentionText(credentialConfigured(credentialStatus, 'dashscope_api_key'))}</p>
                                            <div className="flex gap-2">
                                                <input className={inputClass} placeholder={secretInputPlaceholder(credentialConfigured(credentialStatus, 'dashscope_api_key'))} type="password" value={secretDraft.dashscope_api_key || ''} onChange={e=>setSecretDraft(d=>({...d, dashscope_api_key: e.target.value}))}/>
                                                <button type="button" disabled={secretSaving || !secretDraft.dashscope_api_key} onClick={()=>saveSecret('dashscope_api_key')} className={saveButtonClass}>{lang === 'zh' ? '保存' : 'Save'}</button>
                                            </div>
                                            <SecretFeedback keyName="dashscope_api_key" />
                                        </div>
                                    )}
                                </div>

                                {larkExportRoute === LARK_EXPORT_ROUTE_OPENAPI && (
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
                        </details>
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
            {accountDeletionConfirmOpen && (
                <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 px-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="accountDeletionTitle">
                    <div className="w-full max-w-[440px] rounded-[22px] border border-[#dedada] bg-white p-5 shadow-[0_28px_90px_-52px_rgba(17,17,17,.72)] dark:border-white/[0.12] dark:bg-[#151515]">
                        <h2 id="accountDeletionTitle" className="text-base font-extrabold">{lang === 'zh' ? '确认申请删除账号？' : 'Request account deletion?'}</h2>
                        <p className="mt-2 text-sm leading-relaxed text-on-surface-variant">
                            {lang === 'zh' ? '你的任务会立刻停止，所有设备会退出登录。7 天内使用同一 Google 账号登录可以取消；到期后云端数据将无法恢复。' : 'Jobs stop immediately and every device is signed out. You can cancel by signing in with the same Google account within 7 days; cloud data cannot be restored after that.'}
                        </p>
                        <div className="mt-5 flex justify-end gap-2">
                            <button type="button" onClick={()=>setAccountDeletionConfirmOpen(false)} disabled={accountDeletionBusy} className="inline-flex h-10 items-center rounded-[12px] border border-[#dedada] px-4 text-xs font-bold hover:bg-[#efeeee] disabled:opacity-50 dark:border-white/[0.12] dark:hover:bg-white/[0.12]">{t('edit.cancel')}</button>
                            <button type="button" onClick={requestAccountDeletion} disabled={accountDeletionBusy} className="inline-flex h-10 items-center rounded-[12px] bg-red-600 px-4 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-50">{accountDeletionBusy ? (lang === 'zh' ? '处理中' : 'Working') : (lang === 'zh' ? '确认删除' : 'Confirm deletion')}</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default Settings;
