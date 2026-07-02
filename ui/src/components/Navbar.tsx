import React from 'react';
import { Search, Download, Settings, Users, Terminal, Disc, Activity, CheckCircle2, ShieldCheck, RefreshCw } from 'lucide-react';

export type NavTab = 'dashboard' | 'queue' | 'settings' | 'accounts' | 'logs';

interface NavbarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  queueCount: number;
  activeDownloads: number;
  accountCount: number;
  wsConnected: boolean;
  version: string;
  totalDownloadedItems: number;
  totalDownloadedData: number;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  queueCount,
  activeDownloads,
  accountCount,
  wsConnected,
  version,
  totalDownloadedItems,
  totalDownloadedData
}) => {
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  return (
    <header className="bg-[#18181B] border-b border-zinc-800 sticky top-0 z-40 px-4 lg:px-8 py-3.5 select-none shadow-xl">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">

        {/* Logo & Status */}
        <div className="flex items-center justify-between md:justify-start gap-4">
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => onTabChange('dashboard')}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shadow-lg shadow-emerald-500/20 ring-2 ring-emerald-400/30">
              <Disc className="w-6 h-6 text-white animate-[spin_8s_linear_infinite]" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-sans font-bold text-lg tracking-tight text-white flex items-center gap-1.5">
                  OnTheSpot <span className="text-xs font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">{version || 'v2.0'}</span>
                </h1>
              </div>
              <p className="text-xs text-zinc-400 font-mono flex items-center gap-1.5">
                <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${wsConnected ? 'text-emerald-400' : 'text-amber-400'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${wsConnected ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
                  {wsConnected ? 'WS Sync Active' : 'Connecting WS...'}
                </span>
              </p>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center overflow-x-auto no-scrollbar gap-1 bg-zinc-900/90 p-1 rounded-xl border border-zinc-800">

          <button
            onClick={() => onTabChange('dashboard')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer shrink-0 ${activeTab === 'dashboard'
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30 font-semibold'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
          >
            <Search className="w-4 h-4" />
            <span>Search & Parse</span>
          </button>

          <button
            onClick={() => onTabChange('queue')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer shrink-0 ${activeTab === 'queue'
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30 font-semibold'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
          >
            <div className="relative">
              <Download className="w-4 h-4" />
              {activeDownloads > 0 && (
                <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
              )}
            </div>
            <span>Download Queue</span>
            {queueCount > 0 && (
              <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${activeTab === 'queue' ? 'bg-white/20 text-white' : 'bg-zinc-800 text-zinc-300'
                }`}>
                {queueCount}
              </span>
            )}
          </button>

          <button
            onClick={() => onTabChange('settings')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer shrink-0 ${activeTab === 'settings'
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30 font-semibold'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
          >
            <Settings className="w-4 h-4 animate-[spin_15s_linear_infinite]" />
            <span>OTS Settings</span>
          </button>

          <button
            onClick={() => onTabChange('accounts')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer shrink-0 ${activeTab === 'accounts'
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30 font-semibold'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
          >
            <Users className="w-4 h-4" />
            <span>Accounts</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-mono font-bold ${activeTab === 'accounts' ? 'bg-white/20 text-white' : 'bg-zinc-800 text-zinc-300'
              }`}>
              {accountCount}
            </span>
          </button>

          <button
            onClick={() => onTabChange('logs')}
            className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer shrink-0 ${activeTab === 'logs'
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30 font-semibold'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/50'
              }`}
          >
            <Terminal className="w-4 h-4" />
            <span>Live Logs</span>
          </button>

        </nav>

      </div>
    </header>
  );
};
