import { useCallback, useEffect, useState } from "react";
import { NotificationBannerItem } from "../types";
import { getTargetBackendUrl } from "./api";

const HISTORY_STORAGE_KEY = "ots-notification-history";

/** True for links inside the app, such as "#settings/max_queue_size". */
export function isInAppLink(url: string): boolean {
  return url.startsWith("#");
}

/** Text shown for a notification link: a short label for in-app links, else the URL. */
export function notificationLinkLabel(url: string): string {
  return url.startsWith("#settings") ? "Open settings" : url;
}

// Global dispatch helper to trigger notifications from anywhere in the app
export function notify(item: {
  title: string;
  message: string;
  status?: "Completed" | "Failed" | "Cancelled" | "Downloading" | "success" | "warning" | "error" | "info" | string;
  thumbnail?: string;
  url?: string;
  id?: string;
}) {
  if (typeof window === "undefined") return;
  const notif: NotificationBannerItem = {
    id: item.id || `notif-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
    title: item.title,
    message: item.message,
    status: item.status || "info",
    thumbnail: item.thumbnail,
    url: item.url,
    timestamp: new Date(),
  };
  window.dispatchEvent(new CustomEvent("ots:notification", { detail: notif }));
}

export function useNotifications(userId?: string) {
  const [notifications, setNotifications] = useState<NotificationBannerItem[]>([]);
  const [history, setHistory] = useState<NotificationBannerItem[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      const stored = localStorage.getItem(HISTORY_STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [lastStatusChange, setLastStatusChange] = useState(0);

  // Helper to add a notification to both active banner list and history
  const addNotification = useCallback((item: Partial<NotificationBannerItem> & { title: string; message: string }) => {
    const newNotif: NotificationBannerItem = {
      id: item.id || `notif-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
      title: item.title,
      message: item.message,
      status: item.status || "info",
      thumbnail: item.thumbnail,
      url: item.url,
      timestamp: item.timestamp || new Date(),
    };

    // Add to active banners (limited to recent)
    setNotifications((prev) => {
      // If already present with same id, replace it
      if (prev.some((n) => n.id === newNotif.id)) {
        return prev.map((n) => (n.id === newNotif.id ? newNotif : n));
      }
      return [newNotif, ...prev].slice(0, 5);
    });

    // Record in history (limited to 100)
    setHistory((prev) => {
      const next = [newNotif, ...prev.filter((n) => n.id !== newNotif.id)].slice(0, 100);
      try {
        localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // storage quota exceeded or unavailable
      }
      return next;
    });

    setLastStatusChange(Date.now());
  }, []);

  // Listen to in-app custom event
  useEffect(() => {
    const handleCustomEvent = (e: Event) => {
      const customEvent = e as CustomEvent<NotificationBannerItem>;
      if (customEvent.detail) {
        addNotification(customEvent.detail);
      }
    };

    window.addEventListener("ots:notification", handleCustomEvent);
    return () => {
      window.removeEventListener("ots:notification", handleCustomEvent);
    };
  }, [addNotification]);

  // Connect to FastAPI SSE endpoint if configured
  useEffect(() => {
    const targetUrl = getTargetBackendUrl();
    if (!targetUrl || !userId) return;

    let eventSource: EventSource | null = null;
    try {
      eventSource = new EventSource(`${targetUrl}/api/sse/${userId}`);

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const eventType = data.type;
          const eventData = data.event || null;

          if (eventType === "Notification" && eventData) {
            addNotification({
              id: eventData.id || `sse-${Date.now()}`,
              title: eventData.title || "System Alert",
              message: eventData.message || "",
              url: eventData.url || "",
              status: eventData.status || "info",
            });
          } else if (eventType === "STATUS_CHANGE" && eventData) {
            addNotification({
              id: eventData.local_id || `sse-status-${Date.now()}`,
              title: eventData.name || "Download Update",
              message: `Status: ${eventData.item_status || "Updated"}`,
              status: eventData.item_status || "Downloading",
              thumbnail: eventData.thumbnail || "",
              url: eventData.url || "",
            });
          }
        } catch (error) {
          console.error("Failed to parse SSE notification:", error);
        }
      };

      eventSource.onerror = () => {
        // Handled silently - EventSource will reconnect automatically
      };
    } catch {
      // Fallback
    }

    return () => {
      if (eventSource) {
        eventSource.close();
      }
    };
  }, [userId, addNotification]);

  const dismissNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clearHistory = useCallback(() => {
    setHistory([]);
    try {
      localStorage.removeItem(HISTORY_STORAGE_KEY);
    } catch {
      // storage unavailable
    }
  }, []);

  return {
    notifications,
    history,
    addNotification,
    dismissNotification,
    clearHistory,
    lastStatusChange,
  };
}
