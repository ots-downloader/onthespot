// src/hooks/useNotifications.ts
import { useState, useEffect } from 'react';
import { DownloadQueueItem, NotificationBannerItem } from '../types';
import { getTargetBackendUrl } from './api';

export interface Notification {
  id: string;
  message: string;
}

export function useNotifications(userId: string) {
  const [notifications, setNotifications] = useState<Notification[]>([]);

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
            id: eventData.content?.id || crypto.randomUUID(),           // Use notification.id or generate one
            title: eventData.content?.title || '',            // Safe access with optional chaining
            message: eventData.content?.message || '',        // Safe access
            url: eventData.content?.url || '',                // Safe access
            status: '',                                       // No status from backend yet
            };
            setNotifications(prevItems => [newNotif, ...prevItems]);
        } else if (eventType === 'STATUS_CHANGE') {
            const newNotif: NotificationBannerItem = {
            id: eventData?.local_id || crypto.randomUUID(),            // Use item.local_id if available
            title: eventData?.name || '',                     // Safe access with optional chaining
            message: eventData?.item_status,                       // Backend sends this directly
            status: (eventData?.item_status as any) || '',   // Safe cast
            thumbnail: eventData?.thumbnail || '',            // Safe access
            timestamp: new Date()
            };
            setNotifications(prevItems => {
            if (prevItems.length === 0) return [newNotif];
            if (prevItems.some(item => item.id === newNotif.id)) {
                return prevItems.map(item => item.id === newNotif.id ? newNotif : item)
            } else {
                return [newNotif, ...prevItems]
            }});
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

  return { notifications, dismissNotification };
}