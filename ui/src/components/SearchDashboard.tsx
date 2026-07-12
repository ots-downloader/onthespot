import React, { useState } from "react";
import {
  Search,
  Download,
  ExternalLink,
  Music,
  Disc,
  Tv,
  Film,
  Mic,
  Filter,
  Check,
  Loader2,
  Sparkles,
} from "lucide-react";
import { SearchResultItem, OTSConfig } from "../types";

interface SearchDashboardProps {
  onSearch: (q: string, filters: Record<string, boolean>) => Promise<boolean | SearchResultItem[]>;
  onDownload: (q: string, filters?: Record<string, boolean>) => Promise<boolean>;
  config: OTSConfig | null;
}

export const SearchDashboard: React.FC<SearchDashboardProps> = ({
  onSearch,
  onDownload,
  config,
}) => {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [enqueuedIds, setEnqueuedIds] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<Record<string, boolean>>({
    tracks: config?.enable_search_tracks ?? true,
    albums: config?.enable_search_albums ?? true,
    playlists: config?.enable_search_playlists ?? true,
    artists: config?.enable_search_artists ?? true,
    podcasts: config?.enable_search_podcasts ?? true,
    movies: true,
  });
  const [prefix] = useState<string>(config?.search_prefix || "the");

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    try {
      const formattedQ = query.startsWith("http")
        ? query
        : `${prefix !== "none" ? prefix + " " : ""}${query}`;
      const data = await onSearch(formattedQ, filters);
      setResults(Array.isArray(data) ? data : []);
      setQuery("");
    } catch (err) {
      console.error("Search error", err);
    } finally {
      setLoading(false);
    }
  };

  const triggerDownload = (item: SearchResultItem) => {
    onDownload(item.item_url || item.url);
    setEnqueuedIds((prev) => new Set(prev).add(item.id));
  };

  const toggleFilter = (key: string) => {
    setFilters((prev) => ({ ...prev, [key]: !prev[key] }));
  };


  const getServiceText = (service: string) => {
    switch (service.toLowerCase()) {
      case "spotify": return "Spotify";
      case "tidal": return "Tidal";
      case "apple_music":
      case "applemusic": return "Apple Music";
      case "soundcloud": return "SoundCloud";
      case "youtube_music":
      case "youtube": return "YouTube Music";
      default: return "Generic";
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "album": return <Disc className="h-3.5 w-3.5" />;
      case "playlist": return <Music className="h-3.5 w-3.5" />;
      case "podcast":
      case "episode": return <Mic className="h-3.5 w-3.5" />;
      case "movie": return <Film className="h-3.5 w-3.5" />;
      case "show": return <Tv className="h-3.5 w-3.5" />;
      default: return <Music className="h-3.5 w-3.5" />;
    }
  };

  return (
    <div className="spotify-scrollbar spotify-fade-up ots-page flex flex-col gap-8 overflow-x-hidden">
      <section className="ots-hero relative overflow-hidden px-6 py-8 md:px-10 md:py-12">
        <div className="relative max-w-3xl">
          <div className="mb-5 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.2em] text-[#1ed760]">
            <Sparkles className="h-4 w-4" /> Your music, your library
          </div>
          <h1 className="max-w-2xl text-3xl font-black tracking-tight text-white md:text-5xl">
            Find something to download
          </h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-[#b3b3b3] md:text-base">
            Search across your supported services or paste a direct link. Everything you choose lands in the download queue.
          </p>

          <form onSubmit={handleSearchSubmit} className="mt-6">
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="ots-input relative flex h-12 min-w-0 flex-1 items-center px-4">
                <Search className="h-5 w-5 shrink-0 text-[#6f6f6f]" />
                <input
                  id="global-search"
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="What do you want to download?"
                  className="w-full bg-transparent px-3 py-0 text-sm text-white outline-none placeholder:text-[#6f6f6f]"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="ots-button ots-button-primary ots-button-lg shrink-0 px-7 text-sm"
              >
                {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Search className="h-5 w-5" />}
                {loading ? "Searching" : "Search"}
              </button>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2">
              <span className="mr-1 flex items-center gap-1.5 text-xs font-semibold text-[#8f8f8f]"><Filter className="h-3.5 w-3.5" /> Search in</span>
              <div className="ots-browse-tabs max-w-full">
                {Object.keys(filters).map((key) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={filters[key]}
                    onClick={() => toggleFilter(key)}
                    className={`ots-browse-tab ${filters[key] ? "ots-browse-tab-active" : ""}`}
                  >
                    {key.charAt(0).toUpperCase() + key.slice(1)}
                  </button>
                ))}
              </div>
            </div>
          </form>

        </div>
      </section>

      <section>
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#1ed760]">Discover</p>
            <h2 className="mt-1 text-2xl font-bold tracking-tight text-white">Search results</h2>
          </div>
          {results.length > 0 && <span className="text-xs font-semibold text-[#b3b3b3]">{results.length} items</span>}
        </div>

        {loading ? (
          <div className="ots-panel flex flex-col items-center justify-center py-20 text-[#b3b3b3]">
            <Loader2 className="h-8 w-8 animate-spin text-[#1ed760]" />
            <p className="mt-4 text-sm font-semibold">Fetching media data...</p>
          </div>
        ) : results.length === 0 ? (
          <div className="ots-panel border-dashed px-6 py-16 text-center">
            <Music className="mx-auto h-10 w-10 text-[#535353]" />
            <p className="mt-4 text-sm font-semibold text-[#b3b3b3]">Search for an artist, track, album, or playlist to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
            {results.map((item) => {
              const isEnqueued = enqueuedIds.has(item.id);
              return (
                  <article key={item.id} className="ots-card group p-3 transition-colors hover:bg-[#242424]">
                  <div className="relative aspect-square overflow-hidden rounded-md bg-[#282828] shadow-lg">
                    <img src={item.thumbnail || "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300&auto=format&fit=crop&q=80"} alt={item.name} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105" referrerPolicy="no-referrer" />
                    {item.explicit && <span className="absolute bottom-2 left-2 rounded bg-black/80 px-1.5 py-0.5 text-[10px] font-bold text-white">E</span>}
                    <button onClick={() => triggerDownload(item)} disabled={isEnqueued} className={`absolute bottom-2 right-2 flex h-11 w-11 items-center justify-center rounded-full text-white ots-on-green-text shadow-xl transition-all ${isEnqueued ? "bg-[#147f3e]" : "bg-[#147f3e] opacity-0 translate-y-2 group-hover:translate-y-0 group-hover:opacity-100 hover:scale-105 hover:bg-[#158642]"}`} title={isEnqueued ? "Queued" : "Download"}>
                      {isEnqueued ? <Check className="h-5 w-5" /> : <Download className="h-5 w-5" />}
                    </button>
                  </div>

                  <div className="min-w-0 pt-3">
                    <h3 className="truncate text-sm font-bold text-white" title={item.name}>{item.name}</h3>
                    <p className="mt-1 truncate text-xs text-[#b3b3b3]" title={`${item.artist}${item.album ? ` • ${item.album}` : ""}`}>{item.artist}{item.album && ` • ${item.album}`}</p>
                    <div className="mt-3 flex items-center gap-1.5 truncate text-[10px] font-semibold text-[#8f8f8f]">
                      {getTypeIcon(item.item_type)} <span className="capitalize">{item.item_type}</span><span>•</span><span>{getServiceText(item.item_service)}</span>
                    </div>
                    <div className="mt-3 flex items-center gap-2 border-t border-[#2e2e2e] pt-3">
                      <button onClick={() => triggerDownload(item)} disabled={isEnqueued} className={`ots-button ots-button-sm flex-1 ${isEnqueued ? "ots-queued-state" : "ots-button-primary"}`}>
                        {isEnqueued ? "Queued" : "Download"}
                      </button>
                      <a href={item.item_url} target="_blank" rel="noopener noreferrer" className="ots-icon-button" title="Open source">
                        <ExternalLink className="h-4 w-4" />
                      </a>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
