import React, { useEffect, useRef, useState } from 'react';
import { Terminal, RefreshCw, Search, Trash2, ArrowDownCircle, PauseCircle, PlayCircle, ShieldAlert, Info, AlertTriangle, Cpu } from 'lucide-react';
import { LogEntry } from '../types';

interface LogViewerProps {
  logs: LogEntry[];
  onRefresh: () => void;
  onClear: () => void;
}

type LogLevelFilter = 'ALL' | 'INFO' | 'WARNING' | 'ERROR' | 'GUI';

export const LogViewer: React.FC<LogViewerProps> = ({
  logs,
  onRefresh,
  onClear
}) => {
  const [levelFilter, setLevelFilter] = useState<LogLevelFilter>('ALL');
  const [search, setSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-refresh timer
  useEffect(() => {
    const t = setInterval(() => {
      onRefresh();
    }, 5000);
    return () => clearInterval(t);
  }, [onRefresh]);

  // Auto scroll effect
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  const filteredLogs = logs.filter(l => {
    if (levelFilter !== 'ALL' && l.level !== levelFilter) return false;
    if (search.trim() && !l.message.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const getLevelBadge = (lvl: string) => {
    switch (lvl) {
      case 'ERROR': return <span className="text-rose-400 font-bold bg-rose-500/10 px-1.5 py-0.2 rounded border border-rose-500/20">[ERROR]</span>;
      case 'WARNING': return <span className="text-amber-400 font-bold bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/20">[WARN] </span>;
      case 'GUI': return <span className="text-cyan-400 font-bold bg-cyan-500/10 px-1.5 py-0.2 rounded border border-cyan-500/20">[GUI]  </span>;
      default: return <span className="text-emerald-400 font-bold bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">[INFO] </span>;
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-4 lg:p-8 flex flex-col gap-6 animate-[fadeIn_0.3s_ease-out] h-[calc(100vh-140px)]">

      {/* Top Bar */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-xl shrink-0">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white font-sans flex items-center gap-2.5">
            <Terminal className="w-6 h-6 text-emerald-400 animate-pulse" />
            <span>Server Log Viewer</span>
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-zinc-800 text-emerald-400 border border-zinc-700">
              Live Streaming WS
            </span>
          </h2>
          <p className="text-xs text-zinc-400 font-mono mt-1">
            onthespot.log • Continuously reloading from FastAPI uvicorn daemon threads
          </p>
        </div>

        {/* Controls */}
        <div className="flex items-center flex-wrap gap-2.5">
          {/* Search */}
          <div className="relative bg-zinc-950 border border-zinc-800 rounded-xl px-3 py-2 flex items-center gap-2 focus-within:border-emerald-500 w-full sm:w-64">
            <Search className="w-4 h-4 text-zinc-500 shrink-0" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter log lines..."
              className="bg-transparent text-xs text-white placeholder-zinc-600 outline-none w-full font-mono"
            />
          </div>

          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`px-3.5 py-2 rounded-xl text-xs font-mono font-bold transition-all border flex items-center gap-1.5 cursor-pointer ${autoScroll
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
              : 'bg-zinc-800 text-zinc-400 border-zinc-700'
              }`}
          >
            {autoScroll ? <PauseCircle className="w-4 h-4 text-emerald-400" /> : <PlayCircle className="w-4 h-4" />}
            <span>Auto-Scroll {autoScroll ? 'ON' : 'OFF'}</span>
          </button>

          <button
            onClick={onRefresh}
            className="p-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors border border-zinc-700 cursor-pointer"
            title="Manual force reload logs"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          <button
            onClick={onClear}
            className="p-2 rounded-xl bg-zinc-800 hover:bg-rose-600/20 text-zinc-400 hover:text-rose-300 transition-colors border border-zinc-700 cursor-pointer"
            title="Clear UI buffer"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Level Filter Pills */}
      <div className="flex items-center gap-2 overflow-x-auto no-scrollbar shrink-0">
        {(['ALL', 'INFO', 'WARNING', 'ERROR', 'GUI'] as LogLevelFilter[]).map((lvl) => (
          <button
            key={lvl}
            onClick={() => setLevelFilter(lvl)}
            className={`px-3 py-1 rounded-lg text-xs font-mono transition-all cursor-pointer border ${levelFilter === lvl
              ? 'bg-zinc-800 text-white font-bold border-zinc-600'
              : 'bg-zinc-950 text-zinc-500 border-zinc-900 hover:text-zinc-300'
              }`}
          >
            {lvl}
          </button>
        ))}
        <span className="text-xs font-mono text-zinc-500 ml-auto hidden sm:inline">
          Showing {filteredLogs.length} of {logs.length} lines
        </span>
      </div>

      {/* Terminal Output Window */}
      <div
        ref={scrollRef}
        className="flex-1 bg-[#09090B] border border-zinc-800 rounded-2xl p-4 sm:p-6 overflow-y-auto font-mono text-xs shadow-2xl relative select-text"
      >
        {filteredLogs.length === 0 ? (
          <div className="h-full flex items-center justify-center text-zinc-600">
            No logs match filter "{levelFilter}" {search && `with term "${search}"`}.
          </div>
        ) : (
          <div className="flex flex-col gap-1.5 leading-relaxed">
            {/* Reverse because logs come newest first or oldest first */}
            {[...filteredLogs].map((entry) => (
              <div key={entry.id} className="flex items-start gap-2.5 hover:bg-white/5 px-2 py-1 rounded transition-colors break-all group">
                <span className="text-zinc-600 select-none shrink-0 text-[11px]">
                  {entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString() : '12:00:00'}
                </span>
                <span className="shrink-0 select-none">
                  {getLevelBadge(entry.level)}
                </span>
                <span className={`flex-1 ${entry.level === 'ERROR' ? 'text-rose-300 font-semibold' :
                  entry.level === 'WARNING' ? 'text-amber-200' :
                    entry.level === 'GUI' ? 'text-cyan-200' : 'text-zinc-300'
                  }`}>
                  {entry.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  );
};
