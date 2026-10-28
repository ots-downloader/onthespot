import { Badge } from "@astryxdesign/core/Badge";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Switch } from "@astryxdesign/core/Switch";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { TextInput } from "@astryxdesign/core/TextInput";
import {
  Cpu,
  Download,
  Film,
  Globe,
  Key,
  Music,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
  Sliders,
  Tag
} from "lucide-react";
import React, { useState } from "react";
import { getTargetBackendUrl, setTargetBackendUrl, testBackendConnection } from "../lib/api";
import { DownloadProfile, OTSConfig } from "../types";
import { PageHeader } from "./PageHeader";


/* -------------------------------------------------------------------------- */
/* SettingsPage Component                                                     */
/* -------------------------------------------------------------------------- */

interface SettingsPageProps {
  config: OTSConfig;
  profiles: DownloadProfile[];
  activeProfile: string;
  onUpdateValue: (key: string, value: any) => Promise<boolean>;
  onSave: () => Promise<boolean>;
  onReset: () => Promise<void>;
  onActivateProfile: (profileId: string) => Promise<void>;
  onSaveProfile: (profile: DownloadProfile) => Promise<DownloadProfile>;
  onDeleteProfile: (profileId: string) => Promise<boolean>;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({
  config,
  profiles,
  activeProfile,
  onUpdateValue,
  onSave,
  onReset,
  onActivateProfile,
}) => {
  const [activeTab, setActiveTab] = useState("general");
  const [localBackendUrl, setLocalBackendUrl] = useState(getTargetBackendUrl());
  const [isSavedNotice, setIsSavedNotice] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTestingConn, setIsTestingConn] = useState(false);
  const [connStatus, setConnStatus] = useState<"idle" | "connected" | "failed">("idle");

  const handleSaveAll = async () => {
    setIsSaving(true);
    setTargetBackendUrl(localBackendUrl);
    await onSave();
    setIsSaving(false);
    setIsSavedNotice(true);
    setTimeout(() => setIsSavedNotice(false), 2500);
  };

  const handleTestConnection = async () => {
    setIsTestingConn(true);
    setConnStatus("idle");
    const ok = await testBackendConnection(localBackendUrl);
    setIsTestingConn(false);
    setConnStatus(ok ? "connected" : "failed");
  };

