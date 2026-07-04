import {createRoot} from 'react-dom/client';
import {BrowserRouter, Route, Routes} from 'react-router-dom';
import {Suspense, lazy} from 'react';
import './tailwind.css';
import {I18nProvider} from './app/shared.jsx';
import {AppProvider} from './app/AppProvider.jsx';

const Landing = lazy(() => import('./routes/landing.jsx'));
const AccessGate = lazy(() => import('./app/AccessGate.jsx'));
const AppShell = lazy(() => import('./app/AppShell.jsx'));

createRoot(document.getElementById('root')).render(
    <BrowserRouter>
        <I18nProvider>
            <Suspense fallback={<div className="flex min-h-dvh items-center justify-center bg-[#f5f1e9] text-sm font-semibold text-[#6d655a] dark:bg-[#0f0e0c] dark:text-white/60">Loading...</div>}>
                <Routes>
                    <Route path="/" element={<Landing/>}/>
                    <Route path="/*" element={
                        <AccessGate>
                            <AppProvider>
                                <AppShell/>
                            </AppProvider>
                        </AccessGate>
                    }/>
                </Routes>
            </Suspense>
        </I18nProvider>
    </BrowserRouter>
);
