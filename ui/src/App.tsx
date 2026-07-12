import React, { useEffect, useState, useCallback, useRef } from "react";
import { Navbar, NavTab } from "./components/Navbar";
import { SearchDashboard } from "./components/SearchDashboard";
import { BrowseSpotify } from "./components/BrowseSpotify";
import { LibraryPage } from "./components/LibraryPage";
import { StatisticsPanel } from "./components/StatisticsPanel";
import { DownloadQueue } from "./components/DownloadQueue";
import { SettingsPage } from "./components/SettingsPage";
import { AccountsManager } from "./components/AccountsManager";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { LogViewer } from "./components/LogViewer";
import { NotificationBanner } from "./components/NotificationBanner";
import { NotificationHistory } from "./components/NotificationHistory";
import {
  OTSConfig,
  DownloadQueueItem,
  AccountItem,
  LogEntry,
  NotificationBannerItem,
  SearchResultItem,
  NotificationContent,
  CustomTheme,
  CustomThemePalette,
  DEFAULT_CUSTOM_THEME,
  SavedCustomTheme,
  ThemePreset,
  ThemeMode,
} from "./types";
import { useNotifications } from "./lib/notifications";
import {
  fetchOTSConfig,
  fetchDownloadQueue,
  fetchAccounts,
  fetchAccountHealth,
  reconnectAccounts,
  fetchServerLogs,
  searchMedia,
  enqueueDownload,
  clearQueueItems,
  triggerRetryFailed,
  performQueueAction,
  updateOTSConfigValue,
  saveOTSConfig,
  resetOTSConfig,
  addAccountService,
  removeAccountUUID,
  check_api_version,
  fetchUpdateInfo,
  batchDownloadQueue,
  verifyDownloadQueue,
  fetchDownloadState,
  setDownloadsPaused,
  reorderDownloadQueue,
  fetchDownloadProfiles,
  setActiveDownloadProfile,
  saveDownloadProfile,
  deleteDownloadProfile,
} from "./lib/api";
import type { DownloadProfile, QueueBatchAction } from "./lib/api";
import type { AccountHealth } from "./lib/api";

const isThemePreset = (value: string | null): value is ThemePreset =>
  value === "spotify" ||
  value === "midnight" ||
  value === "forest" ||
  value === "light" ||
  value === "ocean" ||
  value === "sunset" ||
  value === "violet" ||
  value === "rose" ||
  value === "custom";

const isHexColor = (value: unknown): value is string =>
  typeof value === "string" && /^#[0-9a-f]{6}$/i.test(value);

const getHexLuminance = (hex: string): number => {
  const channels = [1, 3, 5].map((offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255);
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
};

const isThemeMode = (value: unknown): value is ThemeMode =>
  value === "light" || value === "dark";

const isCustomThemePalette = (value: unknown): value is CustomThemePalette => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<CustomThemePalette>;
  return (
    isHexColor(candidate.background) &&
    isHexColor(candidate.surface) &&
    isHexColor(candidate.elevated) &&
    isHexColor(candidate.accent) &&
    isHexColor(candidate.text) &&
    isHexColor(candidate.muted)
  );
};

const isCustomTheme = (value: unknown): value is CustomTheme => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<CustomTheme>;
  return (
    isThemeMode(candidate.mode) &&
    isCustomThemePalette(candidate.dark) &&
    isCustomThemePalette(candidate.light)
  );
};

const cloneDefaultCustomTheme = (): CustomTheme => ({
  mode: DEFAULT_CUSTOM_THEME.mode,
  dark: { ...DEFAULT_CUSTOM_THEME.dark },
  light: { ...DEFAULT_CUSTOM_THEME.light },
});

