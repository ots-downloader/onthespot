import {
  OTSConfig,
  SearchResultItem,
  DownloadQueueItem,
  LogEntry,
  AccountItem,
} from "../types";

const config = {
  // Production UI is served by FastAPI, so use the current browser origin.
  // This also works behind Unraid's host/IP and reverse proxies.
  api_url: import.meta.env.VITE_API_URL || window.location.origin,
};
const STORAGE_KEY = "OTS_FASTAPI_URL";
const DEFAULT_URL = config.api_url;
console.log("Using backend URL:", DEFAULT_URL);

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
  options: RequestInit = {},
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
  version?: string;
  target: string;
}> {
  const target = getTargetBackendUrl();
  try {
    const res = await request("/config/get");
    if (!res.ok) throw new Error("Status check failed");
    const config = await res.json();
    return {
      status: "online",
      version: config.version || "FastAPI Engine",
      target,
    };
  } catch (err) {
    return { status: "offline", target };
  }
}

export async function searchMedia(
  query: string,
  filters?: Record<string, boolean>,
): Promise<boolean> {
  try {
    const qParam = query ? `?q=${encodeURIComponent(query)}` : "";
    const res = await request(`/query/url${qParam}`, {
      method: "POST",
      body: JSON.stringify(filters || {}),
    });
    if (!res.ok) throw new Error("Search request failed");
    return res.ok;
  } catch (err) {
    console.error("Search API connection failed:", err);
    throw err;
  }
}

export async function fetchSpotifyCatalog(
  query: string,
  types: string[] = ["track"],
): Promise<SearchResultItem[]> {
  try {
    const params = new URLSearchParams({
      q: query,
      types: types.join(","),
    });
    const res = await request(`/catalog/spotify?${params.toString()}`);
    if (!res.ok) throw new Error("Spotify catalogue search failed");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error("Spotify catalogue search failed:", err);
    return [];
  }
}

export async function fetchDownloadQueue(): Promise<DownloadQueueItem[]> {
  try {
    const res = await request("/queue/downloads");
    if (!res.ok) throw new Error("Failed to fetch queue");
    const data = await res.json();
    return Array.isArray(data)
      ? data
      : typeof data === "object" && data !== null
        ? Object.values(data)
        : [];
  } catch (err) {
    console.error("Fetch download queue failed:", err);
    return [];
  }
}

export async function fetchDownloadState(): Promise<{
  paused: boolean;
  active: number;
  speed: number;
  eta_seconds: number;
}> {
  try {
    const res = await request("/queue/downloads/state");
    if (!res.ok) throw new Error("Failed to fetch download state");
    return await res.json();
  } catch (err) {
    console.error("Fetch download state failed:", err);
    return { paused: false, active: 0, speed: 0, eta_seconds: 0 };
  }
}

