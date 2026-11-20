import { AlertCircle, CheckCircle2, DownloadCloud, Info, X } from "lucide-react";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { isInAppLink, notificationLinkLabel } from "../lib/notifications";
import { NotificationBannerItem } from "../types";
import { IconButton } from "./ui";

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
      className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl shadow-xl border transition-all duration-300 backdrop-blur-md bg-surface/95 border-line text-fg ${
        isExiting ? "opacity-0 translate-x-8 scale-95" : "animate-in fade-in slide-in-from-bottom-2 duration-300"
      }`}
    >
      {/* Status Icon */}
      <div className="shrink-0 mt-0.5">
        {isSuccess && <CheckCircle2 className="w-5 h-5 text-success-fg" />}
        {isFail && <AlertCircle className="w-5 h-5 text-danger-fg" />}
        {isDownloading && <DownloadCloud className="w-5 h-5 text-info-fg animate-pulse" />}
        {!isSuccess && !isFail && !isDownloading && (
          <Info className="w-5 h-5 text-fg-subtle" />
        )}
      </div>

      {/* Thumbnail if provided */}
      {notif.thumbnail && (
        <img
          src={notif.thumbnail}
          alt="Cover art"
          className="w-10 h-10 rounded-md object-cover shrink-0 bg-raised border border-line"
          referrerPolicy="no-referrer"
        />
      )}

      {/* Text Content */}
      <div className="flex-1 min-w-0 pr-2">
        <p className="text-sm font-semibold text-fg truncate mb-0.5">
          {notif.title}
        </p>
        <p className="text-xs text-fg-muted line-clamp-2 leading-relaxed">
          {notif.message}
        </p>
        {notif.url && (
          <a
            href={notif.url}
            {...(isInAppLink(notif.url) ? {} : { target: "_blank", rel: "noopener noreferrer" })}
            className="text-[11px] text-info-fg hover:underline mt-1 block truncate"
          >
            {notificationLinkLabel(notif.url)}
          </a>
        )}
      </div>

      {/* Dismiss button */}
      <IconButton
        label="Dismiss notification"
        icon={<X className="w-4 h-4" />}
        variant="ghost"
        size="sm"
        onClick={handleDismiss}
        className="size-6 rounded-md text-fg-subtle hover:text-fg"
      />
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
