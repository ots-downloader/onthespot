import React, { useState } from "react";
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
  ListMusic,
  Bell,
  GripVertical,
} from "lucide-react";
import { translate, type TranslationKey } from "../lib/i18n";

export type NavTab = "dashboard" | "browse" | "playlist-automation" | "library" | "queue" | "statistics" | "settings" | "accounts" | "diagnostics" | "logs";
type WorkspaceTab = "dashboard" | "browse" | "library" | "playlist-automation" | "queue" | "statistics";
type ManageTab = "accounts" | "diagnostics" | "logs" | "settings";
type ManageItem = ManageTab | "notifications";

const WORKSPACE_TABS: WorkspaceTab[] = ["dashboard", "browse", "library", "playlist-automation", "queue", "statistics"];
const MANAGE_TABS: ManageItem[] = ["accounts", "diagnostics", "notifications", "logs", "settings"];
const NAV_DETAILS: Record<WorkspaceTab | ManageTab, { label: string; labelKey: TranslationKey; icon: React.ElementType; nested?: boolean }> = {
  dashboard: { label: "Search & discover", labelKey: "search_discover", icon: Search }, browse: { label: "Browse catalogue", labelKey: "browse_catalogue", icon: Library, nested: true }, library: { label: "Local library", labelKey: "local_library", icon: Library, nested: true }, "playlist-automation": { label: "Playlist sorting", labelKey: "playlist_sorting", icon: ListMusic, nested: true }, queue: { label: "Download queue", labelKey: "download_queue", icon: Download }, statistics: { label: "Download statistics", labelKey: "download_statistics", icon: BarChart3, nested: true }, accounts: { label: "Accounts", labelKey: "accounts", icon: Users }, diagnostics: { label: "Diagnostics", labelKey: "diagnostics", icon: Activity }, logs: { label: "Server logs", labelKey: "server_logs", icon: Terminal }, settings: { label: "Settings", labelKey: "settings", icon: Settings },
};

const readNavOrder = <T extends string>(key: string, fallback: T[]): T[] => {
  try {
    const stored = JSON.parse(window.localStorage.getItem(key) || "[]");
    if (Array.isArray(stored) && stored.length === fallback.length && stored.every((item) => fallback.includes(item))) return stored as T[];
  } catch { /* Use the default order. */ }
  return fallback;
};

interface NavbarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  queueCount: number;
  activeDownloads: number;
  accountCount: number;
  appVersion: string;
  isDarkMode: "light" | "dark";
  toggleTheme: () => void;
  notificationHistoryCount: number;
  onOpenNotificationHistory: () => void;
  language: string;
}

interface TabButtonProps {
  active: boolean;
  id: string;
  label: string;
  icon: React.ElementType;
  count?: number;
  indicator?: boolean;
  nested?: boolean;
  onActivate: () => void;
  editing?: boolean;
  onDragStart?: () => void;
  onDragOver?: (event: React.DragEvent<HTMLButtonElement>) => void;
  onDrop?: (event: React.DragEvent<HTMLButtonElement>) => void;
  onDragEnd?: () => void;
}

