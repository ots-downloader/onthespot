import React, { useEffect, useState } from 'react';
import { Download, FolderOpen, Trash2, RefreshCw, CheckCircle2, AlertCircle, Clock, Zap, Copy, Check, Play, Pause, XCircle, ListMusic, ChevronDown, ChevronUp, GripVertical, ArrowDown, ArrowUp, Square, CheckSquare, Music2, Waves, Cloud, Disc3, CirclePlay, Heart, Headphones, Film } from 'lucide-react';
import { DownloadQueueItem, OTSConfig } from '../types';
import { DownloadProfile, getTargetBackendUrl, QueueBatchAction } from '../lib/api';
import { OtsSelect } from './OtsSelect';

interface DownloadQueueProps {
  queue: DownloadQueueItem[];
  onClearCompleted: () => Promise<void>;
  onClearFailed: () => Promise<void>;
  onRetryFailed: () => Promise<void>;
  onAction: (local_id: string, action: 'cancel' | 'delete' | 'retry') => Promise<void>;
  onPauseToggle: () => Promise<void>;
  downloadsPaused: boolean;
  downloadSpeed: number;
  downloadEta: number;
  onReorder: (local_ids: string[]) => Promise<void>;
  profiles: DownloadProfile[];
  activeProfile: string;
  onProfileChange: (profile_id: string) => Promise<void>;
  onBatchAction: (local_ids: string[], action: QueueBatchAction, options?: { priority?: number; profile_id?: string }) => Promise<void>;
  onVerify: () => Promise<void>;
  config: OTSConfig | null;
}

type StatusFilter = 'All' | 'Downloading' | 'Paused' | 'Waiting' | 'Downloaded' | 'Failed' | 'Cancelled' | 'Unavailable' | 'Already Exists';

type PlaylistGroup = {
  key: string;
  name: string;
  owner: string;
  items: DownloadQueueItem[];
};

