import { AlertCircle, Bell, CheckCircle2, DownloadCloud, ExternalLink, Info, Trash2, X } from "lucide-react";
import React, { useState } from "react";
import { isInAppLink, notificationLinkLabel } from "../lib/notifications";
import { NotificationBannerItem } from "../types";

interface NotificationHistoryProps {
  history: NotificationBannerItem[];
  onClear: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
}

export const NotificationHistory: React.FC<NotificationHistoryProps> = ({
  history,
  onClear,
  open: controlledOpen,
  onOpenChange,
  hideTrigger = false,
}) => {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = onOpenChange ?? setLocalOpen;

  const formatTimestamp = (dateOrStr?: Date | string) => {
    if (!dateOrStr) return "";
    try {
      const d = typeof dateOrStr === "string" ? new Date(dateOrStr) : dateOrStr;
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  };

  const getStatusIcon = (status?: string) => {
    if (status === "Completed" || status === "success") {
      return <CheckCircle2 className="w-4 h-4 text-emerald-500" />;
    }
    if (status === "Failed" || status === "Cancelled" || status === "error") {
      return <AlertCircle className="w-4 h-4 text-rose-500" />;
    }
    if (status === "Downloading") {
      return <DownloadCloud className="w-4 h-4 text-blue-500" />;
    }
    return <Info className="w-4 h-4 text-neutral-400" />;
  };

  return (
    <>
      {!hideTrigger && (
        <button
          type="button"
          id="btn-notification-history-trigger"
          onClick={() => setOpen(true)}
          className="fixed bottom-5 left-5 z-40 flex items-center gap-2.5 rounded-lg border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3.5 py-2 text-xs font-semibold text-neutral-700 dark:text-neutral-200 shadow-lg transition-all hover:bg-neutral-50 dark:hover:bg-neutral-800 cursor-pointer"
          title="Notification history"
          aria-label="Notification history"
        >
          <Bell className="h-4 w-4 text-emerald-500" />
          <span>History</span>
          {history.length > 0 && (
            <span className="min-w-5 rounded-full bg-emerald-600 px-1.5 py-0.5 text-center text-[10px] font-bold leading-none text-white">
              {history.length}
            </span>
          )}
        </button>
      )}

      {open && (
        <div
          id="notification-history-modal-backdrop"
          className="fixed inset-0 z-[60] flex items-end justify-start bg-black/50 p-4 backdrop-blur-xs sm:items-center sm:justify-center animate-in fade-in duration-200"
          onClick={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <div
            id="notification-history-modal-dialog"
            className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900 shadow-2xl overflow-hidden"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-neutral-200 dark:border-neutral-800 p-4">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
                  Activity Feed
                </p>
                <h2 className="text-base font-bold text-neutral-900 dark:text-neutral-100 flex items-center gap-2">
                  <Bell className="w-4 h-4 text-neutral-500" />
                  Notification History
                </h2>
              </div>
              <button
                type="button"
                id="btn-close-notification-history"
                onClick={() => setOpen(false)}
                aria-label="Close notification history"
                className="p-1 text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 transition cursor-pointer"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* List */}
            <div className="flex-1 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800">
              {history.length === 0 ? (
                <div className="p-12 text-center">
                  <Bell className="w-8 h-8 text-neutral-300 dark:text-neutral-700 mx-auto mb-2" />
                  <p className="text-sm font-medium text-neutral-500 dark:text-neutral-400">
                    No notifications yet
                  </p>
                  <p className="text-xs text-neutral-400 dark:text-neutral-500 mt-0.5">
                    Recent download completions, status changes, and system alerts will appear here.
                  </p>
                </div>
              ) : (
                history.map((item) => (
                  <div
                    key={item.id}
                    className="p-3.5 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors flex items-start gap-3"
                  >
                    <div className="mt-0.5 shrink-0">{getStatusIcon(item.status)}</div>
                    {item.thumbnail && (
                      <img
                        src={item.thumbnail}
                        alt=""
                        className="w-9 h-9 rounded object-cover shrink-0 bg-neutral-100 dark:bg-neutral-800"
                        referrerPolicy="no-referrer"
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                          {item.title}
                        </p>
                        {item.timestamp && (
                          <span className="text-[10px] font-mono text-neutral-400 shrink-0">
                            {formatTimestamp(item.timestamp)}
                          </span>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-neutral-600 dark:text-neutral-400 line-clamp-2">
                        {item.message}
                      </p>
                      {item.url && (
                        <a
                          href={item.url}
                          {...(isInAppLink(item.url) ? {} : { target: "_blank", rel: "noreferrer" })}
                          className="mt-1 inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400 hover:underline truncate max-w-full"
                        >
                          <span className="truncate">{notificationLinkLabel(item.url)}</span>
                          {!isInAppLink(item.url) && <ExternalLink className="w-3 h-3 shrink-0" />}
                        </a>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Footer Actions */}
            <div className="flex items-center justify-between border-t border-neutral-200 dark:border-neutral-800 p-3 bg-neutral-50 dark:bg-neutral-900/50">
              <span className="text-xs text-neutral-500">
                {history.length} {history.length === 1 ? "notification" : "notifications"} logged
              </span>
              <button
                type="button"
                id="btn-clear-notification-history"
                onClick={onClear}
                disabled={history.length === 0}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/30 rounded-md transition cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Clear history
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
