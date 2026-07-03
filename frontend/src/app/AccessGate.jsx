import {useCallback, useEffect, useState} from 'react';
import {API_BASE, AuthCtx, apiFetch, clearGuestTrialSession, getAccessToken, setAccessToken, useI18n} from './shared.jsx';

const AccessGate = ({children}) => {
    const {lang} = useI18n();
    const [checking, setChecking] = useState(true);
    const [required, setRequired] = useState(false);
    const [authenticated, setAuthenticated] = useState(false);
    const [authMode, setAuthMode] = useState('open');
    const [allowSignups, setAllowSignups] = useState(false);
    const [bootstrapRequired, setBootstrapRequired] = useState(false);
    const [user, setUser] = useState(null);
    const [guestTrial, setGuestTrial] = useState(null);
    const [guestMode, setGuestMode] = useState(false);
    const [formMode, setFormMode] = useState('login');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [token, setToken] = useState(getAccessToken());
    const [error, setError] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const refreshStatus = useCallback(async () => {
        setChecking(true);
        try {
            const r = await apiFetch(`${API_BASE}/auth/status`);
            const data = await r.json().catch(()=>({}));
            const nextMode = data.auth_mode || (data.access_required ? 'access_code' : 'open');
            const nextRequired = !!(data.account_required || data.access_required);
            const nextGuestTrial = data.guest_trial || null;
            const nextGuestAllowed = !!nextGuestTrial?.enabled && nextRequired && !data.authenticated && !data.bootstrap_required;
            setAuthMode(nextMode);
            setRequired(nextRequired);
            setAuthenticated(!nextRequired || !!data.authenticated || nextGuestAllowed);
            setAllowSignups(!!data.allow_signups);
            setBootstrapRequired(!!data.bootstrap_required);
            setUser(data.user || null);
            setGuestTrial(nextGuestTrial);
            setGuestMode(nextGuestAllowed);
            if (data.bootstrap_required) setFormMode('register');
        } catch(_) {
            setAuthMode('accounts');
            setRequired(true);
            setAuthenticated(false);
            setUser(null);
            setGuestTrial(null);
            setGuestMode(false);
        } finally {
            setChecking(false);
        }
    }, []);

    useEffect(() => { refreshStatus(); }, [refreshStatus]);

    const logout = useCallback(async () => {
        try {
            await apiFetch(`${API_BASE}/auth/logout`, {method:'POST'});
        } catch(_) {}
        setAccessToken('');
        setToken('');
        setUser(null);
        clearGuestTrialSession();
        setAuthenticated(false);
        await refreshStatus();
    }, [refreshStatus]);

    const openAuth = useCallback((mode='login') => {
        setError('');
        setPassword('');
        setFormMode(mode === 'register' ? 'register' : 'login');
        setGuestMode(false);
        setAuthenticated(false);
    }, []);

    const continueAsGuest = useCallback(() => {
        if (!guestTrial?.enabled) return;
        setError('');
        setPassword('');
        setAuthenticated(true);
        setGuestMode(true);
    }, [guestTrial]);

    const submit = async (e) => {
        e.preventDefault();
        setError('');
        setSubmitting(true);
        try {
            const accountFlow = authMode === 'accounts';
            const endpoint = accountFlow && formMode === 'register' ? '/auth/register' : '/auth/login';
            const body = accountFlow
                ? {email: email.trim(), password}
                : {access_token: token.trim()};
            const r = await apiFetch(`${API_BASE}${endpoint}`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify(body),
            });
            const data = await r.json().catch(()=>({}));
            if(!r.ok) {
                const fallback = accountFlow
                    ? (lang === 'zh' ? '账号验证失败' : 'Account authentication failed')
                    : (lang === 'zh' ? '访问码不正确' : 'Invalid access code');
                throw new Error(data.detail || fallback);
            }
            if (accountFlow) {
                setUser(data.user || null);
                setPassword('');
                setGuestMode(false);
            } else {
                setAccessToken(token.trim());
            }
            setAuthenticated(true);
        } catch(err) {
            setError(err.message || (lang === 'zh' ? '无法进入' : 'Access failed'));
        } finally {
            setSubmitting(false);
        }
    };

    if (checking) {
        return (
            <div className="flex min-h-dvh items-center justify-center bg-[#f8f7fb] px-6 text-sm font-semibold text-[#676970] dark:bg-[#101010] dark:text-white/55">
                <div className="flex items-center gap-3 rounded-[18px] border border-[#dedada] bg-white px-4 py-3 shadow-[0_18px_48px_-36px_rgba(17,17,17,.45)] dark:border-white/[0.12] dark:bg-white/[0.06]">
                    <span className="h-2 w-2 rounded-full bg-[#111111] dark:bg-white"/>
                    {lang === 'zh' ? '正在打开 FluentFlow…' : 'Opening FluentFlow…'}
                </div>
            </div>
        );
    }
    const canRegister = allowSignups || bootstrapRequired;
    if (!required || authenticated) {
        return (
            <AuthCtx.Provider value={{authMode, user, guestMode, guestTrial, canRegister, openAuth, logout}}>
                {children}
            </AuthCtx.Provider>
        );
    }

    const accountFlow = authMode === 'accounts';
    const registerMode = accountFlow && formMode === 'register';
    const title = accountFlow
        ? (registerMode
            ? (bootstrapRequired ? (lang === 'zh' ? '创建管理员账号' : 'Create admin account') : (lang === 'zh' ? '创建账号' : 'Create account'))
            : (lang === 'zh' ? '登录 FluentFlow' : 'Sign in to FluentFlow'))
        : (lang === 'zh' ? '输入访问码' : 'Enter access code');
    const description = accountFlow
        ? (registerMode
            ? (lang === 'zh' ? '首次部署需要创建一个管理员账号。之后任务历史和额度会跟随账号。' : 'Create the first admin account. Jobs and quota will follow this account.')
            : (lang === 'zh' ? '登录后继续查看你的转录任务、字幕和笔记。' : 'Sign in to continue with your transcription jobs, subtitles, and notes.'))
        : (lang === 'zh' ? '当前版本用于小范围试用。访问码由产品维护者提供。' : 'This beta is invite-only. Ask the product maintainer for an access code.');

    return (
        <main className="flex min-h-dvh items-center justify-center bg-[#f8f7fb] px-5 py-8 text-[#111111] dark:bg-[#101010] dark:text-white/[0.92]">
            <form
                onSubmit={submit}
                className="w-full max-w-[480px] overflow-hidden rounded-[24px] border border-[#dedada] bg-white shadow-[0_26px_80px_-54px_rgba(17,17,17,.65)] dark:border-white/[0.12] dark:bg-white/[0.06] dark:shadow-none"
            >
                <div className="border-b border-[#ece8e8] px-6 py-6 dark:border-white/[0.10]">
                    <div className="mb-5 flex items-center gap-3">
                        <div className="flex size-11 items-center justify-center rounded-[15px] bg-[#111111] text-white dark:bg-white dark:text-[#111111]">
                            <span className="text-[18px] font-black leading-none">F</span>
                        </div>
                        <div className="min-w-0">
                            <p className="text-sm font-extrabold leading-tight">FluentFlow</p>
                            <p className="text-[11px] font-semibold text-[#85868c] dark:text-white/50">
                                {lang === 'zh' ? '视频转飞书 AI' : 'Video-to-Lark AI'}
                            </p>
                        </div>
                    </div>
                    <h1 className="font-headline text-[26px] font-extrabold leading-tight text-[#111111] dark:text-white">{title}</h1>
                    <p className="mt-2 max-w-[42ch] text-sm font-semibold leading-relaxed text-[#676970] dark:text-white/58">
                        {description}
                    </p>
                </div>
                <div className="px-6 py-5">
                {accountFlow ? (
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-[12px] font-extrabold text-[#676970] dark:text-white/58">
                                {lang === 'zh' ? '邮箱' : 'Email'}
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e)=>setEmail(e.target.value)}
                                className="h-12 w-full rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 text-sm font-semibold text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40"
                                placeholder="you@example.com"
                                autoFocus
                                autoComplete="email"
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-[12px] font-extrabold text-[#676970] dark:text-white/58">
                                {lang === 'zh' ? '密码' : 'Password'}
                            </label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e)=>setPassword(e.target.value)}
                                className="h-12 w-full rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 text-sm font-semibold text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40"
                                placeholder={lang === 'zh' ? '至少 8 位' : 'At least 8 characters'}
                                autoComplete={registerMode ? 'new-password' : 'current-password'}
                            />
                        </div>
                    </div>
                ) : (
                    <div className="space-y-2">
                        <label className="text-[12px] font-extrabold text-[#676970] dark:text-white/58">
                            {lang === 'zh' ? '访问码' : 'Access code'}
                        </label>
                        <input
                            type="password"
                            value={token}
                            onChange={(e)=>setToken(e.target.value)}
                            className="h-12 w-full rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 text-sm font-semibold text-[#111111] outline-none transition placeholder:text-[#aaa] focus:border-[#111111] focus:bg-white dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white dark:placeholder:text-white/30 dark:focus:border-white/40"
                            placeholder={lang === 'zh' ? '访问码' : 'Access code'}
                            autoFocus
                        />
                    </div>
                )}
                {error && (
                    <p className="mt-4 rounded-[14px] border border-red-200 bg-red-50 px-4 py-3 text-sm font-bold text-red-700 dark:border-red-500/20 dark:bg-red-500/10 dark:text-red-200">
                        {error}
                    </p>
                )}
                <div className="mt-6 flex flex-col gap-3">
                    <button
                        type="submit"
                        disabled={submitting || (accountFlow ? (!email.trim() || !password) : !token.trim())}
                        className="h-12 rounded-[15px] bg-[#111111] px-5 text-sm font-extrabold text-white transition hover:bg-[#2a2a2a] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-[#111111] dark:hover:bg-white/[0.88]"
                    >
                        {submitting
                            ? (lang === 'zh' ? '处理中' : 'Working')
                            : (registerMode ? (lang === 'zh' ? '创建并进入' : 'Create and enter') : (lang === 'zh' ? '进入' : 'Enter'))}
                    </button>
                    {accountFlow && canRegister && !bootstrapRequired && (
                        <button
                            type="button"
                            onClick={()=>{setError(''); setFormMode(registerMode ? 'login' : 'register');}}
                            className="h-11 rounded-[14px] border border-[#dedada] bg-[#fbfbfb] px-4 text-sm font-bold text-[#57585d] transition hover:bg-[#efeeee] hover:text-[#111111] active:translate-y-px dark:border-white/[0.12] dark:bg-white/[0.06] dark:text-white/65 dark:hover:bg-white/[0.10] dark:hover:text-white"
                        >
                            {registerMode
                                ? (lang === 'zh' ? '已有账号，去登录' : 'Already have an account')
                                : (lang === 'zh' ? '没有账号，创建一个' : 'Create an account')}
                        </button>
                    )}
                    {accountFlow && guestTrial?.enabled && !bootstrapRequired && (
                        <button
                            type="button"
                            onClick={continueAsGuest}
                            className="h-11 rounded-[14px] px-4 text-sm font-bold text-[#676970] transition hover:bg-[#efeeee] hover:text-[#111111] active:translate-y-px dark:text-white/58 dark:hover:bg-white/[0.08] dark:hover:text-white"
                        >
                            {lang === 'zh' ? '继续访客试用' : 'Continue as guest'}
                        </button>
                    )}
                </div>
                </div>
            </form>
        </main>
    );
};

export default AccessGate;
