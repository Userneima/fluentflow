// @vitest-environment jsdom
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SideNav from './SideNav.jsx';

// Guards against the guest-nav regression: the guest allow-list used to be a
// hardcoded path list (`['/', '/editor']`) that silently drifted from the real
// entries when the media route moved to `/media-text`, hiding the main trial
// entry from guests. The fix marks guest-visible items on the definition itself
// (`guest: true`) so the two can no longer diverge. These tests lock that in.

const auth = { authMode: 'accounts', user: null, guestMode: false, canRegister: false, openAuth: vi.fn(), logout: vi.fn() };

vi.mock('../app/shared.jsx', () => ({
    useI18n: () => ({ t: (k) => k, lang: 'zh', toggleLang: vi.fn() }),
    useAuth: () => auth,
    useApi: () => ({ getAccountQuota: vi.fn(async () => ({})) }),
    useSettings: () => ({ loadSettings: () => ({}), saveSettings: vi.fn() }),
}));
vi.mock('./AgentAccessPanel.jsx', () => ({ default: () => null }));

const mount = () => render(<MemoryRouter><SideNav /></MemoryRouter>);

describe('SideNav guest navigation', () => {
    beforeEach(() => { auth.user = null; auth.guestMode = false; });

    it('shows the media-notes main entry to guests', () => {
        auth.guestMode = true;
        mount();
        // Main trial entry must be reachable from the sidebar, not just via URL.
        expect(screen.getByText('视频转写与总结')).toBeTruthy();
    });

    it('hides non-guest entries (settings / agent) from guests', () => {
        auth.guestMode = true;
        mount();
        expect(screen.queryByText('nav.settings')).toBeNull();
        expect(screen.queryByText('nav.processing')).toBeNull();
    });

    it('shows the full nav to a signed-in non-guest user', () => {
        auth.user = { id: 'u1', name: 'Yuchao' };
        auth.guestMode = false;
        mount();
        expect(screen.getAllByText('视频转写与总结').length).toBeGreaterThan(0);
        expect(screen.getAllByText('nav.settings').length).toBeGreaterThan(0);
    });
});
