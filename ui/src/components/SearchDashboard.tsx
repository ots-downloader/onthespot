import React, { useEffect, useMemo, useState } from "react";
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
  Music2,
  Waves,
  Cloud,
  CirclePlay,
  Heart,
  Headphones,
} from "lucide-react";
import { AccountItem, SearchResultItem, OTSConfig } from "../types";
import {
  getAvailableCatalogServices,
  getCatalogServiceLabel,
} from "../lib/catalogServices";

interface SearchDashboardProps {
  onSearch: (
    q: string,
    filters: Record<string, boolean>,
    services?: string[],
  ) => Promise<SearchResultItem[]>;
  onDownload: (q: string, filters?: Record<string, boolean>) => Promise<boolean>;
  config: OTSConfig | null;
  accounts: AccountItem[];
  query: string;
  onQueryChange: (query: string) => void;
}

export const SearchDashboard: React.FC<SearchDashboardProps> = ({
  onSearch,
  onDownload,
  config,
  accounts,
  query,
  onQueryChange,
}) => {
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
  const availableServices = useMemo(
    () => getAvailableCatalogServices(accounts),
    [accounts],
  );
  const [selectedServiceOverride, setSelectedServiceOverride] = useState<string[] | null>(null);
  const preferredServices = useMemo(
    () => availableServices.includes("spotify")
      ? ["spotify"]
      : availableServices.slice(0, 1),
    [availableServices],
  );
  const selectedServices = useMemo(
    () => (selectedServiceOverride ?? preferredServices)
      .filter((service) => availableServices.includes(service)),
    [availableServices, preferredServices, selectedServiceOverride],
  );
  const resultServiceCounts = useMemo(() => {
    const counts = new Map<string, number>();
    results.forEach((item) => {
      counts.set(item.item_service, (counts.get(item.item_service) ?? 0) + 1);
    });
    return Array.from(counts.entries()).sort(([left], [right]) =>
      getCatalogServiceLabel(left).localeCompare(getCatalogServiceLabel(right)),
    );
  }, [results]);

  useEffect(() => {
    // Account workers briefly disappear while the backend reconnects. Keep the
    // user's choices during that transient state, while deriving an empty
    // effective selection above so Search remains safely disabled.
    if (availableServices.length === 0) return;
    setSelectedServiceOverride((current) =>
      current === null
        ? null
        : current.filter((service) => availableServices.includes(service)),
    );
  }, [availableServices]);

  const handleSearchSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    try {
      if (/^https?:\/\//i.test(query.trim())) {
        await onDownload(query.trim(), filters);
        return;
      }
      if (selectedServices.length === 0) return;
      const data = await onSearch(query.trim(), filters, selectedServices);
      setResults(data);
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
    setResults([]);
  };

  const toggleService = (service: string) => {
    setResults([]);
    setSelectedServiceOverride((current) => {
      const selected = current ?? preferredServices;
      return selected.includes(service)
        ? selected.filter((value) => value !== service)
        : [...selected, service];
    });
  };

  const toggleAllServices = () => {
    setResults([]);
    setSelectedServiceOverride(
      selectedServices.length === availableServices.length
        ? preferredServices
        : availableServices,
    );
  };


  const getServiceBadge = (service: string) => {
    const base = "inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-semibold";
    switch (service.toLowerCase()) {
      case "spotify": return <span title="Downloads from Spotify" className={`${base} border-green-500/30 bg-green-500/10 text-green-300`}><Music2 className="h-3 w-3" />Spotify</span>;
      case "tidal": return <span title="Downloads from Tidal" className={`${base} border-cyan-500/30 bg-cyan-500/10 text-cyan-300`}><Waves className="h-3 w-3" />Tidal</span>;
      case "apple_music":
      case "applemusic": return <span title="Downloads from Apple Music" className={`${base} border-rose-500/30 bg-rose-500/10 text-rose-300`}><Music2 className="h-3 w-3" />Apple Music</span>;
      case "soundcloud": return <span title="Downloads from SoundCloud" className={`${base} border-orange-500/30 bg-orange-500/10 text-orange-300`}><Cloud className="h-3 w-3" />SoundCloud</span>;
      case "bandcamp": return <span title="Downloads from Bandcamp" className={`${base} border-sky-500/30 bg-sky-500/10 text-sky-300`}><Disc className="h-3 w-3" />Bandcamp</span>;
      case "youtube_music":
      case "youtube": return <span title="Downloads from YouTube Music" className={`${base} border-red-500/30 bg-red-500/10 text-red-300`}><CirclePlay className="h-3 w-3" />YouTube Music</span>;
      case "crunchyroll": return <span title="Downloads from Crunchyroll" className={`${base} border-orange-500/30 bg-orange-500/10 text-orange-300`}><Tv className="h-3 w-3" />Crunchyroll</span>;
      case "deezer": return <span title="Downloads from Deezer" className={`${base} border-violet-500/30 bg-violet-500/10 text-violet-300`}><Heart className="h-3 w-3" />Deezer</span>;
      case "qobuz": return <span title="Downloads from Qobuz" className={`${base} border-sky-500/30 bg-sky-500/10 text-sky-300`}><Headphones className="h-3 w-3" />Qobuz</span>;
      default: {
        const label = getCatalogServiceLabel(service);
        return <span title={`Downloads from ${label}`} className={`${base} border-[#4a4a4a] bg-[#282828] text-[#b3b3b3]`}><Download className="h-3 w-3" />{label}</span>;
      }
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
                  onChange={(e) => onQueryChange(e.target.value)}
                  placeholder="What do you want to download?"
                  className="w-full bg-transparent px-3 py-0 text-sm text-white outline-none placeholder:text-[#6f6f6f]"
                />
              </div>
              <button
                type="submit"
                disabled={loading || (!/^https?:\/\//i.test(query.trim()) && selectedServices.length === 0)}
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

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="mr-1 flex items-center gap-1.5 text-xs font-semibold text-[#8f8f8f]"><Headphones className="h-3.5 w-3.5" /> Search services</span>
              {availableServices.length > 0 ? (
                <div className="ots-browse-tabs max-w-full">
                  <button
                    type="button"
                    aria-pressed={selectedServices.length === availableServices.length}
                    onClick={toggleAllServices}
                    className={`ots-browse-tab ${selectedServices.length === availableServices.length ? "ots-browse-tab-active" : ""}`}
                  >
                    All services
                  </button>
                  {availableServices.map((service) => (
                    <button
                      key={service}
                      type="button"
                      aria-pressed={selectedServices.includes(service)}
                      onClick={() => toggleService(service)}
                      className={`ots-browse-tab ${selectedServices.includes(service) ? "ots-browse-tab-active" : ""}`}
                    >
                      {getCatalogServiceLabel(service)}
                    </button>
                  ))}
                </div>
              ) : (
                <span className="text-xs text-[var(--ots-warning)]">Add or reconnect a searchable account first.</span>
              )}
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
          {results.length > 0 && (
            <div className="flex flex-wrap items-center justify-end gap-1.5 text-xs font-semibold text-[#b3b3b3]">
              <span>{results.length} items</span>
              {resultServiceCounts.map(([service, count]) => (
                <span key={service} className="rounded border border-[var(--ots-border)] bg-[var(--ots-field)] px-2 py-1">
                  {getCatalogServiceLabel(service)} {count}
                </span>
              ))}
            </div>
          )}
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
                      {getTypeIcon(item.item_type)} <span className="capitalize">{item.item_type}</span><span>•</span>{getServiceBadge(item.item_service)}
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
