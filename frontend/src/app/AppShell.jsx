import {Route, Routes} from 'react-router-dom';
import {useEffect, useState} from 'react';
import SideNav from '../components/SideNav.jsx';
import Dashboard from '../routes/dashboard.jsx';
import MediaText from '../routes/media-text.jsx';
import Tasks from '../routes/tasks.jsx';
import AgentTrace from '../routes/agent-trace.jsx';
import Editor from '../routes/editor.jsx';
import Admin from '../routes/admin.jsx';
import Settings from '../routes/settings.jsx';
import About from '../routes/about.jsx';
import {useAuth} from './shared.jsx';

const AppShell = () => {
    const {guestMode} = useAuth();
    const [sidebarCollapsed, setSidebarCollapsed] = useState(() => localStorage.getItem('fluentflow_sidebar_collapsed') === '1');

    useEffect(() => {
        localStorage.setItem('fluentflow_sidebar_collapsed', sidebarCollapsed ? '1' : '0');
    }, [sidebarCollapsed]);

    return (
        <div
            className="flex min-h-screen w-full bg-surface dark:bg-[#101010]"
            style={{'--sidebar-offset': sidebarCollapsed ? '4.5rem' : '14rem'}}
        >
            <SideNav collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((value) => !value)}/>
            <div className="flex-1 flex flex-col w-full h-full relative">
                <Routes>
                    <Route path="/" element={<Dashboard/>}/>
                    <Route path="/media-text" element={<MediaText/>}/>
                    <Route path="/tasks" element={guestMode ? <Dashboard/> : <Tasks/>}/>
                    <Route path="/tasks/:taskId/agent" element={<AgentTrace/>}/>
                    <Route path="/editor" element={<Editor/>}/>
                    <Route path="/admin" element={guestMode ? <Dashboard/> : <Admin/>}/>
                    <Route path="/settings" element={guestMode ? <Dashboard/> : <Settings/>}/>
                    <Route path="/about" element={<About/>}/>
                </Routes>
            </div>
        </div>
    );
};

export default AppShell;
