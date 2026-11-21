import { Badge, Button, Card, ProgressBar } from "./ui";
import {
  Activity,
  CheckCircle2,
  HardDrive,
  RefreshCw,
  Server,
  Sparkles,
  Wifi,
  WifiOff,
  XCircle,
  Zap
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { fetchSystemDiagnostics, getTargetBackendUrl } from "../lib/api";
import { OTSConfig, SystemDiagnostics } from "../types";
import { PageHeader } from "./PageHeader";
import { SectionHeader } from "./SectionHeader";
import { UpdatePanel } from "./UpdatePanel";

interface DiagnosticsPanelProps {
  wsConnected?: boolean;
  newVersion?: boolean;
  onCheckVersion?: () => Promise<void>;
  config?: OTSConfig | null;
}

const formatBytes = (value: number) => {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount.toFixed(index >= 3 ? 1 : 0)} ${units[index]}`;
};

export const DiagnosticsPanel: React.FC<DiagnosticsPanelProps> = ({
  wsConnected = true,
  newVersion = false,
  onCheckVersion,
  config,
}) => {
  const [data, setData] = useState<SystemDiagnostics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date());

  // The 4s poll stays quiet; only a click shows the loading state.
  const refreshDiagnostics = async (isManual = false) => {
    if (isManual) setIsLoading(true);
    try {
      const res = await fetchSystemDiagnostics();
      setData(res);
      setLastRefreshed(new Date());
      if (onCheckVersion) {
        await onCheckVersion();
      }
    } finally {
      if (isManual) setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshDiagnostics(true);
    const timer = setInterval(() => refreshDiagnostics(), 4000);
    return () => clearInterval(timer);
  }, []);

  const formatUptime = (seconds: number) => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    return `${hrs}h ${mins}m ${secs}s`;
  };

  const totalCacheRequests =  0;
  const cacheHitRatio = 0;

  const heapPercent = 0

  const diskUsedPercent =
    data && data.disk && data.disk.total > 0
      ? Math.round((data.disk.used / data.disk.total) * 100)
      : 24;

  const targetApi = data?.target || getTargetBackendUrl() || "http://127.0.0.1:5000";

  // Build worker list from active_workers_map or fallback
  const workerEntries: [string, boolean][] = data?.workers?.active_workers_map
    ? Object.entries(data.workers.active_workers_map)
    : [
        ["queue_worker", data?.workers?.parsing ?? true],
        ["download_worker", data?.workers?.downloads ?? true],
        ["retry_worker", data?.workers?.retry ?? true],
        ["accounts_worker", data?.workers?.accounts ?? true],
        ["connect_service", data?.spotify_api?.connected ?? false],
      ];

  const onlineWorkersCount = workerEntries.filter(([, active]) => active).length;
  const totalWorkersCount = workerEntries.length;

  return (
    <div className="space-y-6 font-sans" id="diagnostics-view">
      {/* Page Header */}
      <PageHeader
        id="diagnostics-page-header"
        icon={<Activity className="w-5 h-5 text-accent" />}
        title="System Diagnostics & Engine Telemetry"
        badge={{
          label: data?.backend.status === "online" ? "FastAPI Online" : "Disconnected",
          variant: data?.backend.status === "online" ? "success" : "error",
        }}
        description="Live status for background thread workers, FFmpeg binary, disk headroom, API rate limits, and memory utilization"
        actions={
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-fg-muted font-mono hidden sm:inline">
              Updated {lastRefreshed.toLocaleTimeString()}
            </span>
            <Button
              variant="secondary"
              size="sm"
              label="Refresh Telemetry"
              icon={<RefreshCw className="w-3.5 h-3.5" />}
              onClick={() => refreshDiagnostics(true)}
              isLoading={isLoading}
              id="btn-refresh-diagnostics"
            />
          </div>
        }
      />

      {data && (
        <div className="space-y-6">
          {/* Real-time Subsystem Status Bar */}
          <div className="rounded-xl border border-line bg-sunken p-4">
            <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-2 text-xs font-semibold">
                  {wsConnected ? (
                    <span className="flex items-center gap-1.5 text-success-fg">
                      <Wifi className="w-4 h-4" />
                      Daemon Connected
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-warning-fg">
                      <WifiOff className="w-4 h-4" />
                      Connecting…
                    </span>
                  )}
                </div>
                <span className="text-fg-subtle">•</span>
                <span className="text-xs font-mono text-fg-muted truncate max-w-xs" title={targetApi}>
                  {targetApi}
                </span>
              </div>

              {/* Status Chips Row */}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {/* 1. OnTheSpot Core */}
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-success/30 bg-success-subtle text-success-fg font-medium">
                  <CheckCircle2 className="w-3.5 h-3.5 text-success-fg" />
                  <span>OTS Core {data.backend.version}</span>
                </div>

                {/* 2. Spotify API */}
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-medium ${
                    data.spotify_api.connected && !data.spotify_api.rate_limited
                      ? "border-success/30 bg-success-subtle text-success-fg"
                      : data.spotify_api.rate_limited
                      ? "border-warning/30 bg-warning-subtle text-warning-fg"
                      : "border-line bg-raised text-fg-muted"
                  }`}
                >
                  <Wifi className="w-3.5 h-3.5" />
                  <span>Spotify API: {data.spotify_api.status}</span>
                </div>

                {/* 3. Spotify Connect */}
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-medium ${
                    data.spotify_api.connect_service?.running
                      ? "border-success/30 bg-success-subtle text-success-fg"
                      : "border-line bg-raised text-fg-muted"
                  }`}
                >
                  {data.spotify_api.connect_service?.running ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-success-fg" />
                  ) : (
                    <WifiOff className="w-3.5 h-3.5 text-fg-subtle" />
                  )}
                  <span>
                    Spotify Connect:{" "}
                    {data.spotify_api.connect_service?.running
                      ? `Discoverable (${data.spotify_api.connect_service.port})`
                      : "Unavailable"}
                  </span>
                </div>

                {/* 4. Rate Limiting */}
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border font-medium ${
                    data.rate_limit?.active || data.spotify_api.rate_limited
                      ? "border-warning/30 bg-warning-subtle text-warning-fg"
                      : "border-line bg-raised text-fg-muted"
                  }`}
                >
                  <span>
                    {data.rate_limit?.active
                      ? `Rate limited: ${data.rate_limit.seconds_remaining}s`
                      : "No Rate Limits Active"}
                  </span>
                </div>

                {newVersion && (
                  <span className="flex items-center gap-1 text-success-fg font-bold">
                    <Sparkles className="w-3.5 h-3.5" /> Update Ready
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Key Metric Tiles */}
          <div>
            <SectionHeader
              title="Telemetry Metrics"
              description="Real-time subsystem statistics polled from OnTheSpot FastAPI background daemon"
            />

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4" id="diagnostics-cards-grid">
              {/* 1. Queue Engine */}
              <Card padding={4} elevation="low">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Zap className="w-4 h-4 text-accent" />
                    <h4 className="text-xs font-semibold text-fg">
                      Download Queue
                    </h4>
                  </div>
                  <Badge
                    variant={data.queue.paused ? "warning" : "info"}
                    label={data.queue.total > 0 ? "No Items" : `${data.queue.total} Items`}
                  />
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Active Streams:</span>
                    <span className="font-mono font-medium text-success-fg">
                      {data.queue.statuses["Downloading"] || 0} downloading
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Pending in Queue:</span>
                    <span className="font-mono text-fg">
                      {data.queue.pending ?? (data.queue.statuses["Waiting"] || 0)} pending
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Metadata Parsing:</span>
                    <span className="font-mono text-fg-muted">
                      {data.queue.parsing ?? 0} parsing
                    </span>
                  </div>
                </div>
              </Card>

              {/* 2. Disk Space */}
              <Card padding={4} elevation="low">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <HardDrive className="w-4 h-4 text-info" />
                    <h4 className="text-xs font-semibold text-fg">
                      Storage & Disk Free
                    </h4>
                  </div>
                  <span className="font-mono text-xs font-medium text-fg">
                    {formatBytes(data.disk.free)} free
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between text-fg-muted">
                    <span>Capacity:</span>
                    <span className="font-mono text-fg">
                      {formatBytes(data.disk.used)} / {formatBytes(data.disk.total)}
                    </span>
                  </div>
                  <ProgressBar
                    label="Disk usage"
                    value={diskUsedPercent}
                    max={100}
                    isLabelHidden={true}
                    variant={diskUsedPercent > 90 ? "error" : "accent"}
                  />
                  <div className="flex justify-between text-fg-muted pt-0.5">
                    <span>Disk Headroom:</span>
                    <span className="font-mono text-success-fg">
                      {100 - diskUsedPercent}% available
                    </span>
                  </div>
                </div>
              </Card>

              {/* 3. FFmpeg Engine */}
              <Card padding={4} elevation="low">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Server className="w-4 h-4 text-fg-subtle" />
                    <h4 className="text-xs font-semibold text-fg">
                      FFmpeg Audio Transcoder
                    </h4>
                  </div>
                  <Badge
                    variant={data.ffmpeg.available ? "success" : "error"}
                    label={data.ffmpeg.available ? "Available" : "Missing"}
                  />
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Binary Path:</span>
                    <span
                      className="font-mono text-fg-muted truncate max-w-[140px]"
                      title={data.ffmpeg.path}
                    >
                      {data.ffmpeg.path || "/usr/bin/ffmpeg"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Version:</span>
                    <span className="font-mono text-fg-muted">
                      {data.ffmpeg.version || "nd"}
                    </span>
                  </div>
                </div>
              </Card>

              {/* 
              {/*4. Process Memory (RAM) 
              <Card padding={4} elevation="low">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-warning" />
                    <h4 className="text-xs font-semibold text-fg">
                      Process Memory (RSS)
                    </h4>
                  </div>
                  <span className="font-mono text-xs font-medium text-fg">
                     MB
                  </span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between text-fg-muted">
                    <span>Heap Allocation:</span>
                    <span className="font-mono text-fg">
                      MB
                    </span>
                  </div>
                  <ProgressBar
                    label="Heap memory"
                    value={heapPercent}
                    max={100}
                    isLabelHidden={true}
                    variant={heapPercent > 85 ? "error" : "accent"}
                  />
                  <div className="flex justify-between text-fg-muted pt-0.5">
                    <span>Memory Pressure:</span>
                    <span className="font-mono text-success-fg">
                      {heapPercent < 80 ? "Healthy (< 80%)" : "Elevated"}
                    </span>
                  </div>
                </div>
              </Card>

              {/* 5. API & Metadata Cache 
              <Card padding={4} elevation="low">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Database className="w-4 h-4 text-accent" />
                    <h4 className="text-xs font-semibold text-fg">
                      Metadata & API Cache
                    </h4>
                  </div>
                  <Badge variant="info" label={`${cacheHitRatio}% Hit Ratio`} />
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between text-fg-muted">
                    <span>Hits vs Misses:</span>
                    <span className="font-mono text-fg">
                      
                    </span>
                  </div>
                  <ProgressBar
                    label="Cache hit ratio"
                    value={cacheHitRatio}
                    max={100}
                    isLabelHidden={true}
                    variant="success"
                  />
                  <div className="flex justify-between text-fg-muted pt-0.5">
                    <span>Cache Storage:</span>
                    <span className="font-mono text-fg-muted">
                       MB
                    </span>
                  </div>
                </div>
              </Card>

              {/* 6. Daemon Host & Uptime 
              <Card padding={4} elevation="low">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Activity className="w-4 h-4 text-fg-subtle" />
                    <h4 className="text-xs font-semibold text-fg">
                      Daemon Runtime
                    </h4>
                  </div>
                  <Badge variant="neutral" label={`v${data.version}`} />
                </div>

                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Engine Uptime:</span>
                    <span className="font-mono font-medium text-fg">
                      {formatUptime(data.uptime_seconds)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Rate Limit Status:</span>
                    <span className="font-mono text-success-fg">
                      {data.rate_limit?.active ? `Throttled (${data.rate_limit.seconds_remaining}s)` : "Normal Throughput"}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-fg-muted">Target Host:</span>
                    <span className="font-mono text-fg-muted truncate max-w-[140px]" title={data.target}>
                      {data.target}
                    </span>
                  </div>
                </div>
              </Card>
              */}
            </div>
          </div>
          
          {/* Worker Threads & Queue Breakdown Panel */}
          <Card padding={5} elevation="low">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-line">
              <div>
                <p className="text-[10px] font-bold uppercase tracking-wider text-accent">
                  Concurrency Runtime
                </p>
                <h3 className="text-sm font-bold text-fg mt-0.5">
                  Worker Threads & Allocation
                </h3>
              </div>
              <span className="text-xs font-semibold text-fg-muted font-mono">
                {onlineWorkersCount}/{totalWorkersCount} Threads Active
              </span>
            </div>

            {/* Worker thread status badges */}
            <div className="mt-4 flex flex-wrap gap-2">
              {workerEntries.map(([name, active]) => (
                <div
                  key={name}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-mono font-medium transition ${
                    active
                      ? "border-success/30 bg-success-subtle text-success-fg"
                      : "border-line bg-raised text-fg-muted"
                  }`}
                >
                  {active ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-fg-subtle shrink-0" />
                  )}
                  <span>{name}</span>
                </div>
              ))}
            </div>

            {/* Queue Breakdown by Status */}
            <div className="mt-5 border-t border-line pt-4">
              <p className="text-[10px] font-bold uppercase tracking-wider text-fg-muted mb-2.5">
                Queue Breakdown by Status
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.queue.statuses).map(([status, count]) => (
                  <div
                    key={status}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-line bg-raised text-xs font-medium text-fg-muted"
                  >
                    <span>{status}:</span>
                    <span className="font-bold font-mono text-fg">
                      {count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          {/* Integrated Update & Version Release Panel */}
          <UpdatePanel currentVersion={config?.version || data.version} />
        </div>
      )}
    </div>
  );
};
