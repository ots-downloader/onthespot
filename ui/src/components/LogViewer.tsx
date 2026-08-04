import React, { useRef, useState } from 'react';
import { Terminal, RefreshCw, Search, Trash2, Download } from 'lucide-react';
import { LogEntry } from '../types';
import { getTargetBackendUrl } from '../lib/api';

interface LogViewerProps {
  logs: LogEntry[];
  onRefresh: () => void;
  onClear: () => void;
}

type LogLevelFilter = 'ALL' | 'INFO' | 'WARNING' | 'ERROR';

export const LogViewer: React.FC<LogViewerProps> = ({
  logs,
  onRefresh,
  onClear
}) => {
  const [levelFilter, setLevelFilter] = useState<LogLevelFilter>('ALL');
  const [search, setSearch] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  const filteredLogs = logs.filter(l => {
    if (levelFilter !== 'ALL' && l.level !== levelFilter) return false;
    if (search.trim() && !l.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const handleDownloadFile = () => {
    const url = `${getTargetBackendUrl()}/logs/download`;
    window.open(url, '_blank');
  };

  const getLevelBadge = (lvl: string) => {
    const baseClass = "ots-log-badge text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider";
    switch (lvl) {
      case 'ERROR': 
        return <span className={`${baseClass} ots-log-badge-error`}>Error</span>;
      case 'WARNING': 
        return <span className={`${baseClass} ots-log-badge-warning`}>Warn</span>;
      default: 
        return <span className={`${baseClass} ots-log-badge-info`}>Info</span>;
    }
  };

  const iconBtnClass = "ots-icon-button";

  return (
    <div className="spotify-fade-up ots-page flex h-[calc(100vh-170px)] flex-col font-sans">
      {/* Material Card Surface */}
      <div className="ots-panel flex h-full flex-col overflow-hidden shadow-xl shadow-black/10">
        
        {/* App Bar / Toolbar */}
        <div className="px-4 py-4 md:px-6 border-b border-gray-100 dark:border-neutral-800/60 flex flex-col md:flex-row md:items-center justify-between gap-4 shrink-0">
          
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-50 dark:bg-blue-500/10 rounded-full">
              <Terminal className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-lg font-medium text-gray-900 dark:text-neutral-100 tracking-tight">
              Server Logs
            </h2>
          </div>

          {/* Actions & Search */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="ots-input relative flex w-full items-center px-4 md:w-64">
              <Search className="w-4 h-4 text-gray-400 shrink-0" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search logs..."
                className="bg-transparent text-sm text-gray-900 dark:text-neutral-100 placeholder-gray-500 outline-none w-full ml-2"
              />
            </div>

            <div className="flex items-center gap-1">
              <button onClick={handleDownloadFile} className={iconBtnClass} title="Download Logs">
                <Download className="w-5 h-5" />
              </button>
              <button onClick={onRefresh} className={iconBtnClass} title="Refresh Logs">
                <RefreshCw className="w-5 h-5" />
              </button>
              <button onClick={onClear} className={iconBtnClass} title="Clear Buffer">
                <Trash2 className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>

        {/* Filter Chips */}
        <div className="px-4 py-3 md:px-6 flex items-center gap-2 border-b border-gray-100 dark:border-neutral-800/60 overflow-x-auto no-scrollbar shrink-0 bg-gray-50/50 dark:bg-[#141414]">
          {(['ALL', 'INFO', 'WARNING', 'ERROR'] as LogLevelFilter[]).map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl)}
              className={`ots-segment whitespace-nowrap ${
                levelFilter === lvl
                  ? 'ots-segment-active'
                  : ''
              }`}
            >
              {lvl}
            </button>
          ))}
          <span className="text-sm text-gray-500 dark:text-neutral-500 ml-auto hidden sm:block">
            {filteredLogs.length} of {logs.length} entries
          </span>
        </div>

        {/* Log Lines Area */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto p-4 md:p-6 bg-gray-50/30 dark:bg-[#0f0f0f] font-mono text-sm selection:bg-blue-200 dark:selection:bg-blue-900/50"
        >
          {filteredLogs.length === 0 ? (
            <div className="h-full flex items-center justify-center text-gray-500 dark:text-neutral-500 font-sans">
              No logs match filter "{levelFilter}" {search && `with term "${search}"`}.
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              {[...filteredLogs].map((entry) => (
                <div 
                  key={entry.id} 
                  className="flex items-start gap-3 py-1.5 px-2 rounded-md hover:bg-black/5 dark:hover:bg-white/5 transition-colors group break-words"
                >
                  <span className="text-gray-400 dark:text-neutral-600 select-none shrink-0 text-xs mt-0.5 w-[72px]">
                    {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '12:00:00'}
                  </span>
                  <span className="shrink-0 mt-[1px]">
                    {getLevelBadge(entry.level)}
                  </span>
                  <span className="flex-1 text-gray-700 dark:text-neutral-300 leading-relaxed">
                    {entry.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </div>
  );
};
