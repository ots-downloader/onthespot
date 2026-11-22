import { Button } from "@astryxdesign/core/Button";
import { Switch } from "@astryxdesign/core/Switch";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  AlertCircle,
  Check,
  Loader2,
  Music2,
  Search,
  Tag,
  X
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { applyItunesMatch, searchItunesMatches } from "../lib/api";
import {
  DownloadQueueItem,
  IdentifyApplyResponse,
  IdentifyCandidate,
  OTSConfig
} from "../types";

interface IdentifyTrackModalProps {
  item: DownloadQueueItem;
  config: OTSConfig;
  onClose: () => void;
  onApplied: (result: IdentifyApplyResponse) => void;
}

export function IdentifyTrackModal({ item, config, onClose, onApplied }: IdentifyTrackModalProps) {
  const [title, setTitle] = useState(item.name || "");
  const [artist, setArtist] = useState(item.artist || "");
  const [album, setAlbum] = useState(item.album || "");
  const [country, setCountry] = useState(config.itunes_metadata_country || "US");
  const [embedArtwork, setEmbedArtwork] = useState(true);
  const [candidates, setCandidates] = useState<IdentifyCandidate[] | null>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [searching, setSearching] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<IdentifyApplyResponse | null>(null);

  useEffect(() => {
    setTitle(item.name || "");
    setArtist(item.artist || "");
    setAlbum(item.album || "");
    setCountry(config.itunes_metadata_country || "US");
    setCandidates(null);
    setSelectedIndex(null);
    setError("");
    setResult(null);
  }, [item.local_id, item.name, item.artist, item.album, config.itunes_metadata_country]);

  const handleSearch = async () => {
    setSearching(true);
    setError("");
    setCandidates(null);
    setSelectedIndex(null);
    try {
      const response = await searchItunesMatches({
        local_id: item.local_id,
        title: title.trim() || null,
        artist: artist.trim() || null,
        album: album.trim() || null,
        country: country.trim() || null,
        limit: 10
      });
      setCandidates(response.candidates);
      if (response.candidates.length === 0) {
        setError("No iTunes matches found. Try a shorter title or a different artist/album.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "iTunes search failed");
    } finally {
      setSearching(false);
    }
  };

  const handleApply = async () => {
    if (selectedIndex === null || !candidates) return;
    setApplying(true);
    setError("");
    try {
      const response = await applyItunesMatch({
        local_id: item.local_id,
        candidate: candidates[selectedIndex],
        embed_artwork: embedArtwork
      });
      setResult(response);
      onApplied(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply the selected match");
    } finally {
      setApplying(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/60 p-4 backdrop-blur-xs sm:items-center">
      <div className="relative flex max-h-[calc(100dvh_-_2rem)] w-full max-w-2xl flex-col overflow-hidden rounded-xl border border-neutral-200 bg-white text-neutral-900 shadow-2xl dark:border-neutral-800 dark:bg-[#1c1c1c] dark:text-white">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-neutral-200 px-6 py-5 dark:border-[#353535]">
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-500 dark:bg-[#173b25]">
              <Tag className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Identify track</h2>
              <p className="text-xs text-neutral-500 dark:text-neutral-400">
                Search iTunes and apply a match to a new tagged copy. The original stays on disk.
              </p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-md p-1 text-neutral-500 transition hover:bg-neutral-100 hover:text-neutral-900 dark:hover:bg-neutral-800 dark:hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-6 py-5">
          <div className="rounded-lg bg-neutral-50 px-3 py-2 text-xs dark:bg-neutral-900/60">
            <p className="truncate font-medium">{item.name}</p>
            <p className="truncate text-neutral-500 dark:text-neutral-400">{item.artist || "Unknown artist"}</p>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <TextInput label="Title" value={title} onChange={setTitle} placeholder="Track title" />
            <TextInput label="Artist" value={artist} onChange={setArtist} placeholder="Artist" />
            <TextInput label="Album" value={album} onChange={setAlbum} placeholder="Album (optional)" />
            <TextInput label="Country" value={country} onChange={setCountry} placeholder="US" />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <Switch
              label="Embed artwork"
              description="Download the selected cover art from Apple's CDN."
              value={embedArtwork}
              onChange={setEmbedArtwork}
              labelPosition="start"
              labelSpacing="spread"
            />
            <Button
              variant="primary"
              size="sm"
              label={searching ? "Searching..." : "Search iTunes"}
              icon={searching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Search className="h-3.5 w-3.5" />}
              onClick={handleSearch}
              isDisabled={searching || !title.trim()}
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {candidates && candidates.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-neutral-500">Matches</p>
              <div className="space-y-2">
                {candidates.map((candidate, index) => (
                  <button
                    key={`${candidate.track_id}-${index}`}
                    type="button"
                    onClick={() => setSelectedIndex(index)}
                    className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition ${
                      selectedIndex === index
                        ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/30"
                        : "border-neutral-200 hover:border-neutral-300 dark:border-neutral-800 dark:hover:border-neutral-700"
                    }`}
                  >
                    {candidate.image_url ? (
                      <img src={candidate.image_url} alt="" className="h-12 w-12 shrink-0 rounded object-cover" />
                    ) : (
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-neutral-100 dark:bg-neutral-800">
                        <Music2 className="h-5 w-5 text-neutral-400" />
                      </div>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{candidate.title || "Untitled"}</p>
                      <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">
                        {candidate.artist || "Unknown artist"}
                        {candidate.album ? ` · ${candidate.album}` : ""}
                      </p>
                      <p className="mt-0.5 text-[10px] text-neutral-400">
                        {candidate.release_year || "—"} · score {candidate.score.toFixed(1)}
                      </p>
                    </div>
                    {selectedIndex === index && <Check className="h-4 w-4 shrink-0 text-emerald-500" />}
                  </button>
                ))}
              </div>
            </div>
          )}

          {result && (
            <div className="space-y-1 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200">
              <p className="flex items-center gap-2 font-medium">
                <Check className="h-4 w-4" /> Tagged copy created
              </p>
              <p className="break-all">New: {result.file_path}</p>
              <p className="break-all">Original kept: {result.original_path}</p>
              {result.warnings.map((warning) => (
                <p key={warning} className="break-all text-amber-700 dark:text-amber-300">
                  {warning}
                </p>
              ))}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center justify-end gap-2 border-t border-neutral-200 px-6 py-4 dark:border-[#353535]">
          <Button variant="secondary" size="sm" label="Close" onClick={onClose} />
          <Button
            variant="primary"
            size="sm"
            label={applying ? "Applying..." : "Apply Tags"}
            icon={applying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Tag className="h-3.5 w-3.5" />}
            onClick={handleApply}
            isDisabled={applying || selectedIndex === null || !candidates}
          />
        </div>
      </div>
    </div>,
    document.body
  );
}
