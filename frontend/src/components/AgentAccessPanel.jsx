import {useEffect, useMemo, useState} from 'react';
import {ClipboardCopy, ExternalLink, KeyRound, Rocket, Terminal, Trash2} from 'lucide-react';
import {API_BASE, apiErrorMessage, apiFetch, useI18n} from '../app/shared.jsx';

const copyText = async (text, onDone) => {
    try {
        await navigator.clipboard?.writeText(text);
        onDone(true);
        window.setTimeout(() => onDone(false), 1400);
    } catch (_) {
        onDone(false);
    }
};

const CodeBlock = ({label, value, copied, onCopy}) => (
    <div className="rounded-[14px] border border-[#e5e5e5] bg-[#faf9f9] p-3 dark:border-white/[0.12] dark:bg-white/[0.05]">
        <div className="mb-2 flex items-center justify-between gap-3">
            <span className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-[#85868c] dark:text-white/50">{label}</span>
            <button
                type="button"
                onClick={() => onCopy(value)}
                className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-[10px] border border-[#dedada] px-2.5 text-[12px] font-extrabold text-[#111111] transition hover:bg-[#efeeee] active:translate-y-px dark:border-white/[0.14] dark:text-white dark:hover:bg-white/[0.08]"
            >
                <ClipboardCopy className="size-3.5" strokeWidth={2.1}/>
                {copied ? '已复制' : '复制'}
            </button>
        </div>
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-5 text-[#111111] dark:text-white">{value}</pre>
    </div>
);

const StepCard = ({number, icon: Icon, title, body}) => (
    <div className="relative rounded-[18px] border border-[#e5e5e5] bg-white p-5 shadow-[0_1px_2px_rgba(17,17,17,0.03)] dark:border-white/[0.12] dark:bg-white/[0.05]">
        <span className="absolute right-5 top-4 text-[24px] font-extrabold leading-none text-[#c5cde0] dark:text-white/20">{number}</span>
        <Icon className="mb-5 size-8 text-[#2f63e5]" strokeWidth={2.1}/>
        <h3 className="pr-8 text-[19px] font-extrabold leading-6 text-[#111111] dark:text-white">{title}</h3>
        <p className="mt-3 text-[14px] font-semibold leading-6 text-[#686a70] dark:text-white/60">{body}</p>
    </div>
);

const AgentAccessPanel = ({compact = false, onClose = null}) => {
    const {lang} = useI18n();
    const [copiedKey, setCopiedKey] = useState('');
    const [apiKeys, setApiKeys] = useState([]);
    const [keyName, setKeyName] = useState('Codex');
    const [createdKey, setCreatedKey] = useState('');
    const [loadingKeys, setLoadingKeys] = useState(true);
    const [savingKey, setSavingKey] = useState(false);
    const [errorMessage, setErrorMessage] = useState('');
    const isZh = lang === 'zh';
    const apiBaseLabel = API_BASE || (typeof window !== 'undefined' ? window.location.origin : 'http://127.0.0.1:8000');
    const accessTokenForConfig = createdKey || '<your-fluentflow-api-key>';
    const mcpConfig = useMemo(() => JSON.stringify({
        mcpServers: {
            fluentflow: {
                command: 'python3',
                args: ['<path-to-fluentflow>/scripts/fluentflow_mcp_server.py'],
                env: {
                    FLUENTFLOW_API_BASE: apiBaseLabel || 'http://127.0.0.1:8000',
                    FLUENTFLOW_CLIENT_ID: 'local-client',
                    FLUENTFLOW_ACCESS_TOKEN: accessTokenForConfig,
                },
            },
        },
    }, null, 2), [accessTokenForConfig, apiBaseLabel]);
    const claudeCommand = `claude mcp add fluentflow -e FLUENTFLOW_API_BASE=${apiBaseLabel || 'http://127.0.0.1:8000'} -e FLUENTFLOW_CLIENT_ID=local-client -e FLUENTFLOW_ACCESS_TOKEN=${accessTokenForConfig} -- python3 "$(pwd)/scripts/fluentflow_mcp_server.py"`;
    const codexCommand = `codex mcp add fluentflow --env FLUENTFLOW_API_BASE=${apiBaseLabel || 'http://127.0.0.1:8000'} --env FLUENTFLOW_CLIENT_ID=local-client --env FLUENTFLOW_ACCESS_TOKEN=${accessTokenForConfig} -- python3 "$(pwd)/scripts/fluentflow_mcp_server.py"`;
    const promptExample = isZh
        ? '请用 fluentflow MCP 帮我把这个视频做成笔记：https://youtu.be/...'
        : 'Use the fluentflow MCP to turn this video into notes: https://youtu.be/...';
    const testCommand = 'npm run mcp:check:e2e';

    const handleCopy = (key, value) => copyText(value, (ok) => setCopiedKey(ok ? key : ''));
    const loadApiKeys = async () => {
        setLoadingKeys(true);
        setErrorMessage('');
        try {
            const response = await apiFetch(`${API_BASE}/account/api-keys`);
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(apiErrorMessage(payload, isZh ? '读取 API Key 失败' : 'Failed to load API keys'));
            setApiKeys(Array.isArray(payload.api_keys) ? payload.api_keys : []);
        } catch (error) {
            setErrorMessage(error?.message || (isZh ? '读取 API Key 失败' : 'Failed to load API keys'));
        } finally {
            setLoadingKeys(false);
        }
    };
    const handleCreateKey = async () => {
        setSavingKey(true);
        setCreatedKey('');
        setErrorMessage('');
        try {
            const response = await apiFetch(`${API_BASE}/account/api-keys`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({name: keyName || 'Agent API Key'}),
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(apiErrorMessage(payload, isZh ? '新建 API Key 失败' : 'Failed to create API key'));
            const secret = payload.one_time_key || payload.api_key?.key || '';
            setCreatedKey(secret);
            if (payload.api_key) {
                const {key: _secret, ...publicKey} = payload.api_key;
                setApiKeys((current) => [publicKey, ...current.filter((item) => item.id !== publicKey.id)]);
            } else {
                await loadApiKeys();
            }
        } catch (error) {
            setErrorMessage(error?.message || (isZh ? '新建 API Key 失败' : 'Failed to create API key'));
        } finally {
            setSavingKey(false);
        }
    };
    const handleRevokeKey = async (keyId) => {
        if (!keyId) return;
        setErrorMessage('');
        try {
            const response = await apiFetch(`${API_BASE}/account/api-keys/${encodeURIComponent(keyId)}/revoke`, {method: 'POST'});
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(apiErrorMessage(payload, isZh ? '撤销 API Key 失败' : 'Failed to revoke API key'));
            setApiKeys((current) => current.map((item) => (item.id === keyId ? payload.api_key : item)).filter(Boolean));
        } catch (error) {
            setErrorMessage(error?.message || (isZh ? '撤销 API Key 失败' : 'Failed to revoke API key'));
        }
    };

    useEffect(() => {
        loadApiKeys();
    }, []);

    return (
        <section className={compact ? 'flex min-h-0 flex-1 flex-col' : 'mx-auto w-full max-w-6xl px-6 py-8 lg:px-10'}>
            <header className={`${compact ? 'border-b border-[#e5e5e5] px-5 py-4 dark:border-white/[0.12]' : 'mb-6'} flex items-start justify-between gap-4`}>
                <div className="min-w-0">
                    <p className="text-[11px] font-extrabold uppercase tracking-[0.08em] text-[#85868c] dark:text-white/50">FluentFlow MCP</p>
                    <h1 id={compact ? 'agent-access-title' : undefined} className={`${compact ? 'text-[18px] leading-6' : 'text-[28px] leading-8'} mt-1 font-extrabold text-[#111111] dark:text-white`}>
                        {isZh ? '把 FluentFlow 接入你的 AI 工具' : 'Connect FluentFlow to your AI tools'}
                    </h1>
                    <p className="mt-2 max-w-[68ch] text-[14px] font-semibold leading-6 text-[#686a70] dark:text-white/60">
                        {isZh
                            ? '接入后，你可以在 Claude Code 或 Codex 里直接发视频链接，让 FluentFlow 转录、生成笔记并返回任务包。'
                            : 'After setup, Claude Code or Codex can send video links to FluentFlow, wait for transcription, generate notes, and read the task package.'}
                    </p>
                </div>
                {onClose && (
                    <button
                        type="button"
                        onClick={onClose}
                        className="h-9 shrink-0 rounded-[12px] border border-[#dedada] px-3 text-[13px] font-extrabold text-[#111111] transition hover:bg-[#efeeee] active:translate-y-px dark:border-white/[0.14] dark:text-white dark:hover:bg-white/[0.08]"
                    >
                        {isZh ? '关闭' : 'Close'}
                    </button>
                )}
            </header>

            <div className={compact ? 'min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-4' : ''}>
                <div className="grid gap-4 md:grid-cols-3">
                    <StepCard
                        number="1"
                        icon={KeyRound}
                        title={isZh ? '新建一把 API Key' : 'Create an API key'}
                        body={isZh ? '云端和本地都使用同一种 Key。明文只显示一次，创建后先复制保存到你的 AI 工具配置里。' : 'Cloud and local setups use the same key. The secret is shown once, so copy it into your AI tool config after creation.'}
                    />
                    <StepCard
                        number="2"
                        icon={ClipboardCopy}
                        title={isZh ? '粘贴到你的 AI 工具' : 'Paste into your AI tool'}
                        body={isZh ? '把配置加到 Claude Code 或 Codex。它们会看到 fluentflow 的 submit、wait、package、diagnose 等工具。' : 'Add the config to Claude Code or Codex. They will see FluentFlow tools such as submit, wait, package, and diagnose.'}
                    />
                    <StepCard
                        number="3"
                        icon={Rocket}
                        title={isZh ? '发链接，自动出笔记' : 'Send a link, get notes'}
                        body={isZh ? '对 AI 说“帮我把这个视频做成笔记”，贴上链接即可。AI 会调用 FluentFlow，而不是让你手动操作页面。' : 'Ask the AI to turn a video into notes and paste the link. The AI calls FluentFlow directly instead of asking you to operate the UI.'}
                    />
                </div>

                <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1fr)]">
                    <div className="rounded-[14px] border border-[#e5e5e5] bg-white p-4 dark:border-white/[0.12] dark:bg-white/[0.05]">
                        <div className="mb-3 flex items-center gap-2 text-[14px] font-extrabold text-[#111111] dark:text-white">
                            <KeyRound className="size-4 text-[#2f63e5]" strokeWidth={2.1}/>
                            {isZh ? 'API Key' : 'API keys'}
                        </div>
                        <div className="flex flex-col gap-2 sm:flex-row">
                            <input
                                value={keyName}
                                onChange={(event) => setKeyName(event.target.value)}
                                className="h-10 min-w-0 flex-1 rounded-[10px] border border-[#dedada] bg-white px-3 text-[14px] font-semibold text-[#111111] outline-none transition focus:border-[#2f63e5] dark:border-white/[0.14] dark:bg-white/[0.06] dark:text-white"
                                placeholder={isZh ? '例如 Codex' : 'For example Codex'}
                            />
                            <button
                                type="button"
                                onClick={handleCreateKey}
                                disabled={savingKey}
                                className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-[10px] bg-[#111111] px-4 text-[13px] font-extrabold text-white transition hover:bg-[#2a2a2a] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-[#111111] dark:hover:bg-white/90"
                            >
                                <KeyRound className="size-4" strokeWidth={2.1}/>
                                {savingKey ? (isZh ? '创建中' : 'Creating') : (isZh ? '新建 Key' : 'Create key')}
                            </button>
                        </div>
                        {errorMessage && (
                            <p className="mt-3 rounded-[10px] border border-[#ffd1d1] bg-[#fff4f4] px-3 py-2 text-[13px] font-semibold leading-5 text-[#a12828] dark:border-red-400/30 dark:bg-red-400/10 dark:text-red-100">{errorMessage}</p>
                        )}
                        {createdKey && (
                            <div className="mt-3">
                                <CodeBlock label={isZh ? '只显示一次的 API Key' : 'One-time API key'} value={createdKey} copied={copiedKey === 'created-key'} onCopy={(value) => handleCopy('created-key', value)}/>
                            </div>
                        )}
                    </div>
                    <div className="rounded-[14px] border border-[#e5e5e5] bg-white p-4 dark:border-white/[0.12] dark:bg-white/[0.05]">
                        <div className="mb-3 text-[14px] font-extrabold text-[#111111] dark:text-white">{isZh ? '已创建的 Key' : 'Created keys'}</div>
                        <div className="space-y-2">
                            {loadingKeys && <p className="text-[13px] font-semibold text-[#686a70] dark:text-white/60">{isZh ? '读取中...' : 'Loading...'}</p>}
                            {!loadingKeys && apiKeys.length === 0 && <p className="text-[13px] font-semibold text-[#686a70] dark:text-white/60">{isZh ? '还没有 API Key。' : 'No API keys yet.'}</p>}
                            {apiKeys.map((item) => (
                                <div key={item.id} className="flex items-center justify-between gap-3 rounded-[10px] border border-[#eceaea] px-3 py-2 dark:border-white/[0.1]">
                                    <div className="min-w-0">
                                        <div className="truncate text-[13px] font-extrabold text-[#111111] dark:text-white">{item.name || 'Agent API Key'}</div>
                                        <div className="mt-0.5 text-[12px] font-semibold text-[#85868c] dark:text-white/45">
                                            {item.key_prefix}{item.revoked_at ? (isZh ? ' · 已撤销' : ' · revoked') : ''}
                                        </div>
                                    </div>
                                    {!item.revoked_at && (
                                        <button
                                            type="button"
                                            onClick={() => handleRevokeKey(item.id)}
                                            className="inline-flex size-8 shrink-0 items-center justify-center rounded-[9px] border border-[#dedada] text-[#686a70] transition hover:bg-[#efeeee] active:translate-y-px dark:border-white/[0.14] dark:text-white/70 dark:hover:bg-white/[0.08]"
                                            aria-label={isZh ? '撤销 API Key' : 'Revoke API key'}
                                            title={isZh ? '撤销 API Key' : 'Revoke API key'}
                                        >
                                            <Trash2 className="size-4" strokeWidth={2.1}/>
                                        </button>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.72fr)]">
                    <CodeBlock label={isZh ? 'MCP 配置' : 'MCP config'} value={mcpConfig} copied={copiedKey === 'config'} onCopy={(value) => handleCopy('config', value)}/>
                    <div className="space-y-4">
                        <CodeBlock label="Claude Code" value={claudeCommand} copied={copiedKey === 'claude'} onCopy={(value) => handleCopy('claude', value)}/>
                        <CodeBlock label="Codex" value={codexCommand} copied={copiedKey === 'codex'} onCopy={(value) => handleCopy('codex', value)}/>
                    </div>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1fr)]">
                    <div className="rounded-[14px] border border-[#e5e5e5] bg-white p-4 dark:border-white/[0.12] dark:bg-white/[0.05]">
                        <div className="mb-3 flex items-center gap-2 text-[14px] font-extrabold text-[#111111] dark:text-white">
                            <Terminal className="size-4 text-[#2f63e5]" strokeWidth={2.1}/>
                            {isZh ? '验证命令' : 'Check command'}
                        </div>
                        <CodeBlock label={isZh ? '端到端检查' : 'End-to-end check'} value={testCommand} copied={copiedKey === 'check'} onCopy={(value) => handleCopy('check', value)}/>
                    </div>
                    <div className="rounded-[14px] border border-[#e5e5e5] bg-white p-4 dark:border-white/[0.12] dark:bg-white/[0.05]">
                        <div className="mb-3 flex items-center gap-2 text-[14px] font-extrabold text-[#111111] dark:text-white">
                            <ExternalLink className="size-4 text-[#2f63e5]" strokeWidth={2.1}/>
                            {isZh ? '发给 AI 的一句话' : 'Prompt to send'}
                        </div>
                        <CodeBlock label={isZh ? '示例' : 'Example'} value={promptExample} copied={copiedKey === 'prompt'} onCopy={(value) => handleCopy('prompt', value)}/>
                    </div>
                </div>
            </div>
        </section>
    );
};

export default AgentAccessPanel;