const migrateLegacyCustomTheme = (value: unknown): CustomTheme | null => {
  if (!value || typeof value !== "object") return null;
  const legacy = value as Partial<CustomThemePalette> & { mode?: unknown };
  if (
    !isThemeMode(legacy.mode) ||
    !isHexColor(legacy.background) ||
    !isHexColor(legacy.surface) ||
    !isHexColor(legacy.elevated) ||
    !isHexColor(legacy.accent) ||
    !isHexColor(legacy.text) ||
    !isHexColor(legacy.muted)
  ) {
    return null;
  }

  const legacyPalette: CustomThemePalette = {
    background: legacy.background,
    surface: legacy.surface,
    elevated: legacy.elevated,
    accent: legacy.accent,
    text: legacy.text,
    muted: legacy.muted,
  };
  const legacyLooksLight = getHexLuminance(legacy.background) > getHexLuminance(legacy.text);

  return {
    mode: legacy.mode,
    dark: !legacyLooksLight
      ? legacyPalette
      : { ...DEFAULT_CUSTOM_THEME.dark, accent: legacy.accent },
    light: legacyLooksLight
      ? legacyPalette
      : { ...DEFAULT_CUSTOM_THEME.light, accent: legacy.accent },
  };
};

const readStoredThemePreset = (): ThemePreset | null => {
  try {
    const stored = window.localStorage.getItem("ots-theme-preset");
    return isThemePreset(stored) ? stored : null;
  } catch {
    return null;
  }
};

const readStoredCustomTheme = (): CustomTheme => {
  try {
    const stored = window.localStorage.getItem("ots-custom-theme");
    if (stored) {
      const parsed: unknown = JSON.parse(stored);
      if (isCustomTheme(parsed)) return parsed;
      const migrated = migrateLegacyCustomTheme(parsed);
      if (migrated) return migrated;
    }
  } catch {
    // Use the default palette when browser storage is unavailable or invalid.
  }
  return cloneDefaultCustomTheme();
};

const CUSTOM_THEMES_STORAGE_KEY = "ots-custom-themes";

const cloneCustomTheme = (theme: CustomTheme): CustomTheme => ({
  mode: theme.mode,
  dark: { ...theme.dark },
  light: { ...theme.light },
});

const isSavedCustomTheme = (value: unknown): value is SavedCustomTheme => {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<SavedCustomTheme>;
  return (
    typeof candidate.id === "string" &&
    candidate.id.length > 0 &&
    typeof candidate.name === "string" &&
    candidate.name.trim().length > 0 &&
    isCustomTheme(candidate.theme) &&
    typeof candidate.updatedAt === "number" &&
    Number.isFinite(candidate.updatedAt)
  );
};

const readStoredCustomThemes = (): SavedCustomTheme[] => {
  try {
    const stored = window.localStorage.getItem(CUSTOM_THEMES_STORAGE_KEY);
    if (!stored) return [];
    const parsed: unknown = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isSavedCustomTheme).slice(0, 50);
  } catch {
    return [];
  }
};

const persistStoredCustomThemes = (themes: SavedCustomTheme[]) => {
  try {
    window.localStorage.setItem(CUSTOM_THEMES_STORAGE_KEY, JSON.stringify(themes));
  } catch {
    // Saved themes still remain available for this session when storage is unavailable.
  }
};

const createCustomThemeId = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
};

const readStoredThemeMode = (): ThemeMode | null => {
  try {
    const stored = window.localStorage.getItem("ots-theme-mode");
    return isThemeMode(stored) ? stored : null;
  } catch {
    return null;
  }
};

