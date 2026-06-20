import {Route, Routes} from 'react-router-dom';
import SideNav from '../components/SideNav.jsx';
import Dashboard from '../routes/dashboard.jsx';
import Tasks from '../routes/tasks.jsx';
import Processing from '../routes/processing.jsx';
import Editor from '../routes/editor.jsx';
import Admin from '../routes/admin.jsx';
import Settings from '../routes/settings.jsx';
import {useAuth} from './shared.jsx';

const AppShell = () => {
    const {guestMode} = useAuth();
    return (
        <div className="flex min-h-screen w-full bg-surface">
            <SideNav/>
            <div className="flex-1 flex flex-col w-full h-full relative">
                <Routes>
                    <Route path="/" element={<Dashboard/>}/>
                    <Route path="/tasks" element={guestMode ? <Dashboard/> : <Tasks/>}/>
                    <Route path="/processing" element={guestMode ? <Dashboard/> : <Processing/>}/>
                    <Route path="/editor" element={<Editor/>}/>
                    <Route path="/admin" element={guestMode ? <Dashboard/> : <Admin/>}/>
                    <Route path="/settings" element={guestMode ? <Dashboard/> : <Settings/>}/>
                </Routes>
            </div>
        </div>
    );
};

export default AppShell;
