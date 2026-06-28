import {useState,useEffect} from 'react';
import {fmtDateTime, useApi, useAuth, useI18n} from '../app/shared.jsx';
import SvgIcon from '../components/SvgIcon.jsx';

const Admin = () => {
    const {t, lang} = useI18n();
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
            <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] transition-[margin] duration-200 ease-out dark:bg-[#101010]">
                <main className="mx-auto flex min-h-[70vh] max-w-[900px] items-center justify-center px-8 py-10">
                    <div className="rounded-[22px] border border-[#e4e0e0] bg-white p-8 text-center shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <SvgIcon name="lock" className="text-4xl text-[#8a8a8a] dark:text-white/40"/>
                        <h1 className="mt-3 text-xl font-extrabold text-[#111111] dark:text-white font-headline">
                            {lang === 'zh' ? '没有管理员权限' : 'Admin access required'}
                        </h1>
                        <p className="mt-2 text-sm font-medium text-[#777] dark:text-white/55 max-w-sm mx-auto">
                            {lang === 'zh'
                                ? '这个页面只用于维护账号额度和余额流水，普通用户不能访问。'
                                : 'This page is only for maintaining account balances and ledger entries.'}
                        </p>
                    </div>
                </main>
            </div>
        );
    }

    const inputClass = "w-full h-10 rounded-[12px] border border-[#dedada] dark:border-white/[0.12] bg-[#f4f3f3] dark:bg-white/[0.08] px-3.5 text-sm font-semibold text-[#111111] dark:text-white outline-none placeholder:text-[#8a8a8a] dark:placeholder:text-white/40 focus:border-primary/60";

    return (
        <div className="ml-[var(--sidebar-offset)] min-h-screen bg-[#f8f7fb] pb-8 text-[#111111] transition-[margin] duration-200 ease-out dark:bg-[#101010] dark:text-white/[0.92]">
            <main className="mx-auto h-dvh max-w-[1500px] overflow-y-auto px-8 py-7 hide-scrollbar">
                <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-extrabold tracking-tight text-[#111111] dark:text-white font-headline">
                            {lang === 'zh' ? '用户额度维护' : 'User balance maintenance'}
                        </h1>
                        <p className="mt-1 text-sm font-medium text-[#777] dark:text-white/55">
                            {lang === 'zh'
                                ? '查余额、看流水、按原因手动增减处理额度。'
                                : 'Inspect balances, review ledger entries, and adjust processing units.'}
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={()=>loadUsers(selectedUser?.id || '')}
                        disabled={loading}
                        className="inline-flex h-10 items-center justify-center gap-2 rounded-[14px] border border-[#dedada] bg-white px-4 text-sm font-bold text-[#111111] shadow-[0_14px_34px_-30px_rgba(17,17,17,.45)] hover:bg-[#efeeee] dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:hover:bg-white/[0.09] dark:shadow-none disabled:opacity-50"
                    >
                        <SvgIcon name="refresh" className={`text-base ${loading ? 'animate-spin' : ''}`}/>
                        {lang === 'zh' ? '刷新' : 'Refresh'}
                    </button>
                </header>

                {(error || notice) && (
                    <div className={`mb-5 rounded-[14px] border px-4 py-3 text-sm font-semibold ${error ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-300' : 'border-green-200 bg-green-50 text-green-700 dark:border-green-500/20 dark:bg-green-500/10 dark:text-green-300'}`}>
                        {error || notice}
                    </div>
                )}

                <div className="grid min-w-0 gap-5 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
                    {/* ── User list ── */}
                    <section className="min-w-0 overflow-hidden rounded-[22px] border border-[#e4e0e0] bg-white shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                        <div className="border-b border-[#e4e0e0] dark:border-white/[0.12] p-4">
                            <div className="flex items-center justify-between gap-3 mb-3">
                                <h2 className="text-sm font-extrabold text-[#111111] dark:text-white font-headline">
                                    {lang === 'zh' ? '账号列表' : 'Accounts'}
                                </h2>
                                <span className="text-xs font-bold text-[#8a8a8a] dark:text-white/40 tabular-nums">{filteredUsers.length}</span>
                            </div>
                            <label className="flex h-9 items-center gap-2 rounded-[12px] border border-[#dedada] dark:border-white/[0.12] bg-[#f4f3f3] dark:bg-white/[0.08] px-3 focus-within:border-primary/60">
                                <SvgIcon name="search" className="text-[18px] text-[#8a8a8a] dark:text-white/40"/>
                                <input
                                    value={query}
                                    onChange={(e)=>setQuery(e.target.value)}
                                    className="h-full min-w-0 flex-1 bg-transparent text-sm font-semibold text-[#111111] dark:text-white outline-none placeholder:text-[#8a8a8a] dark:placeholder:text-white/40"
                                    placeholder={lang === 'zh' ? '搜索邮箱或用户 ID' : 'Search email or user ID'}
                                />
                            </label>
                        </div>
                        <div className="max-h-[calc(100vh-265px)] overflow-y-auto hide-scrollbar p-2 space-y-1">
                            {loading && users.length === 0 ? (
                                <div className="space-y-2 p-2">
                                    {[0,1,2].map((item) => <div key={item} className="h-16 animate-pulse rounded-[14px] bg-[#f4f3f3] dark:bg-white/[0.08]"/>)}
                                </div>
                            ) : filteredUsers.length === 0 ? (
                                <div className="p-6 text-center text-sm font-semibold text-[#8a8a8a] dark:text-white/40">
                                    {lang === 'zh' ? '没有匹配的用户。' : 'No matching users.'}
                                </div>
                            ) : (
                                filteredUsers.map((item) => {
                                    const active = item.id === selectedUser?.id;
                                    const balance = item.quota?.balance_units ?? 0;
                                    const quotaExempt = item.role === 'admin' || item.quota?.unlimited || item.quota?.quota_exempt;
                                    return (
                                        <button
                                            key={item.id}
                                            type="button"
                                            onClick={()=>setSelectedId(item.id)}
                                            className={`w-full rounded-[14px] px-3 py-2.5 text-left transition ${active ? 'bg-[#111111] text-white dark:bg-white dark:text-[#111111]' : 'hover:bg-[#f4f3f3] dark:hover:bg-white/[0.08]'}`}
                                        >
                                            <div className="flex items-start justify-between gap-2">
                                                <div className="min-w-0">
                                                    <p className={`truncate text-sm font-extrabold ${active ? 'text-white dark:text-[#111111]' : 'text-[#111111] dark:text-white'}`} title={item.email || ''}>{item.email}</p>
                                                    <p className={`mt-0.5 text-[11px] font-semibold uppercase ${active ? 'text-white/60 dark:text-[#111111]/60' : 'text-[#8a8a8a] dark:text-white/40'}`}>
                                                        {item.role || 'user'} · {item.status || 'active'}
                                                    </p>
                                                </div>
                                                <span className={`shrink-0 rounded-[10px] px-2 py-1 text-xs font-extrabold tabular-nums ${quotaExempt ? (active ? 'bg-white/20 text-white dark:bg-[#111111]/10 dark:text-[#111111]' : 'bg-primary/10 text-primary') : balance < 0 ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-300' : (active ? 'bg-white/20 text-white dark:bg-[#111111]/10 dark:text-[#111111]' : 'bg-[#efeeee] text-[#111111] dark:bg-white/[0.12] dark:text-white')}`}>
                                                    {quotaExempt ? (lang === 'zh' ? '无限' : 'Unlimited') : balance}
                                                </span>
                                            </div>
                                        </button>
                                    );
                                })
                            )}
                        </div>
                    </section>

                    {/* ── Detail + adjustment ── */}
                    <section className="min-w-0 space-y-5">
                        {selectedUser ? (
                            <>
                                <div className="grid min-w-0 gap-5 2xl:grid-cols-[minmax(0,1fr)_320px]">
                                    <div className="min-w-0 rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                        <h2 className="truncate text-lg font-extrabold text-[#111111] dark:text-white font-headline" title={selectedUser.email || ''}>
                                            {selectedUser.email}
                                        </h2>
                                        <p className="mt-1 break-all text-xs font-medium text-[#8a8a8a] dark:text-white/40">{selectedUser.id}</p>
                                        <div className="mt-4 flex flex-wrap gap-2 text-xs font-semibold">
                                            <span className="rounded-[10px] bg-[#f4f3f3] dark:bg-white/[0.08] px-2.5 py-1 text-[#777] dark:text-white/55">{selectedUser.role || 'user'}</span>
                                            <span className="rounded-[10px] bg-[#f4f3f3] dark:bg-white/[0.08] px-2.5 py-1 text-[#777] dark:text-white/55">{selectedUser.status || 'active'}</span>
                                            <span className="rounded-[10px] bg-[#f4f3f3] dark:bg-white/[0.08] px-2.5 py-1 text-[#777] dark:text-white/55">
                                                {lang === 'zh' ? '创建' : 'Created'} {fmtDateTime(selectedUser.created_at, lang)}
                                            </span>
                                        </div>
                                        <div className="mt-5 rounded-[14px] bg-primary/10 dark:bg-primary/10 px-4 py-3">
                                            <p className="text-[11px] font-bold uppercase tracking-wider text-primary">
                                                {selectedQuotaExempt ? (lang === 'zh' ? '额度豁免' : 'Quota exempt') : (lang === 'zh' ? '当前额度' : 'Balance')}
                                            </p>
                                            <p className={`mt-1 text-3xl font-extrabold leading-none text-primary tabular-nums ${selectedQuotaExempt ? '' : ''}`}>
                                                {selectedQuotaExempt ? (lang === 'zh' ? '无限' : 'Unlimited') : selectedBalance}
                                            </p>
                                        </div>
                                    </div>

                                    <form onSubmit={submitAdjustment} className="min-w-0 rounded-[22px] border border-[#e4e0e0] bg-white p-5 shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                        <h2 className="text-sm font-extrabold text-[#111111] dark:text-white font-headline">
                                            {lang === 'zh' ? '手动调整额度' : 'Manual adjustment'}
                                        </h2>
                                        <div className="mt-4 grid gap-3 sm:grid-cols-2 2xl:grid-cols-1">
                                            <label className="block space-y-1.5">
                                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#8a8a8a] dark:text-white/40">
                                                    {lang === 'zh' ? '额度变化' : 'Unit delta'}
                                                </span>
                                                <input
                                                    type="number"
                                                    step="1"
                                                    value={units}
                                                    onChange={(e)=>setUnits(e.target.value)}
                                                    className={inputClass}
                                                    placeholder={lang === 'zh' ? '例如 100' : 'e.g. 100'}
                                                />
                                            </label>
                                            <label className="block space-y-1.5">
                                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#8a8a8a] dark:text-white/40">
                                                    {lang === 'zh' ? '原因' : 'Reason'}
                                                </span>
                                                <input
                                                    type="text"
                                                    value={reason}
                                                    onChange={(e)=>setReason(e.target.value)}
                                                    className={inputClass}
                                                    placeholder={lang === 'zh' ? '微信手动充值' : 'Manual recharge'}
                                                />
                                            </label>
                                            <label className="block space-y-1.5 sm:col-span-2 2xl:col-span-1">
                                                <span className="text-[10px] font-bold uppercase tracking-wider text-[#8a8a8a] dark:text-white/40">
                                                    {lang === 'zh' ? '凭证备注' : 'Reference'}
                                                </span>
                                                <input
                                                    type="text"
                                                    value={providerReference}
                                                    onChange={(e)=>setProviderReference(e.target.value)}
                                                    className={inputClass}
                                                    placeholder={lang === 'zh' ? '可选，订单号或截图编号' : 'Optional order or screenshot ID'}
                                                />
                                            </label>
                                            <button
                                                type="submit"
                                                disabled={submitting || !units || !reason.trim()}
                                                className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-[14px] bg-[#111111] px-4 text-sm font-bold text-white transition hover:bg-[#2a2a2a] disabled:opacity-40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88] sm:col-span-2 2xl:col-span-1"
                                            >
                                                <SvgIcon name={submitting ? 'hourglass_top' : 'add_card'} className="text-base"/>
                                                {submitting ? (lang === 'zh' ? '提交中' : 'Saving') : (lang === 'zh' ? '提交调整' : 'Apply adjustment')}
                                            </button>
                                        </div>
                                    </form>
                                </div>

                                {/* ── Transaction ledger ── */}
                                <div className="min-w-0 rounded-[22px] border border-[#e4e0e0] bg-white shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                    <div className="flex items-center justify-between gap-3 border-b border-[#e4e0e0] dark:border-white/[0.12] px-5 py-4">
                                        <h2 className="text-sm font-extrabold text-[#111111] dark:text-white font-headline">
                                            {lang === 'zh' ? '最近余额流水' : 'Recent ledger'}
                                        </h2>
                                        <span className="text-xs font-bold text-[#8a8a8a] dark:text-white/40 tabular-nums">{transactions.length}</span>
                                    </div>
                                    {transactions.length === 0 ? (
                                        <div className="p-8 text-center text-sm font-semibold text-[#8a8a8a] dark:text-white/40">
                                            {lang === 'zh' ? '暂无余额流水。' : 'No ledger entries yet.'}
                                        </div>
                                    ) : (
                                        <div className="overflow-x-auto">
                                            <table className="w-full min-w-[720px] text-left text-xs">
                                                <thead className="border-b border-[#e4e0e0] dark:border-white/[0.12] text-[10px] font-bold uppercase tracking-wider text-[#8a8a8a] dark:text-white/40">
                                                    <tr>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '时间' : 'Time'}</th>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '类型' : 'Type'}</th>
                                                        <th className="px-5 py-3 text-right">{lang === 'zh' ? '变化' : 'Delta'}</th>
                                                        <th className="px-5 py-3 text-right">{lang === 'zh' ? '余额' : 'Balance'}</th>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '原因' : 'Reason'}</th>
                                                        <th className="px-5 py-3">{lang === 'zh' ? '任务/凭证' : 'Task / ref'}</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="divide-y divide-[#e4e0e0] dark:divide-white/[0.12]">
                                                    {transactions.map((tx) => {
                                                        const delta = Number(tx.unit_delta) || 0;
                                                        return (
                                                            <tr key={tx.id} className="hover:bg-[#f4f3f3] dark:hover:bg-white/[0.04]">
                                                                <td className="whitespace-nowrap px-5 py-3 font-semibold text-[#777] dark:text-white/55">{fmtDateTime(tx.created_at, lang)}</td>
                                                                <td className="whitespace-nowrap px-5 py-3 font-semibold text-[#111111] dark:text-white">{tx.transaction_type}</td>
                                                                <td className={`whitespace-nowrap px-5 py-3 text-right font-extrabold tabular-nums ${delta >= 0 ? 'text-green-600 dark:text-green-300' : 'text-red-600 dark:text-red-300'}`}>
                                                                    {delta > 0 ? `+${delta}` : delta}
                                                                </td>
                                                                <td className="whitespace-nowrap px-5 py-3 text-right font-bold text-[#111111] dark:text-white tabular-nums">{tx.balance_after}</td>
                                                                <td className="max-w-[240px] px-5 py-3 text-[#777] dark:text-white/55">
                                                                    <span className="line-clamp-2">{tx.reason || '-'}</span>
                                                                </td>
                                                                <td className="max-w-[220px] px-5 py-3 text-xs font-medium text-[#777] dark:text-white/40">
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
                            <div className="rounded-[22px] border border-[#e4e0e0] bg-white p-10 text-center shadow-[0_18px_44px_-34px_rgba(17,17,17,.55)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none">
                                <SvgIcon name="people" className="text-4xl text-[#8a8a8a] dark:text-white/40"/>
                                <p className="mt-3 text-sm font-semibold text-[#777] dark:text-white/55">
                                    {loading ? (lang === 'zh' ? '正在读取用户…' : 'Loading users...') : (lang === 'zh' ? '还没有用户。' : 'No users yet.')}
                                </p>
                            </div>
                        )}
                    </section>
                </div>
            </main>
        </div>
    );
};

export default Admin;
