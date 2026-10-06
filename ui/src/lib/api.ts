import {
  AccountHealth,
  AccountItem,
  DownloadProfile,
  DownloadQueueItem,
  LogEntry,
  OTSConfig,
  PendingQueueItem,
  QueueBatchAction,
  SpotifyCompanionPairing,
  SystemDiagnostics,
  UpdateInfo,
  YouTubeAuthentication,
  YouTubeAuthenticationStatus
} from "../types";

const config = {
  // Production UI is served by FastAPI, so use the current browser origin.
  // This also works behind Unraid's host/IP and reverse proxies.
  api_url: import.meta.env.VITE_API_URL || window.location.origin,
};

const DEFAULT_URL = config.api_url;
const STORAGE_KEY = "OTS_FASTAPI_URL";

export const DEFAULT_CONFIG: OTSConfig = await fetchOTSConfig()

// Default Download Profiles
export const DEFAULT_PROFILES: DownloadProfile[] = await fetchProfiles();

export function getTargetBackendUrl(): string {
  if (typeof window === "undefined") return DEFAULT_URL;
  return localStorage.getItem(STORAGE_KEY) || DEFAULT_URL;
}

export function setTargetBackendUrl(url: string): void {
  if (typeof window === "undefined") return;
  const cleaned = url.trim().replace(/\/$/, "");
  if (!cleaned) {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, cleaned);
  }
}

function getEndpoint(path: string): string {
  const base = getTargetBackendUrl().replace(/\/$/, "");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

async function request(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const url = getEndpoint(path);
  const headers = new Headers(options.headers || {});
  if (
    !headers.has("Content-Type") &&
    options.body &&
    !(typeof FormData !== "undefined" && options.body instanceof FormData)
  ) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, { ...options, headers });
}

export async function checkServerHealth(): Promise<{
  status: "online" | "offline";
  version: string;
  target: string;
}> {
  const target = getTargetBackendUrl();
  if (target) {
    try {
      const res = await fetch(`${target}/config/get`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        const data = await res.json();
        return { status: "online", version: data.version || "FastAPI Engine", target };
      }
    } catch {
      // Offline
    }
  }
  return {
    status: "offline",
    version: "",
    target: target || "No target backend URL configured",
  };
}

