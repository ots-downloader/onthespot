import {
  Check,
  Copy,
  Download,
  Search,
  Terminal,
  Trash2,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import { LogEntry } from "../types";
import { PageHeader } from "./PageHeader";
import {
  Badge,
  Button,
  Card,
  IconButton,
  SegmentedControl,
  SegmentedControlItem,
  TextInput,
} from "./ui";

interface LogViewerProps {
  logs: LogEntry[];
  onRefresh: () => void;
  onClear: () => void;
}

export const LogViewer: React.FC<LogViewerProps> = ({
  logs,
  onClear,
}) => {
  const [levelFilter, setLevelFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");
  const [copied, setCopied] = useState(false);
  const logContainerRef = useRef<HTMLDivElement>(null);

  const filteredLogs = logs.filter((l) => {
    if (levelFilter !== "ALL" && l.level !== levelFilter) return false;
    if (search.trim() && !l.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  useEffect(() => {
    if (logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [filteredLogs]);

  const handleExportLogs = () => {
    const text = filteredLogs
      .map((l) => `[${l.timestamp}] [${l.level}] ${l.service ? `(${l.service}) ` : ""}${l.message}`)
      .join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `onthespot-logs-${new Date().toISOString().slice(0, 10)}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCopyLogs = () => {
    const text = filteredLogs
      .map((l) => `[${l.timestamp}] [${l.level}] ${l.service ? `(${l.service}) ` : ""}${l.message}`)
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getLevelBadge = (level: string) => {
    switch (level) {
      case "ERROR":
        return <Badge variant="error" label="Error" />;
      case "WARNING":
        return <Badge variant="warning" label="Warn" />;
      default:
        return <Badge variant="neutral" label="Info" />;
    }
  };

  return (
    <div className="space-y-5" id="logs-view">
      {/* Reusable PageHeader for Logs */}
      <PageHeader
        id="logs-page-header"
        icon={<Terminal className="w-5 h-5" />}
        title="Live Event Logs & Telemetry"
        badge={{
          label: `${filteredLogs.length} Events`,
          variant: "neutral",
        }}
        description="Real-time output from scraper engines, ffmpeg transcoder threads, and network sessions"
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="secondary"
              size="sm"
              label={copied ? "Copied!" : "Copy All"}
              icon={
                copied ? (
                  <Check className="w-3.5 h-3.5 text-success-fg" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )
              }
              onClick={handleCopyLogs}
            />

            <Button
              variant="secondary"
              size="sm"
              label="Export .log"
              icon={<Download className="w-3.5 h-3.5" />}
              onClick={handleExportLogs}
            />

            <IconButton
              label="Clear all logs"
              icon={<Trash2 className="w-3.5 h-3.5 text-danger-fg" />}
              variant="ghost"
              size="sm"
              onClick={onClear}
            />
          </div>
        }
        bottomContent={
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div className="w-full md:w-72">
              <TextInput
                label="Search log messages"
                isLabelHidden={true}
                placeholder="Filter logs by keyword..."
                value={search}
                onChange={(val) => setSearch(val)}
                hasClear={true}
                size="sm"
                startIcon={<Search className="w-3.5 h-3.5 text-fg-subtle" />}
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-fg-muted">Level:</span>
              <SegmentedControl
                label="Log level filter"
                value={levelFilter}
                onChange={(lvl) => setLevelFilter(lvl)}
              >
                <SegmentedControlItem value="ALL" label="All Levels" />
                <SegmentedControlItem value="INFO" label="Info" />
                <SegmentedControlItem value="WARNING" label="Warn" />
                <SegmentedControlItem value="ERROR" label="Error" />
              </SegmentedControl>
            </div>
          </div>
        }
      />

      {/* Terminal View Container */}
      <Card padding={0} elevation="low" id="terminal-card">
        <div
          ref={logContainerRef}
          data-theme="dark"
          className="h-[520px] overflow-y-auto p-4 space-y-1.5 bg-console text-console-fg font-mono text-xs rounded-xl"
        >
          {filteredLogs.length === 0 ? (
            <div className="h-full flex items-center justify-center text-console-muted text-xs">
              No log messages match the current filter criteria.
            </div>
          ) : (
            filteredLogs.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-2.5 hover:bg-console-line/60 p-1 rounded transition"
              >
                <span className="text-console-muted text-[11px] shrink-0 select-none">
                  {log.timestamp}
                </span>

                <div className="shrink-0">{getLevelBadge(log.level)}</div>

                {log.service && (
                  <span className="text-console-muted font-semibold shrink-0">
                    [{log.service}]
                  </span>
                )}

                <span
                  className={`break-all leading-relaxed ${
                    log.level === "ERROR"
                      ? "text-danger-fg"
                      : log.level === "WARNING"
                      ? "text-warning-fg"
                      : "text-console-fg"
                  }`}
                >
                  {log.message}
                </span>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
};
