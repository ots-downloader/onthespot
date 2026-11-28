import {
  AlertCircle,
  Check,
  Loader2,
  Music2,
  Search,
  Tag
} from "lucide-react";
import React, { useEffect, useState } from "react";
import { applyItunesMatch, searchItunesMatches } from "../lib/api";
import {
  DownloadQueueItem,
  IdentifyApplyResponse,
  IdentifyCandidate,
  OTSConfig
} from "../types";
import { Button, Dialog, Switch, TextInput } from "./ui";

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
  const [applied, setApplied] = useState(false);
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
    setApplied(false);
  }, [item.local_id, item.name, item.artist, item.album, config.itunes_metadata_country]);

  const handleSearch = async () => {
    setSearching(true);
    setError("");
    setCandidates(null);
    setSelectedIndex(null);
    setResult(null);
    setApplied(false);
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
      setApplied(true);
      onApplied(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply the selected match");
    } finally {
      setApplying(false);
    }
  };

  return (
    <Dialog
      isOpen
      onClose={onClose}
      size="lg"
      icon={<Tag />}
      title="Identify track"
      description="Search iTunes and apply a match to a new tagged copy. The original stays on disk."
      closeLabel="Close"
      bodyClassName="space-y-5"
      footer={
        <>
          <Button variant="secondary" size="sm" label="Close" onClick={onClose} />
          <Button
            variant="primary"
            size="sm"
            label={applying ? "Applying..." : applied ? "Applied" : "Apply Tags"}
            icon={
              applying ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : applied ? (
                <Check className="h-3.5 w-3.5" />
              ) : (
                <Tag className="h-3.5 w-3.5" />
              )
            }
            onClick={handleApply}
            isDisabled={applying || applied || selectedIndex === null || !candidates}
          />
        </>
      }
    >
      <div className="rounded-lg bg-sunken px-3 py-2 text-xs">
        <p className="truncate font-medium">{item.name}</p>
        <p className="truncate text-fg-muted">{item.artist || "Unknown artist"}</p>
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
          className="flex-1"
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
        <div className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-subtle px-3 py-2 text-xs text-danger-fg">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="space-y-1 rounded-lg border border-success/30 bg-success-subtle px-3 py-2 text-xs text-success-fg">
          <p className="flex items-center gap-2 font-medium">
            <Check className="h-4 w-4" /> Tagged copy created
          </p>
          <p className="break-all">New: {result.file_path}</p>
          <p className="break-all">Original kept: {result.original_path}</p>
          {result.warnings.map((warning) => (
            <p key={warning} className="break-all text-warning-fg">
              {warning}
            </p>
          ))}
        </div>
      )}

      {candidates && candidates.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Matches</p>
          <div className="space-y-2">
            {candidates.map((candidate, index) => (
              <button
                key={`${candidate.track_id}-${index}`}
                type="button"
                onClick={() => setSelectedIndex(index)}
                className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition ${
                  selectedIndex === index
                    ? "border-accent bg-accent-subtle"
                    : "border-line hover:border-line-strong"
                }`}
              >
                {candidate.image_url ? (
                  <img src={candidate.image_url} alt="" className="h-12 w-12 shrink-0 rounded object-cover" />
                ) : (
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded bg-raised">
                    <Music2 className="h-5 w-5 text-fg-subtle" />
                  </div>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{candidate.title || "Untitled"}</p>
                  <p className="truncate text-xs text-fg-muted">
                    {candidate.artist || "Unknown artist"}
                    {candidate.album ? ` · ${candidate.album}` : ""}
                  </p>
                  <p className="mt-0.5 text-[10px] text-fg-subtle">
                    {candidate.release_year || "—"} · score {candidate.score.toFixed(1)}
                  </p>
                </div>
                {selectedIndex === index && <Check className="h-4 w-4 shrink-0 text-accent" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </Dialog>
  );
}