const getCustomThemeStyle = (theme: CustomTheme, mode: ThemeMode = theme.mode): React.CSSProperties => {
  const palette = theme[mode];
  return {
    "--spotify-black": palette.background,
    "--spotify-surface": palette.surface,
    "--spotify-surface-elevated": palette.elevated,
    "--spotify-text": palette.text,
    "--spotify-muted": palette.muted,
    "--spotify-green": palette.accent,
    "--spotify-green-bright": `color-mix(in srgb, ${palette.accent} 78%, white)`,
    "--ots-green-contrast": `color-mix(in srgb, ${palette.accent} 72%, ${palette.background})`,
    "--ots-green-contrast-hover": `color-mix(in srgb, ${palette.accent} 84%, ${palette.background})`,
    "--ots-border": `color-mix(in srgb, ${palette.text} 18%, ${palette.background})`,
    "--ots-border-strong": `color-mix(in srgb, ${palette.text} 30%, ${palette.background})`,
    "--ots-field": `color-mix(in srgb, ${palette.surface} 72%, ${palette.background})`,
    "--ots-danger": mode === "light" ? "#b42318" : "#ff7b7b",
    "--ots-on-accent": getHexLuminance(palette.accent) > 0.55 ? "#181818" : "#ffffff",
  } as React.CSSProperties;
};

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("dashboard");
  const [config, setConfig] = useState<OTSConfig | null>(null);
  const [queue, setQueue] = useState<DownloadQueueItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [accountHealth, setAccountHealth] = useState<AccountHealth | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const { notifications, history, dismissNotification, clearHistory, lastStatusChange } = useNotifications("webui");
  const [wsConnected, setWsConnected] = useState(false);
  const [themePreset, setThemePreset] = useState<ThemePreset>(() => readStoredThemePreset() ?? "spotify");
  const [customTheme, setCustomTheme] = useState<CustomTheme>(() => readStoredCustomTheme());
  const [savedCustomThemes, setSavedCustomThemes] = useState<SavedCustomTheme[]>(() => readStoredCustomThemes());
  const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
    const storedMode = readStoredThemeMode();
    if (storedMode) return storedMode;
    const storedPreset = readStoredThemePreset();
    if (storedPreset === "light") return "light";
    if (storedPreset === "custom") return readStoredCustomTheme().mode;
    return "dark";
  });
  const isDarkMode: "light" | "dark" = themeMode;
  const [hasNewVersion, SetNewVersion] = useState(false);
  const [downloadsPaused, setDownloadsPausedState] = useState(false);
  const [downloadSpeed, setDownloadSpeed] = useState(0);
  const [downloadEta, setDownloadEta] = useState(0);
  const [profiles, setProfiles] = useState<DownloadProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState("");
  const themePersistenceRef = useRef<Promise<void>>(Promise.resolve());
  const profileMutationRef = useRef(0);

  // Initial load
  const loadData = useCallback(async () => {
    const [cfg, qData, accData, healthData, logData, downloadState, profileData] = await Promise.all([
      fetchOTSConfig(),
      fetchDownloadQueue(),
      fetchAccounts(),
      fetchAccountHealth(),
      fetchServerLogs(),
      fetchDownloadState(),
      fetchDownloadProfiles(),
    ]);
    if (cfg) {
      setWsConnected(true); // Set Connection status
      setConfig(cfg._Config__config);
      // Respect a browser-selected preset; otherwise initialize from backend theme state.
      if (!readStoredThemePreset()) {
        const backendThemeMode: ThemeMode = cfg._Config__config.theme === "dark" ? "dark" : "light";
        setThemePreset(backendThemeMode === "dark" ? "spotify" : "light");
        setThemeMode(backendThemeMode);
      }
    }
    if (qData) setQueue(qData);
    if (accData) setAccounts(accData);
    setAccountHealth(healthData);
    if (logData) setLogs(logData);
    setDownloadsPausedState(downloadState.paused);
    setDownloadSpeed(downloadState.speed);
    setDownloadEta(downloadState.eta_seconds);
    // Do not let a slow initial request overwrite a selection made while the
    // settings page was opening.
    if (profileMutationRef.current === 0) {
      setProfiles(profileData.profiles);
      setActiveProfile(profileData.active);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  useEffect(() => {
    if (isDarkMode === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, [isDarkMode]);

  useEffect(() => {
    if (!config || config.check_for_updates === false) {
      SetNewVersion(false);
      return;
    }
    let mounted = true;
    const checkUpdates = async () => {
      const status = await fetchUpdateInfo();
      if (mounted) SetNewVersion(Boolean(status?.update_available));
    };
    void checkUpdates();
    const interval = window.setInterval(() => void checkUpdates(), 6 * 60 * 60 * 1000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [config?.check_for_updates]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        const input = document.getElementById("global-search") as HTMLInputElement | null;
        input?.focus();
      }
    };
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  useEffect(() => {
    async function fetchQueueData() {
      const q = await fetchDownloadQueue();
      if (q) setQueue(q);
      const state = await fetchDownloadState();
      setDownloadsPausedState(state.paused);
      setDownloadSpeed(state.speed);
      setDownloadEta(state.eta_seconds);
    }
    fetchQueueData();
  }, [lastStatusChange]);

  useEffect(() => {
    let mounted = true;
    const refreshAccountHealth = async () => {
      const [freshAccounts, freshHealth] = await Promise.all([fetchAccounts(), fetchAccountHealth()]);
      if (mounted) {
        setAccounts(freshAccounts);
        setAccountHealth(freshHealth);
      }
    };
    void refreshAccountHealth();
    const interval = window.setInterval(() => void refreshAccountHealth(), 5000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const persistThemeMode = (newMode: ThemeMode) => {
    themePersistenceRef.current = themePersistenceRef.current
      .catch(() => undefined)
      .then(async () => {
        if (!config) return;
        await updateOTSConfigValue("theme", newMode);
        setConfig((prev) => (prev ? { ...prev, theme: newMode } : null));
        await saveOTSConfig();
      });
    return themePersistenceRef.current;
  };

  const handleThemeChange = async (newPreset: ThemePreset) => {
    // Presets choose the colour palette; the Light/Dark control owns the mode.
    // Keeping these independent prevents clicking a preset from changing mode.
    setThemePreset(newPreset);
    try {
      window.localStorage.setItem("ots-theme-preset", newPreset);
      window.localStorage.setItem("ots-theme-mode", themeMode);
    } catch {
      // Theme still applies for this session when storage is unavailable.
    }
  };

  const handleCustomThemeChange = async (newCustomTheme: CustomTheme) => {
    setCustomTheme(newCustomTheme);
    setThemePreset("custom");
    setThemeMode(newCustomTheme.mode);
    try {
      window.localStorage.setItem("ots-custom-theme", JSON.stringify(newCustomTheme));
      window.localStorage.setItem("ots-theme-preset", "custom");
      window.localStorage.setItem("ots-theme-mode", newCustomTheme.mode);
    } catch {
      // Theme still applies for this session when storage is unavailable.
    }
    await persistThemeMode(newCustomTheme.mode);
  };

  const handleSaveCustomTheme = async (name: string): Promise<boolean> => {
    const normalizedName = name.trim();
    if (!normalizedName) return false;

    const snapshot: CustomTheme = cloneCustomTheme({ ...customTheme, mode: themeMode });
    const existing = savedCustomThemes.find(
      (savedTheme) => savedTheme.name.toLocaleLowerCase() === normalizedName.toLocaleLowerCase(),
    );
    const nextTheme: SavedCustomTheme = {
      id: existing?.id ?? createCustomThemeId(),
      name: normalizedName,
      theme: snapshot,
      updatedAt: Date.now(),
    };
    const nextThemes = existing
      ? savedCustomThemes.map((savedTheme) => savedTheme.id === existing.id ? nextTheme : savedTheme)
      : [nextTheme, ...savedCustomThemes].slice(0, 50);

    setSavedCustomThemes(nextThemes);
    persistStoredCustomThemes(nextThemes);
    return true;
  };

  const handleLoadCustomTheme = async (savedTheme: SavedCustomTheme) => {
    await handleCustomThemeChange({
      ...cloneCustomTheme(savedTheme.theme),
      mode: themeMode,
    });
  };

  const handleDeleteCustomTheme = async (id: string) => {
    const nextThemes = savedCustomThemes.filter((savedTheme) => savedTheme.id !== id);
    setSavedCustomThemes(nextThemes);
    persistStoredCustomThemes(nextThemes);
  };

  const handleThemeModeChange = async (newMode: ThemeMode) => {
    setThemeMode(newMode);
    if (themePreset === "custom") {
      await handleCustomThemeChange({ ...customTheme, mode: newMode });
      return;
    }
    try {
      window.localStorage.setItem("ots-theme-mode", newMode);
    } catch {
      // Theme still applies for this session when storage is unavailable.
    }
    await persistThemeMode(newMode);
  };

  const toggleTheme = async () => {
    await handleThemeModeChange(isDarkMode === "dark" ? "light" : "dark");
  };

  const checkNewVersion = async () => {
    const status = await fetchUpdateInfo(true);
    if (status) {
      SetNewVersion(Boolean(status.update_available));
      return;
    }
    const latest = await check_api_version();
    SetNewVersion(!latest);
  };

  const handleDismissNotification = (id: string) => {
    dismissNotification(id);
  };

  const handleDownloadItem = async (
    query: string,
    filters?: Record<string, boolean>,
  ): Promise<boolean> => {
    const res = await searchMedia(query, filters);
    if (res) {
      setActiveTab("queue");
    }
    return res;
  };

  const handleClearCompleted = async () => {
    await clearQueueItems("Downloaded");
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleClearFailed = async () => {
    await clearQueueItems("Failed");
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleRetryFailed = async () => {
    await triggerRetryFailed();
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleQueueAction = async (
    local_id: string,
    action: "cancel" | "delete" | "retry",
  ) => {
    await performQueueAction(local_id, action);
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleBatchAction = async (
    local_ids: string[],
    action: QueueBatchAction,
    options: { priority?: number; profile_id?: string } = {},
  ) => {
    await batchDownloadQueue(local_ids, action, options);
    setQueue(await fetchDownloadQueue());
  };

  const handleVerifyQueue = async () => {
    await verifyDownloadQueue([], true);
    setQueue(await fetchDownloadQueue());
  };

  const handlePauseToggle = async () => {
    const ok = await setDownloadsPaused(!downloadsPaused);
    if (ok) setDownloadsPausedState(!downloadsPaused);
    const state = await fetchDownloadState();
    setDownloadSpeed(state.speed);
    setDownloadEta(state.eta_seconds);
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleReorder = async (local_ids: string[]) => {
    await reorderDownloadQueue(local_ids);
    setQueue(await fetchDownloadQueue());
  };

  const handleProfileChange = async (profile_id: string) => {
    if (await setActiveDownloadProfile(profile_id)) {
      setActiveProfile(profile_id);
      setConfig((prev) => (prev ? { ...prev, active_download_profile: profile_id } : prev));
    }
  };

  const handleSaveProfile = async (profile: DownloadProfile) => {
    const saved = await saveDownloadProfile(profile);
    if (saved) {
      const fresh = await fetchDownloadProfiles();
      setProfiles(fresh.profiles);
      setActiveProfile(fresh.active);
    }
    return saved;
  };

  const handleDeleteProfile = async (profile_id: string) => {
    const ok = await deleteDownloadProfile(profile_id);
    if (ok) {
      const fresh = await fetchDownloadProfiles();
      setProfiles(fresh.profiles);
      setActiveProfile(fresh.active);
    }
    return ok;
  };

  const handleActivateProfile = async (profile_id: string) => {
    const previousProfile = activeProfile;
    profileMutationRef.current += 1;
    setActiveProfile(profile_id);
    setConfig((prev) => (prev ? { ...prev, active_download_profile: profile_id } : prev));

    const ok = await setActiveDownloadProfile(profile_id);
    if (!ok) {
      setActiveProfile(previousProfile);
      setConfig((prev) => (prev ? { ...prev, active_download_profile: previousProfile } : prev));
    }
    return ok;
  };

  const handleUpdateConfigValue = async (
    key: string,
    value: any,
  ): Promise<boolean> => {
    const ok = await updateOTSConfigValue(key, value);
    if (ok) {
      setConfig((prev) => (prev ? { ...prev, [key]: value } : null));
    }
    return ok;
  };

  const handleSaveConfig = async (): Promise<boolean> => {
    return await saveOTSConfig();
  };

  const handleResetConfig = async () => {
    const fresh = await resetOTSConfig();
    if (fresh) setConfig(fresh);
  };

  const handleAddAccount = async (
    service: string,
    creds: { username?: string; token?: string },
  ) => {
    const acc = await addAccountService(service, creds);
    if (acc) {
      const fresh = await fetchAccounts();
      setAccounts(fresh);
      setAccountHealth(await fetchAccountHealth());
    }
    return acc;
  };

  const handleRemoveAccount = async (uuid: string) => {
    const ok = await removeAccountUUID(uuid);
    if (ok) {
      setAccounts((prev) => prev.filter((a) => a.uuid !== uuid));
      setAccountHealth(await fetchAccountHealth());
    }
    return ok;
  };

  const handleReconnectAccounts = async () => {
    const ok = await reconnectAccounts();
    if (ok) {
      window.setTimeout(async () => {
        setAccounts(await fetchAccounts());
        setAccountHealth(await fetchAccountHealth());
      }, 1500);
    }
    return ok;
  };

  const handleClearLogs = () => {
    setLogs([]);
  };

  const handleRefreshLogs = async () => {
    const fresh = await fetchServerLogs();
    setLogs(fresh);
  };

  const activeDownloadsCount = queue.filter(
    (i) => i.item_status === "Downloading" || i.item_status === "Paused",
  ).length;

  return (
    <div
      className={`theme-${themePreset} ${isDarkMode === "dark" ? "dark-theme" : "light-theme"} min-h-screen antialiased`}
      style={themePreset === "custom" ? getCustomThemeStyle(customTheme, themeMode) : undefined}
    >
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        queueCount={
          queue.filter(
            (i) =>
              i.item_status === "Waiting" || i.item_status === "Downloading" || i.item_status === "Paused",
          ).length
        }
        activeDownloads={activeDownloadsCount}
        accountCount={accounts.length}
        isDarkMode={isDarkMode}
        toggleTheme={toggleTheme}
      />

      <main className="min-h-screen pb-10 md:ml-64">
        {activeTab === "dashboard" && (
          <SearchDashboard
            onSearch={handleDownloadItem}
            onDownload={handleDownloadItem}
            config={config}
          />
        )}

        {activeTab === "browse" && (
          <BrowseSpotify onDownload={handleDownloadItem} />
        )}

        {activeTab === "library" && (
          <LibraryPage onQueueChanged={async () => setQueue(await fetchDownloadQueue())} />
        )}

        {activeTab === "queue" && (
          <DownloadQueue
            queue={queue}
            onClearCompleted={handleClearCompleted}
            onClearFailed={handleClearFailed}
            onRetryFailed={handleRetryFailed}
            onAction={handleQueueAction}
            onPauseToggle={handlePauseToggle}
            downloadsPaused={downloadsPaused}
            downloadSpeed={downloadSpeed}
            downloadEta={downloadEta}
            onReorder={handleReorder}
            profiles={profiles}
            activeProfile={activeProfile}
            onProfileChange={handleProfileChange}
            onBatchAction={handleBatchAction}
            onVerify={handleVerifyQueue}
            config={config}
          />
        )}

        {activeTab === "settings" && (
          <SettingsPage
            config={config}
            onUpdateValue={handleUpdateConfigValue}
            onSave={handleSaveConfig}
            onReset={handleResetConfig}
            profiles={profiles}
            activeProfile={activeProfile}
            onSaveProfile={handleSaveProfile}
            onDeleteProfile={handleDeleteProfile}
            onActivateProfile={handleActivateProfile}
            themePreset={themePreset}
            onThemeChange={handleThemeChange}
            themeMode={themeMode}
            onThemeModeChange={handleThemeModeChange}
            customTheme={customTheme}
            onCustomThemeChange={handleCustomThemeChange}
            savedCustomThemes={savedCustomThemes}
            onSaveCustomTheme={handleSaveCustomTheme}
            onLoadCustomTheme={handleLoadCustomTheme}
            onDeleteCustomTheme={handleDeleteCustomTheme}
          />
        )}

        {activeTab === "accounts" && (
          <AccountsManager
            accounts={accounts.length > 0 ? accounts : config?.accounts || []}
            onAddAccount={handleAddAccount}
            onRemoveAccount={handleRemoveAccount}
            health={accountHealth}
            onReconnect={handleReconnectAccounts}
          />
        )}

        {activeTab === "statistics" && <StatisticsPanel />}

        {activeTab === "diagnostics" && <DiagnosticsPanel wsConnected={wsConnected} newVersion={hasNewVersion} checkVersion={checkNewVersion} />}

        {activeTab === "logs" && (
          <LogViewer
            logs={logs}
            onRefresh={handleRefreshLogs}
            onClear={handleClearLogs}
          />
        )}
      </main>

      {/* Real-time floating notification banners */}
      <NotificationBanner
        notifications={notifications}
        onDismiss={handleDismissNotification}
        disabled={config?.disable_download_popups}
      />
      <NotificationHistory history={history} onClear={clearHistory} />
    </div>
  );
}