export async function testBackendConnection(targetUrl: string): Promise<boolean> {
  const target = getTargetBackendUrl();
  if (!target) return false;
  try {
    const res = await fetch(`${target}/config/get`, { signal: AbortSignal.timeout(2500) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchOTSConfig(): Promise<OTSConfig> {
  const res = await request("/config/get");
  if (!res.ok) throw new Error("Failed to fetch configuration");
  return await res.json();
}

export async function saveOTSConfig(): Promise<boolean> {
  try {
    const res = await request("/config/save", { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Save config failed:", err);
    return false;
  }
}

export async function resetOTSConfig(): Promise<OTSConfig> {
  const res = await request("/config/reset", { method: "POST" });
  if (!res.ok) throw new Error("Failed to reset configuration");
  return await res.json();
}
export async function updateOTSConfigValue<K extends keyof OTSConfig>(
  key: K,
  value: OTSConfig[K]
): Promise<boolean> {
  const payload = {
    [key]: value,
  };

  const response = await request(`/config/set`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json();
    console.error(
      errorData.detail 
        ? (typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail))
        : `Failed to update setting '${String(key)}' (Status ${response.status})`
    );
    return false
  } else {
    return response.ok
  }
}

export async function fetchDownloadQueue(): Promise<DownloadQueueItem[]> {
  const res = await request("/queue/downloads");
  if (!res.ok) throw new Error("Failed to fetch download queue");
  const data = await res.json();
  return Array.isArray(data) ? data : Object.values(data);
}

export async function addToQueue(
  item: string
): Promise<any> {

  const res = await request(`/query/url?q=${item}`, {
    method: "POST"
  });
  if (!res.ok) throw new Error("Failed to add to queue");
  return res.body
}

export async function executeQueueAction(
  local_id: number,
  action: "cancel" | "delete" | "retry"
): Promise<void> {
  const res = await request(
    `/queue/downloads/action?lid=${encodeURIComponent(local_id)}&action=${encodeURIComponent(action)}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to execute queue action");
}

export async function executeQueueBatchAction(
  local_ids: number[],
  action: QueueBatchAction,
  options?: { profile_id?: string }
): Promise<void> {
  const res = await request("/queue/downloads/batch", {
    method: "POST",
    body: JSON.stringify({ local_ids, action, ...options }),
  });
  if (!res.ok) throw new Error("Failed to execute batch action");
}

export async function clearCompletedDownloads(): Promise<void> {
  const res = await request("/queue/downloads/clear?status=Downloaded");
  if (!res.ok) throw new Error("Failed to clear completed downloads");
}

export async function clearFailedDownloads(): Promise<void> {
  const res = await request("/queue/downloads/clear?status=Failed");
  if (!res.ok) throw new Error("Failed to clear failed downloads");
}

export async function retryFailedDownloads(): Promise<void> {
  const res = await request("/queue/downloads/retryfailed");
  if (!res.ok) throw new Error("Failed to retry failed downloads");
}

export async function toggleQueuePause(): Promise<boolean> {
  throw new Error("Not implemented yet")
  const diag = await fetchSystemDiagnostics();
  const currentPaused = diag.queue.paused;
  const newPaused = !currentPaused;
  const res = await request(`/queue/downloads/pause?paused=${newPaused ? "true" : "false"}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to toggle queue pause");
  return newPaused;
}

export async function fetchAccounts(): Promise<AccountItem[]> {
  const res = await request("/accounts/get");
  if (!res.ok) throw new Error("Failed to fetch accounts");
  return await res.json();
}

export async function addAccount(
  service: string,
  credentials: { username?: string; token?: string; password?: string }
): Promise<AccountItem> {
  if (credentials.password && !credentials.token) {
    credentials.token = credentials.password
  }
  const res = await request(`/accounts/add?service=${encodeURIComponent(service)}`, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  if (!res.ok) throw new Error("Failed to add account");
  const data = await res.json();
  return data.account || data;
}

export async function removeAccount(uuid: string): Promise<boolean> {
  const res = await request(`/accounts/remove?luuid=${encodeURIComponent(uuid)}`, {
    method: "POST",
  });
  return res.ok;
}

export async function reconnectAccounts(): Promise<boolean> {
  const res = await request("/accounts/reconnect", { method: "POST" });
  return res.ok;
}

export async function createSpotifyCompanionPairing(): Promise<SpotifyCompanionPairing | null> {
  const res = await request("/accounts/spotify/companion/pair", { method: "POST" });
  if (!res.ok) throw new Error("Failed to create companion pairing");
  return await res.json();
}

export async function fetchYouTubeAuthenticationStatus(): Promise<YouTubeAuthenticationStatus | null> {
  const res = await request("/accounts/youtube-auth/status");
  if (!res.ok) return null;
  return await res.json();
}

export async function configureYouTubeAuthentication(
  authentication: YouTubeAuthentication
): Promise<boolean> {
  const res = await request("/accounts/youtube-auth", {
    method: "POST",
    body: JSON.stringify(authentication),
  });
  return res.ok;
}

export async function uploadYouTubeCookies(
  file: File
): Promise<YouTubeAuthenticationStatus | null> {
  const form = new FormData();
  form.append("cookies", file);
  const res = await request("/accounts/youtube-auth/upload", {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("Failed to upload YouTube cookies");
  return await res.json();
}

export async function fetchAccountHealth(): Promise<AccountHealth> {
  const res = await request("/accounts/health");
  if (!res.ok) throw new Error("Failed to fetch account health");
  return await res.json();
}

export async function fetchProfiles(): Promise<DownloadProfile[]> {
  const res = await request("/profiles");
  if (!res.ok) throw new Error("Failed to fetch download profiles");
  const data = await res.json();
  return Array.isArray(data) ? data : data.profiles || [];
}

export async function saveProfile(profile: DownloadProfile): Promise<DownloadProfile> {
  const res = await request("/profiles", {
    method: "POST",
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error("Failed to save profile");
  return await res.json();
}

export async function deleteProfile(profileId: string): Promise<boolean> {
  const res = await request(`/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
  return res.ok;
}

export async function activateProfile(profileId: string): Promise<boolean> {
  const res = await request("/profiles/active", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
  });
  return res.ok;
}

export async function fetchSystemDiagnostics(): Promise<SystemDiagnostics> {
  const res = await request("/system/diagnostics");
  if (!res.ok) throw new Error("Failed to fetch system diagnostics");
  return await res.json();
}

export async function fetchUpdateInfo(force = false): Promise<UpdateInfo> {
  const suffix = force ? "?force=true" : "";
  const res = await request(`/updates/check${suffix}`);
  if (!res.ok) throw new Error("Failed to check for updates");
  return await res.json();
}

export async function fetchLogs(): Promise<LogEntry[]> {
  const res = await request("/logs");
  if (!res.ok) throw new Error("Failed to fetch server logs");
  return await res.json();
}

export async function clearLogs(): Promise<void> {
  const res = await request("/logs/clear", { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear server logs");
}


export async function fetchPendingQueue(): Promise<PendingQueueItem[]> {
  const res = await request("/queue/pending");
  if (!res.ok) throw new Error("Failed to fetch pending queue");
  const data = await res.json();
  const items: DownloadQueueItem[] = data.items;
  return items.map((item) => ({
    id: String(item.local_id),
    name: item.name || `Track #${item.playlist_number || item.local_id}`,
    artist: item.artist || "Metadata will load when downloading",
    album: item.album,
    playlist_name: item.playlist_name,
    thumbnail: item.thumbnail,
    item_service: item.item_service,
    item_type: item.item_type,
    format: item.download_profile.format.toUpperCase(),
    bitrate: `${item.download_profile.bitrate} kbps`,
    profile_id: item.download_profile.id,
    profile_name: item.download_profile.name,
    url: item.item_url,
    status: item.item_status === "Waiting" ? "ready" : "error",
    created_at: "",
    error: item.error,
  }));
}


export async function removePendingItems(pendingIds: string[]): Promise<boolean> {
  const res = await request("/queue/pending/remove", {
    method: "POST",
    body: JSON.stringify({ pending_ids: pendingIds }),
  });
  return res.ok;
}

export async function clearAllPending(): Promise<void> {
  const res = await request("/queue/pending/clear", { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear all pending items");
}
