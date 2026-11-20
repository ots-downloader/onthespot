import { AlertCircle, Bell, CheckCircle2, DownloadCloud, ExternalLink, Info, Trash2 } from "lucide-react";
import React, { useState } from "react";
import { isInAppLink, notificationLinkLabel } from "../lib/notifications";
import { NotificationBannerItem } from "../types";
import { Button, Dialog, focusRing } from "./ui";

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
      return <CheckCircle2 className="w-4 h-4 text-success-fg" />;
    }
    if (status === "Failed" || status === "Cancelled" || status === "error") {
      return <AlertCircle className="w-4 h-4 text-danger-fg" />;
    }
    if (status === "Downloading") {
      return <DownloadCloud className="w-4 h-4 text-info-fg" />;
    }
    return <Info className="w-4 h-4 text-fg-subtle" />;
  };

  return (
    <>
      {!hideTrigger && (
        <button
          type="button"
          id="btn-notification-history-trigger"
          onClick={() => setOpen(true)}
          className={`fixed bottom-5 left-5 z-40 flex items-center gap-2.5 rounded-lg border border-line-strong bg-surface px-3.5 py-2 text-xs font-semibold text-fg-muted shadow-lg transition-all hover:bg-raised cursor-pointer ${focusRing}`}
          title="Notification history"
          aria-label="Notification history"
        >
          <Bell className="h-4 w-4 text-accent" />
          <span>History</span>
          {history.length > 0 && (
            <span className="min-w-5 rounded-full bg-accent px-1.5 py-0.5 text-center text-[10px] font-bold leading-none text-fg-on-accent">
              {history.length}
            </span>
          )}
        </button>
      )}

      <Dialog
        id="notification-history-modal-dialog"
        isOpen={open}
        onClose={() => setOpen(false)}
        closeLabel="Close notification history"
        className="max-h-[80vh]"
        bodyClassName="p-0 sm:p-0 divide-y divide-line"
        title={
          <>
            <span className="block text-[10px] font-bold uppercase tracking-wider text-accent">
              Activity Feed
            </span>
            <span className="flex items-center gap-2 font-bold">
              <Bell className="w-4 h-4 text-fg-subtle" />
              Notification History
            </span>
          </>
        }
        footer={
          <div className="flex w-full items-center justify-between">
            <span className="text-xs text-fg-muted">
              {history.length} {history.length === 1 ? "notification" : "notifications"} logged
            </span>
            <Button
              id="btn-clear-notification-history"
              variant="ghost"
              size="sm"
              label="Clear history"
              icon={<Trash2 className="h-3.5 w-3.5" />}
              onClick={onClear}
              isDisabled={history.length === 0}
              className="text-danger-fg hover:bg-danger-subtle"
            />
          </div>
        }
      >
        {history.length === 0 ? (
          <div className="p-12 text-center">
            <Bell className="w-8 h-8 text-fg-subtle mx-auto mb-2" />
            <p className="text-sm font-medium text-fg-muted">
              No notifications yet
            </p>
            <p className="text-xs text-fg-muted mt-0.5">
              Recent download completions, status changes, and system alerts will appear here.
            </p>
          </div>
        ) : (
          history.map((item) => (
            <div
              key={item.id}
              className="p-3.5 hover:bg-sunken transition-colors flex items-start gap-3"
            >
              <div className="mt-0.5 shrink-0">{getStatusIcon(item.status)}</div>
              {item.thumbnail && (
                <img
                  src={item.thumbnail}
                  alt=""
                  className="w-9 h-9 rounded object-cover shrink-0 bg-raised"
                  referrerPolicy="no-referrer"
                />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-fg truncate">
                    {item.title}
                  </p>
                  {item.timestamp && (
                    <span className="text-[10px] font-mono text-fg-subtle shrink-0">
                      {formatTimestamp(item.timestamp)}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-fg-muted line-clamp-2">
                  {item.message}
                </p>
                {item.url && (
                  <a
                    href={item.url}
                    {...(isInAppLink(item.url) ? {} : { target: "_blank", rel: "noreferrer" })}
                    className="mt-1 inline-flex items-center gap-1 text-[11px] text-accent hover:underline truncate max-w-full"
                  >
                    <span className="truncate">{notificationLinkLabel(item.url)}</span>
                    {!isInAppLink(item.url) && <ExternalLink className="w-3 h-3 shrink-0" />}
                  </a>
                )}
              </div>
            </div>
          ))
        )}
      </Dialog>
    </>
  );
};
