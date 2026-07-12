// src/hooks/useNotifications.ts
import { useState, useEffect } from 'react';
import { NotificationBannerItem } from '../types';
import { getTargetBackendUrl } from './api';

export function useNotifications(userId: string) {
  const [notifications, setNotifications] = useState<NotificationBannerItem[]>([]);
  const [history, setHistory] = useState<NotificationBannerItem[]>(() => {
    try {
      const stored = localStorage.getItem("ots-notification-history");
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  });
  const [lastStatusChange, setLastStatusChange] = useState(0);

  useEffect(() => {
    if (!userId) return;

    // Connect to the FastAPI SSE endpoint
    const eventSource = new EventSource(`${getTargetBackendUrl()}/api/sse/${userId}`);

    // Listen for events pushed from the server
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const eventType = data.type;
        const eventData = data.event || null;
        if (eventType === 'Notification') {
            const newNotif: NotificationBannerItem = {
            id: eventData.id || crypto.randomUUID(),
            title: eventData.title || '',
            message: eventData.message || '',
            url: eventData.url || '',
            status: '',
            };
            setNotifications(prevItems => [newNotif, ...prevItems]);
            setHistory((previous) => {
              const next = [newNotif, ...previous].slice(0, 100);
              try { localStorage.setItem("ots-notification-history", JSON.stringify(next)); } catch { /* storage is optional */ }
              return next;
            });
        } else if (eventType === 'STATUS_CHANGE') {
            // Queue status changes drive the progress UI, but should not create
            // a popup for every track and every progress update.
            setLastStatusChange((value) => value + 1);
        }
      } catch (error) {
        console.error("Failed to parse notification:", error);
      }
    };

    eventSource.onerror = (error) => {
      console.error("SSE Connection Error. Browser will auto-reconnect.", error);
    };

    // CLEANUP: Close connection when the component unmounts
    return () => {
      eventSource.close();
    };
  }, [userId]);

  // Helper function to remove a notification once the user reads it
  const dismissNotification = (id: string) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  };

  const clearHistory = () => {
    setHistory([]);
    try { localStorage.removeItem("ots-notification-history"); } catch { /* storage is optional */ }
  };

  return { notifications, history, dismissNotification, clearHistory, lastStatusChange };
}
