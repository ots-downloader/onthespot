import { AlertCircle, CheckCircle2, DownloadCloud, Info, X } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { isInAppLink, notificationLinkLabel } from "../lib/notifications";
import { NotificationBannerItem } from "../types";

interface NotificationBannerProps {
  notifications: NotificationBannerItem[];
  onDismiss: (id: string) => void;
  disabled?: boolean;
}

const NotificationItem: React.FC<{
  notif: NotificationBannerItem;
  onDismiss: (id: string) => void;
}> = ({ notif, onDismiss }) => {
  const [isExiting, setIsExiting] = useState(false);
  const isExitingRef = useRef(false);
  const onDismissRef = useRef(onDismiss);
  const removalTimerRef = useRef<number | null>(null);

  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  const handleDismiss = useCallback(() => {
    if (isExitingRef.current) return;
    isExitingRef.current = true;
    setIsExiting(true);
    removalTimerRef.current = window.setTimeout(() => {
      onDismissRef.current(notif.id);
    }, 300);
  }, [notif.id]);

  useEffect(() => {
    const autoDismissTimer = window.setTimeout(handleDismiss, 5000);
    return () => {
      window.clearTimeout(autoDismissTimer);
      if (removalTimerRef.current !== null) {
        window.clearTimeout(removalTimerRef.current);
      }
    };
  }, [handleDismiss]);

  const isSuccess = notif.status === "Completed" || notif.status === "success";
  const isFail = notif.status === "Failed" || notif.status === "Cancelled" || notif.status === "error";
  const isDownloading = notif.status === "Downloading";

  return (
    <div
      id={`notification-banner-${notif.id}`}
      className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl shadow-xl border transition-all duration-300 backdrop-blur-md bg-white/95 dark:bg-neutral-900/95 border-neutral-200 dark:border-neutral-800 text-neutral-900 dark:text-neutral-100 ${
        isExiting ? "opacity-0 translate-x-8 scale-95" : "animate-in fade-in slide-in-from-bottom-2 duration-300"
      }`}
    >
      {/* Status Icon */}
      <div className="shrink-0 mt-0.5">
        {isSuccess && <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />}
        {isFail && <AlertCircle className="w-5 h-5 text-rose-600 dark:text-rose-400" />}
        {isDownloading && <DownloadCloud className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-pulse" />}
        {!isSuccess && !isFail && !isDownloading && (
          <Info className="w-5 h-5 text-neutral-500 dark:text-neutral-400" />
        )}
      </div>

      {/* Thumbnail if provided */}
      {notif.thumbnail && (
        <img
          src={notif.thumbnail}
          alt="Cover art"
          className="w-10 h-10 rounded-md object-cover shrink-0 bg-neutral-100 dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700"
          referrerPolicy="no-referrer"
        />
      )}

      {/* Text Content */}
      <div className="flex-1 min-w-0 pr-2">
        <p className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate mb-0.5">
          {notif.title}
        </p>
        <p className="text-xs text-neutral-600 dark:text-neutral-400 line-clamp-2 leading-relaxed">
          {notif.message}
        </p>
        {notif.url && (
          <a
            href={notif.url}
            {...(isInAppLink(notif.url) ? {} : { target: "_blank", rel: "noopener noreferrer" })}
            className="text-[11px] text-blue-600 hover:underline dark:text-blue-400 mt-1 block truncate"
          >
            {notificationLinkLabel(notif.url)}
          </a>
        )}
      </div>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={handleDismiss}
        className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 p-1 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer shrink-0"
        aria-label="Dismiss notification"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

export const NotificationBanner: React.FC<NotificationBannerProps> = ({
  notifications,
  onDismiss,
  disabled,
}) => {
  if (disabled || notifications.length === 0) return null;

  return (
    <div
      id="notification-banners-container"
      className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none px-4 sm:px-0 select-none"
    >
      {notifications.slice(0, 4).map((notif) => (
        <NotificationItem key={notif.id} notif={notif} onDismiss={onDismiss} />
      ))}
    </div>
  );
};
