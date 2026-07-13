import {Navigate, Route, Routes} from 'react-router-dom';
import {Suspense, lazy, useEffect, useState} from 'react';
import SideNav from '../components/SideNav.jsx';
import {useAuth} from './shared.jsx';

const Dashboard = lazy(() => import('../routes/dashboard.jsx'));
const MediaText = lazy(() => import('../routes/media-text.jsx'));
const AgentTrace = lazy(() => import('../routes/agent-trace.jsx'));
const AgentTasks = lazy(() => import('../routes/agent-tasks.jsx'));
const Editor = lazy(() => import('../routes/editor.jsx'));
const Admin = lazy(() => import('../routes/admin.jsx'));
const Settings = lazy(() => import('../routes/settings.jsx'));
const About = lazy(() => import('../routes/about.jsx'));
const WorkspaceApi = lazy(() => import('../routes/workspace-api.jsx'));

const AppShell = () => {
    const {guestMode} = useAuth();
    const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('fluentflow_sidebar_collapsed') === '1');

    useEffect(() => {
        localStorage.setItem('fluentflow_sidebar_collapsed', sidebarCollapsed ? '1' : '0');
    }, [sidebarCollapsed]);

    return (
        <div
            className="flex h-dvh w-full overflow-hidden bg-surface dark:bg-[#101010]"
            style={{'--sidebar-offset': sidebarCollapsed ? '4.5rem' : '14rem'}}
        >
            <SideNav collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((value) => !value)}/>
            <div className="relative flex h-dvh min-h-0 w-full flex-1 flex-col overflow-hidden">
                <Suspense fallback={<div className="flex h-full items-center justify-center text-sm font-semibold text-on-surface-variant">Loading...</div>}>
                    <Routes>
                        <Route path="/app" element={<Dashboard/>}/>
                        <Route path="/media-text" element={<MediaText/>}/>
                        <Route path="/agent" element={guestMode ? <Dashboard/> : <AgentTasks/>}/>
                        <Route path="/processing" element={guestMode ? <Dashboard/> : <Navigate to="/agent" replace/>}/>
                        <Route path="/tasks" element={<Navigate to="/agent" replace/>}/>
                        <Route path="/tasks/:taskId/agent" element={<AgentTrace/>}/>
                        <Route path="/editor" element={<Editor/>}/>
                        <Route path="/admin" element={guestMode ? <Dashboard/> : <Admin/>}/>
                        <Route path="/settings" element={guestMode ? <Dashboard/> : <Settings/>}/>
                        <Route path="/workspace/api" element={<WorkspaceApi/>}/>
                        <Route path="/about" element={<About/>}/>
                        <Route path="/about/:page" element={<About/>}/>
                        <Route path="*" element={<Navigate to="/media-text" replace/>}/>
                    </Routes>
                </Suspense>
            </div>
        </div>
    );
};

export default AppShell;
