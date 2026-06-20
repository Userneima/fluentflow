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
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
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
    NOTE_MODE_OPTIONS,
    noteModeLabel,
    normalizeAiModel,
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

const Processing = () => {
    const {t, lang} = useI18n();
    const {currentJob, runtimeConfig} = useApp();
    const {loadSettings, saveSettings} = useSettings();
    const {getCredentialsStatus, saveCredentials, getSpeakerDiarizationStatus} = useApi();
    const [settings, setSettings] = useState(() => loadSettings());
    const [credentialStatus, setCredentialStatus] = useState(null);
    const [diarizationStatus, setDiarizationStatus] = useState(null);
    const [secretDraft, setSecretDraft] = useState({});
    const [pyannoteTokenEditing, setPyannoteTokenEditing] = useState(false);
    const [secretSaving, setSecretSaving] = useState(false);
    const [secretFeedback, setSecretFeedback] = useState(null);

    const updateSettingNow = (patch) => {
        setSettings((s) => {
            const next = {...s, ...patch};
            saveSettings(next);
            return next;
        });
    };

    useEffect(() => {
        const pk = settings.promptPreset || DEFAULT_PROMPT_PRESET;
        if (isBuiltinPromptPresetHidden(pk, settings)) updateSettingNow({promptPreset: 'default'});
        const normalizedSttModel = normalizeSttModel(settings.sttModel);
        if (settings.sttModel !== normalizedSttModel) updateSettingNow({sttModel: normalizedSttModel});
        if ((settings.sttLanguage || 'auto') !== 'auto') updateSettingNow({sttLanguage: 'auto'});
        getCredentialsStatus().then(setCredentialStatus).catch(() => {});
        getSpeakerDiarizationStatus().then((status) => {
            setDiarizationStatus(status);
            if (!status?.available && effectiveSttProvider(settings, runtimeConfig) === 'local' && settings.speakerDiarization) {
                updateSettingNow({speakerDiarization:false});
            }
        }).catch(() => {});
    }, []);

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

    const aiProvider = settings.aiProvider || 'deepseek';
    const aiModel = normalizeAiModel(aiProvider, settings.aiModel);
    const activeAiSecretKey = aiProvider === 'openai' ? 'openai_api_key' : 'deepseek_api_key';
    const activeAiConfigured = aiProvider === 'openai'
        ? credentialStatus?.openai_api_key_configured
        : credentialStatus?.deepseek_api_key_configured;
    const sttProvider = effectiveSttProvider(settings, runtimeConfig);
    const canChooseSttProvider = runtimeConfig.allowedSttProviders.length > 1;
    const showMaintainerSettings = runtimeConfig.showMaintainerSettings;
    const speakerDiarizationAvailable = sttProvider === 'azure_batch' || (sttProvider === 'local' && !!diarizationStatus?.available);
    const speakerDiarizationHint = sttProvider === 'azure_batch'
        ? (lang==='zh'?'云端转录支持可选说话人区分，效果取决于音频质量。':'Cloud transcription can optionally label speakers. Results depend on audio quality.')
        : diarizationStatus?.available
        ? (lang==='zh'?'使用 pyannote 为字幕段标记 SPEAKER。':'Use pyannote to label transcript segments.')
        : !diarizationStatus
            ? (lang==='zh'?'正在检测本机说话人区分依赖。':'Checking local speaker diarization dependency.')
            : !diarizationStatus.dependency_installed
                ? (lang==='zh'?'需要本机安装 pyannote.audio。':'Requires pyannote.audio installed locally.')
                : (lang==='zh'?'pyannote.audio 已安装，还需要配置 Hugging Face token。':'pyannote.audio is installed. Hugging Face token is still required.');
    const pyannoteTokenConfigured = !!(credentialStatus?.pyannote_auth_token_configured || diarizationStatus?.auth_configured);
    const showPyannoteTokenInput = !pyannoteTokenConfigured || pyannoteTokenEditing;
    const inputClass = "w-full bg-surface-container-lowest border ff-border-control rounded-sm px-3.5 py-2.5 text-sm text-on-surface focus:border-primary focus:ring-2 focus:ring-primary/15 transition-colors";
    const sectionClass = "bg-surface-container-lowest rounded-sm border ff-border-muted shadow-sm p-5 space-y-4";
    const fieldLabelClass = "text-[11px] font-bold uppercase tracking-wider text-on-surface-variant";

    const SectionTitle = ({icon, title, desc}) => (
        <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-sm bg-primary/10 text-primary flex items-center justify-center flex-shrink-0">
                <span className="material-symbols-outlined text-lg">{icon}</span>
            </div>
            <div className="min-w-0">
                <h3 className="font-headline font-bold text-base text-on-surface">{title}</h3>
                {desc && <p className="text-xs text-on-surface-variant leading-snug mt-0.5">{desc}</p>}
            </div>
        </div>
    );

    const ToggleRow = ({id, checked, onChange, label, hint, icon, disabled=false}) => (
        <label htmlFor={id} className={`flex items-start gap-3 p-3 rounded-sm bg-surface-container-low transition-colors ${disabled?'opacity-60 cursor-not-allowed':'hover:bg-surface-container cursor-pointer'}`}>
            <span className="material-symbols-outlined text-primary text-lg mt-0.5">{icon}</span>
            <span className="flex-1 min-w-0">
                <span className="block text-sm font-semibold text-on-surface">{label}</span>
                {hint && <span className="block text-[11px] text-on-surface-variant mt-0.5 leading-snug">{hint}</span>}
            </span>
            <input id={id} type="checkbox" checked={checked} disabled={disabled} onChange={onChange} className="w-4 h-4 mt-1 rounded border-outline-variant text-primary focus:ring-primary disabled:opacity-40"/>
        </label>
    );

    return (
             <div className="ml-64 min-h-screen relative pb-8">
                <main className="p-12 max-w-7xl mx-auto h-[calc(100vh-2rem)] overflow-y-auto hide-scrollbar">
            <div className="space-y-8">
                        <header className="max-w-3xl pt-2">
                    <div className="min-w-0 pt-2">
                    <h1 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface mb-2">{t('proc.title')}</h1>
                    <p className="text-on-surface-variant font-body max-w-2xl">{t('proc.subtitle')}</p>
                        </div>
                </header>

                {currentJob && (
                    <section className="bg-surface-container-lowest rounded-sm p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex items-center gap-3 min-w-0">
                            <div className="w-10 h-10 rounded-sm bg-primary-fixed flex items-center justify-center text-primary flex-shrink-0">
                                <span className="material-symbols-outlined">monitoring</span>
                            </div>
                            <div className="min-w-0">
                                <p className="text-sm font-bold text-on-surface truncate">{currentJob.fileName}</p>
                                <p className="text-xs text-on-surface-variant">{t('work.activeRunHint')}</p>
                            </div>
                        </div>
                        <Link to="/" className="inline-flex items-center justify-center gap-2 px-4 py-3 bg-primary text-white font-bold rounded-sm hover:bg-primary-container transition-colors text-sm flex-shrink-0">
                            <span className="material-symbols-outlined text-base">arrow_back</span>{t('work.viewProgress')}
                        </Link>
                    </section>
                )}

                    <section className="space-y-5">
                        <div className={sectionClass}>
                            <SectionTitle icon="mic_external_on" title={t('work.transcription')} desc={lang==='zh'?'选择转录路线；系统会自动识别中英文，英文会保留原文并生成中文参考。':'Choose the transcription route. FluentFlow detects Chinese or English automatically; English sources keep original text and get Chinese reference translations.'}/>
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                {canChooseSttProvider ? (
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.sttProvider')}</label>
                                        <select className={inputClass} value={sttProvider} onChange={e=>updateSettingNow({sttProvider:e.target.value})}>
                                            {runtimeConfig.allowedSttProviders.includes('azure_batch') && <option value="azure_batch">{t('set.providerAzureBatch')}</option>}
                                            {runtimeConfig.allowedSttProviders.includes('local') && <option value="local">{t('set.providerLocal')}</option>}
                                        </select>
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t('set.sttProvider')}</label>
                                        <div className={`${inputClass} flex items-center justify-between bg-surface-container-low`}>
                                            <span>{sttProvider === 'azure_batch' ? t('set.providerAzureBatch') : t('set.providerLocal')}</span>
                                            <span className="material-symbols-outlined text-base text-primary">lock</span>
                                        </div>
                                    </div>
                                )}
                                {sttProvider === 'local' && (
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.modelSel')}</label>
                                    <select className={inputClass} value={normalizeSttModel(settings.sttModel)} onChange={e=>updateSettingNow({sttModel:e.target.value})}>
                                        <option value="medium">{t('set.optMedium')}</option>
                                        <option value="large-v3">{t('set.optLarge')}</option>
                                    </select>
                                </div>
                                )}
                                {sttProvider === 'local' && (
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('set.sttSpeed')}</label>
                                    <select className={inputClass} value={settings.sttSpeed||"balanced"} onChange={e=>updateSettingNow({sttSpeed:e.target.value})}>
                                        <option value="fast">{t('set.speedFast')}</option>
                                        <option value="balanced">{t('set.speedBalanced')}</option>
                                        <option value="accurate">{t('set.speedAccurate')}</option>
                                    </select>
                                </div>
                                )}
                            </div>
                            {isAzureCloudProvider(sttProvider) && (
                                <div className="rounded-sm border ff-border-muted bg-surface-container-low p-3 flex items-start gap-3">
                                    <span className="material-symbols-outlined text-primary text-lg mt-0.5">cloud_done</span>
                                    <p className="text-xs text-on-surface-variant leading-relaxed">
                                        {lang==='zh'
                                            ? '云端转录由后台统一配置。你只需要上传文件，长任务会继续在后台运行。'
                                            : 'Cloud transcription is configured by the product owner. Upload a file and the long-running job will continue in the background.'}
                                    </p>
                                </div>
                            )}
                            <ToggleRow
                                id="workSpeakerDiarization"
                                checked={!!settings.speakerDiarization && speakerDiarizationAvailable}
                                onChange={e=>updateSettingNow({speakerDiarization:e.target.checked})}
                                label={lang==='zh'?'区分不同讲话人':'Speaker diarization'}
                                hint={speakerDiarizationHint}
                                icon="record_voice_over"
                                disabled={!speakerDiarizationAvailable}
                            />
                            {showMaintainerSettings && sttProvider === 'local' && (
                            <div className="space-y-2 rounded-sm border ff-border-muted bg-surface-container-low p-3">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="space-y-1">
                                        <label className={fieldLabelClass}>PYANNOTE AUTH TOKEN</label>
                                        <p className="text-[11px] text-on-surface-variant leading-relaxed">
                                            {pyannoteTokenConfigured
                                                ? (lang==='zh'?'已配置。token 不会显示在前端；需要更换时再重新输入。':'Configured. The token is not shown in the frontend; re-enter it only when replacing it.')
                                                : (lang==='zh'?'用于本机后端从 Hugging Face 获取 pyannote 讲话人区分模型。音频识别仍在本地执行，不会因为填写 token 上传到 Hugging Face。':'Used by the local backend to fetch the pyannote speaker diarization model from Hugging Face. Audio diarization still runs locally and is not uploaded to Hugging Face because of this token.')}
                                        </p>
                                    </div>
                                    {pyannoteTokenConfigured && !pyannoteTokenEditing && (
                                        <button type="button" onClick={()=>setPyannoteTokenEditing(true)} className="shrink-0 px-3 py-2 rounded-sm border ff-border-control text-xs font-bold text-on-surface hover:bg-surface-container-high">
                                            {lang==='zh'?'更换':'Replace'}
                                        </button>
                                    )}
                                </div>
                                {showPyannoteTokenInput && (
                                    <div className="space-y-2">
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={lang==='zh'?'粘贴 Hugging Face hf_... token':'Paste Hugging Face hf_... token'} type="password" value={secretDraft.pyannote_auth_token||""} onChange={e=>setSecretDraft(d=>({...d,pyannote_auth_token:e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft.pyannote_auth_token} onClick={()=>saveSecret('pyannote_auth_token')} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                            {pyannoteTokenConfigured && (
                                                <button type="button" onClick={()=>{setPyannoteTokenEditing(false); setSecretDraft(d=>({...d,pyannote_auth_token:''}));}} className="px-3 py-2.5 rounded-sm border ff-border-control text-sm font-bold text-on-surface hover:bg-surface-container-high">
                                                    {lang==='zh'?'取消':'Cancel'}
                                                </button>
                                            )}
                                        </div>
                                        <p className="text-[11px] text-on-surface-variant">
                                            {lang==='zh'?'token 只写入本机后端配置，不写入浏览器 localStorage。':'The token is stored only in the local backend config, not in browser localStorage.'}
                                        </p>
                                    </div>
                                )}
                                <SecretFeedback keyName="pyannote_auth_token" />
                            </div>
                            )}
                        </div>

                        <div className={sectionClass}>
                            <SectionTitle icon="psychology" title={t('work.summary')} desc={lang==='zh'?'控制是否生成笔记、默认模板和使用的摘要模型。':'Control note generation, default prompt, and summary model.'}/>
                            <div className="space-y-2">
                                <label className={fieldLabelClass}>{t('work.activePrompt')}</label>
                                <select className={inputClass} value={settings.promptPreset||DEFAULT_PROMPT_PRESET} onChange={e=>updateSettingNow({promptPreset:e.target.value})}>
                                    {allPresetSelectKeys(settings).map((key) => (
                                        <option key={key} value={key}>{presetDisplayLabel(key, settings, lang)}</option>
                                    ))}
                                </select>
                            </div>
                            <ToggleRow
                                id="workSkipSummary"
                                checked={settings.skipAiSummary||false}
                                onChange={e=>updateSettingNow({skipAiSummary:e.target.checked})}
                                label={t('set.skipSummary')}
                                hint={t('set.skipSummaryHint')}
                                icon="subject"
                            />
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t('work.summaryMode')}</label>
                                    <select className={inputClass} value={settings.noteMode||"auto"} onChange={e=>updateSettingNow({noteMode:e.target.value})}>
                                        {NOTE_MODE_OPTIONS.map((item) => (
                                            <option key={item.value} value={item.value}>{lang === 'zh' ? item.labelZh : item.labelEn}</option>
                                        ))}
                                    </select>
                                </div>
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
                            {showMaintainerSettings ? (
                            <div className="space-y-2">
                                <label className={fieldLabelClass}>{aiProvider==='openai'?t('set.openaiKey'):t('set.deepseekKey')}</label>
                                <div className="flex gap-2">
                                    <input className={inputClass} placeholder={secretStatusText(activeAiConfigured)} type="password" value={secretDraft[activeAiSecretKey]||""} onChange={e=>setSecretDraft(d=>({...d,[activeAiSecretKey]:e.target.value}))}/>
                                    <button type="button" disabled={secretSaving || !secretDraft[activeAiSecretKey]} onClick={()=>saveSecret(activeAiSecretKey)} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                </div>
                                <p className="text-[11px] text-on-surface-variant">{secretStatusText(activeAiConfigured)}。{lang==='zh'?'不会写入浏览器 localStorage。':'Not stored in browser localStorage.'}</p>
                            </div>
                            ) : (
                            <div className="rounded-sm border ff-border-muted bg-surface-container-low p-3 flex items-start gap-3">
                                <span className="material-symbols-outlined text-primary text-lg mt-0.5">admin_panel_settings</span>
                                <p className="text-xs text-on-surface-variant leading-relaxed">
                                    {lang==='zh'?'摘要模型由后台统一配置，普通用户不需要填写 API Key。':'The summary model is configured in the backend. Users do not need to enter API keys.'}
                                </p>
                            </div>
                            )}
                        </div>

                        <div className={sectionClass}>
                            <SectionTitle icon="cloud_upload" title={t('work.export')} desc={lang==='zh'?'只放与飞书导出直接相关的开关和连接信息。':'Only export-related switches and connection details live here.'}/>
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                                <ToggleRow
                                    id="workExportToLark"
                                    checked={settings.exportToLark||false}
                                    onChange={e=>updateSettingNow({exportToLark:e.target.checked})}
                                    label={t('set.autoExport')}
                                    icon="ios_share"
                                />
                                <ToggleRow
                                    id="workLarkViaCli"
                                    checked={settings.larkViaCli||false}
                                    onChange={e=>updateSettingNow({larkViaCli:e.target.checked})}
                                    label={t('set.larkViaCli')}
                                    hint={t('set.larkViaCliHint')}
                                    icon="terminal"
                                />
                            </div>
                            {showMaintainerSettings && !settings.larkViaCli && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>App ID</label>
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_id_configured)} value={secretDraft.lark_app_id||""} onChange={e=>setSecretDraft(d=>({...d,lark_app_id:e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft.lark_app_id} onClick={()=>saveSecret('lark_app_id')} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                        </div>
                                    </div>
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>App Secret</label>
                                        <div className="flex gap-2">
                                            <input className={inputClass} placeholder={secretStatusText(credentialStatus?.lark_app_secret_configured)} type="password" value={secretDraft.lark_app_secret||""} onChange={e=>setSecretDraft(d=>({...d,lark_app_secret:e.target.value}))}/>
                                            <button type="button" disabled={secretSaving || !secretDraft.lark_app_secret} onClick={()=>saveSecret('lark_app_secret')} className="px-4 py-2.5 rounded-sm bg-primary text-white text-sm font-bold disabled:opacity-40">{lang==='zh'?'保存':'Save'}</button>
                                        </div>
                                    </div>
                                </div>
                            )}
                            {!showMaintainerSettings && (
                                <div className="rounded-sm border ff-border-muted bg-surface-container-low p-3 flex items-start gap-3">
                                    <span className="material-symbols-outlined text-primary text-lg mt-0.5">{settings.larkViaCli ? 'terminal' : 'cloud_done'}</span>
                                    <p className="text-xs text-on-surface-variant leading-relaxed">
                                        {settings.larkViaCli
                                            ? (lang==='zh'?'将使用后端进程可调用的本机 lark-cli 和当前登录身份导出。':'Export will use the local lark-cli available to the backend process.')
                                            : (lang==='zh'?'将使用后台统一配置的飞书 OpenAPI 凭证导出。':'Export will use the backend-configured Lark OpenAPI credentials.')}
                                    </p>
                                </div>
                            )}
                        </div>
                    </section>
                </div>
        </main>
    </div>
    );
};

