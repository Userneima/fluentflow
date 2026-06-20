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
    fmtDateTime,
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

const Admin = () => {
    const {lang} = useI18n();
    const {user} = useAuth();
    const {getAdminUsers, adjustUserBalance} = useApi();
    const [users, setUsers] = useState([]);
    const [selectedId, setSelectedId] = useState('');
    const [query, setQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [notice, setNotice] = useState('');
    const [units, setUnits] = useState('');
    const [reason, setReason] = useState('');
    const [providerReference, setProviderReference] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const isAdmin = user?.role === 'admin';
    const loadUsers = async (preferredId='') => {
        if (!isAdmin) return;
        setLoading(true);
        setError('');
        try {
            const nextUsers = await getAdminUsers(200);
            setUsers(nextUsers);
            const preferred = preferredId || selectedId;
            const nextSelected = nextUsers.find((item) => item.id === preferred)?.id || nextUsers[0]?.id || '';
            setSelectedId(nextSelected);
        } catch(err) {
            setError(err.message || (lang === 'zh' ? '无法读取用户列表。' : 'Could not load users.'));
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (isAdmin) loadUsers();
    }, [isAdmin]);

    const filteredUsers = users.filter((item) => {
        const q = query.trim().toLowerCase();
        if (!q) return true;
        return String(item.email || '').toLowerCase().includes(q) || String(item.id || '').toLowerCase().includes(q);
    });
    const selectedUser = users.find((item) => item.id === selectedId) || filteredUsers[0] || null;
    const transactions = selectedUser?.quota?.recent_transactions || [];
    const selectedBalance = selectedUser?.quota?.balance_units ?? 0;
    const selectedQuotaExempt = selectedUser?.role === 'admin' || selectedUser?.quota?.unlimited || selectedUser?.quota?.quota_exempt;

    const submitAdjustment = async (e) => {
        e.preventDefault();
        if (!selectedUser) return;
        const parsedUnits = Number.parseInt(units, 10);
        if (!Number.isInteger(parsedUnits) || parsedUnits === 0) {
            setError(lang === 'zh' ? '额度变化必须是非 0 整数。' : 'Unit adjustment must be a non-zero integer.');
            return;
        }
        if (!reason.trim()) {
            setError(lang === 'zh' ? '必须填写调整原因。' : 'Reason is required.');
            return;
        }
        setSubmitting(true);
        setError('');
        setNotice('');
        try {
            const data = await adjustUserBalance(selectedUser.id, {
                units: parsedUnits,
                reason: reason.trim(),
                provider_reference: providerReference.trim(),
            });
            const updatedUser = data.user || null;
            if (updatedUser?.id) {
                setUsers((prev) => prev.map((item) => item.id === updatedUser.id ? updatedUser : item));
                setSelectedId(updatedUser.id);
            } else {
                await loadUsers(selectedUser.id);
            }
            setUnits('');
            setReason('');
            setProviderReference('');
            setNotice(lang === 'zh' ? '额度已更新。' : 'Balance updated.');
        } catch(err) {
            setError(err.message || (lang === 'zh' ? '额度调整失败。' : 'Adjustment failed.'));
        } finally {
            setSubmitting(false);
        }
    };

    if (!isAdmin) {
        return (
            <div className="ml-64 min-h-screen bg-surface px-8 py-10">
                <main className="mx-auto flex min-h-[70vh] max-w-3xl items-center justify-center">
                    <section className="w-full rounded-sm bg-surface-container-lowest p-8 shadow-sm ring-1 ring-outline-variant/30">
                        <div className="flex items-start gap-4">
                            <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-sm bg-red-50 text-red-600">
                                <span className="material-symbols-outlined">lock</span>
                            </div>
                            <div>
                                <h1 className="text-xl font-bold tracking-tight text-on-surface font-headline">
                                    {lang === 'zh' ? '没有管理员权限' : 'Admin access required'}
                                </h1>
                                <p className="mt-2 text-sm leading-relaxed text-on-surface-variant">
                                    {lang === 'zh'
                                        ? '这个页面只用于维护账号额度和余额流水。普通用户不能访问。'
                                        : 'This page is only for maintaining account balances and ledger entries.'}
                                </p>
                            </div>
                        </div>
                    </section>
                </main>
            </div>
        );
    }

    return (
        <div className="ml-64 min-h-screen overflow-x-hidden bg-surface">
            <main className="mx-auto w-full max-w-[1500px] px-6 py-8 lg:px-8">
                <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                    <div className="min-w-0">
                        <p className="text-xs font-bold uppercase tracking-wider text-primary">Admin</p>
                        <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-on-surface font-headline">
                            {lang === 'zh' ? '用户额度维护' : 'User balance maintenance'}
                        </h1>
                        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-on-surface-variant">
                            {lang === 'zh'
                                ? '查余额、看流水、按原因手动增减处理额度。'
                                : 'Inspect balances, review ledger entries, and adjust processing units with a reason.'}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={()=>loadUsers(selectedUser?.id || '')}
                        disabled={loading}
                        className="inline-flex h-10 shrink-0 items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-bold text-white transition hover:bg-primary/90 active:translate-y-px disabled:opacity-50"
                    >
                        <span className={`material-symbols-outlined text-[18px] ${loading ? 'animate-spin' : ''}`}>sync</span>
                        {lang === 'zh' ? '刷新' : 'Refresh'}
                    </button>
                </header>

                {(error || notice) && (
                    <div className={`mb-5 rounded-sm border px-4 py-3 text-sm font-semibold ${error ? 'border-red-500/20 bg-red-500/10 text-red-600' : 'border-green-500/20 bg-green-500/10 text-green-700 dark:text-green-300'}`}>
                        {error || notice}
                    </div>
                )}

                <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
                    <section className="min-w-0 overflow-hidden rounded-sm bg-surface-container-lowest shadow-sm ring-1 ring-outline-variant/25">
                        <div className="border-b ff-border-muted p-4">
                            <div className="flex items-center justify-between gap-3">
                                <h2 className="text-sm font-bold text-on-surface font-headline">
                                    {lang === 'zh' ? '账号列表' : 'Accounts'}
                                </h2>
                                <span className="text-xs font-semibold tabular-nums text-on-surface-variant">{filteredUsers.length}</span>
                            </div>
                            <label className="mt-3 flex h-10 items-center gap-2 rounded-sm border border-outline-variant/40 bg-surface-container-low px-3 focus-within:border-primary/60">
                                <span className="material-symbols-outlined text-[18px] text-outline">search</span>
                                <input
                                    value={query}
                                    onChange={(e)=>setQuery(e.target.value)}
                                    className="h-full min-w-0 flex-1 bg-transparent text-sm font-medium text-on-surface outline-none placeholder:text-outline"
                                    placeholder={lang === 'zh' ? '搜索邮箱或用户 ID' : 'Search email or user ID'}
                                />
                            </label>
                        </div>
                        <div className="max-h-[calc(100vh-265px)] overflow-y-auto hide-scrollbar">
                            {loading && users.length === 0 ? (
                                <div className="space-y-3 p-4">
                                    {[0,1,2].map((item) => <div key={item} className="h-16 animate-pulse rounded-sm bg-surface-container-low"/>)}
                                </div>
                            ) : filteredUsers.length === 0 ? (
                                <div className="p-6 text-sm font-medium text-on-surface-variant">
                                    {lang === 'zh' ? '没有匹配的用户。' : 'No matching users.'}
                                </div>
                            ) : (
                                <div className="divide-y divide-outline-variant/30">
                                    {filteredUsers.map((item) => {
                                        const active = item.id === selectedUser?.id;
                                        const balance = item.quota?.balance_units ?? 0;
                                        const quotaExempt = item.role === 'admin' || item.quota?.unlimited || item.quota?.quota_exempt;
                                        return (
                                            <button
                                                key={item.id}
                                                type="button"
                                                onClick={()=>setSelectedId(item.id)}
                                                className={`w-full px-4 py-3 text-left transition active:translate-y-px ${active ? 'bg-primary/10' : 'hover:bg-surface-container-low'}`}
                                            >
                                                <div className="flex items-start justify-between gap-3">
                                                    <div className="min-w-0">
                                                        <p className="truncate text-sm font-bold text-on-surface" title={item.email || ''}>{item.email}</p>
                                                        <p className="mt-1 text-[11px] font-semibold uppercase tracking-wider text-on-surface-variant">
                                                            {item.role || 'user'} · {item.status || 'active'}
                                                        </p>
                                                    </div>
                                                    <span className={`rounded-sm px-2 py-1 text-xs font-extrabold ${quotaExempt ? 'bg-primary/10 text-primary' : `tabular-nums ${balance < 0 ? 'bg-red-500/10 text-red-600' : 'bg-surface-container text-on-surface-variant'}`}`}>
                                                        {quotaExempt ? (lang === 'zh' ? '无限' : 'Unlimited') : balance}
                                                    </span>
                                                </div>
                                                <p className="mt-2 text-[11px] font-medium text-on-surface-variant">
                                                    {lang === 'zh' ? '最近登录' : 'Last login'} {fmtDateTime(item.last_login_at, lang)}
                                                </p>
                                            </button>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </section>

                    <section className="min-w-0 space-y-5">
                        {selectedUser ? (
                            <>
                                <div className="grid min-w-0 gap-5 2xl:grid-cols-[minmax(0,1fr)_320px]">
                                    <div className="min-w-0 rounded-sm bg-surface-container-lowest p-5 shadow-sm ring-1 ring-outline-variant/25">
                                        <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_160px]">
                                            <div className="min-w-0">
                                                <h2 className="truncate text-xl font-bold tracking-tight text-on-surface font-headline" title={selectedUser.email || ''}>
                                                    {selectedUser.email}
                                                </h2>
                                                <p className="mt-2 break-all text-xs font-medium text-on-surface-variant">{selectedUser.id}</p>
                                                <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold">
                                                    <span className="rounded-sm bg-surface-container-low px-2.5 py-1 text-on-surface-variant">{selectedUser.role || 'user'}</span>
                                                    <span className="rounded-sm bg-surface-container-low px-2.5 py-1 text-on-surface-variant">{selectedUser.status || 'active'}</span>
                                                    <span className="rounded-sm bg-surface-container-low px-2.5 py-1 text-on-surface-variant">
                                                        {lang === 'zh' ? '创建' : 'Created'} {fmtDateTime(selectedUser.created_at, lang)}
                                                    </span>
                                                </div>
                                            </div>
                                            <div className="rounded-sm bg-primary/10 px-4 py-3">
                                                <p className="text-[11px] font-bold uppercase tracking-wider text-primary">
                                                    {selectedQuotaExempt ? (lang === 'zh' ? '额度豁免' : 'Quota exempt') : (lang === 'zh' ? '当前额度' : 'Balance')}
                                                </p>
                                                <p className={`mt-1 text-3xl font-extrabold leading-none text-primary ${selectedQuotaExempt ? '' : 'tabular-nums'}`}>
                                                    {selectedQuotaExempt ? (lang === 'zh' ? '无限' : 'Unlimited') : selectedBalance}
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    <form onSubmit={submitAdjustment} className="min-w-0 rounded-sm bg-surface-container-lowest p-5 shadow-sm ring-1 ring-outline-variant/25">
                                        <h2 className="text-sm font-bold text-on-surface font-headline">
                                            {lang === 'zh' ? '手动调整额度' : 'Manual adjustment'}
                                        </h2>
                                        <div className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
                                            <label className="block space-y-1.5">
                                                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                                    {lang === 'zh' ? '额度变化' : 'Unit delta'}
                                                </span>
                                                <input
                                                    type="number"
                                                    step="1"
                                                    value={units}
                                                    onChange={(e)=>setUnits(e.target.value)}
                                                    className="h-10 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-3 text-sm font-bold tabular-nums text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                                    placeholder={lang === 'zh' ? '例如 100' : 'e.g. 100'}
                                                />
                                            </label>
                                            <label className="block space-y-1.5">
                                                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                                    {lang === 'zh' ? '原因' : 'Reason'}
                                                </span>
                                                <input
                                                    type="text"
                                                    value={reason}
                                                    onChange={(e)=>setReason(e.target.value)}
                                                    className="h-10 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-3 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                                    placeholder={lang === 'zh' ? '微信手动充值' : 'Manual recharge'}
                                                />
                                            </label>
                                            <label className="block space-y-1.5 sm:col-span-2 2xl:col-span-1">
                                                <span className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                                    {lang === 'zh' ? '凭证备注' : 'Reference'}
                                                </span>
                                                <input
                                                    type="text"
                                                    value={providerReference}
                                                    onChange={(e)=>setProviderReference(e.target.value)}
                                                    className="h-10 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-3 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                                    placeholder={lang === 'zh' ? '可选，订单号或截图编号' : 'Optional order or screenshot ID'}
                                                />
                                            </label>
                                            <button
                                                type="submit"
                                                disabled={submitting || !units || !reason.trim()}
                                                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-extrabold text-white transition hover:bg-primary/90 active:translate-y-px disabled:opacity-50 sm:col-span-2 2xl:col-span-1"
                                            >
                                                <span className="material-symbols-outlined text-[18px]">{submitting ? 'hourglass_top' : 'add_card'}</span>
                                                {submitting ? (lang === 'zh' ? '提交中' : 'Saving') : (lang === 'zh' ? '提交调整' : 'Apply adjustment')}
                                            </button>
                                        </div>
                                    </form>
                                </div>

                                <div className="min-w-0 overflow-hidden rounded-sm bg-surface-container-lowest shadow-sm ring-1 ring-outline-variant/25">
                                    <div className="border-b ff-border-muted px-5 py-4">
                                        <div className="flex items-center justify-between gap-3">
                                            <h2 className="text-sm font-bold text-on-surface font-headline">
                                                {lang === 'zh' ? '最近余额流水' : 'Recent ledger'}
                                            </h2>
                                            <span className="text-xs font-semibold tabular-nums text-on-surface-variant">
                                                {transactions.length}
                                            </span>
                                        </div>
                                    </div>
                                    {transactions.length === 0 ? (
                                        <div className="p-6 text-sm font-medium text-on-surface-variant">
                                            {lang === 'zh' ? '暂无余额流水。' : 'No ledger entries yet.'}
                                        </div>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <table className="w-full min-w-[720px] text-left text-sm">
                                                <thead className="bg-surface-container-low text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">
                                                    <tr>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '时间' : 'Time'}</th>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '类型' : 'Type'}</th>
                                                        <th className="px-5 py-3 text-right">{lang === 'zh' ? '变化' : 'Delta'}</th>
                                                        <th className="px-5 py-3 text-right">{lang === 'zh' ? '余额' : 'Balance'}</th>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '原因' : 'Reason'}</th>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '任务/凭证' : 'Task / ref'}</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-outline-variant/30">
                                                    {transactions.map((tx) => {
                                                        const delta = Number(tx.unit_delta) || 0;
                                                        return (
                                                            <tr key={tx.id} className="hover:bg-surface-container-low/60">
                                                                <td className="whitespace-nowrap px-5 py-3 text-xs font-semibold text-on-surface-variant">{fmtDateTime(tx.created_at, lang)}</td>
                                                                <td className="whitespace-nowrap px-5 py-3 font-semibold text-on-surface">{tx.transaction_type}</td>
                                                                <td className={`whitespace-nowrap px-5 py-3 text-right font-extrabold tabular-nums ${delta >= 0 ? 'text-green-700 dark:text-green-300' : 'text-red-600'}`}>
                                                                    {delta > 0 ? `+${delta}` : delta}
                                                                </td>
                                                                <td className="whitespace-nowrap px-5 py-3 text-right font-bold text-on-surface tabular-nums">{tx.balance_after}</td>
                                                                <td className="max-w-[240px] px-5 py-3 text-on-surface-variant">
                                                                    <span className="line-clamp-2">{tx.reason || '-'}</span>
                                                                </td>
                                                                <td className="max-w-[220px] px-5 py-3 text-xs font-medium text-on-surface-variant">
                                                                    <span className="line-clamp-2 break-all">{tx.task_id || tx.provider_reference || '-'}</span>
                                                                </td>
                                                            </tr>
                                                        );
                                                    })}
                                                </tbody>
                                            </table>
                                        </div>
                                    )}
                                </div>
                            </>
                        ) : (
                            <div className="rounded-sm bg-surface-container-lowest p-8 text-sm font-medium text-on-surface-variant shadow-sm ring-1 ring-outline-variant/25">
                                {loading ? (lang === 'zh' ? '正在读取用户…' : 'Loading users...') : (lang === 'zh' ? '还没有用户。' : 'No users yet.')}
                            </div>
                        )}
                    </section>
                </div>
            </main>
        </div>
    );
};

/* ═══════════════ Settings ═══════════════ */

export default Admin;
