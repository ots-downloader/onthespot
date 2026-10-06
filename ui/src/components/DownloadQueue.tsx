import { Badge } from "@astryxdesign/core/Badge";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import {
  AlertCircle,
  Check,
  CheckSquare,
  ChevronRight,
  Clock,
  Copy,
  Disc,
  Download,
  ExternalLink,
  FileDown,
  Folder,
  Info,
  Layers,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
  Sliders,
  Square,
  Trash2,
  User,
  XCircle
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { getTargetBackendUrl } from "../lib/api";
import { getServiceInfo } from "../lib/catalogServices";
import { downloadQueueFailures } from "../lib/queueExport";
import { DownloadProfile, DownloadQueueItem, QueueBatchAction, QueueItemStatus } from "../types";
import { PageHeader } from "./PageHeader";


interface DownloadQueueProps {
  queue: DownloadQueueItem[];
  downloadsPaused: boolean;
  profiles: DownloadProfile[];
  activeProfile: string;
  onPauseToggle: () => Promise<boolean>;
  onClearCompleted: () => Promise<void>;
  onClearFailed: () => Promise<void>;
  onRetryFailed: () => Promise<void>;
  onAction: (local_id: number, action: "cancel" | "delete" | "retry") => Promise<void>;
  onBatchAction: (local_ids: number[], action: QueueBatchAction, options?: any) => Promise<void>;
  onReorder?: (local_ids: string[]) => Promise<void>;
}

export const DownloadQueue: React.FC<DownloadQueueProps> = ({
  queue,
  downloadsPaused,
  profiles: _profiles,
  activeProfile,
  onPauseToggle,
  onClearCompleted,
  onClearFailed,
  onRetryFailed,
  onAction,
  onBatchAction,
}) => {
  const [filter, setFilter] = useState<string>("All");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [showSidePanel, setShowSidePanel] = useState<boolean>(true);
  const [copiedId, setCopiedId] = useState<number | null>(null);

  // Filtered queue items
  const filteredItems = queue.filter((item) => {
    if (filter === "All") return true;
    if (filter === "Downloaded" && item.item_status === "Already Exists") return true;
    return item.item_status === filter;
  });

  // Ensure an item is selected by default if available
  useEffect(() => {
    if (filteredItems.length > 0) {
      const stillExists = filteredItems.some((i) => i.local_id === selectedItemId);
      if (!stillExists || !selectedItemId) {
        setSelectedItemId(filteredItems[0].local_id);
      }
    } else {
      setSelectedItemId(null);
    }
  }, [filteredItems, selectedItemId]);

  const selectedItem = queue.find((i) => i.local_id === selectedItemId) || null;

  // Aggregated status counts
  const counts = {
    All: queue.length,
    Downloading: queue.filter((i) => i.item_status === "Downloading").length,
    Waiting: queue.filter((i) => i.item_status === "Waiting").length,
    Paused: queue.filter((i) => i.item_status === "Paused").length,
    Downloaded: queue.filter((i) => i.item_status === "Downloaded" || i.item_status === "Already Exists").length,
    Failed: queue.filter((i) => i.item_status === "Failed").length,
    Unavailable: queue.filter((i) => i.item_status === "Unavailable").length,
    Cancelled: queue.filter((i) => i.item_status === "Cancelled").length,
  };

  const downloadingItems = queue.filter((i) => i.item_status === "Downloading");

  const downloadFile = (item: DownloadQueueItem) => {
    if (item.file_path) {
      const url = `${getTargetBackendUrl()}/queue/downloads/download?lid=${encodeURIComponent(item.local_id)}`;
      window.open(url, '_blank');
    } else {
      alert("⚠️ File is still queued or downloading.");
    }
  };

  const toggleSelectAll = () => {
    if (selectedIds.length === filteredItems.length && filteredItems.length > 0) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filteredItems.map((i) => i.local_id));
    }
  };

  const toggleSelectItem = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    if (selectedIds.includes(id)) {
      setSelectedIds(selectedIds.filter((item) => item !== id));
    } else {
      setSelectedIds([...selectedIds, id]);
    }
  };

  const handleItemClick = (id: number) => {
    setSelectedItemId(id);
  };

  const handleOpenDetails = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    setSelectedItemId(id);
    setShowSidePanel(true);
  };

  const copyUrl = (id: number, url?: string) => {
    if (!url) return;
    navigator.clipboard.writeText(url);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getStatusBadge = (status: QueueItemStatus, compact = false) => {
    switch (status) {
      case "Downloading":
        return <Badge variant="info" label="Downloading" />;
      case "Downloaded":
      case "Already Exists":
        return <Badge variant="success" label={compact ? "Ready" : status} />;
      case "Failed":
        return <Badge variant="error" label="Failed" />;
      case "Unavailable":
        return <Badge variant="warning" label="Unavailable" />;
      case "Paused":
        return <Badge variant="warning" label="Paused" />;
      case "Waiting":
        return <Badge variant="neutral" label="Waiting" />;
      case "Cancelled":
        return <Badge variant="neutral" label="Cancelled" />;
      default:
        return <Badge variant="info" label={status} />;
    }
  };

  const filterTabs: Array<{ id: string; label: string; count: number }> = [
    { id: "All", label: "All", count: counts.All },
    { id: "Downloading", label: "Downloading", count: counts.Downloading },
    { id: "Waiting", label: "Waiting", count: counts.Waiting },
    { id: "Paused", label: "Paused", count: counts.Paused },
    { id: "Downloaded", label: "Downloaded", count: counts.Downloaded },
    { id: "Failed", label: "Failed", count: counts.Failed },
    { id: "Unavailable", label: "Unavailable", count: counts.Unavailable },
    { id: "Cancelled", label: "Cancelled", count: counts.Cancelled },
  ];

  return (
    <div className="space-y-4" id="download-queue-view">
      {/* Reusable PageHeader for Queue */}
      <PageHeader
        id="queue-page-header"
        icon={<Download className="w-5 h-5" />}
        title="Download Queue"
        badge={
          downloadsPaused
            ? { label: "Worker Paused", variant: "warning" }
            : counts.Downloading > 0
            ? { label: `${counts.Downloading} Active`, variant: "info" }
            : undefined
        }
        description={`${counts.Downloading} active • ${counts.Waiting} waiting • ${counts.Downloaded} completed`}
        actions={
          <>
            {/* Toggle Collapsible Side Panel Button */}
            <Button
              variant={showSidePanel ? "secondary" : "primary"}
              size="sm"
              label={showSidePanel ? "Hide Details" : "Show Details"}
              icon={
                showSidePanel ? (
                  <PanelRightClose className="w-3.5 h-3.5" />
                ) : (
                  <PanelRightOpen className="w-3.5 h-3.5" />
                )
              }
              onClick={() => setShowSidePanel(!showSidePanel)}
              id="btn-toggle-side-view"
            />

            {counts.Failed > 0 && (
              <Button
                variant="secondary"
                size="sm"
                label={`Retry Failed (${counts.Failed})`}
                icon={<RotateCcw className="w-3.5 h-3.5" />}
                onClick={onRetryFailed}
                id="btn-retry-failed"
              />
            )}

            {counts.Downloaded > 0 && (
              <Button
                variant="ghost"
                size="sm"
                label="Clear Completed"
                onClick={onClearCompleted}
                id="btn-clear-completed"
              />
            )}

            {counts.Failed > 0 && (
              <Button
                variant="ghost"
                size="sm"
                label="Clear Failed"
                onClick={onClearFailed}
                id="btn-clear-failed"
              />
            )}
          </>
        }
        bottomContent={
          <>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              {/* Astryx TabList for filtering */}
              <div className="overflow-x-auto h-8">
                <TabList
                  value={filter}
                  onChange={(val) => setFilter(val)}
                  size="sm"
                >
                  {filterTabs.map((tab) => (
                    <Tab
                      key={tab.id}
                      value={tab.id}
                      label={tab.label}
                      endContent={
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-400 font-mono">
                          {tab.count}
                        </span>
                      }
                    />
                  ))}
                </TabList>
              </div>

              {/* Select All toggle button */}
              {filteredItems.length > 0 && (
                <button
                  type="button"
                  onClick={toggleSelectAll}
                  className="text-xs font-medium text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 flex items-center gap-1.5 shrink-0 px-2 py-1 cursor-pointer transition"
                  id="btn-queue-select-all"
                >
                  {selectedIds.length === filteredItems.length ? (
                    <CheckSquare className="w-3.5 h-3.5 text-neutral-900 dark:text-neutral-100" />
                  ) : (
                    <Square className="w-3.5 h-3.5" />
                  )}
                  <span>
                    {selectedIds.length > 0 ? `${selectedIds.length} Selected` : "Select All"}
                  </span>
                </button>
              )}
            </div>
            {counts.Failed + counts.Unavailable > 0 && (
              <div className="mt-3">
                <Button
                  variant="secondary"
                  size="sm"
                  label={`Export Failed / Unavailable (${counts.Failed + counts.Unavailable})`}
                  icon={<FileDown className="w-3.5 h-3.5" />}
                  onClick={() => downloadQueueFailures(queue)}
                  id="btn-export-queue-failures"
                />
              </div>
            )}
          </>
        }
      />

      {/* Batch Action Toolbar */}
      {selectedIds.length > 0 && (
        <Card padding={3} elevation="low" id="queue-batch-bar">
          <div className="flex items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 font-medium text-neutral-700 dark:text-neutral-300">
              <CheckSquare className="w-4 h-4 text-neutral-900 dark:text-neutral-100" />
              <span>{selectedIds.length} items selected in queue</span>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              <Button
                variant="secondary"
                size="sm"
                label="Retry Selected"
                icon={<RotateCcw className="w-3 h-3" />}
                onClick={() => onBatchAction(selectedIds, "retry")}
              />
              <Button
                variant="secondary"
                size="sm"
                label="Cancel Selected"
                icon={<XCircle className="w-3 h-3" />}
                onClick={() => onBatchAction(selectedIds, "cancel")}
              />
              <Button
                variant="destructive"
                size="sm"
                label="Delete Selected"
                icon={<Trash2 className="w-3 h-3" />}
                onClick={() => {
                  onBatchAction(selectedIds, "delete");
                  setSelectedIds([]);
                }}
              />
            </div>
          </div>
        </Card>
      )}

      {/* Divided Layout: Left Queue List + Collapsible Side Details Panel */}
      {filteredItems.length === 0 ? (
        <Card padding={6} elevation="low" id="queue-empty-card">
          <EmptyState
            title={filter === "All" ? "Download queue is empty" : `No items marked as '${filter}'`}
            description="Search for tracks, albums, or playlists from the Dashboard and click 'Queue Download' to begin downloading."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start" id="queue-divided-panel">
          {/* LEFT PANEL: Queue Item List (expands to full 12 cols when side view is collapsed) */}
          <div
            className={`space-y-2 transition-all duration-200 ${
              showSidePanel ? "lg:col-span-6 xl:col-span-6" : "lg:col-span-12"
            }`}
            id="queue-items-list"
          >
            <div className="flex items-center justify-between px-1 text-xs text-neutral-500 font-medium">
              <span>Items ({filteredItems.length})</span>
              <span>
                {showSidePanel
                  ? "Select item to view details"
                  : "Detail view collapsed • Full track specs & transfer actions displayed inline"}
              </span>
            </div>

            <div className="space-y-2 max-h-[calc(100vh-280px)] overflow-y-auto pr-1">
              {filteredItems.map((item) => {
                const serviceInfo = getServiceInfo(item.item_service);
                const isSelectedInBatch = selectedIds.includes(item.local_id);
                const isFocused = item.local_id === selectedItemId;
                const isDownloading = item.item_status === "Downloading";
                const isDownloaded =
                  item.item_status === "Downloaded" || item.item_status === "Already Exists";
                const isFailed = item.item_status === "Failed";

                const absoluteIndex = queue.findIndex((qItem) => qItem.local_id === item.local_id);
                const queueNum = absoluteIndex + 1;

                if (!showSidePanel) {
                  {/* EXPANDED ROW VIEW: Shown when the side detail panel is collapsed */}
                  return (
                    <div
                      key={item.local_id}
                      onClick={() => handleItemClick(item.local_id)}
                      id={`queue-item-row-${item.local_id}`}
                      className={`group relative flex flex-col lg:flex-row lg:items-center justify-between gap-4 p-3.5 rounded-xl border transition-all cursor-pointer select-none ${
                        isFocused
                          ? "bg-neutral-50 dark:bg-neutral-800/90 border-emerald-500/80 dark:border-emerald-500/80 shadow-xs ring-1 ring-emerald-500/30"
                          : "bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800 hover:border-neutral-300 dark:hover:border-neutral-600"
                      }`}
                    >
                      {/* Left: Checkbox, Queue Number, Artwork & Grouped Media Info */}
                      <div className="flex items-center gap-3.5 min-w-0 flex-1">
                        {/* Checkbox for batch selection */}
                        <button
                          type="button"
                          onClick={(e) => toggleSelectItem(e, item.local_id)}
                          className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 cursor-pointer p-0.5 shrink-0"
                          aria-label={`Select ${item.name}`}
                        >
                          {isSelectedInBatch ? (
                            <CheckSquare className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>

                        {/* Queue number */}
                        <span className="text-[11px] font-mono font-medium text-neutral-400 dark:text-neutral-500 w-5 text-right shrink-0">
                          #{queueNum}
                        </span>

                        {/* Artwork with service indicator dot */}
                        <div className="relative w-12 h-12 rounded-lg overflow-hidden bg-neutral-100 dark:bg-neutral-800 shrink-0 border border-neutral-200/80 dark:border-neutral-700/80 shadow-2xs">
                          <img
                            src={
                              item.thumbnail ||
                              "null"
                            }
                            alt={item.name}
                            className="w-full h-full object-cover"
                            referrerPolicy="no-referrer"
                          />
                        </div>

                        {/* Grouped Information Column */}
                        <div className="min-w-0 flex-1 space-y-1">
                          {/* Row 1: Track Title + Status Badge */}
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                              {item.name}
                            </p>
                            <div className="shrink-0 scale-95 origin-left">
                              {getStatusBadge(item.item_status, false)}
                            </div>
                          </div>

                          {/* Row 2: Artist & Album info */}
                          <div className="flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400 truncate">
                            <span className="font-medium text-neutral-700 dark:text-neutral-200 truncate">
                              {item.artist}
                            </span>
                            {item.album && (
                              <>
                                <span className="text-neutral-300 dark:text-neutral-600">•</span>
                                <span className="inline-flex items-center gap-1 truncate text-neutral-500 dark:text-neutral-400">
                                  <Disc className="w-3 h-3 text-neutral-400 shrink-0" />
                                  <span className="truncate">Part of Album: {item.album}</span>
                                </span>
                              </>
                            )}
                            {item.playlist_name && (
                              <>
                                <span className="text-neutral-300 dark:text-neutral-600 hidden sm:inline">•</span>
                                <span className="hidden sm:inline-flex items-center gap-1 text-neutral-400 truncate max-w-[160px]">
                                  <Layers className="w-3 h-3 text-neutral-400 shrink-0" />
                                  <span className="truncate">Part of Playlist: {item.playlist_name}</span>
                                </span>
                              </>
                            )}
                          </div>

                          {/* Row 3: Cohesive Badge Group (Source, Format/Bitrate, Size, Profile) */}
                          <div className="flex items-center gap-1.5 flex-wrap pt-0.5 text-[11px]">
                            {/* Service Source Badge */}
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-neutral-100 dark:bg-neutral-800 border border-neutral-200/60 dark:border-neutral-700/60 text-neutral-700 dark:text-neutral-300 font-medium">
                              <span
                                className="w-1.5 h-1.5 rounded-full"
                                style={{ backgroundColor: serviceInfo.color }}
                              />
                              {serviceInfo.name}
                            </span>

                            {/* Audio Codec & Bitrate */}
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-neutral-100 dark:bg-neutral-800 border border-neutral-200/60 dark:border-neutral-700/60 text-neutral-700 dark:text-neutral-300 font-mono">
                              <Sliders className="w-3 h-3 text-neutral-400" />
                              {item.download_format != "" ? `${item.download_format}`:`Best Source`}
                            </span>

                            {/* File Size Badge */}
                            {item.file_size && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-md bg-neutral-100 dark:bg-neutral-800 border border-neutral-200/60 dark:border-neutral-700/60 text-neutral-600 dark:text-neutral-400 font-mono">
                                {Math.floor((Number(item.file_size) / 1024) / 1024)} MB
                              </span>
                            )}

                            {/* Target Profile */}
                            <span className="hidden md:inline-flex items-center px-2 py-0.5 rounded-md bg-neutral-100 dark:bg-neutral-800 border border-neutral-200/60 dark:border-neutral-700/60 text-neutral-500 dark:text-neutral-400 font-mono">
                              {item.download_profile.name || activeProfile}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Center: Live Progress Bar & Transfer State (NO PATH) */}
                      <div className="w-full lg:w-64 xl:w-72 shrink-0 flex flex-col justify-center gap-1.5 px-1 py-1">
                        {/* Status Header above Progress Bar */}
                        <div className="flex items-center justify-between text-xs">
                          {isDownloading ? (
                            <>
                              <span className="font-mono text-xs font-bold text-neutral-800 dark:text-neutral-200">
                                {item.progress}%{" "}
                              </span>
                            </>
                          ) : isDownloaded ? (
                            <>
                              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium text-xs">
                                <Check className="w-3.5 h-3.5" /> Ready
                              </span>
                              <span className="font-mono text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                                100%
                              </span>
                            </>
                          ) : isFailed ? (
                            <>
                              <span
                                className="text-red-500 font-medium text-xs flex items-center gap-1 truncate max-w-[170px]"
                                title={item.error || "Download error"}
                              >
                                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                                {item.error || "Failed"}
                              </span>
                              <span className="font-mono text-xs font-semibold text-red-500">
                                {item.progress || 0}%
                              </span>
                            </>
                          ) : (
                            <>
                              <span className="flex items-center gap-1 text-xs text-neutral-500 dark:text-neutral-400">
                                <Clock className="w-3.5 h-3.5" />
                                {item.item_status === "Paused" ? "Paused" : "Queued"}
                              </span>
                              <span className="font-mono text-xs text-neutral-400">
                                {item.item_status === "Paused" ? `${item.progress}%` : "0%"}
                              </span>
                            </>
                          )}
                        </div>

                        {/* Progress Bar (Always shown) */}
                        <div className="w-full bg-neutral-200 dark:bg-neutral-800 h-2 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${
                              isDownloading
                                ? "bg-amber-500 dark:bg-amber-400"
                                : isDownloaded
                                ? "bg-emerald-500 dark:bg-emerald-400"
                                : isFailed
                                ? "bg-red-500 dark:bg-red-400"
                                : "bg-neutral-300 dark:bg-neutral-700"
                            }`}
                            style={{
                              width: `${
                                isDownloaded
                                  ? 100
                                  : isFailed
                                  ? Math.max(item.progress || 0, 15)
                                  : isDownloading
                                  ? item.progress
                                  : item.item_status === "Paused"
                                  ? item.progress
                                  : 0
                              }%`,
                            }}
                          />
                        </div>
                      </div>

                      {/* Right: Inline Action Buttons */}
                      <div className="flex items-center gap-2 shrink-0 justify-end pt-2 lg:pt-0 border-t lg:border-t-0 border-neutral-100 dark:border-neutral-800">
                        {isDownloaded && (
                          <Button
                            variant="primary"
                            size="sm"
                            label="Save"
                            icon={<FileDown className="w-3.5 h-3.5" />}
                            onClick={(e) => {
                              e.stopPropagation();
                              downloadFile(item);
                            }}
                            id={`btn-row-save-${item.local_id}`}
                          />
                        )}

                        {isFailed && (
                          <Button
                            variant="secondary"
                            size="sm"
                            label="Retry"
                            icon={<RotateCcw className="w-3.5 h-3.5" />}
                            onClick={(e) => {
                              e.stopPropagation();
                              onAction(item.local_id, "retry");
                            }}
                            id={`btn-row-retry-${item.local_id}`}
                          />
                        )}

                        {isDownloading && (
                          <Button
                            variant="secondary"
                            size="sm"
                            label="Cancel"
                            icon={<XCircle className="w-3.5 h-3.5" />}
                            onClick={(e) => {
                              e.stopPropagation();
                              onAction(item.local_id, "cancel");
                            }}
                            id={`btn-row-cancel-${item.local_id}`}
                          />
                        )}

                        {/* Open Side Detail Panel for this item */}
                        <Button
                          variant="ghost"
                          size="sm"
                          label="Details"
                          icon={<PanelRightOpen className="w-3.5 h-3.5" />}
                          onClick={(e) => handleOpenDetails(e, item.local_id)}
                          id={`btn-row-details-${item.local_id}`}
                        />

                        {/* Quick Delete */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onAction(item.local_id, "delete");
                          }}
                          className="p-1.5 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-400 hover:text-red-500 dark:hover:text-red-400 transition cursor-pointer"
                          title="Remove from queue"
                          aria-label={`Remove ${item.name} from queue`}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                }

                {/* COMPACT ROW VIEW: Shown when side detail panel is OPEN */}
                return (
                  <div
                    key={item.local_id}
                    onClick={() => handleItemClick(item.local_id)}
                    id={`queue-item-row-${item.local_id}`}
                    className={`group relative flex items-center gap-3 p-3 rounded-xl border transition-all cursor-pointer select-none ${
                      isFocused
                        ? "bg-neutral-50 dark:bg-neutral-800/90 border-emerald-500/80 dark:border-emerald-500/80 shadow-xs ring-1 ring-emerald-500/30"
                        : "bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800 hover:border-neutral-300 dark:hover:border-neutral-600"
                    }`}
                  >
                    {/* Checkbox for batch selection */}
                    <button
                      type="button"
                      onClick={(e) => toggleSelectItem(e, item.local_id)}
                      className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 cursor-pointer p-0.5 shrink-0"
                      aria-label={`Select ${item.name}`}
                    >
                      {isSelectedInBatch ? (
                        <CheckSquare className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>

                    {/* Queue number */}
                    <span className="text-[11px] font-mono text-neutral-400 dark:text-neutral-500 w-5 text-right shrink-0">
                      #{queueNum}
                    </span>

                    {/* Artwork with service indicator dot */}
                    <div className="relative w-10 h-10 rounded-lg overflow-hidden bg-neutral-100 dark:bg-neutral-800 shrink-0 border border-neutral-200/60 dark:border-neutral-700/60 shadow-2xs">
                      <img
                        src={
                          item.thumbnail ||
                          "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=120&auto=format&fit=crop&q=80"
                        }
                        alt={item.name}
                        className="w-full h-full object-cover"
                        referrerPolicy="no-referrer"
                      />
                      <span
                        className="absolute top-1 left-1 w-2 h-2 rounded-full ring-1 ring-white/80 dark:ring-black/80"
                        style={{ backgroundColor: serviceInfo.color }}
                        title={serviceInfo.name}
                      />
                    </div>

                    {/* Title, Artist, Status, Format */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                          {item.name}
                        </p>
                        <div className="shrink-0 scale-90 origin-right">
                          {getStatusBadge(item.item_status, true)}
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-2 mt-0.5 text-[11px] text-neutral-500 dark:text-neutral-400">
                        <span className="truncate">{item.artist}</span>
                        {isDownloading ? (
                          <span className="font-mono text-amber-500 font-medium shrink-0">
                            {item.progress}%
                          </span>
                        ) : isDownloaded ? (
                          <span className="font-mono text-emerald-600 dark:text-emerald-400 shrink-0">
                            100%
                          </span>
                        ) : (
                          <span className="font-mono text-neutral-400 shrink-0">
                            {item.target_format || ""}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Active chevron indicator */}
                    <ChevronRight
                      className={`w-4 h-4 shrink-0 transition ${
                        isFocused
                          ? "text-emerald-500 transform translate-x-0.5"
                          : "text-neutral-300 dark:text-neutral-600 opacity-0 group-hover:opacity-100"
                      }`}
                    />
                  </div>
                );
              })}
            </div>
          </div>

          {/* RIGHT PANEL: Collapsible Side View with Item Details & Progress */}
          {showSidePanel && (
            <div
              className="lg:col-span-6 xl:col-span-6 sticky top-4 animate-in fade-in slide-in-from-right-2 duration-200"
              id="queue-item-detail-panel"
            >
              {selectedItem ? (
                <Card padding={5} elevation="low" id={`detail-card-${selectedItem.local_id}`}>
                  {(() => {
                    const serviceInfo = getServiceInfo(selectedItem.item_service);
                    const isDownloading = selectedItem.item_status === "Downloading";
                    const isDownloaded =
                      selectedItem.item_status === "Downloaded" ||
                      selectedItem.item_status === "Already Exists";
                    const isFailed = selectedItem.item_status === "Failed";
                    const absoluteIndex = queue.findIndex(
                      (q) => q.local_id === selectedItem.local_id
                    );
                    const queueNum = absoluteIndex + 1;

                    return (
                      <div className="space-y-5">
                        {/* Header bar of Side Detail Panel with Close / Collapse Button */}
                        <div className="flex items-center justify-between border-b border-neutral-200 dark:border-neutral-800 pb-3">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-md bg-neutral-100 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300">
                              #{queueNum}
                            </span>
                            {getStatusBadge(selectedItem.item_status)}
                            <div
                              className="px-2 py-0.5 rounded-md text-[10px] font-bold text-black shadow-xs flex items-center gap-1 "
                              style={{ backgroundColor: serviceInfo.color }}
                            >
                              <span>{serviceInfo.name}</span>
                            </div>
                          </div>

                          <button
                            type="button"
                            onClick={() => setShowSidePanel(false)}
                            className="p-1 rounded-lg hover:bg-neutral-100 dark:hover:bg-neutral-800 text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition cursor-pointer flex items-center gap-1 text-xs"
                            title="Collapse side details view"
                            aria-label="Collapse side details view"
                          >
                            <PanelRightClose className="w-4 h-4" />
                            <span className="hidden sm:inline text-[11px]">Collapse</span>
                          </button>
                        </div>

                        {/* Media Hero: Artwork, Name, Artist, Album */}
                        <div className="flex items-start gap-4">
                          <div className="relative w-20 h-20 sm:w-24 sm:h-24 rounded-xl overflow-hidden bg-neutral-100 dark:bg-neutral-800 shrink-0 border border-neutral-200 dark:border-neutral-700 shadow-sm">
                            <img
                              src={
                                selectedItem.thumbnail ||
                                "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=240&auto=format&fit=crop&q=80"
                              }
                              alt={selectedItem.name}
                              className="w-full h-full object-cover"
                              referrerPolicy="no-referrer"
                            />
                            
                          </div>

                          <div className="min-w-0 flex-1 space-y-1">
                            <h3 className="text-base font-bold text-neutral-900 dark:text-neutral-100 leading-snug">
                              {selectedItem.name}
                            </h3>
                            <p className="text-sm font-medium text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
                              <User className="w-3.5 h-3.5 text-neutral-400" />
                              <span>{selectedItem.artist}</span>
                            </p>
                            {selectedItem.album && (
                              <p className="text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-1.5">
                                <Disc className="w-3.5 h-3.5 text-neutral-400" />
                                <span>{selectedItem.album}</span>
                              </p>
                            )}
                            {selectedItem.playlist_name && (
                              <p className="text-xs text-neutral-500 dark:text-neutral-400 flex items-center gap-1.5">
                                <Layers className="w-3.5 h-3.5 text-neutral-400" />
                                <span>Playlist: {selectedItem.playlist_name}</span>
                              </p>
                            )}
                          </div>
                        </div>

                        {/* Download Progress & Transfer Details */}
                        <div className="p-3.5 rounded-xl bg-neutral-50 dark:bg-neutral-800 border border-neutral-200/80 dark:border-neutral-700 space-y-2.5">
                          <div className="flex items-center justify-between text-xs">
                            <span className="font-semibold text-neutral-700 dark:text-neutral-300">
                              Download Progress
                            </span>
                            <span className="font-mono font-bold text-neutral-900 dark:text-neutral-100">
                              {selectedItem.progress}%
                            </span>
                          </div>

                          <ProgressBar
                            label={`Progress for ${selectedItem.name}`}
                            value={selectedItem.progress}
                            max={100}
                            isLabelHidden={true}
                            variant={isFailed ? "error" : isDownloaded ? "success" : "accent"}
                          />

                          <div className="flex items-center justify-between text-[11px] text-neutral-500 dark:text-neutral-400">
                            {isDownloaded ? (
                              <span className="text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                                <Check className="w-3.5 h-3.5" /> File complete and saved to disk
                              </span>
                            ) : isFailed ? (
                              <span className="text-red-500 font-medium flex items-center gap-1">
                                <AlertCircle className="w-3.5 h-3.5" /> Download stopped due to error
                              </span>
                            ) : (
                              <span className="flex items-center gap-1 text-neutral-400">
                                <Clock className="w-3.5 h-3.5" /> {selectedItem.item_status}
                              </span>
                            )}

                            {selectedItem.file_size && (
                              <span className="font-mono font-medium">{Math.floor((Number(selectedItem.file_size) / 1024) / 1024)}</span>
                            )}
                          </div>

                          {/* Error message if failed */}
                          {isFailed && selectedItem.error && (
                            <div className="p-2.5 rounded-lg bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-900/60 text-xs text-red-600 dark:text-red-400 flex items-start gap-2">
                              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                              <div>
                                <p className="font-semibold">Download Failure Reason:</p>
                                <p className="mt-0.5 font-mono text-[11px]">{selectedItem.error}</p>
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Technical Specifications Grid */}
                        <div className="space-y-2">
                          <h4 className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-1.5">
                            <Sliders className="w-3.5 h-3.5 text-neutral-500" />
                            Technical Specs & Profile Information
                          </h4>

                          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                            <div className="p-2.5 rounded-lg bg-neutral-100/70 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-neutral-700/50">
                              <span className="text-[10px] text-neutral-400 uppercase font-bold tracking-wider block">
                                Catalog Service
                              </span>
                              <span className="font-medium text-neutral-800 dark:text-neutral-200 mt-0.5 block">
                                {serviceInfo.name}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-lg bg-neutral-100/70 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-neutral-700/50">
                              <span className="text-[10px] text-neutral-400 uppercase font-bold tracking-wider block">
                                Audio Codec
                              </span>
                              <span className="font-mono font-medium text-neutral-800 dark:text-neutral-200 mt-0.5 block">
                                {selectedItem.target_format || "FLAC Lossless"}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-lg bg-neutral-100/70 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-neutral-700/50">
                              <span className="text-[10px] text-neutral-400 uppercase font-bold tracking-wider block">
                                Bitrate & Depth
                              </span>
                              <span className="font-mono font-medium text-neutral-800 dark:text-neutral-200 mt-0.5 block">
                                {selectedItem.bitrate + "kbps"}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-lg bg-neutral-100/70 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-neutral-700/50">
                              <span className="text-[10px] text-neutral-400 uppercase font-bold tracking-wider block">
                                Item Type
                              </span>
                              <span className="font-medium text-neutral-800 dark:text-neutral-200 mt-0.5 capitalize block">
                                {selectedItem.item_type || "track"}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-lg bg-neutral-100/70 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-neutral-700/50">
                              <span className="text-[10px] text-neutral-400 uppercase font-bold tracking-wider block">
                                Profile Target
                              </span>
                              <span className="font-medium text-neutral-800 dark:text-neutral-200 mt-0.5 block truncate">
                                {selectedItem.download_profile.name || activeProfile}
                              </span>
                            </div>

                            <div className="p-2.5 rounded-lg bg-neutral-100/70 dark:bg-neutral-800/60 border border-neutral-200/50 dark:border-neutral-700/50">
                              <span className="text-[10px] text-neutral-400 uppercase font-bold tracking-wider block">
                                Item ID
                              </span>
                              <span
                                className="font-mono text-[11px] text-neutral-800 dark:text-neutral-200 truncate mt-0.5 block"
                                title={selectedItem.item_id}
                              >
                                {selectedItem.item_id || selectedItem.local_id}
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Destination File Path */}
                        {selectedItem.file_path && (
                          <div className="space-y-1">
                            <span className="text-xs font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
                              <Folder className="w-3.5 h-3.5 text-neutral-400" />
                              Storage Destination
                            </span>
                            <div className="p-2 rounded-lg bg-neutral-100/80 dark:bg-neutral-800/80 border border-neutral-200/60 dark:border-neutral-700/60 font-mono text-[11px] text-neutral-600 dark:text-neutral-300 break-all select-all">
                              {selectedItem.file_path}
                            </div>
                          </div>
                        )}

                        {/* URL / Stream Source */}
                        {selectedItem.item_url && (
                          <div className="space-y-1">
                            <span className="text-xs font-semibold text-neutral-700 dark:text-neutral-300 flex items-center gap-1.5">
                              <ExternalLink className="w-3.5 h-3.5 text-neutral-400" />
                              Stream Source URL
                            </span>
                            <div className="flex items-center gap-2">
                              <input
                                type="text"
                                readOnly
                                value={selectedItem.item_url}
                                className="flex-1 px-2.5 py-1.5 rounded-lg bg-neutral-100/80 dark:bg-neutral-800/80 border border-neutral-200 dark:border-neutral-700 font-mono text-[11px] text-neutral-600 dark:text-neutral-300 truncate"
                              />
                              <Button
                                variant="secondary"
                                size="sm"
                                label={copiedId === selectedItem.local_id ? "Copied" : "Copy"}
                                icon={
                                  copiedId === selectedItem.local_id ? (
                                    <Check className="w-3.5 h-3.5 text-emerald-500" />
                                  ) : (
                                    <Copy className="w-3.5 h-3.5" />
                                  )
                                }
                                onClick={() => copyUrl(selectedItem.local_id, selectedItem.item_url)}
                              />
                            </div>
                          </div>
                        )}

                        {/* Actions Footer */}
                        <div className="flex items-center justify-between gap-2 pt-3 border-t border-neutral-200 dark:border-neutral-800 flex-wrap">
                          <div className="flex items-center gap-2">
                            {isDownloaded && (
                              <Button
                                variant="primary"
                                size="sm"
                                label="Download File"
                                icon={<FileDown className="w-3.5 h-3.5" />}
                                onClick={() => downloadFile(selectedItem)}
                                id={`btn-detail-download-${selectedItem.local_id}`}
                              />
                            )}

                            {isFailed && (
                              <Button
                                variant="primary"
                                size="sm"
                                label="Retry Download"
                                icon={<RotateCcw className="w-3.5 h-3.5" />}
                                onClick={() => onAction(selectedItem.local_id, "retry")}
                                id={`btn-detail-retry-${selectedItem.local_id}`}
                              />
                            )}

                            {isDownloading && (
                              <Button
                                variant="secondary"
                                size="sm"
                                label="Cancel Download"
                                icon={<XCircle className="w-3.5 h-3.5" />}
                                onClick={() => onAction(selectedItem.local_id, "cancel")}
                                id={`btn-detail-cancel-${selectedItem.local_id}`}
                              />
                            )}
                          </div>

                          <Button
                            variant="destructive"
                            size="sm"
                            label="Remove From Queue"
                            icon={<Trash2 className="w-3.5 h-3.5" />}
                            onClick={() => onAction(selectedItem.local_id, "delete")}
                            id={`btn-detail-delete-${selectedItem.local_id}`}
                          />
                        </div>
                      </div>
                    );
                  })()}
                </Card>
              ) : (
                <Card padding={6} elevation="low">
                  <EmptyState
                    title="No Item Selected"
                    description="Select a download item from the left panel to inspect full audio specifications, path routing, and actions."
                    icon={<Info className="w-8 h-8 text-neutral-400" />}
                  />
                </Card>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
