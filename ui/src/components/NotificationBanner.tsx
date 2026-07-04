import React, { useState } from 'react';
import { CheckCircle2, AlertCircle, X, DownloadCloud } from 'lucide-react';
import { NotificationBannerItem } from '../types';

interface NotificationBannerProps {
  notifications: NotificationBannerItem[];
  onDismiss: (id: string) => void;
  disabled?: boolean;
}

const NotificationItem: React.FC<{ notif: NotificationBannerItem; onDismiss: (id: string) => void }> = ({ notif, onDismiss }) => {
  const [isExiting, setIsExiting] = useState(false);

  const handleDismiss = () => {
    setIsExiting(true);
    setTimeout(() => {
      onDismiss(notif.id);
    }, 300); // Matches transition duration
  };

  const isSuccess = notif.status === 'Completed';
  const isFail = notif.status === 'Failed' || notif.status === 'Cancelled';
  const isDownloading = notif.status === 'Downloading';

  return (
    <div
      className={`pointer-events-auto flex items-start gap-3 p-4 rounded-xl shadow-lg border transition-all duration-300 bg-white dark:bg-[#1a1a1a] border-gray-200 dark:border-neutral-800 ${
        isExiting ? 'opacity-0 translate-x-8 scale-95' : 'animate-[slideIn_0.3s_ease-out]'
      }`}
    >
      {/* Icon */}
      <div className="shrink-0 mt-0.5">
        {isSuccess && <CheckCircle2 className="w-5 h-5 text-green-600 dark:text-green-400" />}
        {isFail && <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400" />}
        {isDownloading && <DownloadCloud className="w-5 h-5 text-blue-600 dark:text-blue-400" />}
      </div>

      {/* Thumbnail if any */}
      {notif.thumbnail && (
        <img
          src={notif.thumbnail}
          alt="Thumbnail"
          className="w-10 h-10 rounded object-cover shrink-0 bg-gray-100 dark:bg-neutral-800"
          referrerPolicy="no-referrer"
        />
      )}

      {/* Content */}
      <div className="flex-1 min-w-0 pr-2">
        <p className="text-sm font-semibold text-gray-900 dark:text-neutral-100 truncate mb-0.5">
          {notif.title}
        </p>
        <p className="text-xs text-gray-600 dark:text-neutral-400 line-clamp-2 leading-relaxed">
          {notif.message}
        </p>
        {notif.url && (
          <a 
            href={notif.url} 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline dark:text-blue-400 mt-1 block truncate"
          >
            {notif.url}
          </a>
        )}
      </div>

      {/* Close Action */}
      <button
        onClick={handleDismiss}
        className="text-gray-400 hover:text-gray-600 dark:text-neutral-500 dark:hover:text-neutral-300 p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-neutral-800 transition-colors cursor-pointer shrink-0"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
};

export const NotificationBanner: React.FC<NotificationBannerProps> = ({
  notifications,
  onDismiss,
  disabled
}) => {
  if (disabled || notifications.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm w-full pointer-events-none px-4 sm:px-0 select-none font-sans">
      {notifications.slice(0, 4).map((notif) => (
        <NotificationItem key={notif.id} notif={notif} onDismiss={onDismiss} />
      ))}
    </div>
  );
};