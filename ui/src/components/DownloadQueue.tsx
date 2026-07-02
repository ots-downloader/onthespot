import React, { useState } from 'react';
import { Download, FolderOpen, ExternalLink, Trash2, RefreshCw, CheckCircle2, AlertCircle, Clock, Zap, Copy, Check, Play, Filter, ArrowUpDown } from 'lucide-react';
import { DownloadQueueItem, OTSConfig } from '../types';
import { getTargetBackendUrl } from '../lib/api';

interface DownloadQueueProps {
  queue: DownloadQueueItem[];
  onClearCompleted: () => Promise<void>;
  onRetryFailed: () => Promise<void>;
  onAction: (local_id: string, action: 'cancel' | 'delete' | 'retry') => Promise<void>;
  config: OTSConfig | null;
}

type StatusFilter = 'All' | 'Downloading' | 'Waiting' | 'Downloaded' | 'Failed' | 'Cancelled' | 'Already Exists';

export const DownloadQueue: React.FC<DownloadQueueProps> = ({
  queue,
  onClearCompleted,
  onRetryFailed,
  onAction,
  config
}) => {
  const [filter, setFilter] = useState<StatusFilter>('All');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState(false);

  // Filter items based on selected pill AND config display flags
  const filteredQueue = queue.filter(item => {
    // Unify filter for already exists status and return before filter for status
    if (filter === 'Downloaded' && (item.item_status === 'Already Exists' || item.item_status === filter)) return true

    if (filter !== 'All' && item.item_status !== filter) return false;

    // Check config filter flags
    if (item.item_status === 'Waiting' && config?.download_queue_show_waiting === false) return false;
    if (item.item_status === 'Failed' && config?.download_queue_show_failed === false) return false;
    if (item.item_status === 'Cancelled' && config?.download_queue_show_cancelled === false) return false;
    if (item.item_status === 'Downloaded' && config?.download_queue_show_completed === false) return false;

    return true;
  });

  const counts = {
    All: queue.length,
    Downloading: queue.filter(i => i.item_status === 'Downloading').length,
    Waiting: queue.filter(i => i.item_status === 'Waiting').length,
    Downloaded: queue.filter(i => i.item_status === 'Downloaded' || i.item_status === 'Already Exists').length,
    Failed: queue.filter(i => i.item_status === 'Failed').length,
    Cancelled: queue.filter(i => i.item_status === 'Cancelled').length,
  };

  const handleCopyLink = (item: DownloadQueueItem) => {
    navigator.clipboard.writeText(item.file_path || `https://open.spotify.com/track/${item.item_id}`);
    setCopiedId(item.local_id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleLocateClick = (item: DownloadQueueItem) => {
    alert(`📂 OnTheSpot Audio Path:\n${item.file_path || config?.audio_download_path + '/Tracks/' + item.artist + '/' + item.name + '.flac'}`);
  };

  const handleOpenClick = async (item: DownloadQueueItem) => {
    if (item.file_path) {
      alert(`▶ Playing local file:\n${item.file_path}`);
    } else {
      alert("⚠️ File is still queued or downloading.");
    }
  };

  const handleDownloadFile = (item: DownloadQueueItem) => {
    if (item.file_path) {
      const url = `${getTargetBackendUrl()}/queue/downloads/download?id=${encodeURIComponent(item.local_id)}`;
      window.open(url, '_blank');
    } else {
      alert("⚠️ File is still queued or downloading.");
    }
  };
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'Downloading':
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 text-xs font-mono font-bold animate-pulse"><Zap className="w-3.5 h-3.5" /> Downloading</span>;
      case 'Downloaded':
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 text-xs font-mono font-bold"><CheckCircle2 className="w-3.5 h-3.5" /> Completed</span>;
      case 'Waiting':
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 text-xs font-mono font-bold"><Clock className="w-3.5 h-3.5 animate-spin" /> Waiting</span>;
      case 'Failed':
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30 text-xs font-mono font-bold"><AlertCircle className="w-3.5 h-3.5" /> Failed</span>;
      default:
        return <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700 text-xs font-mono font-bold">{status}</span>;
    }
  };

  const getServiceLabel = (service: string) => {
    const s = service.toLowerCase();
    const color = s === 'spotify' ? 'text-[#1ed760]' : s === 'tidal' ? 'text-cyan-400' : s === 'soundcloud' ? 'text-orange-400' : s.includes('apple') ? 'text-rose-400' : 'text-blue-400';
    return <span className={`font-mono font-bold text-[11px] uppercase ${color}`}>{service.replace('_', ' ')}</span>;
  };

  const getServiceBadge = (service: string) => {
    switch (service.toLowerCase()) {
      case 'spotify':
        return <span className="px-2 py-0.5 rounded-md bg-[#1DB954]/20 text-[#1ed760] text-[10px] font-mono font-bold border border-[#1DB954]/40 flex items-center gap-1">Spotify</span>;
      case 'tidal':
        return <span className="px-2 py-0.5 rounded-md bg-cyan-500/20 text-cyan-300 text-[10px] font-mono font-bold border border-cyan-500/40 flex items-center gap-1">Tidal HiFi</span>;
      case 'apple_music':
      case 'applemusic':
        return <span className="px-2 py-0.5 rounded-md bg-rose-500/20 text-rose-300 text-[10px] font-mono font-bold border border-rose-500/40 flex items-center gap-1">Apple Music</span>;
      case 'soundcloud':
        return <span className="px-2 py-0.5 rounded-md bg-orange-500/20 text-orange-300 text-[10px] font-mono font-bold border border-orange-500/40 flex items-center gap-1">SoundCloud</span>;
      case 'bandcamp':
        return <span className="px-2 py-0.5 rounded-md bg-blue-500/20 text-blue-300 text-[10px] font-mono font-bold border border-blue-500/40 flex items-center gap-1">Bandcamp</span>;
      case 'youtube_music':
      case 'youtube':
        return <span className="px-2 py-0.5 rounded-md bg-red-500/20 text-red-300 text-[10px] font-mono font-bold border border-red-500/40 flex items-center gap-1">YT Music</span>;
      default:
        return <span className="px-2 py-0.5 rounded-md bg-zinc-700/50 text-zinc-300 text-[10px] font-mono font-bold border border-zinc-600">Generic DL</span>;
    }
  };

  const showThumbnails = config?.show_download_thumbnails ?? true;

  return (
    <div className="max-w-7xl mx-auto p-4 lg:p-8 flex flex-col gap-6 animate-[fadeIn_0.3s_ease-out]">

      {/* Top Bar: Title & Bulk Actions */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white font-sans flex items-center gap-2.5">
            <span>Download & Conversion Queue</span>
            <span className="text-xs font-mono px-2.5 py-1 rounded-lg bg-zinc-800 text-emerald-400 border border-zinc-700">
              {counts.Downloading} active / {counts.Waiting} waiting
            </span>
          </h2>
          <p className="text-xs text-zinc-400 font-mono mt-1">
            Worker Threads: {config?.maximum_download_workers || 2} DL / {config?.maximum_queue_workers || 3} Queue • Delay: {config?.download_delay || 3}s
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center flex-wrap gap-2.5">
          <button
            onClick={async () => {
              setLoadingAction(true);
              await onRetryFailed();
              setLoadingAction(false);
            }}
            disabled={counts.Failed === 0 && counts.Cancelled === 0 || loadingAction}
            className="px-4 py-2.5 rounded-xl bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 border border-amber-500/30 text-xs font-mono font-bold transition-all flex items-center gap-2 cursor-pointer disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingAction ? 'animate-spin' : ''}`} />
            <span>Retry Failed ({counts.Failed + counts.Cancelled})</span>
          </button>

          <button
            onClick={async () => {
              setLoadingAction(true);
              await onClearCompleted();
              setLoadingAction(false);
            }}
            disabled={counts.Downloaded === 0 || loadingAction}
            className="px-4 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 text-xs font-mono font-bold transition-all flex items-center gap-2 cursor-pointer disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5 text-zinc-400" />
            <span>Clear Completed ({counts.Downloaded})</span>
          </button>

        </div>
      </div>

      {/* Filter Chips Pill */}
      <div className="flex items-center overflow-x-auto no-scrollbar gap-2 bg-zinc-950 p-2 rounded-xl border border-zinc-800">
        {(['All', 'Downloading', 'Waiting', 'Downloaded', 'Failed', 'Cancelled'] as StatusFilter[]).map((pill) => (
          <button
            key={pill}
            onClick={() => setFilter(pill)}
            className={`px-4 py-2 rounded-lg text-xs font-mono font-semibold transition-all cursor-pointer shrink-0 flex items-center gap-2 ${filter === pill
              ? 'bg-emerald-600 text-white shadow-md shadow-emerald-600/30'
              : 'bg-zinc-900 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800'
              }`}
          >
            <span>{pill}</span>
            <span className={`px-1.5 py-0.2 rounded text-[10px] ${filter === pill ? 'bg-white/20 text-white' : 'bg-zinc-800 text-zinc-400'
              }`}>
              {counts[pill]}
            </span>
          </button>
        ))}
      </div>

      {/* Queue Items Table / List */}
      <div className="bg-zinc-900/80 border border-zinc-800 rounded-2xl overflow-hidden shadow-2xl">
        {filteredQueue.length === 0 ? (
          <div className="p-16 text-center text-zinc-500 font-mono flex flex-col items-center justify-center gap-3">
            <Download className="w-8 h-8 text-zinc-600" />
            <p>No items match filter "{filter}".</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/80">
            {filteredQueue.reverse().map((item) => {
              const isDownloading = item.item_status === 'Downloading';
              const isCompleted = item.item_status === 'Downloaded' || item.item_status === 'Already Exists';

              return (
                <div
                  key={item.local_id}
                  className="p-4 sm:p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4 transition-colors hover:bg-zinc-800/40 group"
                >

                  {/* Left: Thumbnail & Info */}
                  <div className="flex items-center gap-4 min-w-0 flex-1">
                    {showThumbnails && (
                      <div className="relative w-14 h-14 rounded-xl overflow-hidden bg-zinc-950 border border-zinc-700 shrink-0 shadow-md">
                        <img
                          src={item.thumbnail || "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=150&auto=format&fit=crop&q=80"}
                          alt={item.name}
                          className="w-full h-full object-cover"
                          referrerPolicy="no-referrer"
                        />
                      </div>
                    )}

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        {getStatusBadge(item.item_status)}
                        <span className="text-zinc-600">•</span>
                        {getServiceBadge(item.item_service)}
                        <span className="text-zinc-600">•</span>
                        <span className="text-[11px] font-mono text-zinc-400 bg-zinc-800/80 px-2 py-0.5 rounded border border-zinc-700/60 truncate">
                          {item.parent_category || 'Track'}
                        </span>
                      </div>

                      <h4 className="font-bold text-white text-base font-sans truncate">
                        {item.name}
                      </h4>
                      <p className="text-xs text-zinc-400 font-sans truncate">
                        {item.artist} {item.album && `• [${item.album}]`}
                      </p>

                      {/* Path if completed */}
                      {isCompleted && item.file_path && (
                        <p className="text-[11px] text-zinc-500 font-mono truncate mt-1 max-w-xl">
                          📂 {item.file_path}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Middle: Progress Bar & Metrics */}
                  <div className="lg:w-72 shrink-0 flex flex-col justify-center gap-1.5">
                    <div className="flex items-center justify-between text-xs font-mono">
                      <span className="text-zinc-400">{item.progress}%</span>
                      <span className="text-emerald-400 font-semibold">{item.bitrate}</span>
                      <span className="text-zinc-500">{(item.file_size / (1024 * 1024)).toFixed(2) + " MB"}</span>
                    </div>

                    <div className="w-full h-2.5 rounded-full bg-zinc-950 overflow-hidden border border-zinc-800">
                      <div
                        className={`h-full transition-all duration-500 ${isCompleted
                          ? 'bg-emerald-500'
                          : isDownloading
                            ? 'bg-gradient-to-r from-cyan-500 via-emerald-400 to-teal-400 animate-[pulse_2s_infinite]'
                            : item.item_status === 'Failed'
                              ? 'bg-rose-500'
                              : 'bg-amber-500/50'
                          }`}
                        style={{ width: `${item.progress}%` }}
                      />
                    </div>
                  </div>

                  {/* Right: Action Buttons (respecting config flags!) */}
                  <div className="flex items-center justify-end gap-1.5 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-zinc-800">

                    {/* Open Button */}
                    {(config?.download_open_btn ?? true) && (
                      <button
                        onClick={() => handleOpenClick(item)}
                        disabled={true}
                        className="p-2.5 rounded-lg bg-zinc-800 hover:bg-emerald-600 text-zinc-300 hover:text-white transition-all cursor-pointer disabled:opacity-30 border border-zinc-700/60"
                        title="Open file / Play"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                    )}

                    {/* Locate Button */}
                    {(config?.download_locate_btn ?? true) && (
                      <button
                        onClick={() => handleLocateClick(item)}
                        className="p-2.5 rounded-lg bg-zinc-800 hover:bg-cyan-600 text-zinc-300 hover:text-white transition-all cursor-pointer border border-zinc-700/60"
                        title="Locate folder"
                      >
                        <FolderOpen className="w-4 h-4" />
                      </button>
                    )}

                    {/* Copy Link Button */}
                    {(config?.download_copy_btn ?? true) && (
                      <button
                        onClick={() => handleCopyLink(item)}
                        className="p-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-all cursor-pointer border border-zinc-700/60"
                        title="Copy file path / stream ID"
                      >
                        {copiedId === item.local_id ? (
                          <Check className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <Copy className="w-4 h-4" />
                        )}
                      </button>
                    )}

                    {/* Delete / Cancel Button */}
                    {config?.download_delete_btn && (item.item_status == "Downloaded" || item.item_status == "Already Exists") && (
                      <button
                        onClick={() => onAction(item.local_id, 'delete')}
                        className="p-2.5 rounded-lg bg-zinc-800 hover:bg-rose-600 text-zinc-400 hover:text-white transition-all cursor-pointer border border-zinc-700/60 ml-1"
                        title="Remove from Queue - Does NOT remove the file"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    {config?.download_delete_btn && (item.item_status == "Downloading") && (
                      <button
                        onClick={() => onAction(item.local_id, 'cancel')}
                        className="p-2.5 rounded-lg bg-zinc-800 hover:bg-rose-600 text-zinc-400 hover:text-white transition-all cursor-pointer border border-zinc-700/60 ml-1"
                        title="Cancel"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                    {(item.item_status == "Failed" || item.item_status == "Cancelled" || item.item_status == "Waiting") && (
                      <button
                        onClick={() => onAction(item.local_id, 'retry')}
                        className="p-2.5 rounded-lg bg-zinc-800 hover:bg-rose-600 text-zinc-400 hover:text-white transition-all cursor-pointer border border-zinc-700/60 ml-1"
                        title="Retry"
                      >
                        <RefreshCw className="w-4 h-4" />
                      </button>
                    )}
                    <button
                      onClick={() => handleDownloadFile(item)}
                      disabled={!isCompleted}
                      className="p-2.5 rounded-lg bg-zinc-800 hover:bg-emerald-600 text-zinc-300 hover:text-white transition-all cursor-pointer disabled:opacity-30 border border-zinc-700/60"
                      title="Download File"
                    >
                      <Download className="w-4 h-4" />
                    </button>
                  </div>

                </div>
              );
            })}
          </div>
        )}
      </div>

    </div>
  );
};
