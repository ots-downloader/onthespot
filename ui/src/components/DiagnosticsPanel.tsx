import React, { useEffect, useState } from "react";
import { Activity, CheckCircle2, Loader2, RefreshCw, Sparkles, Wifi, WifiOff, XCircle } from "lucide-react";
import { fetchSystemDiagnostics, getTargetBackendUrl, SystemDiagnostics } from "../lib/api";

interface DiagnosticsPanelProps {
  wsConnected: boolean;
  newVersion: boolean;
  checkVersion: () => Promise<void>;
}

const formatBytes = (value: number) => {
  if (!value) return "—";
  const units = ["B", "MB", "GB", "TB"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`;
};

export const DiagnosticsPanel: React.FC<DiagnosticsPanelProps> = ({ wsConnected, newVersion, checkVersion }) => {
  const [data, setData] = useState<SystemDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    setData(await fetchSystemDiagnostics());
    setLoading(false);
  };

  useEffect(() => { void refresh(); const interval = window.setInterval(() => void refresh(), 10_000); return () => window.clearInterval(interval); }, []);

  if (loading && !data) return <div className="flex items-center gap-2 p-4 text-sm text-gray-500"><Loader2 className="h-4 w-4 animate-spin" /> Reading worker diagnostics…</div>;
  if (!data) return <div className="p-4 text-sm text-red-600">Diagnostics are unavailable.</div>;

  const activeWorkers = Object.values(data.workers).filter(Boolean).length;
  const queueStatuses = Object.entries(data.queue.statuses);
  const apiUrl = getTargetBackendUrl();
  const spotifyApi = data.spotify_api || { configured: false, connected: false, status: "Unavailable", rate_limited: false, seconds_remaining: 0 };

  return (
    <div className="spotify-fade-up ots-page flex flex-col font-sans">
      <section className="ots-hero">
        <div className="flex min-w-0 flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <p className="mb-2 text-xs font-bold uppercase tracking-[0.2em] text-[#1ed760]">System health</p>
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight text-white"><Activity className="h-6 w-6 text-[#1ed760]" /> OnTheSpot diagnostics</h1>
            <p className="mt-2 text-sm text-[#b3b3b3]">Live service, worker, queue, storage, FFmpeg, and API rate-limit status.</p>
            <div className="mt-3 flex min-w-0 items-center gap-2 text-xs">
              {wsConnected ? <Wifi className="h-4 w-4 shrink-0 text-[#1ed760]" /> : <WifiOff className="h-4 w-4 shrink-0 text-[#f6b94a]" />}
              <span className="font-bold text-white">{wsConnected ? "Connected" : "Connecting"}</span>
              <span className="text-[#555]">•</span>
              <a
                href={apiUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="truncate text-[#8f8f8f] underline-offset-2 transition-colors hover:text-white hover:underline"
                title={`Open ${apiUrl}`}
              >
                {apiUrl}
              </a>
            </div>
          </div>
          <div className="flex w-full shrink-0 flex-col gap-2 xl:max-w-[640px]">
            <div className="grid grid-cols-2 gap-2">
              <span className="ots-status-cell ots-status-cell--online"><CheckCircle2 className="h-4 w-4 shrink-0" /> OnTheSpot online</span>
              <span className={spotifyApi.connected && !spotifyApi.rate_limited ? "ots-status-cell ots-status-cell--online" : spotifyApi.rate_limited ? "ots-status-cell border-[var(--ots-warning)] text-[var(--ots-warning)]" : "ots-status-cell"}>{spotifyApi.rate_limited ? <WifiOff className="h-4 w-4 shrink-0" /> : <Wifi className="h-4 w-4 shrink-0" />} Spotify API: {spotifyApi.status}</span>
              <span className={spotifyApi.connect_service?.running ? "ots-status-cell ots-status-cell--online" : "ots-status-cell border-[var(--ots-warning)] text-[var(--ots-warning)]"}>{spotifyApi.connect_service?.running ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <WifiOff className="h-4 w-4 shrink-0" />} Spotify Connect: {spotifyApi.connect_service?.running ? `Discoverable (${spotifyApi.connect_service.port})` : "Unavailable"}</span>
              <span className={spotifyApi.rate_limited ? "ots-status-cell border-[var(--ots-warning)] text-[var(--ots-warning)]" : "ots-status-cell"}>{spotifyApi.rate_limited ? `Rate limited: ${spotifyApi.seconds_remaining}s` : "No Spotify rate limit"}</span>
              <button type="button" onClick={() => void refresh()} className="ots-status-cell text-white" disabled={loading}><RefreshCw className={`h-4 w-4 shrink-0 ${loading ? "animate-spin" : ""}`} /> Refresh</button>
            </div>
            {newVersion && <span className="flex items-center justify-end gap-1.5 px-1 text-xs font-bold text-[#1ed760]"><Sparkles className="h-3.5 w-3.5" /> New update available</span>}
          </div>
        </div>
      </section>

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <div className="ots-tile"><p className="ots-tile-label">Queue</p><p className="mt-2 text-2xl font-bold text-white">{data.queue.downloads}</p><p className="text-xs text-[#8f8f8f]">{data.queue.pending} pending · {data.queue.parsing} parsing</p></div>
        <div className="ots-tile"><p className="ots-tile-label">Disk free</p><p className="mt-2 text-2xl font-bold text-white">{formatBytes(data.disk.free)}</p><p className="text-xs text-[#8f8f8f]">of {formatBytes(data.disk.total)}</p></div>
        <div className="ots-tile"><p className="ots-tile-label">FFmpeg</p><p className="mt-2 flex items-center gap-2 text-sm font-bold text-white">{data.ffmpeg.available ? <CheckCircle2 className="h-4 w-4 text-[#1ed760]" /> : <XCircle className="h-4 w-4 text-[#ff7b7b]" />} {data.ffmpeg.available ? "Available" : "Missing"}</p><p className="mt-1 truncate text-xs text-[#777]" title={data.ffmpeg.path}>{data.ffmpeg.path || "Set FFMPEG_PATH"}</p></div>
      </section>

      <section className="ots-panel p-5">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
          <div><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#1ed760]">Runtime</p><h2 className="mt-1 text-lg font-bold text-white">Worker threads</h2></div>
          <span className="text-xs font-bold text-[#8f8f8f]">{activeWorkers}/{Object.keys(data.workers).length} online</span>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">{Object.entries(data.workers).map(([name, active]) => <span key={name} className={`flex items-center gap-1.5 border px-3 py-2 text-xs font-bold ${active ? "ots-status-pill--active" : "ots-status-pill--inactive"}`}>{active ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}{name}</span>)}</div>
        <div className="mt-5 border-t border-[#282828] pt-4"><p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-[#777]">Queue breakdown</p>{queueStatuses.length > 0 ? <div className="flex flex-wrap gap-2">{queueStatuses.map(([status, count]) => <span key={status} className="border border-[#333] bg-[#202020] px-3 py-2 text-xs font-bold text-[#b3b3b3]">{status}: <span className="text-white">{count}</span></span>)}</div> : <p className="text-sm text-[#777]">No items are currently in the queue.</p>}</div>
      </section>
    </div>
  );
};
