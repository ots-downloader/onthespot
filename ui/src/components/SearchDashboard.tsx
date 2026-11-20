import {
  AudioWaveform,
  CheckCircle2,
  Clock,
  Disc3,
  Download,
  ListMusic,
  Music2,
  Radio,
  Search,
  Sparkles,
} from "lucide-react";
import React, { useState } from "react";
import { CATALOG_SERVICES, getServiceInfo } from "../lib/catalogServices";
import { SearchResultItem } from "../types";
import { SectionHeader } from "./SectionHeader";
import {
  Badge,
  Button,
  Card,
  Divider,
  EmptyState,
  SegmentedControl,
  SegmentedControlItem,
  TextInput,
  focusRing,
} from "./ui";

interface SearchDashboardProps {
  onSearch: (query: string, filters: Record<string, boolean>, services: string[]) => Promise<SearchResultItem[]>;
  onQueueItem: (item: SearchResultItem) => Promise<void>;
  isSearching: boolean;
  results: SearchResultItem[];
}

export const SearchDashboard: React.FC<SearchDashboardProps> = ({
  onSearch,
  onQueueItem,
  isSearching,
  results,
}) => {
  const [query, setQuery] = useState("");
  const [selectedType, setSelectedType] = useState<string>("all");
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [queuedIds, setQueuedIds] = useState<Set<string>>(new Set());

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const filterMap: Record<string, boolean> = {};
    if (selectedType !== "all") {
      filterMap[selectedType] = true;
    }
    onSearch(query, filterMap, selectedServices);
  };

  const handleTypeChange = (typeVal: string) => {
    setSelectedType(typeVal);
    const filterMap: Record<string, boolean> = {};
    if (typeVal !== "all") {
      filterMap[typeVal] = true;
    }
    onSearch(query, filterMap, selectedServices);
  };

  const toggleService = (serviceId: string) => {
    const updated = selectedServices.includes(serviceId)
      ? selectedServices.filter((s) => s !== serviceId)
      : [...selectedServices, serviceId];
    setSelectedServices(updated);

    const filterMap: Record<string, boolean> = {};
    if (selectedType !== "all") {
      filterMap[selectedType] = true;
    }
    onSearch(query, filterMap, updated);
  };

  const handleQueueClick = async (item: SearchResultItem) => {
    setQueuedIds((prev) => new Set(prev).add(item.id));
    await onQueueItem(item);
  };

  return (
    <div className="space-y-5" id="search-dashboard">
      {/* Search Header Card */}
      <Card padding={4} elevation="low" id="search-bar-card">
        <form onSubmit={handleSearchSubmit} className="space-y-4">
          <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
            <div className="flex-1">
              <TextInput
                label="Search catalog query or paste URL"
                isLabelHidden={true}
                placeholder="Search tracks, artists, albums, or paste a Spotify, Deezer, Tidal, Apple Music URL..."
                value={query}
                onChange={(val) => setQuery(val)}
                hasClear={true}
                size="md"
                startIcon={<Search className="w-4 h-4 text-fg-subtle" />}
              />
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                type="submit"
                variant="primary"
                size="md"
                label="Search Catalog"
                icon={<Search className="w-4 h-4" />}
                isLoading={isSearching}
                id="btn-search-execute"
              />
              {query && (
                <Button
                  type="button"
                  variant="ghost"
                  size="md"
                  label="Reset"
                  onClick={() => {
                    setQuery("");
                    onSearch("", {}, selectedServices);
                  }}
                  id="btn-search-clear"
                />
              )}
            </div>
          </div>

          <Divider />

          {/* Filter Bar: Media Types (SegmentedControl) & Services */}
          <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 pt-0.5">
            {/* Media Type Segmented Control */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs font-medium text-fg-muted">Type:</span>
              <SegmentedControl
                label="Media type filter"
                value={selectedType}
                onChange={handleTypeChange}
              >
                <SegmentedControlItem
                  value="all"
                  label="All Media"
                  icon={<Sparkles className="w-3.5 h-3.5" />}
                />
                <SegmentedControlItem
                  value="track"
                  label="Tracks"
                  icon={<Music2 className="w-3.5 h-3.5" />}
                />
                <SegmentedControlItem
                  value="album"
                  label="Albums"
                  icon={<Disc3 className="w-3.5 h-3.5" />}
                />
                <SegmentedControlItem
                  value="playlist"
                  label="Playlists"
                  icon={<ListMusic className="w-3.5 h-3.5" />}
                />
                <SegmentedControlItem
                  value="podcast"
                  label="Podcasts"
                  icon={<Radio className="w-3.5 h-3.5" />}
                />
              </SegmentedControl>
            </div>

            {/* Service Filters */}
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-medium text-fg-muted mr-1">Services:</span>
              {CATALOG_SERVICES.map((srv) => {
                const isSelected = selectedServices.includes(srv.id);
                return (
                  <button
                    key={srv.id}
                    type="button"
                    onClick={() => toggleService(srv.id)}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition cursor-pointer border ${focusRing} ${
                      isSelected
                        ? "border-inverse bg-inverse text-fg-on-inverse"
                        : "border-line bg-sunken text-fg-muted hover:border-line-strong"
                    }`}
                  >
                    <span
                      className="w-2 h-2 rounded-full"
                      style={{ backgroundColor: srv.color }}
                    />
                    <span>{srv.name}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </form>
      </Card>

      {/* Results Header */}
      <SectionHeader
        title="Catalog Media"
        count={`${results.length} items`}
        badgeVariant="neutral"
        description="Click Queue Download to fetch audio with lossless quality and ID3 tags"
      />

      {/* Results Grid */}
      {results.length < 1 ? (
        <Card padding={6} elevation="low" id="search-empty-card">
          <EmptyState
            title="No media found"
            description="Try searching with a track name, artist, or paste a direct streaming URL from Spotify, Deezer, Tidal, or Apple Music."
            actions={
              <Button
                variant="secondary"
                size="sm"
                label="Reset Search Filters"
                onClick={() => {
                  setQuery("");
                  setSelectedType("all");
                  setSelectedServices([]);
                  onSearch("", {}, []);
                }}
              />
            }
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" id="results-grid">
          {results.map((item) => {
            const serviceInfo = getServiceInfo(item.item_service);
            const isQueued = queuedIds.has(item.id);

            return (
              <Card
                key={item.id}
                padding={4}
                elevation="low"
                id={`media-card-${item.id}`}
              >
                <div className="flex flex-col justify-between h-full space-y-3.5">
                  {/* Top: Thumbnail & Metadata */}
                  <div className="flex gap-3.5 items-start">
                    {/* Thumbnail Artwork */}
                    <div className="relative w-20 h-20 shrink-0 rounded-lg overflow-hidden bg-raised border border-line/60">
                      <img
                        src={item.thumbnail || "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=160&auto=format&fit=crop&q=80"}
                        alt={item.name}
                        className="w-full h-full object-cover"
                        loading="lazy"
                      />
                      <div className="absolute top-1.5 left-1.5">
                        <span
                          className="w-2.5 h-2.5 rounded-full block ring-2 ring-surface shadow-xs"
                          style={{ backgroundColor: serviceInfo.color }}
                          title={serviceInfo.name}
                        />
                      </div>
                      {item.item_count && (
                        <div className="absolute bottom-1 right-1 bg-black/75 backdrop-blur-xs text-[10px] text-white px-1.5 py-0.5 rounded font-medium">
                          {item.item_count} items
                        </div>
                      )}
                    </div>

                    {/* Metadata Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-1.5">
                        <h4
                          className="text-sm font-semibold text-fg truncate leading-snug"
                          title={item.name}
                        >
                          {item.name}
                        </h4>
                        {item.explicit && (
                          <span className="text-[10px] font-bold text-fg-muted border border-line-strong px-1 rounded uppercase tracking-wider shrink-0">
                            E
                          </span>
                        )}
                      </div>

                      <p
                        className="text-xs text-fg-muted truncate mt-0.5"
                        title={item.artist}
                      >
                        {item.artist}
                      </p>

                      <p
                        className="text-[11px] text-fg-muted truncate mt-0.5 min-h-[16px]"
                        title={item.album}
                      >
                        {item.album && item.album !== item.name ? item.album : item.item_type.toUpperCase()}
                      </p>

                      <div className="flex items-center gap-2 text-[11px] text-fg-muted mt-2">
                        <span className="inline-flex items-center gap-1">
                          <Clock className="w-3 h-3 text-fg-subtle" />
                          {item.duration || "3:30"}
                        </span>
                        <span>•</span>
                        <span className="inline-flex items-center gap-1 font-mono text-[10px] text-fg-muted">
                          <AudioWaveform className="w-3 h-3 text-fg-subtle" />
                          {item.bitrate || serviceInfo.maxBitrate}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Card Action Footer */}
                  <div className="pt-3 border-t border-line flex items-center justify-between">
                    <Badge
                      variant={serviceInfo.badgeVariant}
                      label={serviceInfo.name}
                    />

                    <Button
                      variant={isQueued ? "secondary" : "primary"}
                      size="sm"
                      label={isQueued ? "Queued" : "Queue Download"}
                      icon={
                        isQueued ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-success-fg" />
                        ) : (
                          <Download className="w-3.5 h-3.5" />
                        )
                      }
                      onClick={() => handleQueueClick(item)}
                      isDisabled={isQueued}
                      id={`btn-queue-${item.id}`}
                    />
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
