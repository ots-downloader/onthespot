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
  ArrowRight,
} from "lucide-react";
import { SearchResultItem, OTSConfig } from "../types";

interface SearchDashboardProps {
  onSearch: (q: string, filters: Record<string, boolean>) => Promise<boolean>;
  onDownload: (q: string, filters: Record<string, boolean>) => Promise<boolean>;
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

  const [prefix, setPrefix] = useState<string>(config?.search_prefix || "the");

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    try {
      const formattedQ = query.startsWith("http")
        ? query
        : `${prefix !== "none" ? prefix + " " : ""}${query}`;
      const data = await onSearch(formattedQ, filters);
      setResults(data);
      setQuery("");
    } catch (err) {
      console.error("Search error", err);
    } finally {
      setLoading(false);
    }
  };

  const toggleFilter = (key: string) => {
    setFilters((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const triggerDownload = (item: SearchResultItem) => {
    onDownload(item);
    setEnqueuedIds((prev) => new Set(prev).add(item.id));
  };

  const getServiceText = (service: string) => {
    switch (service.toLowerCase()) {
      case "spotify":
        return "Spotify";
      case "tidal":
        return "Tidal";
      case "apple_music":
      case "applemusic":
        return "Apple Music";
      case "soundcloud":
        return "SoundCloud";
      case "youtube_music":
      case "youtube":
        return "YT Music";
      default:
        return "Generic";
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "album":
        return <Disc className="w-3.5 h-3.5" />;
      case "playlist":
        return <Music className="w-3.5 h-3.5" />;
      case "podcast":
      case "episode":
        return <Mic className="w-3.5 h-3.5" />;
      case "movie":
        return <Film className="w-3.5 h-3.5" />;
      case "show":
        return <Tv className="w-3.5 h-3.5" />;
      default:
        return <Music className="w-3.5 h-3.5" />;
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8 flex flex-col gap-8 font-sans">
      {/* Search Header Container */}
      <div className="bg-white dark:bg-[#1a1a1a] rounded-3xl p-6 md:p-10 border border-gray-200 dark:border-neutral-800/60 shadow-sm">
        <div className="max-w-4xl">
          <h2 className="text-2xl font-medium text-gray-900 dark:text-neutral-100 mb-2">
            Search & Download Media
          </h2>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mb-6">
            Paste a link from supported platforms, or search by keywords. Target
            format: {config?.track_file_format?.toUpperCase() || "FLAC"}.
          </p>

          <form onSubmit={handleSearchSubmit} className="flex flex-col gap-4">
            {/* Search Bar Row */}
            <div className="flex flex-col md:flex-row gap-3">
              <div className="relative flex items-center bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 rounded-full flex-1 focus-within:ring-2 focus-within:ring-blue-500/50 transition-shadow overflow-hidden">
                <Search className="w-5 h-5 text-gray-400 absolute left-4" />
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Paste URL or search keywords..."
                  className="w-full bg-transparent pl-12 pr-4 py-3.5 text-base text-gray-900 dark:text-neutral-100 placeholder-gray-500 outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="bg-blue-600 hover:bg-blue-700 text-white px-8 py-3.5 rounded-full font-medium transition-colors flex items-center justify-center gap-2 shrink-0 disabled:opacity-50"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Parsing...
                  </>
                ) : (
                  <>
                    Search
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </div>

            {/* Filters */}
            <div className="flex items-center flex-wrap gap-2 pt-2">
              <span className="text-xs font-medium text-gray-500 dark:text-neutral-500 flex items-center gap-1 mr-2">
                <Filter className="w-3.5 h-3.5" /> Filters:
              </span>
              {Object.keys(filters).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => toggleFilter(key)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium capitalize transition-colors border ${
                    filters[key]
                      ? "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800/50"
                      : "bg-transparent text-gray-600 border-gray-300 hover:bg-gray-50 dark:text-neutral-400 dark:border-neutral-700 dark:hover:bg-neutral-800"
                  }`}
                >
                  {key}
                </button>
              ))}
            </div>
          </form>
        </div>
      </div>

      {/* Results */}
      <div>
        <div className="flex items-center justify-between mb-4 px-1">
          <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
            Results
          </h3>
          {results.length > 0 && (
            <span className="text-xs font-medium bg-gray-100 text-gray-600 dark:bg-neutral-800 dark:text-neutral-400 px-2.5 py-1 rounded-full">
              {results.length} items
            </span>
          )}
        </div>

        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center text-gray-500 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            <p className="text-sm font-medium">Fetching media data...</p>
          </div>
        ) : results.length === 0 ? (
          <div className="bg-gray-50 dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-12 text-center text-gray-500 dark:text-neutral-400 text-sm">
            Enter a search term or paste a link to see results here.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-5">
            {results.map((item) => {
              const isEnqueued = enqueuedIds.has(item.id);

              return (
                <div
                  key={item.id}
                  className="bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 hover:shadow-md rounded-2xl p-4 flex flex-col transition-all group"
                >
                  {/* Image */}
                  <div className="relative aspect-square w-full rounded-xl overflow-hidden bg-gray-100 dark:bg-neutral-800 mb-3 border border-gray-200/50 dark:border-neutral-700/50">
                    <img
                      src={
                        item.thumbnail ||
                        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=300&auto=format&fit=crop&q=80"
                      }
                      alt={item.name}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      referrerPolicy="no-referrer"
                    />
                    {item.explicit && (
                      <div className="absolute bottom-2 right-2 px-1.5 py-0.5 rounded-md bg-black/70 backdrop-blur-sm text-[10px] font-bold text-white uppercase tracking-wider">
                        E
                      </div>
                    )}
                  </div>

                  {/* Metadata */}
                  <div className="flex-1 flex flex-col">
                    <h4 className="font-medium text-gray-900 dark:text-neutral-100 text-sm md:text-base line-clamp-1 mb-0.5">
                      {item.name}
                    </h4>
                    <p className="text-xs text-gray-500 dark:text-neutral-400 line-clamp-1 mb-2">
                      {item.artist} {item.album && `• ${item.album}`}
                    </p>

                    <div className="flex items-center gap-2 text-[10px] font-medium mt-auto mb-4">
                      <span className="bg-gray-100 text-gray-700 dark:bg-neutral-800 dark:text-neutral-300 px-2 py-0.5 rounded flex items-center gap-1 capitalize">
                        {getTypeIcon(item.item_type)}
                        {item.item_type}
                      </span>
                      <span className="text-gray-400 dark:text-neutral-500">
                        •
                      </span>
                      <span className="text-gray-600 dark:text-neutral-400">
                        {getServiceText(item.item_service)}
                      </span>
                      {item.release_year && (
                        <>
                          <span className="text-gray-400 dark:text-neutral-500">
                            •
                          </span>
                          <span className="text-gray-500 dark:text-neutral-400">
                            {item.release_year}
                          </span>
                        </>
                      )}
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 pt-3 border-t border-gray-100 dark:border-neutral-800/60">
                      <button
                        onClick={() => triggerDownload(item)}
                        disabled={isEnqueued}
                        className={`flex-1 font-medium py-2 px-3 rounded-xl text-sm transition-colors flex items-center justify-center gap-1.5 ${
                          isEnqueued
                            ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400 cursor-default"
                            : "bg-blue-50 text-blue-700 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-300 dark:hover:bg-blue-900/40"
                        }`}
                      >
                        {isEnqueued ? (
                          <>
                            <Check className="w-4 h-4" />
                            Queued
                          </>
                        ) : (
                          <>
                            <Download className="w-4 h-4" />
                            Download
                          </>
                        )}
                      </button>

                      <a
                        href={item.item_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-2.5 rounded-xl bg-gray-50 text-gray-600 hover:bg-gray-100 dark:bg-neutral-800 dark:text-neutral-300 dark:hover:bg-neutral-700 transition-colors"
                        title="Open Source"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
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
