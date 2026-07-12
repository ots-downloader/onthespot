import React, { useState } from "react";
import { ExternalLink, Loader2, Search } from "lucide-react";
import { SearchResultItem } from "../types";
import { fetchSpotifyCatalog } from "../lib/api";

interface BrowseSpotifyProps {
  onDownload: (url: string) => Promise<boolean>;
}

type CatalogType = "track" | "album" | "playlist" | "artist";

export const BrowseSpotify: React.FC<BrowseSpotifyProps> = ({ onDownload }) => {
  const [query, setQuery] = useState("");
  const [catalogType, setCatalogType] = useState<CatalogType>("track");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [queuedIds, setQueuedIds] = useState<Set<string>>(new Set());

  const handleSearch = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    try {
      setResults(await fetchSpotifyCatalog(query.trim(), [catalogType]));
    } finally {
      setLoading(false);
    }
  };

  const queueItem = async (item: SearchResultItem) => {
    const url = item.item_url || item.url;
    if (!url) return;
    if (await onDownload(url)) {
      setQueuedIds((current) => new Set(current).add(item.id));
    }
  };

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">
      <section className="ots-hero p-6 md:p-8">
        <p className="ots-kicker">Spotify catalogue</p>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-white md:text-4xl">Browse and queue music</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#b3b3b3]">
          Search by album, artist, playlist, or track, then download the result directly from Spotify’s public catalogue.
        </p>

        <div className="mt-4 flex flex-col gap-3 sm:flex-row">
          <div className="ots-input flex h-11 min-w-0 flex-1 items-center px-4">
            <Search className="h-4 w-4 shrink-0 text-[#8f8f8f]" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={`Search Spotify ${catalogType}s...`}
              className="w-full bg-transparent px-3 py-0 text-sm text-white outline-none placeholder:text-[#8f8f8f]"
            />
          </div>
          <button
            type="button"
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="ots-button ots-button-primary ots-button-md px-6 text-sm"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            Browse
          </button>
        </div>

        <div className="ots-browse-tabs mt-3 sm:w-fit">
          {([
            ["album", "Albums"],
            ["artist", "Artists"],
            ["playlist", "Playlists"],
            ["track", "Tracks"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setCatalogType(value)}
              className={`ots-browse-tab ${catalogType === value ? "ots-browse-tab-active" : ""}`}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="ots-panel p-5 shadow-xl shadow-black/10 md:p-7">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#1ed760]">Results</p>
            <h2 className="mt-1 text-2xl font-bold tracking-tight text-white">{query ? `Spotify ${catalogType}s` : "Start browsing"}</h2>
          </div>
          {results.length > 0 && <span className="text-xs font-semibold text-[#b3b3b3]">{results.length} results</span>}
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-14 text-sm text-[#b3b3b3]"><Loader2 className="mr-3 h-5 w-5 animate-spin text-[#1ed760]" /> Loading Spotify catalogue...</div>
        ) : results.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#3b3b3b] px-5 py-14 text-center text-sm text-[#8f8f8f]">Search above to browse Spotify results.</div>
        ) : (
          <div className="divide-y divide-[#2e2e2e]">
            {results.map((item) => {
              const queued = queuedIds.has(item.id);
              return (
                <div key={`${item.item_type}-${item.id}`} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0 sm:gap-4">
                  <img src={item.thumbnail || "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=120&auto=format&fit=crop&q=80"} alt="" className="h-12 w-12 shrink-0 rounded-md object-cover" referrerPolicy="no-referrer" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold text-white">{item.name}</p>
                    <p className="mt-1 truncate text-xs text-[#b3b3b3]">{item.artist || "Spotify"}</p>
                  </div>
                  <span className="hidden text-xs capitalize text-[#8f8f8f] sm:block">{item.item_type}</span>
                  <a href={item.item_url || item.url} target="_blank" rel="noopener noreferrer" className="ots-icon-button hidden sm:flex" title="Open in Spotify">
                    <ExternalLink className="h-4 w-4" />
                  </a>
                  <button type="button" onClick={() => queueItem(item)} disabled={queued} className={`ots-button h-10 shrink-0 px-4 text-xs ${queued ? "ots-queued-state" : "ots-button-primary"}`}>
                    {queued ? "Queued" : "Download"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};
