import React, {
  lazy,
  Suspense,
  useEffect,
  useState,
  useCallback,
  useRef,
} from "react";
import { Navbar, NavTab } from "./components/Navbar";
import { SearchDashboard } from "./components/SearchDashboard";
import type { SettingsSection } from "./components/SettingsPage";
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
import { installDocumentLocalization } from "./lib/localizeDocument";
import {
  fetchOTSConfig,
  fetchDownloadQueue,
  fetchAccounts,
  fetchAccountHealth,
  reconnectAccounts,
  fetchServerLogs,
  searchCatalog,
  searchMedia,
  clearQueueItems,
  triggerRetryFailed,
  performQueueAction,
  updateOTSConfigValue,
  saveOTSConfig,
  resetOTSConfig,
  addAccountService,
  configureYouTubeAuthentication,
  uploadYouTubeCookies,
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

const PlaylistAutomationPage = lazy(() =>
  import("./components/PlaylistAutomationPage").then((module) => ({
    default: module.PlaylistAutomationPage,
  })),
);
const LibraryPage = lazy(() =>
  import("./components/LibraryPage").then((module) => ({
    default: module.LibraryPage,
  })),
);
const StatisticsPanel = lazy(() =>
  import("./components/StatisticsPanel").then((module) => ({
    default: module.StatisticsPanel,
  })),
);
const DownloadQueue = lazy(() =>
  import("./components/DownloadQueue").then((module) => ({
    default: module.DownloadQueue,
  })),
);
const SettingsPage = lazy(() =>
  import("./components/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);
const AccountsManager = lazy(() =>
  import("./components/AccountsManager").then((module) => ({
    default: module.AccountsManager,
  })),
);
const DiagnosticsPanel = lazy(() =>
  import("./components/DiagnosticsPanel").then((module) => ({
    default: module.DiagnosticsPanel,
  })),
);
const LogViewer = lazy(() =>
  import("./components/LogViewer").then((module) => ({
    default: module.LogViewer,
  })),
);

const PageLoading = () => (
  <div className="ots-page flex min-h-[40vh] items-center justify-center text-sm text-[var(--spotify-text-muted)]">
    Loading…
  </div>
);

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
  const channels = [1, 3, 5].map(
    (offset) => Number.parseInt(hex.slice(offset, offset + 2), 16) / 255,
  );
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
  const legacyLooksLight =
    getHexLuminance(legacy.background) > getHexLuminance(legacy.text);

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
    window.localStorage.setItem(
      CUSTOM_THEMES_STORAGE_KEY,
      JSON.stringify(themes),
    );
  } catch {
    // Saved themes still remain available for this session when storage is unavailable.
  }
};

const createCustomThemeId = (): string => {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
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

const getCustomThemeStyle = (
  theme: CustomTheme,
  mode: ThemeMode = theme.mode,
): React.CSSProperties => {
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
    "--ots-on-accent":
      getHexLuminance(palette.accent) > 0.55 ? "#181818" : "#ffffff",
  } as React.CSSProperties;
};

const initialTabFromLocation = (): NavTab => {
  const tab = new URLSearchParams(window.location.search).get("tab");
  const validTabs: NavTab[] = [
    "dashboard",
    "playlist-automation",
    "library",
    "queue",
    "statistics",
    "settings",
    "accounts",
    "diagnostics",
    "logs",
  ];
  return validTabs.includes(tab as NavTab) ? (tab as NavTab) : "dashboard";
};

export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>(initialTabFromLocation);
  const [searchQuery, setSearchQuery] = useState("");
  const [settingsSection, setSettingsSection] =
    useState<SettingsSection>("general");
  const [config, setConfig] = useState<OTSConfig | null>(null);
  const [queue, setQueue] = useState<DownloadQueueItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [accountHealth, setAccountHealth] = useState<AccountHealth | null>(
    null,
  );
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const {
    notifications,
    history,
    dismissNotification,
    clearHistory,
    lastStatusChange,
  } = useNotifications("webui");
  const [notificationHistoryOpen, setNotificationHistoryOpen] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [themePreset, setThemePreset] = useState<ThemePreset>(
    () => readStoredThemePreset() ?? "spotify",
  );
  const [customTheme, setCustomTheme] = useState<CustomTheme>(() =>
    readStoredCustomTheme(),
  );
  const [savedCustomThemes, setSavedCustomThemes] = useState<
    SavedCustomTheme[]
  >(() => readStoredCustomThemes());
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
    const [
      cfg,
      qData,
      accData,
      healthData,
      logData,
      downloadState,
      profileData,
    ] = await Promise.all([
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
      setConfig(cfg);
      // Respect a browser-selected preset; otherwise initialize from backend theme state.
      if (!readStoredThemePreset()) {
        const backendThemeMode: ThemeMode =
          cfg.theme === "dark" ? "dark" : "light";
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
    const locale = (config?.language || "en_US").replace("_", "-");
    document.documentElement.lang = locale;
    document.documentElement.dataset.applicationLanguage = locale;
  }, [config?.language]);

  useEffect(
    () => installDocumentLocalization(config?.language || "en_US"),
    [config?.language],
  );

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
    const interval = window.setInterval(
      () => void checkUpdates(),
      6 * 60 * 60 * 1000,
    );
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [config?.check_for_updates]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        const input = document.getElementById(
          "global-search",
        ) as HTMLInputElement | null;
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
      const [freshAccounts, freshHealth] = await Promise.all([
        fetchAccounts(),
        fetchAccountHealth(),
      ]);
      if (mounted) {
        setAccounts(freshAccounts);
        setAccountHealth(freshHealth);
      }
    };
    void refreshAccountHealth();
    const interval = window.setInterval(
      () => void refreshAccountHealth(),
      60000,
    );
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
      window.localStorage.setItem(
        "ots-custom-theme",
        JSON.stringify(newCustomTheme),
      );
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

    const snapshot: CustomTheme = cloneCustomTheme({
      ...customTheme,
      mode: themeMode,
    });
    const existing = savedCustomThemes.find(
      (savedTheme) =>
        savedTheme.name.toLocaleLowerCase() ===
        normalizedName.toLocaleLowerCase(),
    );
    const nextTheme: SavedCustomTheme = {
      id: existing?.id ?? createCustomThemeId(),
      name: normalizedName,
      theme: snapshot,
      updatedAt: Date.now(),
    };
    const nextThemes = existing
      ? savedCustomThemes.map((savedTheme) =>
          savedTheme.id === existing.id ? nextTheme : savedTheme,
        )
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
    const nextThemes = savedCustomThemes.filter(
      (savedTheme) => savedTheme.id !== id,
    );
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
    return searchMedia(query, filters);
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
    const succeeded = await performQueueAction(local_id, action);
    if (succeeded && action === "cancel") {
      // Reflect the terminal state immediately while the worker unwinds its
      // current network/read operation and publishes the same event.
      setQueue((current) =>
        current.map((item) =>
          item.local_id === local_id
            ? {
                ...item,
                item_status: "Cancelled",
                error: "Cancelled by the user.",
              }
            : item,
        ),
      );
    }
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
      setConfig((prev) =>
        prev ? { ...prev, active_download_profile: profile_id } : prev,
      );
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
    setConfig((prev) =>
      prev ? { ...prev, active_download_profile: profile_id } : prev,
    );

    const ok = await setActiveDownloadProfile(profile_id);
    if (!ok) {
      setActiveProfile(previousProfile);
      setConfig((prev) =>
        prev ? { ...prev, active_download_profile: previousProfile } : prev,
      );
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

  const handleRefreshAccounts = useCallback(async () => {
    const [freshAccounts, freshHealth] = await Promise.all([
      fetchAccounts(),
      fetchAccountHealth(),
    ]);
    setAccounts(freshAccounts);
    setAccountHealth(freshHealth);
    return freshAccounts;
  }, []);

  const handleConfigureYouTubeAuthentication = async (authentication: {
    mode: "none" | "browser" | "cookie_file";
    browser?: string;
    cookie_file?: string;
  }) => {
    const ok = await configureYouTubeAuthentication(authentication);
    if (ok) {
      const fresh = await fetchOTSConfig();
      if (fresh) setConfig(fresh);
    }
    return ok;
  };

  const handleUploadYouTubeCookies = async (file: File) => {
    const status = await uploadYouTubeCookies(file);
    if (status) {
      const fresh = await fetchOTSConfig();
      if (fresh) setConfig(fresh);
    }
    return status;
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
      style={
        themePreset === "custom"
          ? getCustomThemeStyle(customTheme, themeMode)
          : undefined
      }
    >
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        queueCount={
          queue.filter(
            (i) =>
              i.item_status === "Waiting" ||
              i.item_status === "Downloading" ||
              i.item_status === "Paused",
          ).length
        }
        activeDownloads={activeDownloadsCount}
        accountCount={accounts.length}
        appVersion={config?.version || "v2.0.0 Alpha 2"}
        isDarkMode={isDarkMode}
        toggleTheme={toggleTheme}
        notificationHistoryCount={history.length}
        onOpenNotificationHistory={() => setNotificationHistoryOpen(true)}
        language={config?.language || "en_US"}
      />

      <main className="min-h-screen pb-10 md:ml-64">
        <Suspense fallback={<PageLoading />}>
          {activeTab === "dashboard" && (
            <SearchDashboard
              onSearch={searchCatalog}
              onDownload={handleDownloadItem}
              config={config}
              accounts={accounts}
              query={searchQuery}
              onQueryChange={setSearchQuery}
            />
          )}

          {activeTab === "playlist-automation" && (
            <PlaylistAutomationPage
              onOpenApiConfig={() => {
                setSettingsSection("search");
                setActiveTab("settings");
              }}
              onDownloadPlaylist={handleDownloadItem}
            />
          )}

          {activeTab === "library" && (
            <LibraryPage
              onQueueChanged={async () => setQueue(await fetchDownloadQueue())}
            />
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
              initialSection={settingsSection}
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
              onRefreshAccounts={handleRefreshAccounts}
              health={accountHealth}
              onReconnect={handleReconnectAccounts}
              onConfigureYouTubeAuthentication={
                handleConfigureYouTubeAuthentication
              }
              onUploadYouTubeCookies={handleUploadYouTubeCookies}
              youtubeAuthenticationMode={config?.youtube_auth_mode || "none"}
              youtubeBrowser={config?.youtube_cookies_browser || ""}
              youtubeCookieFile={config?.youtube_cookies_file || ""}
            />
          )}

          {activeTab === "statistics" && <StatisticsPanel />}

          {activeTab === "diagnostics" && (
            <DiagnosticsPanel
              wsConnected={wsConnected}
              newVersion={hasNewVersion}
              checkVersion={checkNewVersion}
            />
          )}

          {activeTab === "logs" && (
            <LogViewer
              logs={logs}
              onRefresh={handleRefreshLogs}
              onClear={handleClearLogs}
            />
          )}
        </Suspense>
      </main>

      {/* Real-time floating notification banners */}
      <NotificationBanner
        notifications={notifications}
        onDismiss={handleDismissNotification}
        disabled={config?.disable_download_popups}
      />
      <NotificationHistory
        history={history}
        onClear={clearHistory}
        open={notificationHistoryOpen}
        onOpenChange={setNotificationHistoryOpen}
        hideTrigger
      />
    </div>
  );
}
