import React, { useEffect, useState } from "react";
import { BarChart3, CheckCircle2, Clock3, HardDrive, RefreshCw, Trash2, XCircle } from "lucide-react";
import { clearDownloadStatistics, DownloadStatistics, fetchDownloadStatistics } from "../lib/api";

const formatBytes = (value: number) => {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`;
};

const formatDate = (timestamp: number) => new Date(timestamp * 1000).toLocaleString(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export const StatisticsPanel: React.FC = () => {
  const [data, setData] = useState<DownloadStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [notice, setNotice] = useState("");

  const load = async () => {
    setLoading(true);
    setData(await fetchDownloadStatistics());
    setLoading(false);
  };

  const clearStats = async () => {
    setClearing(true);
    const success = await clearDownloadStatistics();
    setConfirmClear(false);
    setNotice(success ? "Download statistics cleared." : "Could not clear download statistics.");
    if (success) await load();
    setClearing(false);
  };

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 10000);
    return () => window.clearInterval(interval);
  }, []);

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">
      <section className="ots-hero flex flex-col justify-between gap-4 p-6 md:flex-row md:items-center">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-[#1ed760]">Your download history</p>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-white"><BarChart3 className="h-6 w-6 text-[#1ed760]" /> Download statistics</h1>
          <p className="mt-2 text-sm text-[#b3b3b3]">Track storage, formats, success rate, and recent download activity.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => void load()} disabled={loading || clearing} className="ots-button ots-button-secondary"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} /> Refresh</button>
          {confirmClear ? (
            <>
              <span className="text-xs font-semibold text-[#b3b3b3]">Clear all history?</span>
              <button type="button" onClick={() => setConfirmClear(false)} disabled={clearing} className="ots-button ots-button-secondary">Cancel</button>
              <button type="button" onClick={() => void clearStats()} disabled={clearing} className="ots-button ots-button-danger">{clearing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />} Clear statistics</button>
            </>
          ) : (
            <button type="button" onClick={() => setConfirmClear(true)} disabled={loading || clearing} className="ots-button ots-button-danger"><Trash2 className="h-4 w-4" /> Clear statistics</button>
          )}
        </div>
      </section>

      {notice && <div className="ots-panel px-4 py-3 text-sm text-[#b3b3b3]">{notice}</div>}

      {!data ? (
        <div className="ots-panel p-10 text-center text-sm text-[#b3b3b3]">Statistics are unavailable.</div>
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Downloads", data.totals.downloads.toLocaleString(), <BarChart3 className="h-5 w-5" />],
              ["Storage used", formatBytes(data.storage_used), <HardDrive className="h-5 w-5" />],
              ["Success rate", `${data.totals.success_rate}%`, <CheckCircle2 className="h-5 w-5" />],
              ["Library tracks", data.library_tracks.toLocaleString(), <Clock3 className="h-5 w-5" />],
            ].map(([label, value, icon]) => (
              <div key={String(label)} className="ots-tile p-5">
                <div className="flex items-center justify-between text-[#1ed760]"><span className="ots-tile-label">{label}</span>{icon}</div>
                <p className="mt-3 text-2xl font-bold text-white">{value}</p>
              </div>
            ))}
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <div className="ots-panel p-5">
              <h2 className="text-lg font-bold text-white">Formats</h2>
              <div className="mt-4 flex flex-col gap-3">
                {Object.entries(data.formats).length === 0 ? <p className="text-sm text-[#777]">No completed downloads yet.</p> : Object.entries(data.formats).map(([format, count]) => {
                  const max = Math.max(...Object.values(data.formats));
                  return <div key={format}><div className="mb-1 flex justify-between text-xs font-bold text-[#b3b3b3]"><span>{format.toUpperCase()}</span><span>{count}</span></div><div className="h-2 bg-[#282828]"><div className="h-full bg-[#1ed760]" style={{ width: `${(count / max) * 100}%` }} /></div></div>;
                })}
              </div>
            </div>
            <div className="ots-panel p-5">
              <h2 className="text-lg font-bold text-white">Queue status</h2>
              <div className="mt-4 grid grid-cols-2 gap-2 text-sm">
                {Object.entries(data.queue_counts).map(([status, count]) => <div key={status} className="flex items-center justify-between bg-[#202020] px-3 py-2 text-[#b3b3b3]"><span>{status}</span><span className="font-bold text-white">{count}</span></div>)}
              </div>
            </div>
          </section>

          <section className="ots-panel overflow-hidden">
            <div className="border-b border-[#282828] p-5"><h2 className="text-lg font-bold text-white">Recent activity</h2></div>
            {data.history.length === 0 ? <p className="p-8 text-center text-sm text-[#777]">No download history yet.</p> : <div className="divide-y divide-[#282828]">{data.history.map((event) => <div key={event.id} className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between"><div className="min-w-0"><p className="truncate text-sm font-bold text-white">{event.name || "Untitled download"}</p><p className="truncate text-xs text-[#8f8f8f]">{event.artist || "Unknown artist"} · {formatDate(event.timestamp)}</p></div><div className="flex items-center gap-3 text-xs font-bold"><span className={event.success ? "text-[#1ed760]" : "text-[#ff7b7b]"}>{event.success ? <CheckCircle2 className="inline h-4 w-4" /> : <XCircle className="inline h-4 w-4" />} {event.status}</span><span className="text-[#777]">{formatBytes(event.bytes)}</span></div></div>)}</div>}
          </section>
        </>
      )}
    </div>
  );
};
