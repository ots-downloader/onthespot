import {
  Activity,
  Bell,
  Disc3,
  Download,
  ListPlus,
  Sliders,
  Terminal,
  Users
} from "lucide-react";
import { useEffect, useState } from "react";

import {
  activateProfile,
  addAccount,
  addToQueue,
  checkServerHealth,
  clearAllPending,
  clearCompletedDownloads,
  clearFailedDownloads,
  clearLogs,
  configureYouTubeAuthentication,
  DEFAULT_CONFIG,
  DEFAULT_PROFILES,
  deleteProfile,
  executeQueueAction,
  executeQueueBatchAction,
  fetchAccountHealth,
  fetchAccounts,
  fetchDownloadQueue,
  fetchLogs,
  fetchOTSConfig,
  fetchPendingQueue,
  fetchProfiles,
  reconnectAccounts,
  removeAccount,
  removePendingItems,
  resetOTSConfig,
  retryFailedDownloads,
  saveOTSConfig,
  saveProfile,
  toggleQueuePause,
  updateOTSConfigValue,
  uploadYouTubeCookies
} from "./lib/api";
import { useNotifications } from "./lib/notifications";
import { applyAppearance } from "./lib/theme";
import {
  AccountHealth,
  AccountItem,
  DownloadProfile,
  DownloadQueueItem,
  IdentifyApplyResponse,
  LogEntry,
  OTSConfig,
  ParsingJob,
  PendingQueueItem,
  QueueBatchAction,
  SearchResultItem,
} from "./types";

import { AccountsManager } from "./components/AccountsManager";
import { DiagnosticsPanel } from "./components/DiagnosticsPanel";
import { DownloadQueue } from "./components/DownloadQueue";
import { IdentifyTrackModal } from "./components/IdentifyTrackModal";
import { LogViewer } from "./components/LogViewer";
import { NotificationBanner } from "./components/NotificationBanner";
import { NotificationHistory } from "./components/NotificationHistory";
import { ParsingPendingQueue } from "./components/ParsingPendingQueue";
import { SettingsPage } from "./components/SettingsPage";
import {
  AppShell,
  Badge,
  Button,
  SideNav,
  SideNavItem,
  SideNavSection,
  StatusDot,
  TopNav,
} from "./components/ui";

type NavigationTab = "parsing" | "queue" | "accounts" | "settings" | "diagnostics" | "logs";

export const uuid = Math.random().toString(36).substring(2, 7)

