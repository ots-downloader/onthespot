import React from 'react';
import { Search, Download, Settings, Users, Terminal, Disc, Moon, Sun } from 'lucide-react';

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
  isDarkMode: 'light' | 'dark';
  toggleTheme: () => void;
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
  totalDownloadedData,
  isDarkMode,
  toggleTheme,
}) => {
  
  const TabButton = ({ 
    id, label, icon: Icon, count, indicator 
  }: { 
    id: NavTab, label: string, icon: React.ElementType, count?: number, indicator?: boolean 
  }) => {
    const isActive = activeTab === id;
    
    return (
      <button
        onClick={() => onTabChange(id)}
        className={`relative flex items-center gap-2 px-4 py-2 rounded-full text-sm font-medium transition-colors shrink-0 ${
          isActive
            ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
            : 'text-gray-600 hover:bg-gray-100 dark:text-neutral-400 dark:hover:bg-neutral-800'
        }`}
      >
        <div className="relative">
          <Icon className="w-[18px] h-[18px]" />
          {indicator && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-blue-500 ring-2 ring-white dark:ring-neutral-900" />
          )}
        </div>
        <span>{label}</span>
        
        {count !== undefined && count > 0 && (
          <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
            isActive 
              ? 'bg-blue-200 text-blue-800 dark:bg-blue-800 dark:text-blue-100' 
              : 'bg-gray-200 text-gray-700 dark:bg-neutral-700 dark:text-neutral-300'
          }`}>
            {count}
          </span>
        )}
      </button>
    );
  };

  return (
    <header className="bg-white dark:bg-[#141414] border-b border-gray-200 dark:border-neutral-800/60 sticky top-0 z-40 px-4 md:px-6 py-3 select-none">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row md:items-center justify-between gap-4">

        {/* Logo & Status */}
        <div className="flex items-center justify-between md:justify-start gap-4">
          <div 
            className="flex items-center gap-3 cursor-pointer group" 
            onClick={() => onTabChange('dashboard')}
          >
            <div className="w-10 h-10 rounded-full bg-blue-50 dark:bg-blue-500/10 flex items-center justify-center group-hover:bg-blue-100 dark:group-hover:bg-blue-500/20 transition-colors">
              <Disc className="w-6 h-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div >
              <div className="flex items-center gap-2">
                <h1 className="font-sans font-semibold text-lg tracking-tight text-gray-900 dark:text-neutral-100">
                  OnTheSpot
                </h1>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-neutral-800 dark:text-neutral-400">
                  {version || 'v2.0'}
                </span>
              </div>
              
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`w-2 h-2 rounded-full ${wsConnected ? 'bg-green-500' : 'bg-orange-500'}`} />
                <span className="text-xs text-gray-500 dark:text-neutral-500 font-medium">
                  {wsConnected ? 'Connected' : 'Connecting...'}
                </span>
              </div>
            </div>
          </div>

          <button 
            onClick={toggleTheme}
            className="p-2 rounded-full text-gray-600 dark:text-neutral-400 hover:bg-gray-100 dark:hover:bg-neutral-800 transition-all"
            aria-label="Toggle theme"
          >
            {isDarkMode === "dark" ? (
              <Moon className="w-5 h-5" />
            ) : (
              <Sun className="w-5 h-5" />
            )}
          </button>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center overflow-x-auto no-scrollbar gap-1 py-1">
          <TabButton id="dashboard" label="Search" icon={Search} />
          <TabButton id="queue" label="Queue" icon={Download} count={queueCount} indicator={activeDownloads > 0} />
          <TabButton id="settings" label="Settings" icon={Settings} />
          <TabButton id="accounts" label="Accounts" icon={Users} count={accountCount} />
          <TabButton id="logs" label="Logs" icon={Terminal} />
        </nav>

      </div>
    </header>
  );
};