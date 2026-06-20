import {createRoot} from 'react-dom/client';
import {BrowserRouter} from 'react-router-dom';
import './tailwind.css';
import AccessGate from './app/AccessGate.jsx';
import AppShell from './app/AppShell.jsx';
import {AppProvider, I18nProvider} from './app/shared.jsx';

createRoot(document.getElementById('root')).render(
    <BrowserRouter>
        <I18nProvider>
            <AccessGate>
                <AppProvider>
                    <AppShell/>
                </AppProvider>
            </AccessGate>
        </I18nProvider>
    </BrowserRouter>
);
