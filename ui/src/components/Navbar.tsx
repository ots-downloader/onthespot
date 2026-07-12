import React from "react";
import {
  Search,
  Download,
  Settings,
  Users,
  Terminal,
  Disc3,
  Library,
  Activity,
  Moon,
  Sun,
  BarChart3,
} from "lucide-react";

export type NavTab = "dashboard" | "browse" | "library" | "queue" | "statistics" | "settings" | "accounts" | "diagnostics" | "logs";

interface NavbarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  queueCount: number;
  activeDownloads: number;
  accountCount: number;
  isDarkMode: "light" | "dark";
  toggleTheme: () => void;
}

interface TabButtonProps {
  activeTab: NavTab;
  id: NavTab;
  label: string;
  icon: React.ElementType;
  count?: number;
  indicator?: boolean;
  nested?: boolean;
  onTabChange: (tab: NavTab) => void;
}

const TabButton: React.FC<TabButtonProps> = ({
  activeTab,
  id,
  label,
  icon: Icon,
  count,
  indicator,
  nested,
  onTabChange,
}) => {
  const isActive = activeTab === id;

  return (
    <button
      onClick={() => onTabChange(id)}
      className={`ots-nav-item ${nested ? "md:ml-3 md:w-[calc(100%-0.75rem)]" : ""} group relative flex w-full items-center gap-4 rounded-lg px-4 py-3 text-left text-sm font-semibold transition-all duration-200 focus:outline-none ${
        isActive
          ? "bg-[#282828] text-white"
          : "text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white"
      }`}
    >
      <span className="relative shrink-0">
        <Icon className={`h-5 w-5 transition-transform group-hover:scale-105 ${isActive ? "text-[#1ed760]" : ""}`} />
        {indicator && (
          <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-[#1ed760] ring-2 ring-[#121212]" />
        )}
      </span>
      <span>{label}</span>
      {count !== undefined && count > 0 && (
        <span className="ml-auto min-w-6 rounded-full bg-[#147f3e] px-1.5 py-0.5 text-center text-[10px] font-bold text-white ots-on-green-text">
          {count}
        </span>
      )}
    </button>
  );
};

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  queueCount,
  activeDownloads,
  accountCount,
  isDarkMode,
  toggleTheme,
}) => {
  return (
    <header className="z-40 flex w-full shrink-0 flex-col border-b border-[#282828] bg-[#121212] md:fixed md:inset-y-0 md:left-0 md:w-64 md:border-b-0 md:border-r">
      <div className="flex items-center justify-between px-5 py-4 md:block md:px-4 md:py-5">
        <button
          onClick={() => onTabChange("dashboard")}
          className="group flex items-center gap-3 text-left"
          aria-label="Go to dashboard"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-md bg-[#147f3e] text-white ots-on-green-text transition-transform group-hover:scale-105">
            <Disc3 className="h-6 w-6" strokeWidth={2.5} />
          </span>
          <span>
            <span className="block text-[17px] font-bold tracking-tight text-white">OnTheSpot</span>
            <span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-[#8f8f8f]">your music utility</span>
          </span>
        </button>

        <button
          onClick={toggleTheme}
          className="ots-theme-toggle rounded-full p-2 text-[#b3b3b3] transition-colors hover:bg-[#282828] hover:text-white md:hidden"
          aria-label="Toggle theme"
        >
          {isDarkMode === "dark" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
        </button>
      </div>

      <nav className="spotify-scrollbar flex items-center gap-1 overflow-x-auto px-3 pb-3 md:block md:space-y-1 md:overflow-visible md:px-3">
        <p className="hidden px-4 pb-2 pt-1 text-[10px] font-bold uppercase tracking-[0.2em] text-[#6f6f6f] md:block">Workspace</p>
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="dashboard" label="Search & discover" icon={Search} />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="browse" label="Browse catalogue" icon={Library} nested />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="library" label="Local library" icon={Library} nested />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="queue" label="Download queue" icon={Download} count={queueCount} indicator={activeDownloads > 0} />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="statistics" label="Download statistics" icon={BarChart3} nested />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="accounts" label="Accounts" icon={Users} count={accountCount} />
        <p className="hidden px-4 pb-2 pt-5 text-[10px] font-bold uppercase tracking-[0.2em] text-[#6f6f6f] md:block">Manage</p>
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="diagnostics" label="Diagnostics" icon={Activity} />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="settings" label="Settings" icon={Settings} />
        <TabButton activeTab={activeTab} onTabChange={onTabChange} id="logs" label="Server logs" icon={Terminal} />
      </nav>

      <div className="mt-auto hidden p-4 md:block">
        <button
          onClick={toggleTheme}
          className="ots-theme-toggle flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-semibold text-[#b3b3b3] transition-colors hover:bg-[#1f1f1f] hover:text-white"
          aria-label="Toggle theme"
        >
          {isDarkMode === "dark" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
          <span>{isDarkMode === "dark" ? "Dark mode" : "Light mode"}</span>
        </button>
      </div>
    </header>
  );
};
