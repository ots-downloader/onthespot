import { OTSConfig, SearchResultItem, DownloadQueueItem, LogEntry, AccountItem } from '../types';


const config = {
  api_url: import.meta.env.VITE_API_URL || '',
};
const STORAGE_KEY = 'OTS_FASTAPI_URL';
const DEFAULT_URL = config.api_url;
console.log("Using backend URL:", DEFAULT_URL);

export function getTargetBackendUrl(): string {
  if (typeof window === 'undefined') return DEFAULT_URL;
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_URL;
}

export function setTargetBackendUrl(url: string): void {
  if (typeof window === 'undefined') return;
  const cleaned = url.trim().replace(/\/$/, '');
  if (!cleaned) {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, cleaned);
  }
}

function getEndpoint(path: string): string {
  const base = getTargetBackendUrl().replace(/\/$/, '');
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const url = getEndpoint(path);
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json');
  }
  return fetch(url, { ...options, headers });
}

export async function checkServerHealth(): Promise<{ status: 'online' | 'offline'; version?: string; target: string }> {
  const target = getTargetBackendUrl();
  try {
    const res = await request('/config/get');
    if (!res.ok) throw new Error("Status check failed");
    const config = await res.json();
    return { status: 'online', version: config.version || 'FastAPI Engine', target };
  } catch (err) {
    return { status: 'offline', target };
  }
}

export async function searchMedia(query: string, filters?: Record<string, boolean>): Promise<SearchResultItem[]> {
  try {
    const qParam = query ? `?q=${encodeURIComponent(query)}` : '';
    const res = await request(`/query/url${qParam}`, {
      method: 'POST',
      body: JSON.stringify(filters || {})
    });
    if (!res.ok) throw new Error("Search request failed");
    const data = await res.json();
    return Array.isArray(data) ? data : (typeof data === 'object' && data !== null ? Object.values(data) : []);
  } catch (err) {
    console.error("Search API connection failed:", err);
    throw err;
  }
}

export async function fetchDownloadQueue(): Promise<DownloadQueueItem[]> {
  try {
    const res = await request('/queue/downloads');
    if (!res.ok) throw new Error("Failed to fetch queue");
    const data = await res.json();
    return Array.isArray(data) ? data : (typeof data === 'object' && data !== null ? Object.values(data) : []);
  } catch (err) {
    console.error("Fetch download queue failed:", err);
    return [];
  }
}

export async function enqueueDownload(item: SearchResultItem): Promise<{ success: boolean }> {
  try {
    const res = await request('/queue/downloads/add', {
      method: 'POST',
      body: JSON.stringify({ item })
    });
    if (!res.ok) throw new Error("Enqueue failed");
    return await res.json();
  } catch (err) {
    console.error("Enqueue download failed:", err);
    return { success: false };
  }
}

export async function clearQueueItems(status: 'Downloaded' | 'all'): Promise<boolean> {
  try {
    const statusParam = status === 'all' ? 'All' : status;
    const res = await request(`/queue/downloads/clear?status=${encodeURIComponent(statusParam)}`);
    return res.ok;
  } catch (err) {
    console.error("Clear queue failed:", err);
    return false;
  }
}

export async function triggerRetryFailed(): Promise<{ success: boolean }> {
  try {
    const res = await request('/queue/downloads/retryfailed');
    if (!res.ok) return { success: false };
    return await res.json().catch(() => ({ success: true }));
  } catch (err) {
    console.error("Retry failed API error:", err);
    return { success: false };
  }
}

export async function performQueueAction(local_id: string, action: 'cancel' | 'delete' | 'retry'): Promise<boolean> {
  try {
    const res = await request(`/queue/downloads/action?lid=${encodeURIComponent(local_id)}&action=${encodeURIComponent(action)}`, {
      method: 'POST'
    });
    return res.ok;
  } catch (err) {
    console.error(`Perform queue action (${action}) failed:`, err);
    return false;
  }
}

export async function fetchOTSConfig(): Promise<OTSConfig | null> {
  try {
    const res = await request('/config/get');
    if (!res.ok) throw new Error("Failed to fetch configuration");
    return await res.json();
  } catch (err) {
    console.error("Fetch OTS config failed:", err);
    return null;
  }
}

export async function updateOTSConfigValue(key: string, value: any): Promise<boolean> {
  try {
    const strVal = typeof value === 'object' ? JSON.stringify(value) : String(value);
    const res = await request(`/config/set?nkey=${encodeURIComponent(key)}&nvalue=${encodeURIComponent(strVal)}`, {
      method: 'POST'
    });
    return res.ok;
  } catch (err) {
    console.error("Update config value failed:", err);
    return false;
  }
}

export async function saveOTSConfig(): Promise<boolean> {
  try {
    const res = await request('/config/save', { method: 'POST' });
    return res.ok;
  } catch (err) {
    console.error("Save config failed:", err);
    return false;
  }
}

export async function resetOTSConfig(): Promise<OTSConfig | null> {
  try {
    const res = await request('/config/reset', { method: 'POST' });
    if (!res.ok) throw new Error("Reset config failed");
    return await res.json();
  } catch (err) {
    console.error("Reset config failed:", err);
    return null;
  }
}

export async function fetchAccounts(): Promise<AccountItem[]> {
  try {
    const res = await request('/accounts/get');
    if (!res.ok) throw new Error("Failed to fetch accounts");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error("Fetch accounts failed:", err);
    return [];
  }
}

export async function addAccountService(service: string, credentials: { username?: string; token?: string }): Promise<AccountItem | null> {
  try {
    const res = await request(`/accounts/add?service=${encodeURIComponent(service)}`, {
      method: 'POST',
      body: JSON.stringify(credentials)
    });
    if (!res.ok) throw new Error("Add account request failed");
    const data = await res.json();
    return data.account || (credentials as AccountItem);
  } catch (err) {
    console.error("Add account failed:", err);
    return null;
  }
}

export async function removeAccountUUID(uuid: string): Promise<boolean> {
  try {
    const res = await request(`/accounts/remove?luuid=${encodeURIComponent(uuid)}`, {
      method: 'POST'
    });
    return res.ok;
  } catch (err) {
    console.error("Remove account failed:", err);
    return false;
  }
}

export async function toggleMirrorSpotify(state: boolean): Promise<boolean> {
  try {
    const res = await request(`/spotify/mirror?state=${state ? 'true' : 'false'}`, {
      method: 'POST'
    });
    return res.ok;
  } catch (err) {
    console.error("Toggle mirror Spotify failed:", err);
    return false;
  }
}

export async function fetchServerLogs(): Promise<LogEntry[]> {
  try {
    const res = await request('/logs');
    if (!res.ok) throw new Error("Failed to fetch server logs");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error("Fetch server logs failed:", err);
    return [];
  }
}

