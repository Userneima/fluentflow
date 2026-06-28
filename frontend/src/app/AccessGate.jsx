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
        return <div className="min-h-screen bg-surface flex items-center justify-center text-sm font-semibold text-on-surface-variant">{lang === 'zh' ? '正在检查访问权限…' : 'Checking access…'}</div>;
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
        <main className="min-h-screen bg-surface flex items-center justify-center px-6">
            <form onSubmit={submit} className="w-full max-w-[460px] rounded-sm bg-surface-container-lowest p-8 shadow-xl border border-outline-variant/30 dark:border-white/10">
                <div className="space-y-2 mb-6">
                    <p className="text-xs font-bold uppercase tracking-widest text-primary">FluentFlow</p>
                    <h1 className="text-3xl font-headline font-bold text-on-surface">{title}</h1>
                    <p className="text-sm leading-relaxed text-on-surface-variant">
                        {description}
                    </p>
                </div>
                {accountFlow ? (
                    <div className="space-y-4">
                        <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                {lang === 'zh' ? '邮箱' : 'Email'}
                            </label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e)=>setEmail(e.target.value)}
                                className="h-12 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-4 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                placeholder="you@example.com"
                                autoFocus
                                autoComplete="email"
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                                {lang === 'zh' ? '密码' : 'Password'}
                            </label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e)=>setPassword(e.target.value)}
                                className="h-12 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-4 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                                placeholder={lang === 'zh' ? '至少 8 位' : 'At least 8 characters'}
                                autoComplete={registerMode ? 'new-password' : 'current-password'}
                            />
                        </div>
                    </div>
                ) : (
                    <div className="space-y-2">
                        <label className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
                            {lang === 'zh' ? '访问码' : 'Access code'}
                        </label>
                        <input
                            type="password"
                            value={token}
                            onChange={(e)=>setToken(e.target.value)}
                            className="h-12 w-full rounded-sm border border-outline-variant/40 bg-surface-container-low px-4 text-sm font-semibold text-on-surface outline-none focus:border-primary/60 focus:ring-0"
                            placeholder={lang === 'zh' ? '访问码' : 'Access code'}
                            autoFocus
                        />
                    </div>
                )}
                {error && <p className="mt-4 text-sm font-semibold text-red-600">{error}</p>}
                <div className="mt-6 flex flex-col gap-3">
                    <button
                        type="submit"
                        disabled={submitting || (accountFlow ? (!email.trim() || !password) : !token.trim())}
                        className="h-12 rounded-sm bg-primary px-5 text-sm font-extrabold text-white transition hover:bg-primary/90 disabled:opacity-50"
                    >
                        {submitting
                            ? (lang === 'zh' ? '处理中' : 'Working')
                            : (registerMode ? (lang === 'zh' ? '创建并进入' : 'Create and enter') : (lang === 'zh' ? '进入' : 'Enter'))}
                    </button>
                    {accountFlow && canRegister && !bootstrapRequired && (
                        <button
                            type="button"
                            onClick={()=>{setError(''); setFormMode(registerMode ? 'login' : 'register');}}
                            className="h-11 rounded-sm bg-surface-container-low px-4 text-sm font-bold text-on-surface-variant transition hover:bg-surface-container-high hover:text-on-surface"
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
                            className="h-11 rounded-sm px-4 text-sm font-bold text-on-surface-variant transition hover:bg-surface-container-low hover:text-on-surface"
                        >
                            {lang === 'zh' ? '继续访客试用' : 'Continue as guest'}
                        </button>
                    )}
                </div>
            </form>
        </main>
    );
};

export default AccessGate;