export default function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>("parsing");
  const [notificationHistoryOpen, setNotificationHistoryOpen] = useState(false);
  const [hasNewVersion, setHasNewVersion] = useState(false);
  const [settingsFocusField, setSettingsFocusField] = useState<string | undefined>(undefined);

  // In-app links such as "#settings/max_queue_size" (sent with backend
  // notifications) open the settings page and jump to that field.
  useEffect(() => {
    const openSettingsFromHash = () => {
      const match = window.location.hash.match(/^#settings(?:\/([\w-]+))?$/);
      if (!match) return;
      setActiveTab("settings");
      setSettingsFocusField(match[1]);
      // Clear the hash so the same link works again on the next click.
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    };
    openSettingsFromHash();
    window.addEventListener("hashchange", openSettingsFromHash);
    return () => window.removeEventListener("hashchange", openSettingsFromHash);
  }, []);

  // Real-time Notification Banner & History Hook
  const {
    notifications,
    history,
    addNotification,
    dismissNotification,
    clearHistory,
  } = useNotifications(`ots-user-${uuid}`);

  // App Data States
  const [config, setConfig] = useState<OTSConfig>(DEFAULT_CONFIG);
  const [queue, setQueue] = useState<DownloadQueueItem[]>([]);
  const [identifyItem, setIdentifyItem] = useState<DownloadQueueItem | null>(null);
  const [parsingJobs, setParsingJobs] = useState<ParsingJob[]>([]);
  const [pendingQueue, setPendingQueue] = useState<PendingQueueItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [accountHealth, setAccountHealth] = useState<AccountHealth | null>(null);
  const [profiles, setProfiles] = useState<DownloadProfile[]>(DEFAULT_PROFILES);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [searchResults, setSearchResults] = useState<SearchResultItem[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [downloadsPaused, setDownloadsPaused] = useState(false);
  const [serverStatus, setServerStatus] = useState<"online" | "offline">("online");
  const [serverVersion, setServerVersion] = useState("");

  // Light/dark mode follows the "Theme Appearance" setting.
  useEffect(() => {
    applyAppearance(config.theme);
  }, [config.theme]);

  // Load initial data
  useEffect(() => {
    async function loadData() {
      try {
        const [
          health,
          cfg,
          q,
          pQueue,
          accs,
          profs,
          lgs,
          acctHealth,
        ] = await Promise.all([
          checkServerHealth().catch(() => ({ status: "offline" as const, version: "", target: "" })),
          fetchOTSConfig().catch(() => DEFAULT_CONFIG),
          fetchDownloadQueue().catch(() => []),
          fetchPendingQueue().catch(() => []),
          fetchAccounts().catch(() => []),
          fetchProfiles().catch(() => DEFAULT_PROFILES),
          fetchLogs().catch(() => []),
          fetchAccountHealth().catch(() => null),
        ]);

        setServerStatus(health.status);
        setServerVersion(health.version);
        setConfig(cfg);
        setQueue(q);
        setPendingQueue(pQueue);
        setAccounts(accs);
        setAccountHealth(acctHealth);
        setProfiles(profs);
        setLogs(lgs);
      } catch (err) {
        console.error("Initialization error", err);
      }
    }

    loadData();
  }, []);

  useEffect(() => {
    async function refreshQueue() {
      try {
        const [
          q,
          pQueue,
        ] = await Promise.all([
          fetchDownloadQueue().catch(() => []),
          fetchPendingQueue().catch(() => []),
        ]);
        setQueue(q);
        setPendingQueue(pQueue);
      } catch (err) {
        console.error("Initialization error", err);
      }
    }

    refreshQueue();
  }, [notifications]);

  // Parsing & Pending Action Handlers
  const handleParseUrl = async (url: string, profileId?: string, autoQueue?: boolean) => {
    try {
      await addToQueue(url);
    } catch (err) {
      addNotification({
        title: `Url: ${url}`,
        message: err instanceof Error ? err.message : "Could not add URL",
        status: "error",
      });
      return false;
    }
    addNotification({
      title: `Url: ${url}`,
      message: `Added to Parsing Queue`,
    });
    return true;
  };

  const handleCancelJob = async (jobId: string) => {
    return
  };

  const handleDeleteJob = async (jobId: string) => {
    return
  };

  const handleClearCompletedJobs = async () => {
    return
  };

  const handleQueuePendingItems = async (itemIds: string[], profileId?: string) => {
    const [pending, updatedQueue] = await Promise.all([
      fetchPendingQueue(),
      fetchDownloadQueue(),
    ]);
    

    if (updatedQueue != queue) {
      addNotification({
        title: `Queued ${updatedQueue.length} track(s)`,
        message: `Transferred ${updatedQueue.length} parsed track(s) to the download queue.`,
        status: "Downloading",
        thumbnail: updatedQueue[0].thumbnail,
      });
    }
    setPendingQueue(pending);
    setQueue(updatedQueue);
  };

  const handleRemovePendingItems = async (itemIds: string[]) => {
    await removePendingItems(itemIds);
    const pending = await fetchPendingQueue();
    setPendingQueue(pending);
  };

  const handleClearAllPending = async () => {
    await clearAllPending();
    setPendingQueue([]);
  };

  const handleRefreshParsingQueue = async () => {
    const [pending] = await Promise.all([
      fetchPendingQueue(),
    ]);
    setPendingQueue(pending);
  };

  // Queue actions
  const handlePauseToggle = async () => {
    const isPaused = await toggleQueuePause();
    setDownloadsPaused(isPaused);
    const updatedQueue = await fetchDownloadQueue();
    setQueue(updatedQueue);
    return isPaused;
  };

  const handleQueueAction = async (
    local_id: number,
    action: "cancel" | "delete" | "retry"
  ) => {
    await executeQueueAction(local_id, action);
    const updatedQueue = await fetchDownloadQueue();
    setQueue(updatedQueue);
  };

  const handleIdentifyApplied = async (result: IdentifyApplyResponse) => {
    try {
      const updatedQueue = await fetchDownloadQueue();
      setQueue(updatedQueue);
    } catch (err) {
      console.error("Could not refresh queue after identify", err);
    }
    addNotification({
      title: "Track identified",
      message: result.warnings.length
        ? `Tagged copy created with ${result.warnings.length} warning(s).`
        : `Tagged copy saved to ${result.file_path}`,
      status: "Downloaded"
    });
  };

  const handleBatchAction = async (
    local_ids: number[],
    action: QueueBatchAction,
    options?: any
  ) => {
    await executeQueueBatchAction(local_ids, action, options);
    const updatedQueue = await fetchDownloadQueue();
    setQueue(updatedQueue);
  };

  const handleClearCompleted = async () => {
    await clearCompletedDownloads();
    const updatedQueue = await fetchDownloadQueue();
    setQueue(updatedQueue);
  };

  const handleClearFailed = async () => {
    await clearFailedDownloads();
    const updatedQueue = await fetchDownloadQueue();
    setQueue(updatedQueue);
  };

  const handleRetryFailed = async () => {
    await retryFailedDownloads();
    const updatedQueue = await fetchDownloadQueue();
    setQueue(updatedQueue);
  };

  const handleReorder = async (local_ids: string[]) => {
    return
  };

  // Accounts actions
  const handleAddAccount = async (service: string, credentials: any) => {
    const newAcc = await addAccount(service, credentials);
    const [updatedAccounts, updatedHealth] = await Promise.all([
      fetchAccounts(),
      fetchAccountHealth(),
    ]);
    setAccounts(updatedAccounts);
    setAccountHealth(updatedHealth);

    addNotification({
      title: "Account Connected",
      message: `Successfully connected ${service.toUpperCase()} worker account.`,
      status: "success",
    });
    return newAcc;
  };

  const handleRemoveAccount = async (uuid: string) => {
    const success = await removeAccount(uuid);
    const [updatedAccounts, updatedHealth] = await Promise.all([
      fetchAccounts(),
      fetchAccountHealth(),
    ]);
    setAccounts(updatedAccounts);
    setAccountHealth(updatedHealth);
    return success;
  };

  const handleRefreshAccounts = async () => {
    const [updatedAccounts, updatedHealth] = await Promise.all([
      fetchAccounts(),
      fetchAccountHealth(),
    ]);
    setAccounts(updatedAccounts);
    setAccountHealth(updatedHealth);
    return updatedAccounts;
  };

  const handleReconnectWorkers = async () => {
    const success = await reconnectAccounts();
    const [updatedAccounts, updatedHealth] = await Promise.all([
      fetchAccounts(),
      fetchAccountHealth(),
    ]);
    setAccounts(updatedAccounts);
    setAccountHealth(updatedHealth);
    return success;
  };

  // Settings actions
  const handleUpdateConfigValue = async (
    key: string,
    value: any,
  ): Promise<boolean> => {
    const ok = await updateOTSConfigValue(key, value);
    if (ok) {
      setConfig((prev) => ({ ...prev, [key]: value }));
      return true
    }
    return false
  };

  const handleSaveConfig = async () => {
    await saveOTSConfig();

    addNotification({
      title: "Configuration Saved",
      message: "OnTheSpot settings and profile parameters have been saved.",
      status: "success",
    });
    return true;
  };

  const handleResetConfig = async () => {
    const def = await resetOTSConfig();
    setConfig(def);
  };

  // Profiles actions
  const handleActivateProfile = async (profileId: string) => {
    await activateProfile(profileId);
    const profs = await fetchProfiles();
    setProfiles(profs);
    setConfig((prev) => ({ ...prev, active_download_profile: profileId }));
    return;
  };

  const handleSaveProfile = async (profile: DownloadProfile) => {
    const saved = await saveProfile(profile);
    const profs = await fetchProfiles();
    setProfiles(profs);
    return saved;
  };

  const handleDeleteProfile = async (profileId: string) => {
    const deleted = await deleteProfile(profileId);
    const profs = await fetchProfiles();
    setProfiles(profs);
    return deleted;
  };

  // Logs actions
  const handleClearLogs = async () => {
    await clearLogs();
    setLogs([]);
  };

  const handleRefreshLogs = async () => {
    const updatedLogs = await fetchLogs();
    setLogs(updatedLogs);
  };

  // Counts for navigation badges
  const activeDownloadsCount = queue.filter((i) => i.item_status === "Downloading").length;
  const waitingCount = queue.filter((i) => i.item_status === "Waiting").length;
  const pendingCount = activeDownloadsCount + waitingCount;

  return (
    <>
      <AppShell
        topNav={
          <TopNav
            label="OnTheSpot Main Navigation"
            heading={
              <div className="flex items-center gap-2.5 py-1">
                <div className="w-8 h-8 rounded-lg bg-inverse flex items-center justify-center text-fg-on-inverse shadow-xs">
                  <Disc3 className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-sm tracking-tight text-fg">
                      OnTheSpot
                    </span>
                    {serverVersion && <Badge variant="neutral" label={serverVersion} />}
                  </div>
                </div>
              </div>
            }
            centerContent={
              <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-raised border border-line text-xs">
                <StatusDot
                  variant={serverStatus === "online" ? "success" : "error"}
                  label={serverStatus === "online" ? "Online" : "Offline"}
                />
                <span className="text-fg-muted font-medium">
                  {serverStatus === "online" ? "FastAPI Core Ready" : "Disconnected"}
                </span>
                {activeDownloadsCount > 0 && (
                  <>
                    <span className="text-fg-subtle">•</span>
                    <span className="text-success-fg font-medium">
                      {activeDownloadsCount} active download{activeDownloadsCount > 1 ? "s" : ""}
                    </span>
                  </>
                )}
              </div>
            }
            endContent={
              <div className="hidden items-center gap-2 sm:flex">
                {/* Notification History Button in place of Queue button */}
                <Button
                  variant={notificationHistoryOpen ? "primary" : "secondary"}
                  size="sm"
                  label={`History (${history.length})`}
                  icon={<Bell className="w-3.5 h-3.5 text-accent" />}
                  onClick={() => setNotificationHistoryOpen(true)}
                  id="btn-header-notifications"
                />
              </div>
            }
          />
        }
        sideNav={
          <SideNav>
            <SideNavSection title="Downloader">
              <SideNavItem
                label="Parsing & Pending"
                icon={<ListPlus className="w-4 h-4" />}
                isSelected={activeTab === "parsing"}
                onClick={() => setActiveTab("parsing")}
                endContent={
                  pendingQueue.length > 0 ? (
                    <Badge variant="warning" label={String(pendingQueue.length)} />
                  ) : undefined
                }
              />
              <SideNavItem
                label="Download Queue"
                icon={<Download className="w-4 h-4" />}
                isSelected={activeTab === "queue"}
                onClick={() => setActiveTab("queue")}
                endContent={
                  pendingCount > 0 ? (
                    <Badge variant="info" label={String(pendingCount)} />
                  ) : (
                    <span className="text-[11px] text-fg-muted font-mono">{queue.length}</span>
                  )
                }
              />
              <SideNavItem
                label="Media Accounts"
                icon={<Users className="w-4 h-4" />}
                isSelected={activeTab === "accounts"}
                onClick={() => setActiveTab("accounts")}
                endContent={
                  <Badge variant="success" label={String(accounts.length)} />
                }
              />
            </SideNavSection>

            <SideNavSection title="System">
              <SideNavItem
                label="Settings"
                icon={<Sliders className="w-4 h-4" />}
                isSelected={activeTab === "settings"}
                onClick={() => setActiveTab("settings")}
              />
              <SideNavItem
                label="Diagnostics"
                icon={<Activity className="w-4 h-4" />}
                isSelected={activeTab === "diagnostics"}
                onClick={() => setActiveTab("diagnostics")}
              />
              <SideNavItem
                label="Event Logs"
                icon={<Terminal className="w-4 h-4" />}
                isSelected={activeTab === "logs"}
                onClick={() => setActiveTab("logs")}
                endContent={
                  <span className="text-[11px] font-mono text-fg-muted">
                    {logs.length}
                  </span>
                }
              />
            </SideNavSection>
          </SideNav>
        }
      >
        {/* Main Content View Container */}
        <div className="max-w-7xl mx-auto pb-8">
          {activeTab === "parsing" && (
            <ParsingPendingQueue
              jobs={parsingJobs}
              pendingItems={pendingQueue}
              profiles={profiles}
              activeProfile={config.active_download_profile || ""}
              onChangeActiveProfile={handleActivateProfile}
              onParseUrl={handleParseUrl}
              onCancelJob={handleCancelJob}
              onDeleteJob={handleDeleteJob}
              onClearCompletedJobs={handleClearCompletedJobs}
              onQueuePendingItems={handleQueuePendingItems}
              onRemovePendingItems={handleRemovePendingItems}
              onClearAllPending={handleClearAllPending}
              onRefresh={handleRefreshParsingQueue}
            />
          )}

          {activeTab === "queue" && (
            <DownloadQueue
              queue={queue}
              downloadsPaused={downloadsPaused}
              profiles={profiles}
              activeProfile={config.active_download_profile || ""}
              onPauseToggle={handlePauseToggle}
              onClearCompleted={handleClearCompleted}
              onClearFailed={handleClearFailed}
              onRetryFailed={handleRetryFailed}
              onAction={handleQueueAction}
              onIdentify={setIdentifyItem}
              onBatchAction={handleBatchAction}
              onReorder={handleReorder}
            />
          )}

          {identifyItem && (
            <IdentifyTrackModal
              item={identifyItem}
              config={config}
              onClose={() => setIdentifyItem(null)}
              onApplied={handleIdentifyApplied}
            />
          )}

          {activeTab === "accounts" && (
            <AccountsManager
              accounts={accounts}
              health={accountHealth}
              onAddAccount={handleAddAccount}
              onRemoveAccount={handleRemoveAccount}
              onRefreshAccounts={handleRefreshAccounts}
              onReconnect={handleReconnectWorkers}
              onConfigureYouTubeAuthentication={configureYouTubeAuthentication}
              onUploadYouTubeCookies={uploadYouTubeCookies}
              youtubeAuthenticationMode={config.youtube_authentication_mode}
              youtubeBrowser={config.youtube_browser}
              youtubeCookieFile={config.youtube_cookie_file}
            />
          )}

          {activeTab === "settings" && (
            <SettingsPage
              config={config}
              profiles={profiles}
              activeProfile={config.active_download_profile || ""}
              onUpdateValue={handleUpdateConfigValue}
              onSave={handleSaveConfig}
              onReset={handleResetConfig}
              onActivateProfile={handleActivateProfile}
              onSaveProfile={handleSaveProfile}
              onDeleteProfile={handleDeleteProfile}
              focusField={settingsFocusField}
              onFocusHandled={() => setSettingsFocusField(undefined)}
            />
          )}

          {activeTab === "diagnostics" && (
            <DiagnosticsPanel
              wsConnected={serverStatus === "online"}
              newVersion={hasNewVersion}
              config={config}
            />
          )}

          {activeTab === "logs" && (
            <LogViewer
              logs={logs}
              onRefresh={handleRefreshLogs}
              onClear={handleClearLogs}
            />
          )}
        </div>
      </AppShell>

      {/* Floating Auto-dismiss Notification Banner Alert */}
      <NotificationBanner
        notifications={notifications}
        onDismiss={dismissNotification}
        disabled={config.disable_download_popups}
      />

      {/* Notification Activity History Panel / Dialog */}
      <NotificationHistory
        history={history}
        onClear={clearHistory}
        open={notificationHistoryOpen}
        onOpenChange={setNotificationHistoryOpen}
        hideTrigger={true}
      />
    </>
  );
}