const TabButton: React.FC<TabButtonProps> = ({
  active,
  id,
  label,
  icon: Icon,
  count,
  indicator,
  nested,
  onActivate,
  editing,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}) => {
  return (
    <button
      draggable={editing}
      onDragStart={onDragStart}
      onDragOver={onDragOver}
      onDrop={onDrop}
      onDragEnd={onDragEnd}
      onClick={onActivate}
      className={`ots-nav-item ${nested ? "md:ml-3 md:w-[calc(100%-0.75rem)]" : ""} group relative flex w-full items-center gap-4 rounded-lg px-4 py-3 text-left text-sm font-semibold transition-all duration-200 focus:outline-none ${editing ? "cursor-grab" : ""} ${
        active
          ? "bg-[#282828] text-white"
          : "text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white"
      }`}
    >
      {editing && <GripVertical className="h-4 w-4 shrink-0 text-[#777]" aria-label="Drag to reorder" />}
      <span className="relative shrink-0">
        <Icon className={`h-5 w-5 transition-transform group-hover:scale-105 ${active ? "text-[#1ed760]" : ""}`} />
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
  appVersion,
  isDarkMode,
  toggleTheme,
  notificationHistoryCount,
  onOpenNotificationHistory,
  language,
}) => {
  const [workspaceOrder, setWorkspaceOrder] = useState<WorkspaceTab[]>(() => readNavOrder("ots-workspace-nav-order", WORKSPACE_TABS));
  const [manageOrder, setManageOrder] = useState<ManageItem[]>(() => readNavOrder("ots-manage-nav-order", MANAGE_TABS));
  const [editingNavigation, setEditingNavigation] = useState(false);
  const [draggedNavigation, setDraggedNavigation] = useState<{ group: "workspace" | "manage"; id: string } | null>(null);
  const localizeNavItem = <T extends WorkspaceTab | ManageTab>(id: T) => {
    const item = NAV_DETAILS[id];
    return { ...item, label: translate(language, item.labelKey, item.label) };
  };
  const reorderNavigation = (group: "workspace" | "manage", target: string) => {
    if (!draggedNavigation || draggedNavigation.group !== group || draggedNavigation.id === target) return;
    const apply = <T extends string>(current: T[], setCurrent: React.Dispatch<React.SetStateAction<T[]>>, key: string) => {
      const next = [...current]; const from = next.indexOf(draggedNavigation.id as T); const to = next.indexOf(target as T);
      if (from < 0 || to < 0) return;
      next.splice(from, 1); next.splice(to, 0, draggedNavigation.id as T);
      setCurrent(next); window.localStorage.setItem(key, JSON.stringify(next));
    };
    if (group === "workspace") apply(workspaceOrder, setWorkspaceOrder, "ots-workspace-nav-order"); else apply(manageOrder, setManageOrder, "ots-manage-nav-order");
    setDraggedNavigation(null);
  };
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
        <p className="hidden px-4 pb-2 pt-1 text-[10px] font-bold uppercase tracking-[0.2em] text-[#6f6f6f] md:block">{translate(language, "workspace", "Workspace")}</p>
        {workspaceOrder.map((id) => { const item = localizeNavItem(id); return <TabButton key={id} id={id} {...item} active={activeTab === id} onActivate={() => onTabChange(id)} count={id === "queue" ? queueCount : undefined} indicator={id === "queue" && activeDownloads > 0} editing={editingNavigation} onDragStart={() => setDraggedNavigation({ group: "workspace", id })} onDragOver={(event) => { if (editingNavigation) event.preventDefault(); }} onDrop={(event) => { event.preventDefault(); reorderNavigation("workspace", id); }} onDragEnd={() => setDraggedNavigation(null)} />; })}
        <p className="hidden px-4 pb-2 pt-5 text-[10px] font-bold uppercase tracking-[0.2em] text-[#6f6f6f] md:block">{translate(language, "manage", "Manage")}</p>
        {manageOrder.map((id) => id === "notifications" ? <button key={id} draggable={editingNavigation} onDragStart={() => setDraggedNavigation({ group: "manage", id })} onDragOver={(event) => { if (editingNavigation) event.preventDefault(); }} onDrop={(event) => { event.preventDefault(); reorderNavigation("manage", id); }} onDragEnd={() => setDraggedNavigation(null)} onClick={onOpenNotificationHistory} className={`ots-nav-item group relative flex w-full items-center gap-4 rounded-lg px-4 py-3 text-left text-sm font-semibold text-[#b3b3b3] transition-all duration-200 hover:bg-[#1f1f1f] hover:text-white focus:outline-none ${editingNavigation ? "cursor-grab" : ""}`}>{editingNavigation && <GripVertical className="h-4 w-4 shrink-0 text-[#777]" aria-label="Drag to reorder" />}<Bell className="h-5 w-5 text-[#b3b3b3] transition-transform group-hover:scale-105" /><span>{translate(language, "notification_history", "Notification history")}</span>{notificationHistoryCount > 0 && <span className="ml-auto min-w-6 rounded-full bg-[#147f3e] px-1.5 py-0.5 text-center text-[10px] font-bold text-white ots-on-green-text">{notificationHistoryCount}</span>}</button> : (() => { const item = localizeNavItem(id); return <TabButton key={id} id={id} {...item} active={activeTab === id} onActivate={() => onTabChange(id)} count={id === "accounts" ? accountCount : undefined} editing={editingNavigation} onDragStart={() => setDraggedNavigation({ group: "manage", id })} onDragOver={(event) => { if (editingNavigation) event.preventDefault(); }} onDrop={(event) => { event.preventDefault(); reorderNavigation("manage", id); }} onDragEnd={() => setDraggedNavigation(null)} />; })())}
      </nav>

      <div className="mt-auto hidden p-4 md:block">
        <button
          type="button"
          onClick={() => setEditingNavigation((current) => !current)}
          className={`ots-nav-item mb-2 flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-semibold transition-colors focus:outline-none ${
            editingNavigation
              ? "bg-[#282828] text-white"
              : "text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white"
          }`}
          aria-pressed={editingNavigation}
        >
          <GripVertical className="h-5 w-5" />
          <span>{editingNavigation ? translate(language, "done_editing", "Done editing") : translate(language, "edit_navigation", "Edit navigation")}</span>
        </button>
        <button
          onClick={toggleTheme}
          className="ots-theme-toggle ots-nav-item flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-semibold text-[#b3b3b3] transition-colors hover:bg-[#1f1f1f] hover:text-white"
          aria-label="Toggle theme"
        >
          {isDarkMode === "dark" ? <Moon className="h-5 w-5" /> : <Sun className="h-5 w-5" />}
          <span>{isDarkMode === "dark" ? translate(language, "dark_mode", "Dark mode") : translate(language, "light_mode", "Light mode")}</span>
        </button>
        <p className="px-4 pt-3 text-center text-[10px] font-medium text-[#6f6f6f]">OnTheSpot {appVersion}</p>
      </div>
    </header>
  );
};
