import React, { useState } from "react";
import { Bell, Trash2, X } from "lucide-react";
import { NotificationBannerItem } from "../types";

interface NotificationHistoryProps {
  history: NotificationBannerItem[];
  onClear: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  hideTrigger?: boolean;
}

export const NotificationHistory: React.FC<NotificationHistoryProps> = ({ history, onClear, open: controlledOpen, onOpenChange, hideTrigger = false }) => {
  const [localOpen, setLocalOpen] = useState(false);
  const open = controlledOpen ?? localOpen;
  const setOpen = onOpenChange ?? setLocalOpen;

  return (
    <>
      {!hideTrigger && <button type="button" onClick={() => setOpen(true)} className="fixed bottom-5 left-5 z-40 flex items-center gap-2.5 rounded-lg border border-[#282828] bg-[#181818] px-3.5 py-2.5 text-sm font-semibold text-[#b3b3b3] shadow-lg shadow-black/20 transition-colors hover:bg-[#242424] hover:text-white" title="Notification history" aria-label="Notification history">
        <Bell className="h-4 w-4 text-[#1ed760]" />
        <span>History</span>
        {history.length > 0 && <span className="min-w-5 rounded-full bg-[#147f3e] px-1.5 py-0.5 text-center text-[10px] font-bold leading-none text-white ots-on-green-text">{history.length}</span>}
      </button>}
      {open && (
        <div
          className="fixed inset-0 z-[60] flex items-end justify-start bg-black/50 p-5 sm:items-center sm:justify-center"
          onClick={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <div className="flex max-h-[75vh] w-full max-w-lg flex-col border border-[#333] bg-[#202020] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#333] p-4"><div><p className="text-xs font-bold uppercase tracking-wider text-[#1ed760]">Activity</p><h2 className="text-lg font-bold text-white">Notification history</h2></div><button type="button" onClick={() => setOpen(false)} aria-label="Close notification history" className="p-1 text-[#b3b3b3] hover:text-white"><X className="h-5 w-5" /></button></div>
            <div className="flex-1 overflow-y-auto">
              {history.length === 0 ? <p className="p-8 text-center text-sm text-[#777]">No notifications yet.</p> : history.map((item) => <div key={item.id} className="border-b border-[#2e2e2e] p-4"><p className="text-sm font-bold text-white">{item.title}</p><p className="mt-1 text-xs text-[#b3b3b3]">{item.message}</p>{item.url && <a href={item.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-[#1ed760]">{item.url}</a>}</div>)}
            </div>
            <div className="flex justify-end border-t border-[#333] p-3"><button type="button" onClick={onClear} disabled={history.length === 0} className="flex items-center gap-2 px-3 py-2 text-xs font-bold text-[#ff7b7b] hover:bg-[#3a2424] disabled:opacity-40"><Trash2 className="h-4 w-4" /> Clear history</button></div>
          </div>
        </div>
      )}
    </>
  );
};
