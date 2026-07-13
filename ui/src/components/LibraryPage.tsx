import React, { useEffect, useRef, useState } from "react";
import {
  AudioLines,
  ArrowDownAZ,
  ArrowUpAZ,
  Check,
  ChevronDown,
  Edit3,
  FolderOpen,
  ListMusic,
  Loader2,
  Play,
  RefreshCw,
  Search,
  Tag,
  Trash2,
  Upload,
  WandSparkles,
} from "lucide-react";
import {
  createLibraryM3U,
  fetchLibrary,
  fetchMissingLibraryItems,
  getLibraryCoverUrl,
  LibraryItem,
  LibraryFilters,
  openLibraryItem,
  renameLibraryItem,
  removeMissingLibraryItems,
  requeueMissingLibraryItem,
  scanLibrary,
  updateLibraryMetadata,
  uploadLibraryCover,
  verifyLibraryFiles,
} from "../lib/api";

interface LibraryPageProps {
  onQueueChanged?: () => Promise<void>;
}

type SortMode = "artist" | "album" | "genre" | "title" | "date" | "size";

type LibraryLoadOverrides = Partial<{
  sort: SortMode;
  sortDescending: boolean;
  duplicatesOnly: boolean;
  missingArtwork: boolean;
  failedMetadata: boolean;
  formatFilter: string;
  artistFilter: string;
  genreFilter: string;
  dateFrom: string;
  dateTo: string;
}>;

