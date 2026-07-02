import React, { useState } from 'react';
import { Search, Download, ExternalLink, Music2, Disc, Radio, Tv, Film, BookOpen, Mic, Filter, Sparkles, Check, Loader2, ArrowRight } from 'lucide-react';
import { SearchResultItem, OTSConfig } from '../types';

interface SearchDashboardProps {
  onSearch: (q: string, filters: Record<string, boolean>) => Promise<SearchResultItem[]>;
  onDownload: (item: SearchResultItem) => void;
  config: OTSConfig | null;
}

export const SearchDashboard: React.FC<SearchDashboardProps> = ({
  onSearch,
  onDownload,
  config
}) => {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [enqueuedIds, setEnqueuedIds] = useState<Set<string>>(new Set());

  // Filters matching otsconfig.py
  const [filters, setFilters] = useState<Record<string, boolean>>({
    tracks: config?.enable_search_tracks ?? true,
    albums: config?.enable_search_albums ?? true,
    playlists: config?.enable_search_playlists ?? true,
    artists: config?.enable_search_artists ?? true,
    podcasts: config?.enable_search_podcasts ?? true,
    episodes: config?.enable_search_episodes ?? true,
    audiobooks: config?.enable_search_audiobooks ?? true,
    movies: true,
    shows: true
  });

  const [prefix, setPrefix] = useState<string>(config?.search_prefix || "the");

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!query.trim()) return;

    setLoading(true);
    try {
      const formattedQ = query.startsWith('http') ? query : `${prefix !== 'none' ? prefix + ' ' : ''}${query}`;
      const data = await onSearch(formattedQ, filters);
      setResults(data);
      setQuery("")
    } catch (err) {
      console.error("Search error", err);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickUrlClick = (url: string) => {
    setQuery(url);
  };

  const toggleFilter = (key: string) => {
    setFilters(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const triggerDownload = (item: SearchResultItem) => {
    onDownload(item);
    setEnqueuedIds(prev => new Set(prev).add(item.id));
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

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'album': return <Disc className="w-3.5 h-3.5 text-zinc-400" />;
      case 'playlist': return <Music2 className="w-3.5 h-3.5 text-zinc-400" />;
      case 'podcast':
      case 'episode': return <Mic className="w-3.5 h-3.5 text-zinc-400" />;
      case 'movie': return <Film className="w-3.5 h-3.5 text-zinc-400" />;
      case 'show': return <Tv className="w-3.5 h-3.5 text-zinc-400" />;
      default: return <Radio className="w-3.5 h-3.5 text-zinc-400" />;
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-4 lg:p-8 flex flex-col gap-8 animate-[fadeIn_0.3s_ease-out]">

      {/* Hero Header & Search Form */}
      <div className="bg-gradient-to-b from-zinc-900 to-[#18181B] rounded-2xl p-6 lg:p-10 border border-zinc-800 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 right-0 -mt-12 -mr-12 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute bottom-0 left-0 -mb-12 -ml-12 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl">

          <h2 className="text-2xl lg:text-4xl font-bold tracking-tight text-white font-sans mb-3">
            Paste Media URL
          </h2>
          <p className="text-zinc-400 text-sm mb-6 leading-relaxed">
            Enter a direct URL from Spotify, Tidal, Apple Music, SoundCloud, Bandcamp, or YouTube. The parser converts to your preferred format ({config?.track_file_format?.toUpperCase() || 'FLAC'}).
          </p>

          {/* Form */}
          <form onSubmit={handleSearchSubmit} className="flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row gap-2.5">

              {/* Search Prefix Selector */}
              <div className="sm:w-32 bg-zinc-950 border border-zinc-800 rounded-xl flex items-center px-3 focus-within:border-emerald-500 shrink-0">
                <span className="text-[10px] text-zinc-500 font-mono mr-1">Prefix:</span>
                <select
                  value={prefix}
                  onChange={(e) => setPrefix(e.target.value)}
                  className="bg-transparent text-xs text-zinc-200 font-mono outline-none w-full cursor-pointer py-3.5"
                >
                  <option value="the" className="bg-zinc-900">the</option>
                  <option value="a" className="bg-zinc-900">a</option>
                  <option value="an" className="bg-zinc-900">an</option>
                  <option value="none" className="bg-zinc-900">none</option>
                </select>
              </div>

              {/* Main Input */}
              <div className="flex-1 relative">
                <Search className="w-5 h-5 text-zinc-400 absolute left-4 top-1/2 -translate-y-1/2 pointer-events-none" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Paste URL (https://open.spotify.com/...) or query 'Daft Punk'"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl pl-12 pr-4 py-3.5 text-sm text-white placeholder-zinc-500 outline-none focus:border-emerald-500 transition-all font-sans shadow-inner"
                />
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold px-6 py-3.5 rounded-xl transition-all shadow-lg shadow-emerald-500/20 flex items-center justify-center gap-2 cursor-pointer shrink-0 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Parsing...</span>
                  </>
                ) : (
                  <>
                    <span>Download URL</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>

            {/* Filter Toggle Pills */}
            <p className="text-zinc-400 text-sm mt-8 leading-relaxed">
              Filter the results to the selected media type with the button below
            </p>
            <div className="flex items-center flex-wrap gap-1.5 pt-2">
              <span className="text-xs text-zinc-500 font-mono mr-2 flex items-center gap-1">
                <Filter className="w-3 h-3" /> Categories:
              </span>
              {Object.keys(filters).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleFilter(key)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-mono capitalize transition-all cursor-pointer border flex items-center gap-1.5 ${filters[key]
                    ? 'bg-zinc-800 text-emerald-400 border-emerald-500/40 font-medium'
                    : 'bg-zinc-950 text-zinc-500 border-zinc-900 hover:text-zinc-300'
                    }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${filters[key] ? 'bg-emerald-400' : 'bg-zinc-700'}`} />
                  {key}
                </button>
              ))}
            </div>
          </form>
        </div>
      </div>

      {/* Results Grid */}
      <div>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-bold text-white font-sans flex items-center gap-2">
            <span>Parsed Search Results</span>
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
              {results.length} available
            </span>
          </h3>
        </div>

        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-zinc-500 font-mono gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
            <p>Contacting OnTheSpot FastAPI endpoint...</p>
          </div>
        ) : results.length === 0 ? (
          <div className="bg-zinc-900/50 border border-zinc-800/80 rounded-2xl p-12 text-center text-zinc-500 font-mono">
            No media found. Try typing a track name or pasting a Spotify/Tidal URL above.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {results.map((item) => {
              const isEnqueued = enqueuedIds.has(item.id);

              return (
                <div
                  key={item.id}
                  className="bg-zinc-900/90 border border-zinc-800/80 hover:border-zinc-700 rounded-xl p-4 flex flex-col justify-between transition-all hover:shadow-xl group relative"
                >
                  <div>
                    {/* Thumbnail + Badges */}
                    <div className="relative aspect-square w-full rounded-lg overflow-hidden bg-zinc-950 mb-3.5 border border-zinc-800 shadow-md">
                      <img
                        src={item.thumbnail || "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300&auto=format&fit=crop&q=80"}
                        alt={item.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                        referrerPolicy="no-referrer"
                      />

                      {/* Top Badges */}
                      <div className="absolute top-2.5 left-2.5 right-2.5 flex items-center justify-between pointer-events-none">
                        {getServiceBadge(item.item_service)}
                        {item.explicit && (
                          <span className="w-5 h-5 rounded bg-rose-600 text-white font-bold text-xs flex items-center justify-center shadow-lg font-mono">
                            {config?.explicit_label || '🅴'}
                          </span>
                        )}
                      </div>

                      {/* Bottom Info Bar */}
                      <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between text-[11px] font-mono bg-black/80 backdrop-blur px-2 py-1 rounded text-zinc-300 border border-white/10">
                        <span className="flex items-center gap-1 capitalize">
                          {getTypeIcon(item.item_type)}
                          {item.item_type}
                        </span>
                      </div>
                    </div>

                    {/* Metadata */}
                    <div className="mb-4">
                      <h4 className="font-bold text-white text-sm font-sans line-clamp-1 group-hover:text-emerald-400 transition-colors">
                        {item.name}
                      </h4>
                      <p className="text-xs text-zinc-400 font-sans line-clamp-1 mt-0.5">
                        {item.artist}
                      </p>

                      <div className="flex items-center gap-2 mt-2 text-[11px] font-mono text-zinc-500">
                        {item.album && <span className="truncate max-w-[120px]">💽 {item.album}</span>}
                        {item.release_year && <span>• [{item.release_year}]</span>}
                        {item.bitrate && <span className="text-cyan-400 bg-cyan-500/10 px-1.5 py-0.5 rounded ml-auto">{item.bitrate}</span>}
                      </div>
                    </div>
                  </div>

                  {/* Actions Button */}
                  <div className="flex items-center gap-2 pt-3 border-t border-zinc-800">
                    <button
                      onClick={() => triggerDownload(item)}
                      disabled={true}
                      className={`flex-1 font-bold py-2.5 px-3 rounded-lg text-xs transition-all flex items-center justify-center gap-1.5 cursor-pointer shadow-md ${isEnqueued
                        ? 'bg-zinc-800 text-emerald-400 border border-emerald-500/30 cursor-default'
                        : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20'
                        }`}
                    >
                      {isEnqueued ? (
                        <>
                          <Check className="w-4 h-4" />
                          <span>In Queue</span>
                        </>
                      ) : (
                        <>
                          <Download className="w-4 h-4" />
                          <span>Queue Download</span>
                        </>
                      )}
                    </button>

                    <a
                      href={item.item_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="p-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors border border-zinc-700/50"
                      title="Stream on source platform"
                    >
                      <ExternalLink className="w-4 h-4" />
                    </a>
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