export async function setDownloadsPaused(paused: boolean): Promise<boolean> {
  try {
    const res = await request(`/queue/downloads/pause?paused=${paused ? "true" : "false"}`, { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Set download pause failed:", err);
    return false;
  }
}

export async function reorderDownloadQueue(local_ids: string[]): Promise<boolean> {
  try {
    const res = await request("/queue/downloads/reorder", {
      method: "POST",
      body: JSON.stringify({ local_ids }),
    });
    return res.ok;
  } catch (err) {
    console.error("Reorder download queue failed:", err);
    return false;
  }
}

export type QueueBatchAction = "pause" | "resume" | "retry" | "cancel" | "delete" | "priority" | "profile";

export async function batchDownloadQueue(
  local_ids: string[],
  action: QueueBatchAction,
  options: { priority?: number; profile_id?: string } = {},
): Promise<boolean> {
  try {
    const res = await request("/queue/downloads/batch", {
      method: "POST",
      body: JSON.stringify({ local_ids, action, ...options }),
    });
    return res.ok;
  } catch (err) {
    console.error(`Batch queue action (${action}) failed:`, err);
    return false;
  }
}

export async function verifyDownloadQueue(
  local_ids: string[] = [],
  retry = true,
): Promise<{ checked: number; healthy: number; corrupt: number; retried: number }> {
  try {
    const res = await request("/queue/downloads/verify", {
      method: "POST",
      body: JSON.stringify({ local_ids, retry }),
    });
    if (!res.ok) throw new Error("Queue verification failed");
    return await res.json();
  } catch (err) {
    console.error("Verify download queue failed:", err);
    return { checked: 0, healthy: 0, corrupt: 0, retried: 0 };
  }
}

export interface DownloadProfile {
  id: string;
  name: string;
  format: string;
  bitrate: string;
  download_path: string;
}

export async function fetchDownloadProfiles(): Promise<{ active: string; profiles: DownloadProfile[] }> {
  try {
    const res = await request("/profiles");
    if (!res.ok) throw new Error("Failed to fetch download profiles");
    return await res.json();
  } catch (err) {
    console.error("Fetch download profiles failed:", err);
    return { active: "", profiles: [] };
  }
}

export async function setActiveDownloadProfile(profile_id: string): Promise<boolean> {
  try {
    const res = await request("/profiles/active", {
      method: "POST",
      body: JSON.stringify({ profile_id }),
    });
    if (!res.ok) return false;
    const data = await res.json().catch(() => ({}));
    return data.success !== false;
  } catch (err) {
    console.error("Set active download profile failed:", err);
    return false;
  }
}

export async function saveDownloadProfile(profile: DownloadProfile): Promise<DownloadProfile | null> {
  try {
    const res = await request("/profiles", { method: "POST", body: JSON.stringify(profile) });
    if (!res.ok) throw new Error("Save profile failed");
    const data = await res.json();
    return data?.success === false ? null : data;
  } catch (err) {
    console.error("Save download profile failed:", err);
    return null;
  }
}

export async function deleteDownloadProfile(profile_id: string): Promise<boolean> {
  try {
    const res = await request(`/profiles/${encodeURIComponent(profile_id)}`, { method: "DELETE" });
    if (!res.ok) return false;
    const data = await res.json().catch(() => ({}));
    return data.success !== false;
  } catch (err) {
    console.error("Delete download profile failed:", err);
    return false;
  }
}

export interface LibraryItem {
  id: string;
  path: string;
  relative_path: string;
  filename: string;
  format: string;
  size: number;
  modified_at: number;
  title: string;
  artist: string;
  album_artist?: string;
  album: string;
  genre: string;
  year: string;
  release_date?: string;
  lyrics?: string;
  has_artwork?: boolean;
  metadata_complete?: boolean;
  metadata_error?: string;
  track_number?: number | null;
  disc_number?: number | null;
  duration_seconds?: number | null;
  bitrate?: number | null;
  sample_rate?: number | null;
  channels?: number | null;
  duplicate_count?: number;
  is_duplicate?: boolean;
  source_url?: string;
  source_service?: string;
  source_type?: string;
  source_id?: string;
  playlist_name?: string;
  playlist_by?: string;
}

export interface LibraryResponse {
  items: LibraryItem[];
  count: number;
  duplicate_count: number;
  roots: string[];
  storage_used?: number;
  scanned_at: number;
}

export interface LibraryFilters {
  missingArtwork?: boolean;
  failedMetadata?: boolean;
  format?: string;
  artist?: string;
  genre?: string;
  dateFrom?: string;
  dateTo?: string;
}

const dateToTimestamp = (value?: string, endOfDay = false) => {
  if (!value) return "";
  const date = new Date(`${value}T${endOfDay ? "23:59:59" : "00:00:00"}`);
  return Number.isNaN(date.getTime()) ? "" : String(Math.floor(date.getTime() / 1000));
};

const libraryParams = (query: string, sort: string, sortDescending: boolean, duplicatesOnly: boolean, filters: LibraryFilters) => {
  const params = new URLSearchParams({ q: query, sort, sort_descending: String(sortDescending), duplicates_only: String(duplicatesOnly) });
  if (filters.missingArtwork) params.set("missing_artwork", "true");
  if (filters.failedMetadata) params.set("failed_metadata", "true");
  if (filters.format) params.set("file_format", filters.format);
  if (filters.artist) params.set("artist", filters.artist);
  if (filters.genre) params.set("genre", filters.genre);
  const from = dateToTimestamp(filters.dateFrom);
  const to = dateToTimestamp(filters.dateTo, true);
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  return params;
};

export function getLibraryCoverUrl(path: string, cacheKey?: number): string {
  const params = new URLSearchParams({ path });
  if (cacheKey) params.set("v", String(cacheKey));
  return `${getTargetBackendUrl()}/library/cover?${params.toString()}`;
}

export async function fetchLibrary(
  query = "",
  sort = "artist",
  sortDescending = false,
  duplicatesOnly = false,
  filters: LibraryFilters = {},
): Promise<LibraryResponse> {
  try {
    const params = libraryParams(query, sort, sortDescending, duplicatesOnly, filters);
    const res = await request(`/library?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch local library");
    return await res.json();
  } catch (err) {
    console.error("Fetch local library failed:", err);
    return { items: [], count: 0, duplicate_count: 0, roots: [], storage_used: 0, scanned_at: 0 };
  }
}

export async function scanLibrary(
  query = "",
  sort = "artist",
  sortDescending = false,
  duplicatesOnly = false,
  filters: LibraryFilters = {},
): Promise<LibraryResponse> {
  try {
    const params = libraryParams(query, sort, sortDescending, duplicatesOnly, filters);
    const res = await request(`/library/scan?${params.toString()}`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to scan local library");
    return await res.json();
  } catch (err) {
    console.error("Scan local library failed:", err);
    return { items: [], count: 0, duplicate_count: 0, roots: [], storage_used: 0, scanned_at: 0 };
  }
}

export async function verifyLibraryFiles(paths: string[] = []): Promise<{ checked: number; healthy: number; corrupt: number }> {
  try {
    const res = await request("/library/verify", { method: "POST", body: JSON.stringify({ paths }) });
    if (!res.ok) throw new Error("Library verification failed");
    return await res.json();
  } catch (err) {
    console.error("Verify library files failed:", err);
    return { checked: 0, healthy: 0, corrupt: 0 };
  }
}

export async function fetchMissingLibraryItems(query = ""): Promise<LibraryItem[]> {
  try {
    const params = new URLSearchParams({ q: query });
    const res = await request(`/library/missing?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch missing library items");
    const data = await res.json();
    return Array.isArray(data?.items) ? data.items : [];
  } catch (err) {
    console.error("Fetch missing library items failed:", err);
    return [];
  }
}

export async function openLibraryItem(path: string, action: "play" | "folder" = "folder"): Promise<boolean> {
  try {
    const res = await request("/library/open", { method: "POST", body: JSON.stringify({ path, action }) });
    return res.ok;
  } catch (err) {
    console.error("Open library item failed:", err);
    return false;
  }
}

export async function renameLibraryItem(path: string, new_name: string): Promise<LibraryItem | null> {
  try {
    const res = await request("/library/rename", { method: "POST", body: JSON.stringify({ path, new_name }) });
    if (!res.ok) {
      let detail = "Could not rename that file.";
      try {
        const payload = await res.json();
        if (typeof payload?.detail === "string") detail = payload.detail;
      } catch {
        // Keep the useful fallback when the server did not return JSON.
      }
      throw new Error(detail);
    }
    const data = await res.json();
    return data.item || null;
  } catch (err) {
    console.error("Rename library item failed:", err);
    throw err;
  }
}

export async function updateLibraryMetadata(
  path: string,
  changes: Partial<Pick<LibraryItem, "title" | "artist" | "album" | "genre" | "year" | "release_date" | "lyrics">> & {
    album_artist?: string;
    track_number?: string | number;
    disc_number?: string | number;
  },
): Promise<LibraryItem | null> {
  try {
    const res = await request("/library/metadata", { method: "POST", body: JSON.stringify({ path, ...changes }) });
    if (!res.ok) return null;
    const data = await res.json();
    return data.item || null;
  } catch (err) {
    console.error("Update library metadata failed:", err);
    return null;
  }
}

export async function uploadLibraryCover(path: string, file: File): Promise<LibraryItem | null> {
  try {
    const form = new FormData();
    form.append("path", path);
    form.append("cover", file);
    const res = await request("/library/cover", { method: "POST", body: form });
    if (!res.ok) return null;
    const data = await res.json();
    return data.item || null;
  } catch (err) {
    console.error("Update library cover failed:", err);
    return null;
  }
}

export async function createLibraryM3U(name: string, paths: string[]): Promise<string | null> {
  try {
    const res = await request("/library/m3u", { method: "POST", body: JSON.stringify({ name, paths }) });
    if (!res.ok) return null;
    const data = await res.json();
    return data.path || null;
  } catch (err) {
    console.error("Create library playlist failed:", err);
    return null;
  }
}

export async function requeueMissingLibraryItem(path: string): Promise<boolean> {
  try {
    const res = await request("/library/requeue", { method: "POST", body: JSON.stringify({ path }) });
    return res.ok;
  } catch (err) {
    console.error("Requeue missing library item failed:", err);
    return false;
  }
}

export async function enqueueDownload(
  item: SearchResultItem,
): Promise<{ success: boolean }> {
  try {
    const res = await request("/queue/downloads/add", {
      method: "POST",
      body: JSON.stringify({ item }),
    });
    if (!res.ok) throw new Error("Enqueue failed");
    return await res.json();
  } catch (err) {
    console.error("Enqueue download failed:", err);
    return { success: false };
  }
}

export async function clearQueueItems(
  status: "Downloaded" | "Failed" | "all",
): Promise<boolean> {
  try {
    const statusParam = status === "all" ? "All" : status;
    const res = await request(
      `/queue/downloads/clear?status=${encodeURIComponent(statusParam)}`,
    );
    return res.ok;
  } catch (err) {
    console.error("Clear queue failed:", err);
    return false;
  }
}

export async function triggerRetryFailed(): Promise<{ success: boolean }> {
  try {
    const res = await request("/queue/downloads/retryfailed");
    if (!res.ok) return { success: false };
    return await res.json().catch(() => ({ success: true }));
  } catch (err) {
    console.error("Retry failed API error:", err);
    return { success: false };
  }
}

export async function performQueueAction(
  local_id: string,
  action: "cancel" | "delete" | "retry",
): Promise<boolean> {
  try {
    const res = await request(
      `/queue/downloads/action?lid=${encodeURIComponent(local_id)}&action=${encodeURIComponent(action)}`,
      {
        method: "POST",
      },
    );
    return res.ok;
  } catch (err) {
    console.error(`Perform queue action (${action}) failed:`, err);
    return false;
  }
}

export async function fetchOTSConfig(): Promise<OTSConfig | null> {
  try {
    const res = await request("/config/get");
    if (!res.ok) throw new Error("Failed to fetch configuration");
    return await res.json();
  } catch (err) {
    console.error("Fetch OTS config failed:", err);
    return null;
  }
}

export async function updateOTSConfigValue(
  key: string,
  value: any,
): Promise<boolean> {
  try {
    const strVal =
      typeof value === "object" ? JSON.stringify(value) : String(value);
    const res = await request(
      `/config/set?nkey=${encodeURIComponent(key)}&nvalue=${encodeURIComponent(strVal)}`,
      {
        method: "POST",
      },
    );
    return res.ok;
  } catch (err) {
    console.error("Update config value failed:", err);
    return false;
  }
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

export async function resetOTSConfig(): Promise<OTSConfig | null> {
  try {
    const res = await request("/config/reset", { method: "POST" });
    if (!res.ok) throw new Error("Reset config failed");
    return await res.json();
  } catch (err) {
    console.error("Reset config failed:", err);
    return null;
  }
}

export async function fetchAccounts(): Promise<AccountItem[]> {
  try {
    const res = await request("/accounts/get");
    if (!res.ok) throw new Error("Failed to fetch accounts");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error("Fetch accounts failed:", err);
    return [];
  }
}

export interface AccountHealth {
  healthy: boolean;
  spotify: { configured: boolean; connected: boolean; status: string };
  configured_accounts: number;
  authenticated_accounts: number;
  missing_services: string[];
  checked_at: number;
}

export async function fetchAccountHealth(): Promise<AccountHealth> {
  try {
    const res = await request("/accounts/health");
    if (!res.ok) throw new Error("Failed to fetch account health");
    return await res.json();
  } catch (err) {
    console.error("Fetch account health failed:", err);
    return {
      healthy: false,
      spotify: { configured: false, connected: false, status: "Unavailable" },
      configured_accounts: 0,
      authenticated_accounts: 0,
      missing_services: [],
      checked_at: 0,
    };
  }
}

export async function reconnectAccounts(): Promise<boolean> {
  try {
    const res = await request("/accounts/reconnect", { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Reconnect accounts failed:", err);
    return false;
  }
}

export interface SystemDiagnostics {
  backend: { status: string; version: string };
  workers: Record<string, boolean>;
  queue: { pending: number; parsing: number; downloads: number; statuses: Record<string, number>; paused: boolean };
  ffmpeg: { path: string; available: boolean };
  disk: { total: number; free: number; used: number };
  rate_limit: { active: boolean; host: string; seconds_remaining: number; count: number };
  spotify_api: { configured: boolean; connected: boolean; status: string; rate_limited: boolean; seconds_remaining: number };
}

export interface UpdateAsset {
  name: string;
  size: number;
  download_url: string;
  platform: string;
}

export interface UpdateInfo {
  repository: string;
  current_version: string;
  latest_version: string;
  update_available: boolean;
  release_name: string;
  release_url: string;
  release_notes: string;
  published_at: string | null;
  prerelease: boolean;
  assets: UpdateAsset[];
  recommended_asset: UpdateAsset | null;
  install_supported: boolean;
  checked_at: number;
  error: string;
}

export interface UpdateInstallResult {
  success: boolean;
  supported: boolean;
  restart_required?: boolean;
  latest_version?: string;
  download_url?: string;
  message: string;
}

export async function fetchUpdateInfo(force = false): Promise<UpdateInfo | null> {
  try {
    const suffix = force ? "?force=true" : "";
    const res = await request(`/updates/check${suffix}`);
    if (!res.ok) throw new Error("Failed to check for updates");
    return await res.json();
  } catch (err) {
    console.error("Fetch update information failed:", err);
    return null;
  }
}

export async function installApplicationUpdate(): Promise<UpdateInstallResult | null> {
  try {
    const res = await request("/updates/install", { method: "POST" });
    const data = await res.json();
    if (!data || typeof data !== "object") throw new Error("Invalid update response");
    return data as UpdateInstallResult;
  } catch (err) {
    console.error("Install application update failed:", err);
    return null;
  }
}

export async function fetchSystemDiagnostics(): Promise<SystemDiagnostics | null> {
  try {
    const res = await request("/system/diagnostics");
    if (!res.ok) throw new Error("Failed to fetch diagnostics");
    return await res.json();
  } catch (err) {
    console.error("Fetch system diagnostics failed:", err);
    return null;
  }
}

export interface DownloadStatistics {
  totals: { downloads: number; bytes: number; success: number; failed: number; success_rate: number };
  formats: Record<string, number>;
  history: Array<{ id: string; timestamp: number; status: string; success: boolean; bytes: number; format: string; name: string; artist: string; error?: string }>;
  storage_used: number;
  library_tracks: number;
  queue_counts: Record<string, number>;
}

export async function fetchDownloadStatistics(): Promise<DownloadStatistics | null> {
  try {
    const res = await request("/statistics");
    if (!res.ok) throw new Error("Failed to fetch download statistics");
    return await res.json();
  } catch (err) {
    console.error("Fetch download statistics failed:", err);
    return null;
  }
}

export async function clearDownloadStatistics(): Promise<boolean> {
  try {
    const res = await request("/statistics/clear", { method: "POST" });
    if (!res.ok) throw new Error("Failed to clear download statistics");
    return true;
  } catch (err) {
    console.error("Clear download statistics failed:", err);
    return false;
  }
}

export async function exportBackup(): Promise<Record<string, unknown> | null> {
  try {
    const res = await request("/backup/export");
    if (!res.ok) throw new Error("Failed to export backup");
    return await res.json();
  } catch (err) {
    console.error("Export backup failed:", err);
    return null;
  }
}

export async function saveBackupFile(backup: Record<string, unknown>, directory = ""): Promise<string | null> {
  try {
    const res = await request("/backup/export-file", { method: "POST", body: JSON.stringify({ backup, directory }) });
    if (!res.ok) throw new Error("Failed to save backup file");
    return String((await res.json()).path || "") || null;
  } catch (err) {
    console.error("Save backup file failed:", err);
    return null;
  }
}

export async function fetchExportDirectory(): Promise<string> {
  try {
    const res = await request("/exports/location");
    if (!res.ok) throw new Error("Failed to fetch export location");
    return String((await res.json()).directory || "");
  } catch (err) {
    console.error("Fetch export location failed:", err);
    return "";
  }
}

export async function fetchPlaylistBackupDirectory(): Promise<string> {
  try {
    const res = await request("/exports/playlist-backup-location");
    if (!res.ok) throw new Error("Failed to fetch playlist backup location");
    return String((await res.json()).directory || "");
  } catch (err) {
    console.error("Fetch playlist backup location failed:", err);
    return "";
  }
}

export async function savePlaylistBackupDirectory(directory: string): Promise<string | null> {
  try {
    const res = await request("/exports/playlist-backup-location", { method: "POST", body: JSON.stringify({ directory }) });
    if (!res.ok) throw new Error("Failed to save playlist backup location");
    return String((await res.json()).directory || "") || null;
  } catch (err) {
    console.error("Save playlist backup location failed:", err);
    return null;
  }
}

export async function saveTextExport(filename: string, content: string, directory = ""): Promise<string | null> {
  try {
    const res = await request("/exports/write", { method: "POST", body: JSON.stringify({ filename, content, directory }) });
    if (!res.ok) throw new Error("Failed to save export file");
    return String((await res.json()).path || "") || null;
  } catch (err) {
    console.error("Save text export failed:", err);
    return null;
  }
}

export async function openExportFolder(playlistBackups = false): Promise<string | null> {
  try {
    const res = await request("/exports/open-folder", { method: "POST", body: JSON.stringify({ playlist_backups: playlistBackups }) });
    if (!res.ok) throw new Error("Failed to open export folder");
    return String((await res.json()).path || "") || null;
  } catch (err) {
    console.error("Open export folder failed:", err);
    return null;
  }
}

export async function importBackup(payload: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await request("/backup/import", { method: "POST", body: JSON.stringify(payload) });
    return res.ok;
  } catch (err) {
    console.error("Import backup failed:", err);
    return false;
  }
}

export async function exportSettings(): Promise<Record<string, unknown> | null> {
  try {
    const res = await request("/config/export");
    if (!res.ok) throw new Error("Failed to export settings");
    return await res.json();
  } catch (err) {
    console.error("Export settings failed:", err);
    return null;
  }
}

export async function importSettings(payload: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await request("/config/import", { method: "POST", body: JSON.stringify(payload) });
    return res.ok;
  } catch (err) {
    console.error("Import settings failed:", err);
    return false;
  }
}

export async function addAccountService(
  service: string,
  credentials: { username?: string; token?: string },
): Promise<AccountItem | null> {
  try {
    const res = await request(
      `/accounts/add?service=${encodeURIComponent(service)}`,
      {
        method: "POST",
        body: JSON.stringify(credentials),
      },
    );
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
    const res = await request(
      `/accounts/remove?luuid=${encodeURIComponent(uuid)}`,
      {
        method: "POST",
      },
    );
    return res.ok;
  } catch (err) {
    console.error("Remove account failed:", err);
    return false;
  }
}

export async function toggleMirrorSpotify(state: boolean): Promise<boolean> {
  try {
    const res = await request(
      `/spotify/mirror?state=${state ? "true" : "false"}`,
      {
        method: "POST",
      },
    );
    return res.ok;
  } catch (err) {
    console.error("Toggle mirror Spotify failed:", err);
    return false;
  }
}

export async function fetchServerLogs(): Promise<LogEntry[]> {
  try {
    const res = await request("/logs");
    if (!res.ok) throw new Error("Failed to fetch server logs");
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error("Fetch server logs failed:", err);
    return [];
  }
}

export async function check_api_version(): Promise<boolean> {
  try {
    const res = await request("/config/version");
    if (!res.ok) throw new Error("Failed to fetch api version");
    return Boolean(await res.json());
  } catch (err) {
    console.error("Fetch version failed:", err);
    return false;
  }
}

export type YouTubeAuthentication = {
  mode: "none" | "browser" | "cookie_file";
  browser?: string;
  cookie_file?: string;
};

export async function configureYouTubeAuthentication(authentication: YouTubeAuthentication): Promise<boolean> {
  try {
    const res = await request("/accounts/youtube-auth", {
      method: "POST",
      body: JSON.stringify(authentication),
    });
    return res.ok;
  } catch (err) {
    console.error("Configure YouTube authentication failed:", err);
    return false;
  }
}

export interface PlaylistAutomationStatus {
  configured: boolean;
  authenticated: boolean;
  redirect_uri: string;
  scope: string;
  credentials_source?: string;
  user?: { id?: string; display_name?: string; images?: Array<{ url?: string }> } | null;
}

export interface SpotifyPlaylistSummary {
  id: string;
  name: string;
  owner: string;
  editable: boolean;
  collaborative: boolean;
  public: boolean;
  tracks: number;
  image: string;
}

export interface PlaylistAutomationTrack {
  id: string;
  uri: string;
  name: string;
  artist: string;
  album: string;
  album_artist?: string;
  release_date: string;
  track_number?: number;
  disc_number?: number;
  duration_ms?: number;
  explicit?: boolean;
  popularity?: number;
  bpm?: number;
  energy?: number;
  danceability?: number;
  valence?: number;
  source_playlist?: string;
  source_playlists?: string[];
}

export interface PlaylistAutomationPreview {
  source_playlist_count: number;
  original_count: number;
  track_count: number;
  duplicates_removed: number;
  versions_replaced: number;
  tracks: PlaylistAutomationTrack[];
  uris: string[];
}

export interface PlaylistSortChange {
  id: string;
  type: "duplicate" | "replace";
  track_uri?: string;
  original_uri?: string;
  track_id?: string;
  newTitle?: string;
  newArtist?: string;
  newAlbum?: string;
  newDate?: string;
  remTitle?: string;
  remArtist?: string;
  remAlbum?: string;
  remDate?: string;
}

export interface PlaylistSortPreview {
  playlist_id: string;
  name: string;
  changes: PlaylistSortChange[];
  stats: {
    original_count: number;
    duplicates_removed: number;
    versions_replaced: number;
    sorted: boolean;
  };
  preview_uris?: string[];
}

export interface PlaylistAutomationSortRule {
  id: string;
  field: string;
  descending: boolean;
}

export interface PlaylistAutomationConfig {
  id: string;
  name: string;
  target_playlist_id: string;
  source_playlist_ids: string[];
  sort_rules: PlaylistAutomationSortRule[];
  sort_enabled?: boolean;
  deduplicate?: boolean;
  dupe_preference?: string;
  version_replacer?: boolean;
  version_preference?: string;
  exclude_keywords?: string[];
  include_liked_songs?: boolean;
  exclude_liked_songs?: boolean;
  sample_per_source?: number | null;
  update_mode?: "replace" | "merge" | "append";
  automatic_group?: string;
  preserve_local_files?: boolean;
}

export interface PlaylistAutomationSchedule {
  id: string;
  config_id: string;
  cron_expression: string;
  enabled: boolean;
  last_run?: number | string | null;
  next_run?: number | null;
}

export interface PlaylistAutomationHistoryItem {
  id: string;
  timestamp: number;
  action: string;
  playlist_id: string;
  playlist_name: string;
  tracks_processed: number;
}

export async function fetchPlaylistAutomationStatus(): Promise<PlaylistAutomationStatus | null> {
  try {
    const res = await request("/playlist-automation/status");
    if (!res.ok) throw new Error("Failed to fetch playlist automation status");
    return await res.json();
  } catch (err) {
    console.error("Fetch playlist automation status failed:", err);
    return null;
  }
}

export function getPlaylistAutomationLoginUrl(): string {
  return getEndpoint("/playlist-automation/login");
}

export async function configurePlaylistAutomation(payload: { client_id: string; client_secret: string; redirect_uri?: string }): Promise<PlaylistAutomationStatus | null> {
  try {
    const res = await request("/playlist-automation/config", { method: "POST", body: JSON.stringify(payload) });
    if (!res.ok) throw new Error("Could not save Spotify playlist credentials");
    return await res.json();
  } catch (err) {
    console.error("Configure playlist automation failed:", err);
    return null;
  }
}

export async function logoutPlaylistAutomation(): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/logout", { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Playlist automation logout failed:", err);
    return false;
  }
}

export async function fetchPlaylistAutomationPlaylists(): Promise<SpotifyPlaylistSummary[]> {
  try {
    const res = await request("/playlist-automation/playlists");
    if (!res.ok) throw new Error("Failed to fetch Spotify playlists");
    const data = await res.json();
    return Array.isArray(data.playlists) ? data.playlists : [];
  } catch (err) {
    console.error("Fetch Spotify playlists failed:", err);
    return [];
  }
}

export async function scanPlaylistAutomation(payload: Record<string, unknown>): Promise<PlaylistAutomationPreview | null> {
  try {
    const res = await request("/playlist-automation/scan", { method: "POST", body: JSON.stringify(payload) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to scan playlists");
    return await res.json();
  } catch (err) {
    console.error("Scan playlists failed:", err);
    return null;
  }
}

export async function scanSelectedPlaylistsForSorting(payload: Record<string, unknown>): Promise<PlaylistSortPreview[]> {
  try {
    const res = await request("/playlist-automation/sort/scan", { method: "POST", body: JSON.stringify(payload) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to scan playlists for sorting");
    const data = await res.json();
    return Array.isArray(data.playlists) ? data.playlists : [];
  } catch (err) {
    console.error("Scan selected playlists failed:", err);
    return [];
  }
}

export async function applySelectedPlaylistSorting(payload: Record<string, unknown>): Promise<{ success: boolean; playlist_name?: string; tracks_processed?: number } | null> {
  try {
    const res = await request("/playlist-automation/sort/apply", { method: "POST", body: JSON.stringify(payload) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to apply playlist sorting");
    return await res.json();
  } catch (err) {
    console.error("Apply playlist sorting failed:", err);
    return null;
  }
}

export async function applyPlaylistAutomation(payload: Record<string, unknown>): Promise<{ success: boolean; playlist_name?: string; tracks_processed?: number } | null> {
  try {
    const res = await request("/playlist-automation/apply", { method: "POST", body: JSON.stringify(payload) });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Failed to update playlist");
    return await res.json();
  } catch (err) {
    console.error("Apply playlist automation failed:", err);
    return null;
  }
}

export async function fetchPlaylistAutomationHistory(): Promise<PlaylistAutomationHistoryItem[]> {
  try {
    const res = await request("/playlist-automation/history");
    if (!res.ok) throw new Error("Failed to fetch playlist history");
    const data = await res.json();
    return Array.isArray(data.history) ? data.history : [];
  } catch (err) {
    console.error("Fetch playlist automation history failed:", err);
    return [];
  }
}

export async function restorePlaylistAutomationHistory(id: string): Promise<boolean> {
  try {
    const res = await request(`/playlist-automation/history/${encodeURIComponent(id)}/restore`, { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Restore playlist history failed:", err);
    return false;
  }
}

export async function clearPlaylistAutomationHistory(): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/history", { method: "DELETE" });
    return res.ok;
  } catch (err) {
    console.error("Clear playlist history failed:", err);
    return false;
  }
}

export async function deletePlaylistAutomationHistory(id: string): Promise<boolean> {
  try {
    const res = await request(`/playlist-automation/history/${encodeURIComponent(id)}`, { method: "DELETE" });
    return res.ok;
  } catch (err) {
    console.error("Delete playlist history failed:", err);
    return false;
  }
}

export async function comparePlaylistAutomation(playlist_ids: string[]): Promise<{ playlists_compared: number; duplicate_count: number; duplicates: Array<{ name: string; artist: string; track_id: string; found_in_playlists: string[] }> } | null> {
  try {
    const res = await request("/playlist-automation/compare", { method: "POST", body: JSON.stringify({ playlist_ids }) });
    if (!res.ok) throw new Error("Failed to compare playlists");
    return await res.json();
  } catch (err) {
    console.error("Compare playlists failed:", err);
    return null;
  }
}

export async function removePlaylistAutomationTrack(playlist_id: string, track_uri: string): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/remove-track", { method: "POST", body: JSON.stringify({ playlist_id, track_uri }) });
    return res.ok;
  } catch (err) {
    console.error("Remove playlist duplicate failed:", err);
    return false;
  }
}

export async function ignorePlaylistAutomationTrack(track: PlaylistAutomationTrack): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/ignored", { method: "POST", body: JSON.stringify(track) });
    return res.ok;
  } catch (err) {
    console.error("Ignore playlist track failed:", err);
    return false;
  }
}

export async function fetchIgnoredPlaylistAutomationTracks(): Promise<Array<{ track_id: string; name: string; artist: string }>> {
  try {
    const res = await request("/playlist-automation/ignored");
    if (!res.ok) throw new Error("Failed to fetch ignored tracks");
    const data = await res.json();
    return Array.isArray(data.items) ? data.items : [];
  } catch (err) {
    console.error("Fetch ignored playlist tracks failed:", err);
    return [];
  }
}

export async function removeIgnoredPlaylistAutomationTracks(track_ids: string[]): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/ignored", { method: "DELETE", body: JSON.stringify({ track_ids }) });
    return res.ok;
  } catch (err) {
    console.error("Remove ignored playlist tracks failed:", err);
    return false;
  }
}

export async function fetchPlaylistAutomationConfigs(): Promise<PlaylistAutomationConfig[]> {
  try {
    const res = await request("/playlist-automation/configs");
    if (!res.ok) throw new Error("Failed to fetch automation configs");
    const data = await res.json();
    return Array.isArray(data.configs) ? data.configs : [];
  } catch (err) {
    console.error("Fetch automation configs failed:", err);
    return [];
  }
}

export async function savePlaylistAutomationConfig(value: Partial<PlaylistAutomationConfig>): Promise<PlaylistAutomationConfig | null> {
  try {
    const res = await request("/playlist-automation/configs", { method: "POST", body: JSON.stringify(value) });
    if (!res.ok) throw new Error("Failed to save automation config");
    return await res.json();
  } catch (err) {
    console.error("Save automation config failed:", err);
    return null;
  }
}

export async function deletePlaylistAutomationConfig(id: string): Promise<boolean> {
  try {
    const res = await request(`/playlist-automation/configs/${encodeURIComponent(id)}`, { method: "DELETE" });
    return res.ok;
  } catch (err) {
    console.error("Delete automation config failed:", err);
    return false;
  }
}

export async function reorderPlaylistAutomationConfigs(config_ids: string[]): Promise<PlaylistAutomationConfig[] | null> {
  try {
    const res = await request("/playlist-automation/configs/reorder", { method: "POST", body: JSON.stringify({ config_ids }) });
    if (!res.ok) throw new Error("Failed to reorder automation configs");
    const data = await res.json();
    return Array.isArray(data.configs) ? data.configs : [];
  } catch (err) {
    console.error("Reorder automation configs failed:", err);
    return null;
  }
}

export async function runPlaylistAutomationConfig(id: string): Promise<boolean> {
  try {
    const res = await request(`/playlist-automation/configs/${encodeURIComponent(id)}/run`, { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Run automation config failed:", err);
    return false;
  }
}

export async function runAllPlaylistAutomationConfigs(): Promise<{ success: boolean; configs_processed?: number } | null> {
  try {
    const res = await request("/playlist-automation/configs/run-all", { method: "POST" });
    if (!res.ok) throw new Error("Failed to run playlist sorting configs");
    return await res.json();
  } catch (err) {
    console.error("Run all playlist configs failed:", err);
    return null;
  }
}

export async function fetchPlaylistAutomationSchedules(): Promise<PlaylistAutomationSchedule[]> {
  try {
    const res = await request("/playlist-automation/schedules");
    if (!res.ok) throw new Error("Failed to fetch automation schedules");
    const data = await res.json();
    return Array.isArray(data.schedules) ? data.schedules : [];
  } catch (err) {
    console.error("Fetch automation schedules failed:", err);
    return [];
  }
}

export async function savePlaylistAutomationSchedule(value: Partial<PlaylistAutomationSchedule>): Promise<PlaylistAutomationSchedule | null> {
  try {
    const res = await request("/playlist-automation/schedules", { method: "POST", body: JSON.stringify(value) });
    if (!res.ok) throw new Error("Failed to save automation schedule");
    return await res.json();
  } catch (err) {
    console.error("Save automation schedule failed:", err);
    return null;
  }
}

export async function deletePlaylistAutomationSchedule(id: string): Promise<boolean> {
  try {
    const res = await request(`/playlist-automation/schedules/${encodeURIComponent(id)}`, { method: "DELETE" });
    return res.ok;
  } catch (err) {
    console.error("Delete automation schedule failed:", err);
    return false;
  }
}

export async function fetchPlaylistAutomationBackups(): Promise<Array<{ filename: string; created_at: number; playlists: number }>> {
  try {
    const res = await request("/playlist-automation/backups");
    if (!res.ok) throw new Error("Failed to fetch playlist backups");
    const data = await res.json();
    return Array.isArray(data.backups) ? data.backups : [];
  } catch (err) {
    console.error("Fetch playlist backups failed:", err);
    return [];
  }
}

export async function createPlaylistAutomationBackup(playlist_ids: string[]): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/backups", { method: "POST", body: JSON.stringify({ playlist_ids }) });
    return res.ok;
  } catch (err) {
    console.error("Create playlist backup failed:", err);
    return false;
  }
}

export async function restorePlaylistAutomationBackup(filename: string, target_playlist_id = ""): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/backups/restore", { method: "POST", body: JSON.stringify({ filename, target_playlist_id }) });
    return res.ok;
  } catch (err) {
    console.error("Restore playlist backup failed:", err);
    return false;
  }
}