const formatBytes = (value: number) => {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let amount = value;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount.toFixed(index ? 1 : 0)} ${units[index]}`;
};

const formatDuration = (seconds?: number | null) => {
  if (!seconds) return "—";
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
};

const formatDate = (timestamp: number) => {
  if (!timestamp) return "—";
  return new Date(timestamp * 1000).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
};

const LibraryArtwork: React.FC<{ item: LibraryItem }> = ({ item }) => {
  const [unavailable, setUnavailable] = useState(false);

  return (
    <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden bg-[#282828] text-[#1ed760]">
      {unavailable ? (
        <AudioLines className="h-5 w-5" />
      ) : (
        <img
          src={getLibraryCoverUrl(item.path, item.modified_at)}
          alt={`${item.album || item.title || item.filename} artwork`}
          loading="lazy"
          className="h-full w-full object-cover"
          onError={() => setUnavailable(true)}
        />
      )}
    </div>
  );
};

export const LibraryPage: React.FC<LibraryPageProps> = ({ onQueueChanged }) => {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [missing, setMissing] = useState<LibraryItem[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("artist");
  const [sortDescending, setSortDescending] = useState(false);
  const [duplicatesOnly, setDuplicatesOnly] = useState(false);
  const [missingArtwork, setMissingArtwork] = useState(false);
  const [failedMetadata, setFailedMetadata] = useState(false);
  const [formatFilter, setFormatFilter] = useState("");
  const [artistFilter, setArtistFilter] = useState("");
  const [genreFilter, setGenreFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<LibraryItem | null>(null);
  const [editValues, setEditValues] = useState({ title: "", artist: "", album_artist: "", album: "", genre: "", year: "", release_date: "", track_number: "", disc_number: "", lyrics: "" });
  const [renaming, setRenaming] = useState<LibraryItem | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const coverInput = useRef<HTMLInputElement>(null);
  const [coverTarget, setCoverTarget] = useState<LibraryItem | null>(null);

  const load = async (forceScan = false, overrides: LibraryLoadOverrides = {}) => {
    const activeSort = overrides.sort ?? sort;
    const activeSortDescending = overrides.sortDescending ?? sortDescending;
    const activeDuplicatesOnly = overrides.duplicatesOnly ?? duplicatesOnly;
    const filters: LibraryFilters = {
      missingArtwork: overrides.missingArtwork ?? missingArtwork,
      failedMetadata: overrides.failedMetadata ?? failedMetadata,
      format: overrides.formatFilter ?? formatFilter,
      artist: overrides.artistFilter ?? artistFilter,
      genre: overrides.genreFilter ?? genreFilter,
      dateFrom: overrides.dateFrom ?? dateFrom,
      dateTo: overrides.dateTo ?? dateTo,
    };
    setLoading(!forceScan);
    setScanning(forceScan);
    const result = forceScan
      ? await scanLibrary(query, activeSort, activeSortDescending, activeDuplicatesOnly, filters)
      : await fetchLibrary(query, activeSort, activeSortDescending, activeDuplicatesOnly, filters);
    setItems(result.items);
    const missingResult = await fetchMissingLibraryItems(query);
    setMissing(missingResult);
    setLoading(false);
    setScanning(false);
  };

  useEffect(() => {
    void load();
    // The library only needs to scan once on initial view; search/sort changes
    // are explicit so a large collection is not rescanned on every keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    void load();
  };

  const beginEdit = (item: LibraryItem) => {
    setEditing(item);
    setEditValues({
      title: item.title || "",
      artist: item.artist || "",
      album: item.album || "",
      album_artist: item.album_artist || "",
      genre: item.genre || "",
      year: item.year || "",
      release_date: item.release_date || item.year || "",
      track_number: item.track_number ? String(item.track_number) : "",
      disc_number: item.disc_number ? String(item.disc_number) : "",
      lyrics: item.lyrics || "",
    });
  };

  const saveEdit = async () => {
    if (!editing) return;
    const updated = await updateLibraryMetadata(editing.path, editValues);
    if (!updated) {
      setStatus("Could not update that file's tags.");
      return;
    }
    setItems((current) => current.map((item) => item.id === editing.id ? updated : item));
    setEditing(null);
    setStatus("Metadata saved.");
  };

  const beginRename = (item: LibraryItem) => {
    setRenaming(item);
    setRenameValue(item.filename);
  };

  const saveRename = async () => {
    if (!renaming) return;
    const newName = renameValue.trim();
    if (!newName || newName === renaming.filename) {
      setStatus("Enter a different file name.");
      return;
    }
    setRenameBusy(true);
    try {
      const updated = await renameLibraryItem(renaming.path, newName);
      if (!updated) {
        setStatus("Could not rename that file.");
        return;
      }
      setItems((current) => current.map((entry) => entry.id === renaming.id ? updated : entry));
      setRenaming(null);
      setStatus("File renamed.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Could not rename that file.");
    } finally {
      setRenameBusy(false);
    }
  };

  const chooseCover = (item: LibraryItem) => {
    setCoverTarget(item);
    window.setTimeout(() => coverInput.current?.click(), 0);
  };

  const uploadCover = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !coverTarget) return;
    const updated = await uploadLibraryCover(coverTarget.path, file);
    if (updated) {
      setItems((current) => current.map((item) => item.id === coverTarget.id ? updated : item));
      setStatus("Cover art saved.");
    } else {
      setStatus("Could not save cover art.");
    }
    event.target.value = "";
    setCoverTarget(null);
  };

  const requeueMissing = async (item: LibraryItem) => {
    const ok = await requeueMissingLibraryItem(item.path);
    setStatus(ok ? `Queued ${item.title || item.filename} for re-download.` : "This entry cannot be re-downloaded yet.");
    if (ok) await onQueueChanged?.();
  };

  const removeMissing = async (paths: string[], all = false) => {
    const message = all
      ? `Remove all ${missing.length} missing entries from the library index? This will not delete any files.`
      : "Remove this missing entry from the library index? This will not delete any files.";
    if (!window.confirm(message)) return;
    const removed = await removeMissingLibraryItems(paths);
    if (!removed) {
      setStatus("Could not remove those missing library entries.");
      return;
    }
    setStatus(`Removed ${removed} missing ${removed === 1 ? "entry" : "entries"} from the library index.`);
    await load();
  };

  const verifyFiles = async () => {
    const result = await verifyLibraryFiles();
    setStatus(result.corrupt ? `Found ${result.corrupt} corrupt or incomplete file(s).` : `Verified ${result.healthy} library file(s).`);
    await load();
  };

  const clearFilters = () => {
    setDuplicatesOnly(false);
    setMissingArtwork(false);
    setFailedMetadata(false);
    setFormatFilter("");
    setArtistFilter("");
    setGenreFilter("");
    setDateFrom("");
    setDateTo("");
    void load(false, {
      duplicatesOnly: false,
      missingArtwork: false,
      failedMetadata: false,
      formatFilter: "",
      artistFilter: "",
      genreFilter: "",
      dateFrom: "",
      dateTo: "",
    });
  };

  const createPlaylist = async () => {
    if (items.length === 0) return;
    const name = window.prompt("Playlist file name", "My OnTheSpot Library");
    if (!name) return;
    const path = await createLibraryM3U(name, items.map((item) => item.path));
    setStatus(path ? `Playlist written to ${path}` : "Could not create the playlist file.");
  };

  const sortDirectionLabel = sort === "date"
    ? (sortDescending ? "Oldest first" : "Newest first")
    : sort === "size"
      ? (sortDescending ? "Smallest first" : "Largest first")
      : (sortDescending ? "Z–A" : "A–Z");

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">
      <input ref={coverInput} type="file" accept="image/*" className="hidden" onChange={uploadCover} />

      <section className="ots-hero flex flex-col justify-between gap-5 p-6 md:flex-row md:items-center">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[#1ed760]">
            <AudioLines className="h-5 w-5" />
            <span className="text-xs font-bold uppercase tracking-[0.2em]">Your downloaded music</span>
          </div>
          <h1 className="text-2xl font-bold text-white">Local library</h1>
          <p className="mt-1 text-sm text-[#b3b3b3]">Search, sort, edit, and play the files OnTheSpot has saved.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-[#b3b3b3]">
          <span className="bg-[#282828] px-3 py-2">{items.length} tracks</span>
          <span className="bg-[#282828] px-3 py-2">{items.filter((item) => item.is_duplicate).length} duplicates</span>
          <button type="button" onClick={() => void load(true)} disabled={scanning} className="ots-button ots-button-primary disabled:opacity-50">
            {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Scan library
          </button>
          <button type="button" onClick={() => void verifyFiles()} className="ots-button ots-button-secondary">Verify files</button>
        </div>
      </section>

      <section className="ots-panel flex flex-col gap-3 p-4 md:flex-row md:items-center">
        <form onSubmit={submitSearch} className="flex min-w-0 flex-1 items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#777]" />
            <input id="library-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search title, artist, album, or genre" className="ots-input ots-search-input w-full pr-3 text-sm" />
          </div>
          <button type="submit" className="ots-button ots-button-secondary ots-toolbar-control">Search</button>
        </form>
        <div className="relative shrink-0">
          <ArrowDownAZ className="pointer-events-none absolute left-3 top-1/2 z-10 h-4 w-4 -translate-y-1/2 text-[#8f8f8f]" />
          <select aria-label="Sort library by" value={sort} onChange={(event) => { const nextSort = event.target.value as SortMode; setSort(nextSort); setSortDescending(false); void load(false, { sort: nextSort, sortDescending: false }); }} className="ots-select ots-sort-select ots-toolbar-control min-w-[160px] appearance-none text-sm font-semibold">
            <option value="artist">Sort by artist</option>
            <option value="album">Sort by album</option>
            <option value="genre">Sort by genre</option>
            <option value="title">Sort by title</option>
            <option value="date">Sort by date added</option>
            <option value="size">Sort by file size</option>
          </select>
          <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#8f8f8f]" />
        </div>
        <button
          type="button"
          aria-label={`Sort ${sortDescending ? "ascending" : "descending"}`}
          title={`Current order: ${sortDirectionLabel}. Click to reverse.`}
          onClick={() => { const nextDirection = !sortDescending; setSortDescending(nextDirection); void load(false, { sortDescending: nextDirection }); }}
          className="ots-button ots-button-secondary ots-toolbar-control min-w-[116px] text-sm"
        >
          {sortDescending ? <ArrowUpAZ className="h-4 w-4" /> : <ArrowDownAZ className="h-4 w-4" />}
          {sortDirectionLabel}
        </button>
        <div className="ots-browse-tabs ots-library-filters max-w-full">
          <button type="button" onClick={() => { const nextValue = !duplicatesOnly; setDuplicatesOnly(nextValue); void load(false, { duplicatesOnly: nextValue }); }} aria-pressed={duplicatesOnly} className={`ots-browse-tab ${duplicatesOnly ? "ots-browse-tab-active" : ""}`}>
            <WandSparkles className="h-4 w-4" /> Duplicates only
          </button>
          <button type="button" onClick={() => { const nextValue = !missingArtwork; setMissingArtwork(nextValue); void load(false, { missingArtwork: nextValue }); }} aria-pressed={missingArtwork} className={`ots-browse-tab ${missingArtwork ? "ots-browse-tab-active" : ""}`}>Missing artwork</button>
          <button type="button" onClick={() => { const nextValue = !failedMetadata; setFailedMetadata(nextValue); void load(false, { failedMetadata: nextValue }); }} aria-pressed={failedMetadata} className={`ots-browse-tab ${failedMetadata ? "ots-browse-tab-active" : ""}`}>Metadata issues</button>
        </div>
        <button type="button" onClick={() => void createPlaylist()} disabled={items.length === 0} className="ots-button ots-button-secondary ots-toolbar-control text-sm">
          <ListMusic className="h-4 w-4" /> Create .m3u
        </button>
      </section>

      <section className="ots-panel grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
        <select value={formatFilter} onChange={(event) => { const nextFormat = event.target.value; setFormatFilter(nextFormat); void load(false, { formatFilter: nextFormat }); }} className="ots-select text-sm">
          <option value="">All formats</option>
          <option value="mp3">MP3</option>
          <option value="flac">FLAC</option>
          <option value="m4a">M4A</option>
          <option value="opus">Opus</option>
          <option value="ogg">OGG</option>
          <option value="wav">WAV</option>
        </select>
        <input value={artistFilter} onChange={(event) => setArtistFilter(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void load(false, { artistFilter: event.currentTarget.value }); } }} placeholder="Filter by artist" className="ots-input text-sm" />
        <input value={genreFilter} onChange={(event) => setGenreFilter(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); void load(false, { genreFilter: event.currentTarget.value }); } }} placeholder="Filter by genre" className="ots-input text-sm" />
        <div className="flex items-center gap-2">
          <input type="date" value={dateFrom} onChange={(event) => { const nextDate = event.target.value; setDateFrom(nextDate); void load(false, { dateFrom: nextDate }); }} className="ots-input min-w-0 text-sm" aria-label="Downloaded from" />
          <span className="text-xs text-[#777]">to</span>
          <input type="date" value={dateTo} onChange={(event) => { const nextDate = event.target.value; setDateTo(nextDate); void load(false, { dateTo: nextDate }); }} className="ots-input min-w-0 text-sm" aria-label="Downloaded to" />
        </div>
        {(formatFilter || artistFilter || genreFilter || dateFrom || dateTo || duplicatesOnly || missingArtwork || failedMetadata) && <button type="button" onClick={clearFilters} className="ots-button ots-button-ghost text-sm sm:col-span-2 lg:col-span-4">Clear library filters</button>}
      </section>

      {status && (
        <div className="flex items-center gap-2 border border-[#275c37] bg-[#173b25] px-4 py-3 text-sm text-[#b8f5c9]">
          <Check className="h-4 w-4" /> {status}
        </div>
      )}

      {missing.length > 0 && (
        <section className="border border-[#6a4920] bg-[#2c2417] p-5">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[#f6b94a]"><Trash2 className="h-4 w-4" /><h2 className="font-bold">Missing files</h2></div>
            <button type="button" onClick={() => void removeMissing([], true)} className="ots-button ots-button-danger ots-button-sm shrink-0"><Trash2 className="h-4 w-4" /> Remove all</button>
          </div>
          <p className="mb-4 text-xs text-[#c6b28d]">These indexed downloads are no longer on disk. Entries with a saved source can be queued again.</p>
          <div className="flex flex-col gap-2">
            {missing.map((item) => (
              <div key={item.id} className="flex flex-col justify-between gap-3 border border-[#4b3a20] bg-[#211b12] p-3 sm:flex-row sm:items-center">
                <div className="min-w-0"><p className="truncate text-sm font-bold text-white">{item.title || item.filename}</p><p className="truncate text-xs text-[#b3b3b3]">{item.artist || "Unknown artist"} · {item.filename}</p></div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  <button type="button" onClick={() => void requeueMissing(item)} disabled={!item.source_url} className="ots-button ots-button-warning ots-button-sm disabled:opacity-40">Re-download</button>
                  <button type="button" onClick={() => void removeMissing([item.path])} className="ots-button ots-button-danger ots-button-sm"><Trash2 className="h-4 w-4" /> Remove</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="ots-panel overflow-hidden shadow-xl shadow-black/10">
        {loading ? (
          <div className="flex items-center justify-center gap-2 p-16 text-sm text-[#b3b3b3]"><Loader2 className="h-5 w-5 animate-spin" /> Loading library…</div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 p-16 text-center text-[#777]"><AudioLines className="h-10 w-10" /><p className="font-bold text-[#b3b3b3]">No local tracks found</p><p className="max-w-md text-sm">Run a scan after downloading a track, or check the audio folder in Settings.</p></div>
        ) : (
          <div className="divide-y divide-[#282828]">
            {items.map((item) => (
              <article key={item.id} className="ots-library-row flex flex-col gap-4 p-4 transition md:flex-row md:items-center">
                <div className="flex min-w-0 flex-1 items-center gap-4">
                  <LibraryArtwork item={item} />
                  <div className="min-w-0">
                    <h2 className="truncate font-bold text-white">{item.title || item.filename}</h2>
                    <p className="truncate text-sm text-[#b3b3b3]">{item.artist || "Unknown artist"}{item.album ? ` · ${item.album}` : ""}</p>
                    <p className="truncate text-xs text-[#777]">{item.relative_path} · {formatBytes(item.size)} · {formatDuration(item.duration_seconds)} · {formatDate(item.modified_at)}</p>
                    <div className="mt-2 flex flex-wrap gap-2 text-[10px] font-bold uppercase tracking-wider text-[#8e8e8e]">
                      <span className="bg-[#282828] px-2 py-1">{item.format}</span>
                      {item.genre && <span className="bg-[#282828] px-2 py-1">{item.genre}</span>}
                      {item.is_duplicate && <span className="bg-[#4a2c1f] px-2 py-1 text-[#f6b94a]">Duplicate ×{item.duplicate_count}</span>}
                    </div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1 md:justify-end">
                  <button type="button" onClick={() => void openLibraryItem(item.path, "play")} className="ots-icon-button text-[#1ed760]" title="Play file"><Play className="h-4 w-4 fill-current" /></button>
                  <button type="button" onClick={() => void openLibraryItem(item.path, "folder")} className="ots-icon-button" title="Open containing folder"><FolderOpen className="h-4 w-4" /></button>
                  <button type="button" onClick={() => beginEdit(item)} className="ots-icon-button" title="Edit metadata"><Tag className="h-4 w-4" /></button>
                  <button type="button" onClick={() => beginRename(item)} className="ots-icon-button" title="Rename file"><Edit3 className="h-4 w-4" /></button>
                  <button type="button" onClick={() => chooseCover(item)} className="ots-icon-button" title="Set cover art"><Upload className="h-4 w-4" /></button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg border border-[#333] bg-[#202020] p-6 shadow-2xl">
            <div className="mb-5 flex items-center justify-between"><div><p className="text-xs font-bold uppercase tracking-wider text-[#1ed760]">Edit tags</p><h2 className="mt-1 text-xl font-bold text-white">{editing.filename}</h2></div><button type="button" onClick={() => setEditing(null)} className="text-[#b3b3b3] hover:text-white">×</button></div>
            <div className="grid gap-3 sm:grid-cols-2">
              {(["title", "artist", "album_artist", "album", "genre", "release_date", "track_number", "disc_number"] as const).map((field) => (
                <label key={field} className={`flex flex-col gap-1 text-xs font-bold capitalize text-[#b3b3b3] ${field === "title" ? "sm:col-span-2" : ""}`}>
                  {field.replaceAll("_", " ")}
                  <input value={editValues[field]} onChange={(event) => setEditValues((current) => ({ ...current, [field]: event.target.value }))} className="ots-input text-sm font-normal" />
                </label>
              ))}
              <label className="flex flex-col gap-1 text-xs font-bold capitalize text-[#b3b3b3] sm:col-span-2">
                Lyrics
                <textarea value={editValues.lyrics} onChange={(event) => setEditValues((current) => ({ ...current, lyrics: event.target.value }))} rows={5} className="ots-input min-h-28 resize-y text-sm font-normal" />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2"><button type="button" onClick={() => setEditing(null)} className="ots-button ots-button-ghost">Cancel</button><button type="button" onClick={() => void saveEdit()} className="ots-button ots-button-primary"><Check className="h-4 w-4" /> Save tags</button></div>
          </div>
        </div>
      )}

      {renaming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <form
            className="w-full max-w-lg border border-[#333] bg-[#202020] p-6 shadow-2xl"
            onSubmit={(event) => {
              event.preventDefault();
              void saveRename();
            }}
          >
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-[#1ed760]">Rename file</p>
                <h2 className="mt-1 truncate text-xl font-bold text-white">{renaming.filename}</h2>
              </div>
              <button type="button" onClick={() => setRenaming(null)} className="text-[#b3b3b3] hover:text-white">×</button>
            </div>
            <label className="flex flex-col gap-2 text-xs font-bold text-[#b3b3b3]">
              New file name
              <input
                autoFocus
                value={renameValue}
                onChange={(event) => setRenameValue(event.target.value)}
                className="ots-input text-sm font-normal"
                placeholder="Track name.mp3"
              />
            </label>
            <p className="mt-2 text-xs text-[#777]">Use a file name only; the file stays in its current folder. The extension is added automatically if omitted.</p>
            <div className="mt-6 flex justify-end gap-2">
              <button type="button" onClick={() => setRenaming(null)} className="ots-button ots-button-ghost">Cancel</button>
              <button type="submit" disabled={renameBusy} className="ots-button ots-button-primary">
                {renameBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                {renameBusy ? "Renaming…" : "Rename file"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