export const DownloadQueue: React.FC<DownloadQueueProps> = ({
  queue,
  onClearCompleted,
  onClearFailed,
  onRetryFailed,
  onAction,
  onPauseToggle,
  downloadsPaused,
  downloadSpeed,
  downloadEta,
  onReorder,
  profiles,
  activeProfile,
  onProfileChange,
  onBatchAction,
  onVerify,
  config
}) => {
  const [filter, setFilter] = useState<StatusFilter>('All');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [loadingAction, setLoadingAction] = useState(false);
  const [showPlaylistTracks, setShowPlaylistTracks] = useState(false);
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [batchPriority, setBatchPriority] = useState(0);
  const [batchProfile, setBatchProfile] = useState("");

  // Filter items based on selected pill AND config display flags
  const filteredQueue = queue.filter(item => {
    if (filter === 'Downloaded' && (item.item_status === 'Already Exists' || item.item_status === filter)) return true;

    if (filter !== 'All' && item.item_status !== filter) return false;

    // Check config filter flags
    if (item.item_status === 'Waiting' && config?.download_queue_show_waiting === false) return false;
    if (item.item_status === 'Failed' && config?.download_queue_show_failed === false) return false;
    if (item.item_status === 'Cancelled' && config?.download_queue_show_cancelled === false) return false;
    if (item.item_status === 'Unavailable' && config?.download_queue_show_unavailable === false) return false;
    if (item.item_status === 'Downloaded' && config?.download_queue_show_completed === false) return false;

    return true;
  });

  const counts = {
    All: queue.length,
    Downloading: queue.filter(i => i.item_status === 'Downloading').length,
    Paused: queue.filter(i => i.item_status === 'Paused').length,
    Waiting: queue.filter(i => i.item_status === 'Waiting').length,
    Downloaded: queue.filter(i => i.item_status === 'Downloaded' || i.item_status === 'Already Exists').length,
    Failed: queue.filter(i => i.item_status === 'Failed').length,
    Cancelled: queue.filter(i => i.item_status === 'Cancelled').length,
    Unavailable: queue.filter(i => i.item_status === 'Unavailable').length,
  };

  const playlistGroupMap = new Map<string, PlaylistGroup>();
  queue.forEach((item) => {
    if (item.parent_category !== 'playlist' || !item.playlist_name) return;
    const key = `${item.playlist_name}\u0000${item.playlist_by || ''}`;
    const existing = playlistGroupMap.get(key);
    if (existing) {
      existing.items.push(item);
    } else {
      playlistGroupMap.set(key, {
        key,
        name: item.playlist_name,
        owner: item.playlist_by || '',
        items: [item],
      });
    }
  });
  const playlistGroups = Array.from(playlistGroupMap.values());
  const visibleQueueItems = showPlaylistTracks
    ? filteredQueue
    : filteredQueue.filter((item) => item.parent_category !== 'playlist');

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => queue.some((item) => item.local_id === id)));
  }, [queue]);

  const toggleSelected = (localId: string) => {
    setSelectedIds((current) => current.includes(localId) ? current.filter((id) => id !== localId) : [...current, localId]);
  };

  const toggleAllVisible = () => {
    const visibleIds = visibleQueueItems.map((item) => item.local_id);
    setSelectedIds((current) => visibleIds.every((id) => current.includes(id)) ? current.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...current, ...visibleIds])));
  };

  const runBatch = async (action: QueueBatchAction, options: { priority?: number; profile_id?: string } = {}) => {
    if (!selectedIds.length) return;
    setLoadingAction(true);
    await onBatchAction(selectedIds, action, options);
    if (action === "delete" || action === "cancel" || action === "retry") setSelectedIds([]);
    setLoadingAction(false);
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
      const url = `${getTargetBackendUrl()}/queue/downloads/download?lid=${encodeURIComponent(item.local_id)}`;
      window.open(url, '_blank');
    } else {
      alert("⚠️ File is still queued or downloading.");
    }
  };
  
  // Clean Material tonal badges for status
  const getStatusBadge = (status: string) => {
    const baseClasses = "inline-flex items-center gap-1.5 px-2 py-0.5 text-[11px] font-medium rounded-md transition-colors duration-200";

    switch (status) {
      case 'Downloading':
        return <span className={`${baseClasses} bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300`}><Zap className="w-3 h-3" /> Downloading</span>;
      case 'Paused':
        return <span className={`${baseClasses} bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300`}><Pause className="w-3 h-3" /> Paused</span>;
      case 'Downloaded':
      case 'Already Exists':
        return <span className={`${baseClasses} bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300`}><CheckCircle2 className="w-3 h-3" /> Completed</span>;
      case 'Waiting':
        return <span className={`${baseClasses} bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-300`}><Clock className="w-3 h-3" /> Waiting</span>;
      case 'Failed':
        return <span className={`${baseClasses} bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300`}><AlertCircle className="w-3 h-3" /> Failed</span>;
      default:
        const isCancelled = status === 'Cancelled';
        return (
          <span className={`${baseClasses} ${isCancelled ? 'bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400' : 'bg-gray-100 text-gray-700 dark:bg-neutral-800 dark:text-neutral-300'}`}>
            {status}
          </span>
        );
    }
  };

  // Standardized service badges
  const getServiceBadge = (service: string) => {
    const base = "inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] font-semibold tracking-wide transition-colors";
    switch (service.toLowerCase()) {
      case 'spotify': return <span title="Source service: Spotify" className={`${base} border-green-500/30 bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300`}><Music2 className="h-3 w-3" />Spotify</span>;
      case 'tidal': return <span title="Source service: Tidal" className={`${base} border-cyan-500/30 bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300`}><Waves className="h-3 w-3" />Tidal</span>;
      case 'apple_music':
      case 'applemusic': return <span title="Source service: Apple Music" className={`${base} border-rose-500/30 bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300`}><Music2 className="h-3 w-3" />Apple Music</span>;
      case 'soundcloud': return <span title="Source service: SoundCloud" className={`${base} border-orange-500/30 bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300`}><Cloud className="h-3 w-3" />SoundCloud</span>;
      case 'bandcamp': return <span title="Source service: Bandcamp" className={`${base} border-blue-500/30 bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300`}><Disc3 className="h-3 w-3" />Bandcamp</span>;
      case 'youtube_music':
      case 'youtube': return <span title="Source service: YouTube Music" className={`${base} border-red-500/30 bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300`}><CirclePlay className="h-3 w-3" />YouTube Music</span>;
      case 'deezer': return <span title="Source service: Deezer" className={`${base} border-violet-500/30 bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-300`}><Heart className="h-3 w-3" />Deezer</span>;
      case 'qobuz': return <span title="Source service: Qobuz" className={`${base} border-sky-500/30 bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-300`}><Headphones className="h-3 w-3" />Qobuz</span>;
      case 'crunchyroll': return <span title="Source service: Crunchyroll" className={`${base} border-amber-500/30 bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300`}><Film className="h-3 w-3" />Crunchyroll</span>;
      default: return <span title="Source service: Generic" className={`${base} border-gray-300 bg-gray-100 text-gray-800 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300`}><Download className="h-3 w-3" />Generic</span>;
    }
  };

  const showThumbnails = config?.show_download_thumbnails ?? true;

  const iconBtnClass = "p-2 rounded-full transition-colors focus:outline-none focus:ring-2 disabled:opacity-40 disabled:cursor-not-allowed";

  const moveQueueItem = (sourceId: string, targetId: string) => {
    if (sourceId === targetId) return;
    const ids = queue.filter((item) => item.item_status === 'Waiting').map((item) => item.local_id);
    const sourceIndex = ids.indexOf(sourceId);
    const targetIndex = ids.indexOf(targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    const [moved] = ids.splice(sourceIndex, 1);
    ids.splice(targetIndex, 0, moved);
    void onReorder(ids);
  };

  const formatEta = (seconds?: number | null) => {
    if (!seconds || seconds < 0) return "—";
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  };

  const formatSpeed = (bytesPerSecond: number) => {
    if (!bytesPerSecond) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let value = bytesPerSecond;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
    return `${value.toFixed(index ? 1 : 0)} ${units[index]}/s`;
  };

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">

      {/* Top Bar: Status & Queue Controls */}
      <div className="ots-queue-header p-5 md:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-bold tracking-tight text-white">Download Queue</h2>
              <div className="flex items-center gap-1.5 border border-[#3a3a3a] bg-[#181818] px-3 py-1.5 text-xs font-bold">
                <span className="text-[#1ed760]">{counts.Downloading} Active</span>
                <span className="text-[#555]">•</span>
                <span className="text-[#f6b94a]">{counts.Waiting} Waiting</span>
              </div>
            </div>
            <p className="mt-2 text-sm text-[#a7a7a7]">
              {queue.length === 0 ? "Your queue is empty" : `${queue.length} item${queue.length === 1 ? "" : "s"} in the queue`}
              <span className="mx-2 text-[#555]">•</span>
              Workers: {config?.maximum_download_workers || 2} DL / {config?.maximum_queue_workers || 3} Queue
              <span className="mx-2 text-[#555]">•</span>
              Delay: {config?.download_delay || 3}s
            </p>
            {(downloadSpeed > 0 || downloadsPaused) && (
              <p className={`mt-3 inline-flex items-center gap-2 border px-3 py-1.5 text-xs font-bold ${downloadsPaused ? "border-[#6a4920] bg-[#2c2417] text-[#f6b94a]" : "border-[#275c37] bg-[#173b25] text-[#b8f5c9]"}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${downloadsPaused ? "bg-[#f6b94a]" : "animate-pulse bg-[#1ed760]"}`} />
                {downloadsPaused ? "Downloads paused" : `${formatSpeed(downloadSpeed)} · ETA ${formatEta(downloadEta)}`}
              </p>
            )}
          </div>

          <div className="flex shrink-0 flex-col gap-2.5 lg:min-w-[590px] lg:items-end">
            <div className="flex flex-wrap items-center gap-2">
              {profiles.length > 0 && (
                <OtsSelect
                  value={activeProfile}
                  onChange={(event) => void onProfileChange(event.target.value)}
                  className="h-11 max-w-[190px] text-xs font-bold"
                  title="Download profile"
                >
                  {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
                </OtsSelect>
              )}
              <button
                onClick={async () => { setLoadingAction(true); await onPauseToggle(); setLoadingAction(false); }}
                disabled={queue.length === 0 || loadingAction}
                className="ots-button ots-button-primary ots-button-md disabled:cursor-not-allowed"
              >
                {downloadsPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                {downloadsPaused ? "Resume" : "Pause"}
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
              <button
                onClick={async () => {
                  setLoadingAction(true);
                  await onRetryFailed();
                  setLoadingAction(false);
                }}
                disabled={(counts.Failed === 0 && counts.Cancelled === 0 && counts.Unavailable === 0) || loadingAction}
                className="ots-button ots-button-warning ots-button-sm disabled:cursor-not-allowed"
              >
                <RefreshCw className={`h-4 w-4 ${loadingAction ? "animate-spin" : ""}`} />
                Retry Failed ({counts.Failed + counts.Cancelled + counts.Unavailable})
              </button>

              <button
                onClick={async () => {
                  setLoadingAction(true);
                  if (window.confirm(`Remove all ${counts.Downloaded} completed items from the queue?`)) await onClearCompleted();
                  setLoadingAction(false);
                }}
                disabled={counts.Downloaded === 0 || loadingAction}
                className="ots-button ots-button-danger ots-button-sm disabled:cursor-not-allowed"
              >
                <Trash2 className="h-4 w-4" />
                Clear Completed ({counts.Downloaded})
              </button>

              <button
                onClick={async () => {
                  setLoadingAction(true);
                  if (window.confirm(`Remove all ${counts.Failed} failed items from the queue?`)) await onClearFailed();
                  setLoadingAction(false);
                }}
                disabled={counts.Failed + counts.Cancelled + counts.Unavailable === 0 || loadingAction}
                className="ots-button ots-button-danger ots-button-sm disabled:cursor-not-allowed"
              >
                <Trash2 className="h-4 w-4" />
                Clear Failed ({counts.Failed + counts.Cancelled + counts.Unavailable})
              </button>
              <button type="button" onClick={() => void onVerify()} disabled={counts.Downloaded === 0 || loadingAction} className="ots-button ots-button-secondary ots-button-sm disabled:cursor-not-allowed"><CheckCircle2 className="h-4 w-4" /> Verify files</button>
            </div>
          </div>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="ots-browse-tabs ots-queue-filters spotify-scrollbar flex items-center gap-2">
        {(['All', 'Downloading', 'Paused', 'Waiting', 'Downloaded', 'Failed', 'Cancelled', 'Unavailable'] as StatusFilter[]).map((pill) => (
          <button
            key={pill}
            onClick={() => setFilter(pill)}
            className={`ots-filter-chip ${filter === pill ? 'ots-filter-chip-active' : ''}`}
          >
            <span>{pill}</span>
            <span className="ots-filter-count">
              {counts[pill]}
            </span>
          </button>
        ))}
      </div>

      <div className="ots-panel flex flex-col gap-3 p-4 md:flex-row md:items-center">
        <button type="button" onClick={toggleAllVisible} className="ots-button ots-button-secondary ots-button-sm"><CheckSquare className="h-4 w-4" /> {visibleQueueItems.length > 0 && visibleQueueItems.every((item) => selectedIds.includes(item.local_id)) ? "Clear selection" : "Select visible"}</button>
        {selectedIds.length > 0 && <>
          <span className="text-xs font-bold text-[#b3b3b3]">{selectedIds.length} selected</span>
          <button type="button" onClick={() => void runBatch("pause")} disabled={loadingAction} className="ots-button ots-button-secondary ots-button-sm"><Pause className="h-4 w-4" /> Pause</button>
          <button type="button" onClick={() => void runBatch("resume")} disabled={loadingAction} className="ots-button ots-button-secondary ots-button-sm"><Play className="h-4 w-4" /> Resume</button>
          <button type="button" onClick={() => void runBatch("retry")} disabled={loadingAction} className="ots-button ots-button-warning ots-button-sm"><RefreshCw className="h-4 w-4" /> Retry</button>
          <button type="button" onClick={() => void runBatch("cancel")} disabled={loadingAction} className="ots-button ots-button-danger ots-button-sm"><XCircle className="h-4 w-4" /> Cancel</button>
          <button type="button" onClick={() => { if (window.confirm(`Delete ${selectedIds.length} selected queue item(s)?`)) void runBatch("delete"); }} disabled={loadingAction} className="ots-button ots-button-danger ots-button-sm"><Trash2 className="h-4 w-4" /> Delete</button>
          <OtsSelect value={batchPriority} onChange={(event) => setBatchPriority(Number(event.target.value))} className="h-9 text-xs"><option value={0}>Normal priority</option><option value={1}>High priority</option><option value={2}>Urgent priority</option></OtsSelect>
          <button type="button" onClick={() => void runBatch("priority", { priority: batchPriority })} disabled={loadingAction} className="ots-button ots-button-secondary ots-button-sm">Apply priority</button>
          <OtsSelect value={batchProfile} onChange={(event) => setBatchProfile(event.target.value)} className="h-9 max-w-44 text-xs"><option value="">Change profile…</option>{profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</OtsSelect>
          <button type="button" onClick={() => void runBatch("profile", { profile_id: batchProfile })} disabled={!batchProfile || loadingAction} className="ots-button ots-button-secondary ots-button-sm">Apply profile</button>
        </>}
      </div>

      {playlistGroups.length > 0 && (
        <div className="ots-panel p-5">
          <div className="flex items-center justify-between gap-4 mb-4">
            <div>
              <h3 className="flex items-center gap-2 text-base font-medium text-gray-900 dark:text-neutral-100">
                <ListMusic className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                Playlist progress
              </h3>
              <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1">
                Tracks download individually, with one overall progress view.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowPlaylistTracks((value) => !value)}
              className="flex items-center gap-1.5 rounded-full bg-[#282828] px-3 py-2 text-xs font-bold text-[#1ed760] transition-colors hover:bg-[#333]"
            >
              {showPlaylistTracks ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
              {showPlaylistTracks ? 'Hide tracks' : 'Show tracks'}
            </button>
          </div>

          <div className="flex flex-col gap-4">
            {playlistGroups.map((group) => {
              const completed = group.items.filter((item) => item.item_status === 'Downloaded' || (item.item_status as string) === 'Already Exists').length;
              const activeItem = group.items.find((item) => item.item_status === 'Downloading' || item.item_status === 'Paused');
              const nextItem = group.items.find((item) => item.item_status === 'Waiting');
              const progress = group.items.length
                ? Math.round(group.items.reduce((sum, item) => sum + Math.min(100, Math.max(0, Number(item.progress) || 0)), 0) / group.items.length)
                : 0;
              const currentItem = activeItem || nextItem;

              return (
                <div key={group.key} className="rounded-xl border border-[#303030] bg-[#202020] p-4">
                  <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-gray-900 dark:text-neutral-100 truncate">
                        {group.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5">
                        {group.owner ? `${group.owner} • ` : ''}{completed}/{group.items.length} tracks completed
                      </p>
                    </div>
                    <div className="flex items-center gap-3 min-w-0">
                      <p className="text-xs text-gray-600 dark:text-neutral-300 truncate">
                        {activeItem
                          ? activeItem.item_status === 'Paused'
                            ? `Paused: ${activeItem.name || 'current track'}`
                            : `Downloading: ${activeItem.name || 'current track'}`
                          : nextItem
                            ? `Next: ${nextItem.name || 'queued track'}`
                            : 'Playlist complete'}
                      </p>
                      {activeItem && (
                        <button
                          type="button"
                          onClick={() => onAction(activeItem.local_id, 'cancel')}
                          className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-medium text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20"
                        >
                          <XCircle className="w-3.5 h-3.5" />
                          Cancel track
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="w-full h-2 rounded-full bg-gray-100 dark:bg-neutral-800 overflow-hidden mt-4">
                    <div
                      className="h-full rounded-full bg-blue-500 transition-all duration-500"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                  <div className="flex items-center justify-between text-xs text-gray-500 dark:text-neutral-400 mt-2">
                    <span>{progress}% overall</span>
                    <span>{group.items.length - completed} remaining</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Queue Items Table / List */}
      {(visibleQueueItems.length > 0 || playlistGroups.length === 0) && (
        <div className="ots-panel overflow-hidden">
          {visibleQueueItems.length === 0 ? (
              <div className="p-16 flex flex-col items-center justify-center text-gray-500 dark:text-neutral-500 gap-3">
                <Download className="w-8 h-8 text-gray-400 dark:text-neutral-600" />
                <p className="text-sm font-medium">No items match filter "{filter}"</p>
              </div>
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-neutral-800/60">
            {visibleQueueItems.map((item) => {
              const isDownloading = item.item_status === 'Downloading' || item.item_status === 'Paused';
              const isCompleted = item.item_status === 'Downloaded' || item.item_status === 'Already Exists';

              return (
                <div
                  key={item.local_id}
                  className="group p-4 md:p-5 flex flex-col gap-4 transition-colors hover:bg-gray-50/50 dark:hover:bg-white/[0.02]"
                >
                  
                  {/* Top Row: Info & Actions */}
                  <div
                    className="flex w-full items-start justify-between gap-4"
                    draggable={item.item_status === 'Waiting'}
                    onDragStart={() => setDraggedId(item.local_id)}
                    onDragEnd={() => setDraggedId(null)}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={() => { if (draggedId) moveQueueItem(draggedId, item.local_id); setDraggedId(null); }}
                  >
                    
                    {/* Left: Thumbnail & Text Info */}
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <button type="button" onClick={() => toggleSelected(item.local_id)} className="shrink-0 text-[#777] hover:text-[#1ed760]" aria-label={`${selectedIds.includes(item.local_id) ? "Deselect" : "Select"} ${item.name}`}>
                        {selectedIds.includes(item.local_id) ? <CheckSquare className="h-5 w-5 text-[#1ed760]" /> : <Square className="h-5 w-5" />}
                      </button>
                      {showThumbnails && (
                        <div className="relative w-14 h-14 rounded-xl overflow-hidden bg-gray-100 dark:bg-neutral-800 shrink-0 border border-gray-200 dark:border-neutral-700/50">
                          <img
                            src={item.thumbnail || "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?w=150&auto=format&fit=crop&q=80"}
                            alt={item.name}
                            className="w-full h-full object-cover"
                            referrerPolicy="no-referrer"
                          />
                        </div>
                      )}

                      <div className="relative min-w-0 flex-1 flex flex-col justify-center">
                        {item.item_status === 'Waiting' && <span title="Drag to reorder"><GripVertical className="absolute -left-7 top-1 hidden h-4 w-4 cursor-grab text-gray-400 sm:block" /></span>}
                        {/* Title */}
                        <h4 className="font-medium text-gray-900 dark:text-neutral-100 text-sm md:text-base truncate leading-snug">
                          {item.name}
                        </h4>
                        {/* Artist & Album */}
                        <p className="text-xs md:text-sm text-gray-500 dark:text-neutral-400 truncate mt-0.5">
                          {item.artist}
                          {item.album && (
                            <span className="text-gray-400 dark:text-neutral-500"> • {item.album} </span>
                          )}
                          {isCompleted && item.file_path && (
                          <span className="text-sm md:text-xs text-gray-600 dark:text-neutral-600 truncate mt-0.5">
                            • {item.file_path}
                          </span>
                          )}
                        </p>
                        {/* Path if completed */}
                        
                        {/* Badges */}
                        <div className="flex flex-wrap items-center gap-2 mt-2">
                          {getStatusBadge(item.item_status)}
                          {getServiceBadge(item.item_service)}
                          <span className="text-[10px] font-medium text-gray-600 bg-gray-100 px-2 py-0.5 rounded-md dark:text-neutral-400 dark:bg-neutral-800">
                            {item.parent_category || 'Track'}
                          </span>
                        </div>
                        {item.item_status === 'Failed' && item.error && (
                          <p className="mt-2 line-clamp-2 text-xs text-red-600 dark:text-red-400" title={item.error}>
                            {item.error}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Right: Action Buttons (Top Right) */}
                    <div className="flex items-center justify-end gap-1 shrink-0 -mt-1 -mr-2">
                      {/* Open Button */}
                      {(config?.download_open_btn ?? true) && (
                        <button
                          onClick={() => handleOpenClick(item)}
                          disabled={!isCompleted}
                          className={`${iconBtnClass} text-green-600 hover:bg-green-50 dark:text-green-400 dark:hover:bg-green-900/20 focus:ring-green-500/20`}
                          title="Open file / Play"
                        >
                          <Play className="w-5 h-5 fill-current" />
                        </button>
                      )}

                      {/* Locate Button */}
                      {(config?.download_locate_btn ?? true) && (
                        <button
                          onClick={() => handleLocateClick(item)}
                          className={`${iconBtnClass} text-gray-500 hover:bg-gray-100 dark:text-neutral-400 dark:hover:bg-neutral-800 focus:ring-gray-500/20`}
                          title="Locate folder"
                        >
                          <FolderOpen className="w-5 h-5" />
                        </button>
                      )}

                      {/* Copy Link Button */}
                      {(config?.download_copy_btn ?? true) && (
                        <button
                          onClick={() => handleCopyLink(item)}
                          className={`${iconBtnClass} ${
                            copiedId === item.local_id 
                              ? 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20' 
                              : 'text-gray-500 hover:bg-gray-100 dark:text-neutral-400 dark:hover:bg-neutral-800'
                          } focus:ring-gray-500/20`}
                          title="Copy file path"
                        >
                          {copiedId === item.local_id ? <Check className="w-5 h-5" /> : <Copy className="w-5 h-5" />}
                        </button>
                      )}

                      {/* Delete / Cancel Button */}
  {(config?.download_delete_btn && (item.item_status === "Downloaded" || item.item_status === "Already Exists" || item.item_status === "Cancelled")) && (
                        <button
                          onClick={() => onAction(item.local_id, 'delete')}
                          className={`${iconBtnClass} text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 focus:ring-red-500/20`}
                          title="Remove from queue"
                        >
                          <Trash2 className="w-5 h-5" />
                        </button>
                      )}
                      {(item.item_status === "Downloading" || item.item_status === "Paused") && (
                        <button
                          onClick={() => onAction(item.local_id, 'cancel')}
                          className={`${iconBtnClass} flex items-center gap-1.5 px-3 text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 focus:ring-red-500/20`}
                          title="Cancel download"
                          aria-label={`Cancel download for ${item.name || 'current track'}`}
                        >
                          <XCircle className="w-5 h-5" />
                          <span className="hidden sm:inline text-xs font-medium">Cancel</span>
                        </button>
                      )}

                      {item.item_status === "Waiting" && (
                        <>
                          <button
                            onClick={() => {
                              const waiting = queue.filter((entry) => entry.item_status === "Waiting").map((entry) => entry.local_id);
                              const index = waiting.indexOf(item.local_id);
                              if (index > 0) moveQueueItem(item.local_id, waiting[index - 1]);
                            }}
                            disabled={queue.filter((entry) => entry.item_status === "Waiting").findIndex((entry) => entry.local_id === item.local_id) <= 0}
                            className={`${iconBtnClass} text-gray-500 hover:bg-gray-100 dark:text-neutral-400 dark:hover:bg-neutral-800`}
                            title="Move priority up"
                          ><ArrowUp className="h-4 w-4" /></button>
                          <button
                            onClick={() => {
                              const waiting = queue.filter((entry) => entry.item_status === "Waiting").map((entry) => entry.local_id);
                              const index = waiting.indexOf(item.local_id);
                              if (index >= 0 && index < waiting.length - 1) moveQueueItem(item.local_id, waiting[index + 1]);
                            }}
                            disabled={queue.filter((entry) => entry.item_status === "Waiting").findIndex((entry) => entry.local_id === item.local_id) === queue.filter((entry) => entry.item_status === "Waiting").length - 1}
                            className={`${iconBtnClass} text-gray-500 hover:bg-gray-100 dark:text-neutral-400 dark:hover:bg-neutral-800`}
                            title="Move priority down"
                          ><ArrowDown className="h-4 w-4" /></button>
                        </>
                      )}
                      
                      {/* Retry Button */}
                      {(item.item_status === "Failed" || item.item_status === "Cancelled" || item.item_status === "Unavailable" || item.item_status === "Waiting") && (
                        <button
                          onClick={() => onAction(item.local_id, 'retry')}
                          className={`${iconBtnClass} text-orange-600 hover:bg-orange-50 dark:text-orange-400 dark:hover:bg-orange-900/20 focus:ring-orange-500/20`}
                          title="Retry"
                        >
                          <RefreshCw className="w-5 h-5" />
                        </button>
                      )}

                      {/* Download Button */}
                      <button
                        onClick={() => handleDownloadFile(item)}
                        disabled={!isCompleted}
                        className={`${iconBtnClass} ${
                          isCompleted 
                            ? 'text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-900/20 focus:ring-blue-500/20' 
                            : 'text-gray-400 dark:text-neutral-600'
                        }`}
                        title="Download File"
                      >
                        <Download className="w-5 h-5" />
                      </button>
                    </div>

                  </div>

                  {/* Bottom Row: Path, Metrics & Expanded Progress Bar */}
                  <div className="flex flex-col gap-2.5 w-full mt-1">
                    
                    

                    {/* Detailed Metrics Layout */}
                    <div className="flex items-center justify-between text-xs text-gray-500 dark:text-neutral-400 font-medium px-0.5">
                      <div className="flex items-center gap-2 md:gap-3">
                        <span className="uppercase tracking-wider">{item.format}</span>
                        <span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-neutral-700"></span>
                        <span className="bg-gray-100 dark:bg-neutral-800 px-1.5 py-0.5 rounded text-gray-700 dark:text-neutral-300 font-mono text-[10px] tracking-wide">
                          {item.bitrate}
                        </span>
                        <span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-neutral-700"></span>
                        <span>{Number.isFinite(Number(item.file_size)) ? `${(Number(item.file_size) / (1024 * 1024)).toFixed(1)} MB` : '— MB'}</span>
                        {item.download_speed && <><span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-neutral-700"></span><span>{item.download_speed}</span></>}
                        {isDownloading && <><span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-neutral-700"></span><span>ETA {formatEta(item.eta_seconds)}</span></>}
                      </div>
                      <span className="text-xs font-mono tabular-nums text-gray-600 dark:text-neutral-300">
                        {Math.round(item.progress)}%
                      </span>
                    </div>

                    {/* Full Width Progress Bar */}
                    <div className="w-full h-1.5 rounded-full bg-gray-100 dark:bg-neutral-800 overflow-hidden relative">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ease-out ${
                          isCompleted
                            ? 'bg-green-500'
                            : isDownloading
                              ? 'bg-blue-500'
                              : item.item_status === 'Failed'
                                ? 'bg-red-500'
                                : 'bg-orange-500'
                        }`}
                        style={{ width: `${item.progress}%` }}
                      />
                    </div>
                  </div>

                </div>
              );
            })}
            </div>
          )}
        </div>
      )}

    </div>
  );
};
