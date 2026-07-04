import React, { useState } from 'react';
import { Download, FolderOpen, Trash2, RefreshCw, CheckCircle2, AlertCircle, Clock, Zap, Copy, Check, Play } from 'lucide-react';
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
    if (filter === 'Downloaded' && (item.item_status === 'Already Exists' || item.item_status === filter)) return true;

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
    const base = "px-2 py-0.5 rounded-md text-[10px] font-medium tracking-wide transition-colors";
    switch (service.toLowerCase()) {
      case 'spotify': return <span className={`${base} bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300`}>Spotify</span>;
      case 'tidal': return <span className={`${base} bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300`}>Tidal</span>;
      case 'apple_music':
      case 'applemusic': return <span className={`${base} bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300`}>Apple Music</span>;
      case 'soundcloud': return <span className={`${base} bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300`}>SoundCloud</span>;
      case 'bandcamp': return <span className={`${base} bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300`}>Bandcamp</span>;
      case 'youtube_music':
      case 'youtube': return <span className={`${base} bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300`}>YT Music</span>;
      default: return <span className={`${base} bg-gray-100 text-gray-800 dark:bg-neutral-800 dark:text-neutral-300`}>Generic DL</span>;
    }
  };

  const showThumbnails = config?.show_download_thumbnails ?? true;

  const iconBtnClass = "p-2 rounded-full transition-colors focus:outline-none focus:ring-2 disabled:opacity-40 disabled:cursor-not-allowed";

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8 flex flex-col gap-6 font-sans">

      {/* Top Bar: Title & Bulk Actions */}
      <div className="bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-6 shadow-sm">
        <div className="flex flex-col">
          <h2 className="text-xl font-medium text-gray-900 dark:text-neutral-100 flex items-center flex-wrap gap-3">
            <span>Download Queue</span>
            <div className="flex items-center gap-2 text-xs font-medium px-3 py-1 rounded-full bg-gray-100 dark:bg-neutral-800/50">
              <span className='text-blue-600 dark:text-blue-400'>{counts.Downloading} Active</span>
              <span className='text-gray-400 dark:text-neutral-500'>•</span>
              <span className='text-orange-600 dark:text-orange-400'>{counts.Waiting} Waiting</span>
            </div>
          </h2>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            Workers: {config?.maximum_download_workers || 2} DL / {config?.maximum_queue_workers || 3} Queue • Delay: {config?.download_delay || 3}s
          </p>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center flex-wrap gap-3">
          <button
            onClick={async () => {
              setLoadingAction(true);
              await onRetryFailed();
              setLoadingAction(false);
            }}
            disabled={counts.Failed === 0 && counts.Cancelled === 0 || loadingAction}
            className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-orange-50 text-orange-700 hover:bg-orange-100 dark:bg-orange-900/20 dark:text-orange-400 dark:hover:bg-orange-900/40 transition-colors font-medium text-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loadingAction ? 'animate-spin' : ''}`} />
            Retry Failed ({counts.Failed + counts.Cancelled})
          </button>

          <button
            onClick={async () => {
              setLoadingAction(true);
              await onClearCompleted();
              setLoadingAction(false);
            }}
            disabled={counts.Downloaded === 0 || loadingAction}
            className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-red-50 text-red-700 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/40 transition-colors font-medium text-sm disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" />
            Clear Completed ({counts.Downloaded})
          </button>
        </div>
      </div>

      {/* Filter Chips */}
      <div className="flex items-center overflow-x-auto no-scrollbar gap-2 p-1">
        {(['All', 'Downloading', 'Waiting', 'Downloaded', 'Failed', 'Cancelled'] as StatusFilter[]).map((pill) => (
          <button
            key={pill}
            onClick={() => setFilter(pill)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors cursor-pointer shrink-0 flex items-center gap-2 whitespace-nowrap border ${
              filter === pill
                ? 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50 dark:bg-[#1a1a1a] dark:text-neutral-400 dark:border-neutral-800/60 dark:hover:bg-neutral-800'
            }`}
          >
            <span>{pill}</span>
            <span className={`px-1.5 py-0.5 rounded-full text-xs ${
              filter === pill 
                ? 'bg-blue-200 text-blue-800 dark:bg-blue-800 dark:text-blue-100' 
                : 'bg-gray-100 text-gray-500 dark:bg-neutral-800 dark:text-neutral-400'
            }`}>
              {counts[pill]}
            </span>
          </button>
        ))}
      </div>

      {/* Queue Items Table / List */}
      <div className="bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 rounded-2xl overflow-hidden shadow-sm">
        {filteredQueue.length === 0 ? (
          <div className="p-16 flex flex-col items-center justify-center text-gray-500 dark:text-neutral-500 gap-3">
            <Download className="w-8 h-8 text-gray-400 dark:text-neutral-600" />
            <p className="text-sm font-medium">No items match filter "{filter}"</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-neutral-800/60">
            {filteredQueue.reverse().map((item) => {
              const isDownloading = item.item_status === 'Downloading';
              const isCompleted = item.item_status === 'Downloaded' || item.item_status === 'Already Exists';

              return (
                <div
                  key={item.local_id}
                  className="group p-4 md:p-5 flex flex-col gap-4 transition-colors hover:bg-gray-50/50 dark:hover:bg-white/[0.02]"
                >
                  
                  {/* Top Row: Info & Actions */}
                  <div className="flex items-start justify-between gap-4 w-full">
                    
                    {/* Left: Thumbnail & Text Info */}
                    <div className="flex items-center gap-4 min-w-0 flex-1">
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

                      <div className="min-w-0 flex-1 flex flex-col justify-center">
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
                      {(config?.download_delete_btn && (item.item_status === "Downloaded" || item.item_status === "Already Exists")) && (
                        <button
                          onClick={() => onAction(item.local_id, 'delete')}
                          className={`${iconBtnClass} text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 focus:ring-red-500/20`}
                          title="Remove from queue"
                        >
                          <Trash2 className="w-5 h-5" />
                        </button>
                      )}
                      {config?.download_delete_btn && (item.item_status === "Downloading") && (
                        <button
                          onClick={() => onAction(item.local_id, 'cancel')}
                          className={`${iconBtnClass} text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-900/20 focus:ring-red-500/20`}
                          title="Cancel"
                        >
                          <Trash2 className="w-5 h-5" />
                        </button>
                      )}
                      
                      {/* Retry Button */}
                      {(item.item_status === "Failed" || item.item_status === "Cancelled" || item.item_status === "Waiting") && (
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
                        <span>{(item.file_size / (1024 * 1024)).toFixed(1)} MB</span>
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

    </div>
  );
};