export function downloadPlaylistAutomationConfig(): void {
  window.open(getEndpoint("/playlist-automation/export/config"), "_blank");
}

export async function importPlaylistAutomationConfig(value: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await request("/playlist-automation/import/config", { method: "POST", body: JSON.stringify(value) });
    return res.ok;
  } catch (err) {
    console.error("Import playlist automation config failed:", err);
    return false;
  }
}

export async function exportPlaylistAutomationCsv(tracks: PlaylistAutomationTrack[]): Promise<Blob | null> {
  try {
    const res = await request("/playlist-automation/export/csv", { method: "POST", body: JSON.stringify({ tracks }) });
    if (!res.ok) throw new Error("Failed to export playlist CSV");
    return await res.blob();
  } catch (err) {
    console.error("Export playlist CSV failed:", err);
    return null;
  }
}

export async function exportSelectedPlaylistsCsv(playlist_ids: string[]): Promise<Blob | null> {
  try {
    const res = await request("/playlist-automation/export/playlists-csv", { method: "POST", body: JSON.stringify({ playlist_ids }) });
    if (!res.ok) throw new Error("Failed to export selected playlists");
    return await res.blob();
  } catch (err) {
    console.error("Export selected playlists failed:", err);
    return null;
  }
}

export function getSelectedPlaylistsCsvUrl(playlist_ids: string[]): string {
  return `${getEndpoint("/playlist-automation/export/playlists-csv")}?playlist_ids=${encodeURIComponent(playlist_ids.join(","))}`;
}

export async function saveSelectedPlaylistsCsv(playlist_ids: string[], directory = ""): Promise<string | null> {
  try {
    const res = await request("/playlist-automation/export/playlists-csv-file", { method: "POST", body: JSON.stringify({ playlist_ids, directory }) });
    if (!res.ok) throw new Error("Failed to save selected playlists CSV");
    return String((await res.json()).path || "") || null;
  } catch (err) {
    console.error("Save selected playlists CSV failed:", err);
    return null;
  }
}

export async function savePlaylistAutomationConfigFile(directory = ""): Promise<string | null> {
  try {
    const res = await request("/playlist-automation/export/config-file", { method: "POST", body: JSON.stringify({ directory }) });
    if (!res.ok) throw new Error("Failed to save playlist automation config");
    return String((await res.json()).path || "") || null;
  } catch (err) {
    console.error("Save playlist automation config failed:", err);
    return null;
  }
}
