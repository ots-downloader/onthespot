import React, { useEffect, useState, useCallback } from 'react';
import { Navbar, NavTab } from './components/Navbar';
import { SearchDashboard } from './components/SearchDashboard';
import { DownloadQueue } from './components/DownloadQueue';
import { SettingsPage } from './components/SettingsPage';
import { AccountsManager } from './components/AccountsManager';
import { LogViewer } from './components/LogViewer';
import { NotificationBanner } from './components/NotificationBanner';
import { OTSConfig, DownloadQueueItem, AccountItem, LogEntry, NotificationBannerItem, SearchResultItem, NotificationContent } from './types';
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
  connectWebSocket
} from './lib/api';


export default function App() {
  const [activeTab, setActiveTab] = useState<NavTab>('dashboard');
  const [config, setConfig] = useState<OTSConfig | null>(null);
  const [queue, setQueue] = useState<DownloadQueueItem[]>([]);
  const [accounts, setAccounts] = useState<AccountItem[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [notifications, setNotifications] = useState<NotificationBannerItem[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  // Initial load
  const loadData = useCallback(async () => {
    const [cfg, qData, accData, logData] = await Promise.all([
      fetchOTSConfig(),
      fetchDownloadQueue(),
      fetchAccounts(),
      fetchServerLogs()
    ]);
    if (cfg) setConfig(cfg._Config__config);
    if (qData) setQueue(qData);
    if (accData) setAccounts(accData);
    if (logData) setLogs(logData);
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // WebSocket real-time subscription
  useEffect(() => {
    const unsubscribe = connectWebSocket(
      (data) => {
        const item: DownloadQueueItem = data.item;
        if (data.type === 'QUEUE_UPDATE' && data.queue) {
          const newQueue = Array.isArray(data.queue) ? data.queue : (typeof data.queue === 'object' ? Object.values(data.queue) : []);
          setQueue(newQueue as DownloadQueueItem[]);
        } else if (data.type === 'STATUS_CHANGE' && data.item) {
          setQueue(prev => {
            const idx = prev.findIndex(i => i.local_id === item.local_id);
            if (idx === -1) return [item, ...prev];
            const updated = [...prev];
            updated[idx] = item;
            return updated;
          });
        } else if (data.type === 'LOG' && data.line) {
          setLogs(prev => [data.line, ...prev.slice(0, 499)]);
        } else if (data.type === 'HANDSHAKE' && data.queue) {
          const newQueue = Array.isArray(data.queue) ? data.queue : (typeof data.queue === 'object' ? Object.values(data.queue) : []);
          setQueue(newQueue as DownloadQueueItem[]);
        } else if (data.type === 'Keepalive') {
          return
        } else if (data.type === 'Notification') {
          const content: NotificationContent = data.content
          const newNotif: NotificationBannerItem = {
            id: content.id,
            title: content.title,
            message: data.notification,
            url: content.url,
            status: "",
          };
          setNotifications(prevItems => [newNotif, ...prevItems]);
        }
        if (data.notification) {
          if (item.available === false) {
            return
          }
          const newNotif: NotificationBannerItem = {
            id: item.local_id,
            title: item.name,
            message: data.notification,
            status: item.item_status as any,
            thumbnail: item.thumbnail,
            timestamp: new Date()
          };
          setNotifications(prevItems => {
            if (prevItems.length === 0) return [newNotif];
            if (prevItems.some(item => item.id === newNotif.id)) {
              return prevItems.map(item => item.id === newNotif.id ? newNotif : item)
            } else {
              return [newNotif, ...prevItems]
            }

          });
        }
      },
      (connected) => {
        setWsConnected(connected);
      }
    );

    return () => {
      unsubscribe();
    };
  }, []);

  const handleNotificationPush = (newNotif) => {
    let newnot = []
    try {
      notifications.forEach((notif) => {
        if (notif.id == newNotif.id) {
          newnot.push(newNotif)
          console.log(notif.id + 'new')
        } else {
          newnot.push(notif)
          console.log(notif.id + 'old')
        }
      });
    } catch (error) {
      newnot.push(newNotif)
      console.error("Caught error:", error.message);
    } finally {
      setNotifications(newnot);
    }
  };

  const handleDismissNotification = (id: string) => {
    setNotifications(prev => prev.filter(n => n.id !== id));
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
    <div className="min-h-screen bg-[#121214] text-zinc-100 flex flex-col antialiased selection:bg-emerald-500 selection:text-white">

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

