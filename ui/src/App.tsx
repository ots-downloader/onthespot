import React, { useEffect, useState, useCallback } from 'react';
import { Navbar, NavTab } from './components/Navbar';
import { SearchDashboard } from './components/SearchDashboard';
import { DownloadQueue } from './components/DownloadQueue';
import { SettingsPage } from './components/SettingsPage';
import { AccountsManager } from './components/AccountsManager';
import { LogViewer } from './components/LogViewer';
import { NotificationBanner } from './components/NotificationBanner';
import { OTSConfig, DownloadQueueItem, AccountItem, LogEntry, NotificationBannerItem, SearchResultItem, NotificationContent } from './types';
import { useNotifications } from './lib/notifications';
import {
  fetchOTSConfig,
  fetchDownloadQueue,
  fetchAccounts,
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
} from './lib/api';


export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [config, setConfig] = useState<OTSConfig | null>(null);
  const [queue, setQueue] = useState<DownloadQueueItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const { notifications, dismissNotification } = useNotifications("webui");
  const [wsConnected, setWsConnected] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState<'light' | 'dark'>('dark');

  // Initial load
  const loadData = useCallback(async () => {
    const [cfg, qData, accData, logData] = await Promise.all([
      fetchOTSConfig(),
      fetchDownloadQueue(),
      fetchAccounts(),
      fetchServerLogs()
    ]);
    if (cfg) {
        setConfig(cfg._Config__config);
        // Initialize theme based on config if available
        setIsDarkMode(cfg._Config__config.theme === 'dark' ? 'dark' : 'light');
    }
    if (qData) setQueue(qData);
    if (accData) setAccounts(accData);
    if (logData) setLogs(logData);
  }, []);

  useEffect(() => {
    loadData();
    if (isDarkMode === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [loadData, isDarkMode]);

  useEffect(() => {
    async function fetchQueueData() {
      const q = await fetchDownloadQueue();
      if (q) setQueue(q);
    }
    fetchQueueData();
  }, [notifications]);

  const toggleTheme = async () => {
    const newTheme = isDarkMode === 'dark' ? 'light' : 'dark';
    setIsDarkMode(newTheme);
    if (config) {
        await updateOTSConfigValue('theme', newTheme);
        setConfig(prev => prev ? ({ ...prev, theme: newTheme }) : null);
        await saveOTSConfig(); // Persist the change
    }
  };

  const handleDismissNotification = (id: string) => {
    dismissNotification(id);
  };

  const handleDownloadItem = async (query: string, filters?: Record<string, boolean>) => {
    const res = await searchMedia(query, filters);
    if (res) {
      setActiveTab('queue')
    }
  };

  const handleClearCompleted = async () => {
    await clearQueueItems('Downloaded');
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleRetryFailed = async () => {
    await triggerRetryFailed();
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleQueueAction = async (local_id: string, action: 'cancel' | 'delete' | 'retry') => {
    await performQueueAction(local_id, action);
    const q = await fetchDownloadQueue();
    setQueue(q);
  };

  const handleUpdateConfigValue = async (key: string, value: any): Promise<boolean> => {
    const ok = await updateOTSConfigValue(key, value);
    if (ok) {
      setConfig(prev => prev ? { ...prev, [key]: value } : null);
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

  const handleAddAccount = async (service: string, creds: { username?: string; token?: string }) => {
    const acc = await addAccountService(service, creds);
    if (acc) {
      const fresh = await fetchAccounts();
      setAccounts(fresh);
    }
    return acc;
  };

  const handleRemoveAccount = async (uuid: string) => {
    const ok = await removeAccountUUID(uuid);
    if (ok) {
      setAccounts(prev => prev.filter(a => a.uuid !== uuid));
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

  const activeDownloadsCount = queue.filter(i => i.item_status === 'Downloading').length;

  return (
<div className={`min-h-screen flex flex-col antialiased selection:bg-emerald-500 selection:text-white dark:bg-zinc-950 bg-[#121214] text-zinc-100 bg-white text-zinc-900`}>

      {/* Top sticky navbar */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        queueCount={queue.filter(i => i.item_status === 'Waiting' || i.item_status === 'Downloading').length}
        activeDownloads={activeDownloadsCount}
        accountCount={accounts.length}
        wsConnected={wsConnected}
        version={config?.version || 'v2.0.0alpha1'}
        totalDownloadedItems={config?.total_downloaded_items || queue.filter(i => i.item_status === 'Downloaded').length}
        totalDownloadedData={config?.total_downloaded_data || 0}
        isDarkMode={isDarkMode}
        toggleTheme={toggleTheme}
      />

      {/* Main Tab Content */}
      <main className="flex-1 pb-16">
        {activeTab === 'dashboard' && (
          <SearchDashboard
            onSearch={handleDownloadItem}
            onDownload={handleDownloadItem}
            config={config}
          />
        )}

        {activeTab === 'queue' && (
          <DownloadQueue
            queue={queue}
            onClearCompleted={handleClearCompleted}
            onRetryFailed={handleRetryFailed}
            onAction={handleQueueAction}
            config={config}
          />
        )}

        {activeTab === 'settings' && (
          <SettingsPage
            config={config}
            onUpdateValue={handleUpdateConfigValue}
            onSave={handleSaveConfig}
            onReset={handleResetConfig}
          />
        )}

        {activeTab === 'accounts' && (
          <AccountsManager
            accounts={accounts.length > 0 ? accounts : config?.accounts || []}
            onAddAccount={handleAddAccount}
            onRemoveAccount={handleRemoveAccount}
          />
        )}

        {activeTab === 'logs' && (
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

    </div>
  );
}