const GuestEditorPreview = ({lang}) => {
    const content = lang === 'zh'
        ? {
            eyebrow: '样例预览',
            title: '处理完成后，编辑器会这样呈现结果',
            subtitle: '左侧保留可校对的逐字稿，右侧生成可直接使用的结构化笔记。',
            source: '产品访谈录音片段',
            transcriptLabel: '转录原文',
            noteLabel: 'AI 笔记',
            cta: '上传音视频生成自己的结果',
            hint: '示例内容不会占用访客试用额度。',
            segments: [
                {time: '00:00', speaker: 'Speaker 1', text: '今天这段访谈主要聊的是，用户为什么会在看完课程后没有形成可复用的笔记。'},
                {time: '00:18', speaker: 'Speaker 2', text: '他们不是没有记录，而是记录太散，回看时找不到结构，也很难继续编辑。'},
                {time: '00:43', speaker: 'Speaker 1', text: '所以产品要把转录、重点提炼和后续编辑放在同一个工作流里。'},
                {time: '01:12', speaker: 'Speaker 2', text: '最有价值的不是单纯生成摘要，而是保留可以校对的原文依据。'},
            ],
            noteTitle: '试听材料笔记',
            overviewTitle: '核心观点',
            overview: '这段访谈讨论了从音视频到可复用笔记的完整工作流：先得到可核对的转录，再用 AI 提炼结构，最后允许用户继续编辑和下载。',
            bulletsTitle: '整理结果',
            bullets: [
                '问题：原始记录分散，用户回看成本高。',
                '机会：把转录、摘要、编辑整合在同一界面，减少来回切换。',
                '产品判断：笔记不能只给结论，还要保留可追溯的原文依据。',
            ],
            quoteTitle: '可引用片段',
            quote: '“最有价值的不是单纯生成摘要，而是保留可以校对的原文依据。”',
        }
        : {
            eyebrow: 'Sample preview',
            title: 'After processing, results will appear like this',
            subtitle: 'The transcript stays editable on the left, while the AI note is ready to use on the right.',
            source: 'Product interview excerpt',
            transcriptLabel: 'Transcript',
            noteLabel: 'AI note',
            cta: 'Upload media to create your result',
            hint: 'This sample does not use your guest trial.',
            segments: [
                {time: '00:00', speaker: 'Speaker 1', text: 'This interview is about why users fail to turn course videos into reusable notes.'},
                {time: '00:18', speaker: 'Speaker 2', text: 'They do take notes, but the notes are scattered and hard to revisit or edit later.'},
                {time: '00:43', speaker: 'Speaker 1', text: 'The product should keep transcription, insight extraction, and editing in one workflow.'},
                {time: '01:12', speaker: 'Speaker 2', text: 'The real value is not just summary generation, but keeping the source text available for review.'},
            ],
            noteTitle: 'Demo Material Note',
            overviewTitle: 'Core Idea',
            overview: 'The conversation describes a workflow that turns media into reusable notes: first a reviewable transcript, then AI structure, then editing and download.',
            bulletsTitle: 'Generated Structure',
            bullets: [
                'Problem: raw notes are scattered and expensive to revisit.',
                'Opportunity: combine transcription, summary, and editing in one place.',
                'Product decision: notes should preserve source evidence instead of only showing conclusions.',
            ],
            quoteTitle: 'Reusable Quote',
            quote: '"The real value is not just summary generation, but keeping the source text available for review."',
        };

    return (
        <div className="ml-64 min-h-screen bg-[#F5F8FC] p-8 xl:p-10">
            <main className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-7xl flex-col justify-center">
                <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div className="max-w-3xl">
                        <div className="mb-3 inline-flex items-center gap-2 rounded-sm border border-primary/15 bg-primary/5 px-3 py-1 text-xs font-bold text-primary">
                            <span className="material-symbols-outlined text-base">visibility</span>
                            {content.eyebrow}
                        </div>
                        <h1 className="font-headline text-3xl font-bold leading-tight text-on-surface">{content.title}</h1>
                        <p className="mt-3 text-sm leading-6 text-on-surface-variant">{content.subtitle}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                        <span className="text-xs font-medium text-slate-500">{content.hint}</span>
                        <Link to="/" className="inline-flex items-center gap-2 rounded-sm bg-primary px-5 py-3 text-sm font-bold text-white shadow-lg shadow-primary/20 transition hover:bg-primary-container">
                            <span className="material-symbols-outlined text-xl">upload_file</span>
                            {content.cta}
                        </Link>
                    </div>
                </div>

                <div className="grid gap-5 xl:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.82fr)]">
                    <section className="min-w-0 overflow-hidden rounded-sm border border-slate-200 bg-white shadow-sm">
                        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                            <div>
                                <p className="text-xs font-bold uppercase tracking-wide text-slate-400">{content.source}</p>
                                <h2 className="mt-1 text-base font-bold text-on-surface">{content.transcriptLabel}</h2>
                            </div>
                            <span className="material-symbols-outlined text-slate-300">graphic_eq</span>
                        </div>
                        <div className="max-h-[560px] space-y-3 overflow-y-auto p-5">
                            {content.segments.map((segment, index) => (
                                <div key={index} className="grid grid-cols-[72px_minmax(0,1fr)] gap-4 rounded-sm border border-slate-100 bg-slate-50/60 p-4">
                                    <div className="text-xs font-bold text-primary">{segment.time}</div>
                                    <div className="min-w-0">
                                        <div className="mb-1 text-xs font-bold text-slate-500">{segment.speaker}</div>
                                        <p className="text-sm leading-7 text-slate-700">{segment.text}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </section>

                    <section className="min-w-0 overflow-hidden rounded-sm border border-slate-200 bg-white shadow-sm">
                        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                            <div>
                                <p className="text-xs font-bold uppercase tracking-wide text-slate-400">{content.noteLabel}</p>
                                <h2 className="mt-1 text-base font-bold text-on-surface">{content.noteTitle}</h2>
                            </div>
                            <span className="material-symbols-outlined text-slate-300">auto_awesome</span>
                        </div>
                        <div className="space-y-6 p-6">
                            <div>
                                <h3 className="mb-2 text-sm font-bold text-on-surface">{content.overviewTitle}</h3>
                                <p className="text-sm leading-7 text-slate-700">{content.overview}</p>
                            </div>
                            <div>
                                <h3 className="mb-3 text-sm font-bold text-on-surface">{content.bulletsTitle}</h3>
                                <ul className="space-y-3">
                                    {content.bullets.map((item, index) => (
                                        <li key={index} className="flex gap-3 text-sm leading-6 text-slate-700">
                                            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary"></span>
                                            <span>{item}</span>
                                        </li>
                                    ))}
                                </ul>
                            </div>
                            <div className="border-l-2 border-primary/40 bg-primary/5 px-4 py-3">
                                <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-primary">{content.quoteTitle}</h3>
                                <p className="text-sm leading-7 text-slate-700">{content.quote}</p>
                            </div>
                        </div>
                    </section>
                </div>
            </main>
        </div>
    );
};

/* ═══════════════ Editor ═══════════════ */

export default Processing;
