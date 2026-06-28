const SvgIcon = ({name, className = ''}) => {
    const common = {
        className,
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: 'currentColor',
        strokeWidth: 2.2,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        'aria-hidden': 'true',
    };
    const fillBrand = {
        className,
        viewBox: '0 0 24 24',
        fill: 'currentColor',
        stroke: 'none',
        'aria-hidden': 'true',
    };

    switch (name) {
        case 'video':
            return <svg {...common}><rect x="4" y="6" width="11" height="12" rx="2"/><path d="m15 10 5-3v10l-5-3z"/><path d="M9 10h2M9 14h2"/></svg>;
        case 'grid':
            return <svg {...common}><rect x="4" y="4" width="6" height="6" rx="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5"/><rect x="14" y="14" width="6" height="6" rx="1.5"/></svg>;
        case 'monitoring':
            return <svg {...common}><path d="M4 19V5"/><path d="M4 19h16"/><path d="m7 15 3-4 3 2 5-7"/><path d="M8 19v-3M12 19v-5M16 19v-7M20 19V8"/></svg>;
        case 'queue':
            return <svg {...common}><path d="M4 6h16"/><path d="M4 12h10"/><path d="M4 18h13"/></svg>;
        case 'tune':
            return <svg {...common}><path d="M4 6h10M18 6h2"/><path d="M4 12h3M11 12h9"/><path d="M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>;
        case 'subject':
            return <svg {...common}><path d="M5 6h14M5 12h14M5 18h9"/></svg>;
        case 'shield':
            return <svg {...common}><path d="M12 3 5 6v5c0 5 3 8 7 10 4-2 7-5 7-10V6z"/><path d="M12 8v5M12 17h.01"/></svg>;
        case 'settings':
            return <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></svg>;
        case 'sun':
            return <svg {...common}><circle cx="12" cy="12" r="5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"/></svg>;
        case 'moon':
            return <svg {...common}><path d="M20 14.1A6 6 0 1 1 15.1 4 8 8 0 1 0 20 14.1z"/></svg>;
        case 'logout':
            return <svg {...common}><path d="M10 6H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h4"/><path d="M14 8l4 4-4 4"/><path d="M18 12H9"/></svg>;
        case 'translate':
            return <svg {...common}><path d="M4 5h9"/><path d="M8 5c0 5-1.5 8-4 10"/><path d="M6 10c1.5 2.5 3.5 4 6 5"/><path d="M15 19l3-8 3 8"/><path d="M16 16h4"/></svg>;
        case 'sidebar-collapse':
            return <svg {...common}><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 4v16"/><path d="m16 9-3 3 3 3"/></svg>;
        case 'sidebar-expand':
            return <svg {...common}><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M9 4v16"/><path d="m13 9 3 3-3 3"/></svg>;
        case 'hand':
            return <svg {...common}><path d="M18 11V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2"/><path d="M14 10V4a2 2 0 0 0-2-2 2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg>;
        case 'wave':
            return <svg {...common}><path d="M8 11V6.5a1.5 1.5 0 0 1 3 0V11"/><path d="M11 10V5.5a1.5 1.5 0 0 1 3 0V11"/><path d="M14 11V7a1.5 1.5 0 0 1 3 0v6"/><path d="M8 12.5 6.6 11a1.6 1.6 0 0 0-2.3 2.2l4.5 5.1A6 6 0 0 0 19 14v-3a1.5 1.5 0 0 0-3 0v2"/><path d="M4 4 2.5 2.5M6 2.5 5.5 1M2.5 6 1 5.5"/></svg>;
        case 'arrow-right':
            return <svg {...common}><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>;
        case 'upload-file':
            return <svg {...common}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 17V10"/><path d="m9 13 3-3 3 3"/></svg>;
        case 'subtitles':
            return <svg {...common}><rect x="4" y="6" width="16" height="12" rx="2"/><path d="M8 11h4M8 15h2M14 15h2"/></svg>;
        case 'playlist-add':
            return <svg {...common}><path d="M4 7h10M4 12h10M4 17h7"/><path d="M17 11v6M14 14h6"/></svg>;
        case 'sync':
            return <svg {...common}><path d="M20 11a8 8 0 0 0-14.9-3"/><path d="M5 4v4h4"/><path d="M4 13a8 8 0 0 0 14.9 3"/><path d="M19 20v-4h-4"/></svg>;
        case 'cancel':
            return <svg {...common}><circle cx="12" cy="12" r="8"/><path d="m9 9 6 6M15 9l-6 6"/></svg>;
        case 'check-circle':
            return <svg {...common}><circle cx="12" cy="12" r="8"/><path d="m8.5 12.5 2.3 2.3 4.7-5.3"/></svg>;
        case 'error':
            return <svg {...common}><circle cx="12" cy="12" r="8"/><path d="M12 7v6M12 17h.01"/></svg>;
        case 'bilibili':
            return <svg {...fillBrand}><path d="M18.223 3.086a1.25 1.25 0 0 1 0 1.768L17.08 5.996h1.17A3.75 3.75 0 0 1 22 9.747v7.5a3.75 3.75 0 0 1-3.75 3.75H5.75A3.75 3.75 0 0 1 2 17.247v-7.5a3.75 3.75 0 0 1 3.75-3.75h1.166L5.775 4.855a1.25 1.25 0 1 1 1.767-1.768l2.652 2.652c.079.079.145.165.198.257h3.213c.053-.092.12-.18.199-.258l2.651-2.652a1.25 1.25 0 0 1 1.768 0zm.027 5.42H5.75a1.25 1.25 0 0 0-1.247 1.157l-.003.094v7.5c0 .659.51 1.199 1.157 1.246l.093.004h12.5a1.25 1.25 0 0 0 1.247-1.157l.003-.093v-7.5c0-.69-.56-1.25-1.25-1.25zm-10 2.5c.69 0 1.25.56 1.25 1.25v1.25a1.25 1.25 0 1 1-2.5 0v-1.25c0-.69.56-1.25 1.25-1.25zm7.5 0c.69 0 1.25.56 1.25 1.25v1.25a1.25 1.25 0 1 1-2.5 0v-1.25c0-.69.56-1.25 1.25-1.25z"/></svg>;
        case 'youtube':
            return <svg {...fillBrand}><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>;
        case 'douyin':
            return <svg {...fillBrand}><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>;
        case 'local-file':
            return <svg {...common}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h3"/></svg>;
        default:
            return <svg {...common}><circle cx="12" cy="12" r="8"/></svg>;
    }
};

export default SvgIcon;
