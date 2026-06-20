import {useEffect, useState} from 'react';
import {Link, useLocation} from 'react-router-dom';
import {useApi, useAuth, useI18n} from '../app/shared.jsx';

/* ═══════════════ shared components ═══════════════ */
const SideNav = () => {
    const {t, lang, toggleLang} = useI18n();
    const {authMode, user, guestMode, canRegister, openAuth, logout} = useAuth();
    const {getAccountQuota} = useApi();
    const [quota, setQuota] = useState(user?.quota || null);
    const loc = useLocation();
    useEffect(() => {
        let cancelled = false;
        setQuota(user?.quota || null);
        if (authMode !== 'accounts' || !user || guestMode) return () => { cancelled = true; };
        const load = () => {
            getAccountQuota()
                .then((data) => { if (!cancelled) setQuota(data); })
                .catch(() => {});
        };
        load();
        const timer = setInterval(load, 30000);
        return () => {
            cancelled = true;
            clearInterval(timer);
        };
    }, [authMode, user?.id, guestMode]);
    const fullItems = [
        {path:'/',icon:'dashboard',k:'nav.dashboard'},
        {path:'/tasks',icon:'monitoring',k:'nav.tasks'},
        {path:'/processing',icon:'tune',k:'nav.processing'},
        {path:'/editor',icon:'subject',k:'nav.editor'},
        ...(user?.role === 'admin' ? [{path:'/admin',icon:'admin_panel_settings',k:'nav.admin'}] : []),
        {path:'/settings',icon:'settings',k:'nav.settings'},
    ];
    const items = guestMode ? fullItems.filter((item) => ['/', '/editor'].includes(item.path)) : fullItems;
    const quotaExempt = user?.role === 'admin' || quota?.unlimited || quota?.quota_exempt;
            return (
                <aside className="h-screen w-64 fixed left-0 top-0 flex flex-col bg-slate-50 border-r border-slate-200 z-50">
                    <div className="flex flex-col h-full p-4">
                        <div className="flex items-center gap-3 px-4 py-6 mb-8">
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary-container flex items-center justify-center text-white shadow-lg">
                        <span className="material-symbols-outlined" style={{fontVariationSettings:"'FILL' 1"}}>auto_videocam</span>
                            </div>
                            <div>
                                <h1 className="text-xl font-bold text-slate-900 leading-tight font-headline">FluentFlow</h1>
                        <p className="text-[10px] text-slate-500 font-medium tracking-widest uppercase">{t('nav.subtitle')}</p>
                            </div>
                        </div>
                        <nav className="flex-1 space-y-1">
                    {items.map(it => {
                        const active = loc.pathname===it.path;
                        return <Link key={it.path} to={it.path} className={`px-4 py-3 rounded-lg flex items-center gap-3 transition-colors text-sm tracking-tight ${active?'bg-blue-50 text-blue-700 font-semibold':'text-slate-500 hover:text-slate-900 hover:bg-slate-200/50'}`}>
                            <span className="material-symbols-outlined">{it.icon}</span><span>{t(it.k)}</span>
                        </Link>;
                            })}
                        </nav>
                        <div className="mt-auto border-t ff-border-muted px-2 pt-3">
                    {authMode === 'accounts' && user && (
                        <div className="mb-3 rounded-lg bg-surface-container-lowest px-3 py-3 shadow-sm border ff-border-muted">
                            <p className="truncate text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">
                                {lang==='zh'?'当前账号':'Account'}
                            </p>
                            <p className="mt-1 truncate text-sm font-semibold text-on-surface" title={user.email || ''}>
                                {user.email}
                            </p>
                            {quota && (
                                <div className="mt-3 rounded-md bg-surface-container-low px-3 py-2">
                                    <div className="flex items-center justify-between gap-3">
                                        <span className="text-xs font-semibold text-on-surface-variant">{quotaExempt ? (lang==='zh'?'额度豁免':'Quota exempt') : (lang==='zh'?'处理额度':'Balance')}</span>
                                        <span className="text-sm font-bold text-primary">{quotaExempt ? (lang==='zh'?'无限':'Unlimited') : (quota.balance_units ?? 0)}</span>
                                    </div>
                                </div>
                            )}
                            <button
                                type="button"
                                onClick={logout}
                                className="mt-2 inline-flex items-center gap-1.5 rounded-md px-0 text-xs font-semibold text-on-surface-variant transition hover:text-red-600"
                            >
                                <span className="material-symbols-outlined text-[16px]">logout</span>
                                {lang==='zh'?'退出登录':'Sign out'}
                            </button>
                        </div>
                    )}
                    {guestMode && (
                        <div className="mb-3 rounded-lg bg-surface-container-lowest px-3 py-3 shadow-sm border ff-border-muted">
                            <p className="text-[11px] font-bold uppercase tracking-wider text-on-surface-variant">
                                {lang==='zh'?'访客试用':'Guest trial'}
                            </p>
                            <p className="mt-1 text-xs leading-relaxed text-on-surface-variant">
                                {lang==='zh'?'支持一次短视频真实转录与笔记生成。':'Run one short real transcription and note trial.'}
                            </p>
                            {authMode === 'accounts' && (
                                <div className="mt-3 flex flex-col gap-2">
                                    <button
                                        type="button"
                                        onClick={()=>openAuth('login')}
                                        className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md bg-primary px-3 text-xs font-bold text-white transition hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                                    >
                                        <span className="material-symbols-outlined text-[16px]">login</span>
                                        {lang==='zh'?'登录账号':'Sign in'}
                                    </button>
                                    {canRegister && (
                                        <button
                                            type="button"
                                            onClick={()=>openAuth('register')}
                                            className="inline-flex h-9 w-full items-center justify-center rounded-md bg-surface-container px-3 text-xs font-bold text-on-surface transition hover:bg-surface-container-high focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30"
                                        >
                                            {lang==='zh'?'创建账号':'Create account'}
                                        </button>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                    <button
                        onClick={toggleLang}
                        className="group flex h-10 w-full items-center gap-3 rounded-lg px-3 text-[13px] font-semibold text-on-surface-variant transition-colors hover:bg-surface-container-low hover:text-on-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
                        aria-label={lang==='zh'?'切换界面语言':'Switch interface language'}
                    >
                        <span className="material-symbols-outlined text-[20px] leading-none text-outline group-hover:text-on-surface-variant">translate</span>
                        <span className="min-w-0 flex-1 truncate text-left">{lang==='zh'?'界面语言':'Language'}</span>
                        <span className="min-w-8 rounded-md bg-primary/10 px-2 py-1 text-center text-[11px] font-bold leading-none text-primary">
                            {lang==='en'?'中文':'EN'}
                        </span>
                    </button>
                        </div>
                    </div>
                </aside>
            );
        };

/* ═══════════════ Dashboard ═══════════════ */

export default SideNav;