  const formatBytes = (bytes: number): string => {
    if (!bytes || bytes <= 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const inputClass =
    "w-full px-3 py-1.5 text-xs rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-1 focus:ring-neutral-400";

  /* ------------------------------------------------------------------------ */
  /* Unified Dynamic Input Renderer                                           */
  /* ------------------------------------------------------------------------ */

  const renderInput = (field) => {
    const rawVal = config[field.key];

    switch (field.type) {
      case "switch":
        return (
          <div key={field.key} className="py-1">
            <Switch
              label={field.label}
              description={field.description}
              value={Boolean(rawVal)}
              onChange={(checked) => onUpdateValue(field.key, checked)}
              labelPosition="start"
              labelSpacing="spread"
            />
          </div>
        );

      case "number":
        return (
          <div key={field.key}>
            <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
              {field.label}
            </label>
            <input
              type="number"
              min={field.min}
              max={field.max}
              step={field.step}
              value={rawVal ?? field.defaultValue ?? ""}
              onChange={(e) => {
                const parsed = field.isFloat
                  ? parseFloat(e.target.value) || 0
                  : parseInt(e.target.value, 10) || 0;
                onUpdateValue(field.key, parsed);
              }}
              placeholder={field.placeholder}
              className={inputClass}
            />
            {field.description && (
              <p className="text-[11px] text-neutral-500 mt-1">{field.description}</p>
            )}
          </div>
        );

      case "select":
        return (
          <div key={field.key}>
            <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
              {field.label}
            </label>
            <select
              value={rawVal ?? field.defaultValue ?? ""}
              onChange={(e) => {
                const val = field.isNumber
                  ? parseInt(e.target.value, 10) || 0
                  : e.target.value;
                onUpdateValue(field.key, val);
              }}
              className={inputClass}
            >
              {field.options.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            {field.description && (
              <p className="text-[11px] text-neutral-500 mt-1">{field.description}</p>
            )}
          </div>
        );

      case "string-array":
        return (
          <div key={field.key}>
            <TextInput
              label={field.label}
              value={Array.isArray(rawVal) ? rawVal.join(field.delimiter ?? " ") : ""}
              onChange={(val) =>
                onUpdateValue(
                  field.key,
                  val.split(field.delimiter ?? " ").filter(Boolean)
                )
              }
              description={field.description}
              placeholder={field.placeholder}
              size="md"
            />
          </div>
        );

      case "text":
      case "password":
      default:
        return (
          <div key={field.key}>
            <TextInput
              label={field.label}
              type={field.type === "password" ? "password" : "text"}
              value={rawVal ?? ""}
              onChange={(val) => onUpdateValue(field.key, val)}
              description={field.description}
              placeholder={field.placeholder}
              size="md"
            />
          </div>
        );
    }
  };

  return (
    <div className="space-y-5" id="settings-view">
      {/* Page Header */}
      <PageHeader
        id="settings-page-header"
        icon={<Sliders className="w-5 h-5" />}
        title="Settings & Configuration"
        badge={isSavedNotice ? { label: "Saved Successfully", variant: "success" } : undefined}
        description="Configure downloader concurrency, metadata embedding, directory paths, video conversion, and API integrations"
        actions={
          <>
            <Button
              variant="ghost"
              size="sm"
              label="Reset Defaults"
              icon={<RotateCcw className="w-3.5 h-3.5" />}
              onClick={onReset}
              id="btn-settings-reset"
            />
            <Button
              variant="primary"
              size="sm"
              label="Save Configuration"
              icon={<Save className="w-3.5 h-3.5" />}
              onClick={handleSaveAll}
              isLoading={isSaving}
              id="btn-settings-save"
            />
          </>
        }
        bottomContent={
          <div className="overflow-x-auto h-8">
            <TabList
              value={activeTab}
              onChange={(tabId) => setActiveTab(tabId)}
              size="sm"
            >
              <Tab value="general" label="General & Workers" icon={<Cpu className="w-3.5 h-3.5" />} />
              <Tab value="audio" label="Audio & Output" icon={<Music className="w-3.5 h-3.5" />} />
              <Tab value="video" label="Video & Shows" icon={<Film className="w-3.5 h-3.5" />} />
              <Tab value="metadata" label="Metadata & ID3" icon={<Tag className="w-3.5 h-3.5" />} />
              <Tab value="integrations" label="Services & Auth" icon={<Key className="w-3.5 h-3.5" />} />
              <Tab value="profiles" label="Download Profiles" icon={<Download className="w-3.5 h-3.5" />} />
              <Tab value="backend" label="Backend & System" icon={<Server className="w-3.5 h-3.5" />} />
            </TabList>
          </div>
        }
      />

      {/* ========================================================================= */}
      {/* 1. GENERAL & WORKERS                                                      */}
      {/* ========================================================================= */}
      {activeTab === "general" && (
        <div className="space-y-4" id="settings-tab-general">
          <Card padding={4} elevation="low">
            <div className="flex items-center gap-2 mb-4">
              <Cpu className="w-4 h-4 text-neutral-500" />
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                Worker Concurrency & Rate Limiting
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                { key: "maximum_download_workers", label: "Maximum Download Workers", type: "number", min: 1, max: 16, defaultValue: 2, description: "Simultaneous stream download threads." },
                { key: "maximum_queue_workers", label: "Queue Polling Workers", type: "number", min: 1, max: 16, defaultValue: 4, description: "Tracks parsing and catalog gathering threads." },
                { key: "download_delay", label: "Download Delay (Seconds)", type: "number", step: "0.1", min: 0, isFloat: true, defaultValue: 1.5, description: "Simulates organic playback requests." },
                { key: "download_delay_variance", label: "Delay Variance (Seconds)", type: "number", step: "0.1", min: 0, isFloat: true, defaultValue: 0.5, description: "Random jitter window (± seconds)." },
                { key: "api_request_delay", label: "API Request Delay (Seconds)", type: "number", step: "0.05", min: 0, isFloat: true, defaultValue: 0, description: "Pacing interval between catalog queries." },
                { key: "api_retry_max_attempts", label: "API Retry Max Attempts", type: "number", min: 1, max: 20, defaultValue: 3 },
                { key: "api_retry_base_delay", label: "API Retry Base Delay (Seconds)", type: "number", step: "0.5", min: 0, isFloat: true, defaultValue: 1 },
                { key: "api_retry_max_delay", label: "API Retry Max Delay (Seconds)", type: "number", step: 1, min: 1, defaultValue: 30 },
                { key: "retry_worker_delay", label: "Retry Worker Delay (Seconds)", type: "number", min: 1, max: 300, defaultValue: 5 },
              ].map(renderInput)}
            </div>

            <div className="mt-5 pt-4 border-t border-neutral-200 dark:border-neutral-800 space-y-2">
              {[
                { key: "rotate_active_account_number", label: "Automatic Worker Account Rotation", type: "switch", description: "Distribute media load across authenticated accounts of the same service." },
                { key: "enable_retry_worker", label: "Enable Background Retry Worker", type: "switch", description: "Periodically retry enqueued items that timed out or hit rate limits." },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Application & System Preferences
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {[
                {
                  key: "theme",
                  label: "Theme Appearance",
                  type: "select",
                  defaultValue: "system",
                  options: [
                    { value: "system", label: "System Default" },
                    { value: "dark", label: "Dark Mode" },
                    { value: "light", label: "Light Mode" },
                  ],
                },
              ].map(renderInput)}
            </div>

            <div className="mt-5 pt-4 border-t border-neutral-200 dark:border-neutral-800 space-y-2">
              {[
                { key: "check_for_updates", label: "Check for Updates Automatically", type: "switch", description: "Query the release repository on launch and intervals." },
                { key: "windows_10_explorer_thumbnails", label: "Windows 10 Explorer Thumbnail Support", type: "switch", description: "Format cover streams for standard Explorer folder caching." },
                { key: "debug_mode", label: "Debug Logging Mode", type: "switch", description: "Output verbose internal states and network request traces." },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              UI Controls & Queue Item Action Buttons
            </h3>

            <div className="space-y-2">
              {[
                { key: "show_search_thumbnails", label: "Show Search Thumbnails", type: "switch", description: "Display album artwork beside catalog search results." },
                { key: "show_download_thumbnails", label: "Show Download Queue Thumbnails", type: "switch", description: "Display media artwork next to active items in queue." },
                { key: "disable_download_popups", label: "Disable Download Popups", type: "switch", description: "Suppress banner notifications when adding items to queue." },
              ].map(renderInput)}
            </div>

          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Catalog Search Queries & Filters
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {[
                { key: "max_search_results", label: "Max Search Results per Query", type: "number", min: 1, max: 100, defaultValue: 20 },
                { key: "search_prefix", label: "Default Search Prefix", type: "text", placeholder: "e.g. spotify: or artist:" },
              ].map(renderInput)}
            </div>

            <div className="space-y-4">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2">
                  Universal Search Content Categories
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {[
                    { key: "enable_search_tracks", label: "Search Tracks", type: "switch" },
                    { key: "enable_search_albums", label: "Search Albums", type: "switch" },
                    { key: "enable_search_playlists", label: "Search Playlists", type: "switch" },
                    { key: "enable_search_artists", label: "Search Artists", type: "switch" },
                    { key: "enable_search_episodes", label: "Search Episodes", type: "switch" },
                    { key: "enable_search_podcasts", label: "Search Podcasts", type: "switch" },
                    { key: "enable_search_audiobooks", label: "Search Audiobooks", type: "switch" },
                  ].map(renderInput)}
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 2. AUDIO & OUTPUT                                                         */}
      {/* ========================================================================= */}
      {activeTab === "audio" && (
        <div className="space-y-4" id="settings-tab-audio">
          <Card padding={4} elevation="low">
            <div className="flex items-center gap-2 mb-4">
              <Music className="w-4 h-4 text-neutral-500" />
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                Audio Storage Paths & Naming Formatters
              </h3>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { key: "audio_download_path", label: "Audio Download Path", type: "text", placeholder: "/music/OnTheSpot", description: "Primary directory." },
                ].map(renderInput)}
              </div>

              {[
                { key: "track_path_formatter", label: "Track File Path Formatter", type: "text", description: "Tags: {artist}, {album}, {track_number}, {disc_number}, {name}, {year}, {genre}" },
                { key: "playlist_path_formatter", label: "Playlist Path Formatter", type: "text", description: "Layout when 'Use Playlist Path Structure' is enabled." },
              ].map(renderInput)}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { key: "podcast_path_formatter", label: "Podcast Path Formatter", type: "text", description: "Target folder for podcasts" },
                  { key: "podcast_file_format", label: "Podcast File Format", type: "text", description: "Target container for voice episodes." },
                ].map(renderInput)}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  { key: "album_cover_format", label: "Album Cover Format", type: "text", description: "Artwork format (jpg, png)." },
                  { key: "illegal_character_replacement", label: "Illegal Character Replacement", type: "text", description: "Replaces / \\ ? * : | < >" },
                  { key: "file_hertz", label: "Audio Sample Rate (Hertz)", type: "number", min: 22050, max: 192000, step: 100, defaultValue: 44100, description: "Output sample rate (e.g. 44100, 48000)." },
                ].map(renderInput)}
              </div>

              {renderInput({
                key: "ffmpeg_args",
                label: "Custom FFmpeg Arguments",
                type: "string-array",
                description: "Space-delimited arguments forwarded directly to the FFmpeg transcoder.",
              })}

              <div className="pt-4 border-t border-neutral-200 dark:border-neutral-800 space-y-2">
                {[
                  { key: "use_playlist_path", label: "Use Playlist Path Structure", type: "switch", description: "Store playlist tracks inside a dedicated playlist directory." },
                  { key: "use_double_digit_path_numbers", label: "Use Double Digit Numbers", type: "switch", description: "Zero-pad track and disc numbers (01, 02...) in file paths." },
                  { key: "translate_file_path", label: "Translate File Paths", type: "switch", description: "Convert non-ASCII characters to standard Latin equivalents in file paths." },
                ].map(renderInput)}
              </div>
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              M3U &amp; M3U8 Playlist Export Options
            </h3>

            <div className="space-y-4">
              {renderInput({
                key: "create_m3u_file",
                label: "Create M3U Playlist Files",
                type: "switch",
                description: "Automatically generate playlist index files alongside downloaded playlists.",
              })}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { key: "m3u_path_formatter", label: "M3U Path Formatter", type: "text" },
                  { key: "m3u_format", label: "M3U Format Flavor", type: "text" },
                  { key: "extinf_separator", label: "EXTINF Separator", type: "text" },
                  { key: "extinf_label", label: "EXTINF Label Pattern", type: "text" },
                ].map(renderInput)}
              </div>
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Audio Bitrate, Lyrics &amp; Artwork
            </h3>

            <div className="space-y-2">
              {[
                { key: "use_source_format", label: "Use source format", type: "switch", description: "Use the same format of the download file for saved files (override profiles!)" },
                { key: "prefer_best_source_format", label: "Raw Media Download", type: "switch", description: "Always prefer the best source format for download" },
                { key: "raw_media_download", label: "Raw Media Download", type: "switch", description: "Write directly streamed chunks to disk without decoding. (override profiles!)" },
                { key: "save_album_cover", label: "Save Separate Album Artwork Image", type: "switch", description: "Save folder.jpg or cover.jpg alongside audio tracks." },
                { key: "download_lyrics", label: "Download Lyrics", type: "switch", description: "Retrieve track lyrics from catalog providers." },
                { key: "save_lrc_file", label: "Save .LRC Lyrics Files", type: "switch", description: "Save synchronized lyric files alongside audio tracks." },
                { key: "only_download_synced_lyrics", label: "Only Download Synced Lyrics", type: "switch", description: "Skip lyrics if time-synced markers are unavailable." },
                { key: "only_download_plain_lyrics", label: "Only Download Plain Lyrics", type: "switch", description: "Prefer un-synced plain text lines over timed files." },
              ].map(renderInput)}
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 3. VIDEO & SHOWS                                                          */}
      {/* ========================================================================= */}
      {activeTab === "video" && (
        <div className="space-y-4" id="settings-tab-video">
          <Card padding={4} elevation="low">
            <div className="flex items-center gap-2 mb-4">
              <Film className="w-4 h-4 text-neutral-500" />
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                Video Storage Paths &amp; Quality Parameters
              </h3>
            </div>

            <div className="space-y-4">
              {renderInput({
                key: "video_download_path",
                label: "Video Download Destination Folder",
                type: "text",
                placeholder: "/videos/OnTheSpot",
                description: "Base destination for movies, TV series, and video episodes.",
              })}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { key: "movie_path_formatter", label: "Movie Path Formatter", type: "text" },
                  { key: "movie_file_format", label: "Movie File Format", type: "text" },
                  { key: "show_path_formatter", label: "TV Show Path Formatter", type: "text" },
                  { key: "show_file_format", label: "TV Show File Format", type: "text" },
                ].map(renderInput)}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                  {
                    key: "preferred_video_resolution",
                    label: "Preferred Video Resolution",
                    type: "select",
                    isNumber: true,
                    defaultValue: 1080,
                    options: [
                      { value: 2160, label: "4K UHD (2160p)" },
                      { value: 1440, label: "QHD (1440p)" },
                      { value: 1080, label: "FHD (1080p)" },
                      { value: 720, label: "HD (720p)" },
                      { value: 480, label: "SD (480p)" },
                    ],
                  },
                  { key: "preferred_audio_language", label: "Preferred Audio Language", type: "text", placeholder: "en" },
                  { key: "preferred_subtitle_language", label: "Preferred Subtitle Language", type: "text", placeholder: "en" },
                ].map(renderInput)}
              </div>

              <div className="pt-4 border-t border-neutral-200 dark:border-neutral-800 space-y-2">
                {[
                  { key: "download_subtitles", label: "Download Subtitles", type: "switch", description: "Extract subtitle streams into video containers or .srt files." },
                  { key: "download_chapters", label: "Download Video Chapters", type: "switch", description: "Embed chapter markers into output video containers." },
                  { key: "download_all_available_audio", label: "Download All Available Audio Tracks", type: "switch", description: "Preserve all available localized audio language tracks." },
                  { key: "download_all_available_subtitles", label: "Download All Available Subtitle Languages", type: "switch", description: "Keep every subtitle stream provided by the source catalog." },
                ].map(renderInput)}
              </div>
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Video-to-Audio (V2A) Extraction
            </h3>

            <div className="space-y-4">
              {renderInput({
                key: "v2a_enable",
                label: "Enable Automatic Video-to-Audio Extraction",
                type: "switch",
                description: "Automatically transcode downloaded video streams into audio files.",
              })}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { key: "v2a_preferred_codec", label: "V2A Target Codec", type: "text", placeholder: "mp3" },
                  { key: "v2a_preferred_bitrate", label: "V2A Target Bitrate (kbps)", type: "number", min: 64, max: 512, step: 32, defaultValue: 320 },
                ].map(renderInput)}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 4. METADATA & ID3                                                         */}
      {/* ========================================================================= */}
      {activeTab === "metadata" && (
        <div className="space-y-4" id="settings-tab-metadata">
          <Card padding={4} elevation="low">
            <div className="flex items-center gap-2 mb-4">
              <Tag className="w-4 h-4 text-neutral-500" />
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                Metadata Tags &amp; Field Delimiters
              </h3>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              {[
                { key: "metadata_separator", label: "Metadata Multi-Value Separator", type: "text", description: "Delimiter between multiple artists or genres." },
                { key: "explicit_label", label: "Explicit Advisory Label", type: "text", description: "Marker applied to explicit tracks." },
              ].map(renderInput)}
            </div>

            <div className="space-y-2 pt-2">
              {[
                { key: "overwrite_existing_metadata", label: "Overwrite Existing Metadata", type: "switch", description: "Overwrite pre-existing ID3 tags in media files." },
                { key: "cache_metadata_in_queue", label: "Cache Queue Metadata in Memory", type: "switch", description: "Keep track metadata cached to avoid duplicate requests." },
                { key: "prefer_composer_as_album_artist", label: "Prefer Composer as Album Artist", type: "switch", description: "Assign classical music composer to Album Artist tag frame." },
                { key: "shorten_composer_tag", label: "Shorten Composer Tag", type: "switch", description: "Omit dates and prefixes from composer metadata frames." },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Spotify Specific Catalog Scraping (Needs WebAPI Keys)
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { key: "fetch_genre_metadata", label: "Fetch Genre Metadata", type: "switch", description: "Enrich missing track genres from MusicBrainz/services." },
                { key: "fetch_extended_album_metadata", label: "Fetch Extended Album Metadata", type: "switch", description: "Scrape edition labels, UPC, and liner note details." },
                { key: "fetch_audio_features", label: "Fetch Audio Features", type: "switch", description: "Retrieve musical key signature, BPM, and acoustic metrics." },
                { key: "fetch_track_credits", label: "Fetch Track Credits", type: "switch", description: "Enrich files with composers, writers, and producers." },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              ID3 Container Standard Text Fields
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {[
                { key: "embed_name", label: "Track Name (TIT2)", type: "switch" },
                { key: "embed_artist", label: "Artist (TPE1)", type: "switch" },
                { key: "embed_album", label: "Album (TALB)", type: "switch" },
                { key: "embed_albumartist", label: "Album Artist (TPE2)", type: "switch" },
                { key: "embed_year", label: "Release Year & Date", type: "switch" },
                { key: "embed_genre", label: "Genre (TCON)", type: "switch" },
                { key: "embed_tracknumber", label: "Track Number (TRCK)", type: "switch" },
                { key: "embed_discnumber", label: "Disc Number (TPOS)", type: "switch" },
                { key: "embed_label", label: "Record Label (TPUB)", type: "switch" },
                { key: "embed_copyright", label: "Copyright (TCOP)", type: "switch" },
                { key: "embed_description", label: "Track Description (COMM)", type: "switch" },
                { key: "embed_language", label: "Language (TLAN)", type: "switch" },
                { key: "embed_isrc", label: "ISRC Code (TSRC)", type: "switch" },
                { key: "embed_length", label: "Track Length (TLEN)", type: "switch" },
                { key: "embed_url", label: "Source URL (WOAS)", type: "switch" },
                { key: "embed_key", label: "Musical Key (TKEY)", type: "switch" },
                { key: "embed_bpm", label: "Tempo / BPM (TBPM)", type: "switch" },
                { key: "embed_compilation", label: "Compilation Flag (TCMP)", type: "switch" },
                { key: "embed_upc", label: "Barcode / UPC Tag", type: "switch" },
                { key: "embed_service_id", label: "Service Identifier (UFID)", type: "switch" },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Credits &amp; Production Personnel
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {[
                { key: "embed_composer", label: "Composer (TCOM)", type: "switch" },
                { key: "embed_writers", label: "Songwriters (TEXT)", type: "switch" },
                { key: "embed_producers", label: "Producers (TIPL/IPLS)", type: "switch" },
                { key: "embed_performers", label: "Performers & Musicians", type: "switch" },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              Artwork, Lyrics &amp; Branding Embedding
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { key: "embed_cover", label: "Embed Album Artwork (APIC)", type: "switch", description: "Embed artwork into the file's metadata block." },
                { key: "embed_lyrics", label: "Embed Lyrics (USLT / SYLT)", type: "switch", description: "Write lyric frames directly into audio headers." },
                { key: "embed_explicit", label: "Embed Explicit Content Advisory", type: "switch", description: "Write parental advisory classification tags." },
                { key: "embed_branding", label: "Embed OnTheSpot Branding Marker", type: "switch", description: "Append 'Downloaded with OnTheSpot' in comments." },
              ].map(renderInput)}
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 5. SERVICES & AUTH                                                        */}
      {/* ========================================================================= */}
      {activeTab === "integrations" && (
        <div className="space-y-4" id="settings-tab-integrations">
          <Card padding={4} elevation="low">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <Globe className="w-4 h-4 text-neutral-500" />
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                  Spotify Web API &amp; Connect
                </h3>
              </div>
              {config.spotify_webapi_override_client_secret_configured && (
                <Badge variant="success" label="Custom API Secret Configured" />
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { key: "spotify_webapi_override_client_id", label: "Spotify Override Client ID", type: "text", placeholder: "Your client ID" },
                { key: "spotify_webapi_override_client_secret", label: "Spotify Override Client Secret", type: "text", placeholder: "Your Client Secret" },
              ].map(renderInput)}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-4">
              API In-Memory Caching &amp; Expiration TTLs
            </h3>

            <div className="space-y-4">
              {renderInput({
                key: "cache_api_calls",
                label: "Cache API Calls in Memory",
                type: "switch",
                description: "Store responses in local memory to prevent duplicate requests.",
              })}

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  { key: "api_response_cache_ttl_seconds", label: "General API Cache TTL (s)", type: "number", min: 0, defaultValue: 3600 },
                  { key: "spotify_metadata_cache_ttl_seconds", label: "Spotify Metadata Cache TTL (s)", type: "number", min: 0, defaultValue: 86400 },
                  { key: "spotify_search_cache_ttl_seconds", label: "Spotify Search Cache TTL (s)", type: "number", min: 0, defaultValue: 3600 },
                  { key: "playlist_automation_cache_ttl_seconds", label: "Playlist Auto Cache TTL (s)", type: "number", min: 0, defaultValue: 7200 },
                ].map(renderInput)}
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 6. DOWNLOAD PROFILES                                                      */}
      {/* ========================================================================= */}
      {activeTab === "profiles" && (
        <div className="space-y-4" id="settings-tab-profiles">
          <Card padding={4} elevation="low">
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="flex items-center gap-2">
                  <Download className="w-4 h-4 text-neutral-500" />
                  <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                    Audio Quality Profiles
                  </h3>
                </div>
                <p className="text-xs text-neutral-500 mt-0.5">
                  Select which quality preset is applied by default when enqueuing new items.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {(profiles || config.download_profiles || []).map((prof) => {
                const isCurrentActive =
                  prof.id === (config.active_download_profile || activeProfile);
                return (
                  <Card key={prof.id} padding={4} elevation="low" id={`profile-card-${prof.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                            {prof.name}
                          </h4>
                          {isCurrentActive && <Badge variant="success" label="Active Default" />}
                        </div>
                        <p className="text-xs font-mono text-neutral-500 mt-1">
                          Format: {prof.format} • Bitrate: {prof.bitrate}
                        </p>
                      </div>

                      {!isCurrentActive && (
                        <Button
                          variant="secondary"
                          size="sm"
                          label="Set Default"
                          onClick={() => {
                            onUpdateValue("active_download_profile", prof.id);
                            onActivateProfile(prof.id);
                          }}
                        />
                      )}
                    </div>
                  </Card>
                );
              })}
            </div>
          </Card>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 7. BACKEND & SYSTEM STATS                                                 */}
      {/* ========================================================================= */}
      {activeTab === "backend" && (
        <div className="space-y-4" id="settings-tab-backend">
          <Card padding={4} elevation="low">
            <div className="flex items-center gap-2 mb-4">
              <Server className="w-4 h-4 text-neutral-500" />
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                FastAPI Backend Endpoint
              </h3>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 dark:text-neutral-300 mb-1.5">
                  OnTheSpot FastAPI Server URL
                </label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <div className="flex-1">
                    <TextInput
                      label="Backend URL"
                      isLabelHidden={true}
                      value={localBackendUrl}
                      onChange={(val) => setLocalBackendUrl(val)}
                      placeholder="http://localhost:8000"
                      size="md"
                    />
                  </div>
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    label="Test Connection"
                    icon={<RefreshCw className="w-3.5 h-3.5" />}
                    onClick={handleTestConnection}
                    isLoading={isTestingConn}
                  />
                </div>
                <p className="text-[11px] text-neutral-500 mt-1">
                  Point this client UI to your local or remote OnTheSpot daemon instance.
                </p>
              </div>

              {connStatus !== "idle" && (
                <div
                  className={`p-3 rounded-lg border text-xs flex items-center gap-2.5 ${
                    connStatus === "connected"
                      ? "border-green-300 bg-green-50 dark:bg-green-950/20 text-green-800 dark:text-green-300"
                      : "border-red-300 bg-red-50 dark:bg-red-950/20 text-red-800 dark:text-red-300"
                  }`}
                >
                  <StatusDot
                    variant={connStatus === "connected" ? "success" : "error"}
                    label={connStatus === "connected" ? "Connected" : "Disconnected"}
                  />
                  <span>
                    {connStatus === "connected"
                      ? `Successfully connected to FastAPI daemon at ${localBackendUrl}`
                      : `Could not reach ${localBackendUrl}.`}
                  </span>
                </div>
              )}
            </div>
          </Card>

          <Card padding={4} elevation="low">
            <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 mb-3">
              Runtime Diagnostics &amp; Statistics
            </h3>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="p-3 rounded-lg bg-neutral-50 dark:bg-neutral-900/40 border border-neutral-200/60 dark:border-neutral-800">
                <span className="block text-[11px] font-medium text-neutral-500">Daemon Version</span>
                <span className="text-sm font-bold text-neutral-900 dark:text-neutral-100">
                  {config.version || "Unknown"}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-neutral-50 dark:bg-neutral-900/40 border border-neutral-200/60 dark:border-neutral-800">
                <span className="block text-[11px] font-medium text-neutral-500">Total Items Downloaded</span>
                <span className="text-sm font-bold text-neutral-900 dark:text-neutral-100">
                  {(config.total_downloaded_items ?? 0).toLocaleString()}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-neutral-50 dark:bg-neutral-900/40 border border-neutral-200/60 dark:border-neutral-800">
                <span className="block text-[11px] font-medium text-neutral-500">Total Data Downloaded</span>
                <span className="text-sm font-bold text-neutral-900 dark:text-neutral-100">
                  {formatBytes(config.total_downloaded_data ?? 0)}
                </span>
              </div>

              <div className="p-3 rounded-lg bg-neutral-50 dark:bg-neutral-900/40 border border-neutral-200/60 dark:border-neutral-800">
                <span className="block text-[11px] font-medium text-neutral-500">Authenticated Accounts</span>
                <span className="text-sm font-bold text-neutral-900 dark:text-neutral-100">
                  {config.accounts?.length ?? 0}
                </span>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
};