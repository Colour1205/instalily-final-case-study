// Where the API lives. On GitHub Pages it is the laptop's public Tailscale Funnel address;
// anywhere else (the backend serving this page itself) it is the same server.
export const API_BASE = location.hostname.endsWith('github.io') ? 'https://jennie.tail293afe.ts.net' : '';
