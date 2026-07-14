import React, { useEffect, useState } from "react";
import {
  Save,
  RotateCcw,
  Sliders,
  Music,
  Film,
  Tag,
  Search,
  Eye,
  Cpu,
  Check,
  Loader2,
  Download,
  Upload,
  Palette,
  Trash2,
  Archive,
  GripVertical,
} from "lucide-react";
import {
  CustomTheme,
  CustomThemePalette,
  DEFAULT_CUSTOM_THEME,
  OTSConfig,
  SavedCustomTheme,
  THEME_PRESETS,
  ThemeMode,
  ThemePreset,
} from "../types";
import { DownloadProfile, exportBackup, importBackup, saveBackupFile } from "../lib/api";
import { translate } from "../lib/i18n";
import { DownloadProfilesPanel } from "./DownloadProfilesPanel";
import { UpdatePanel } from "./UpdatePanel";

interface SettingsPageProps {
  initialSection?: SettingsSection;
  config: OTSConfig | null;
  onUpdateValue: (key: string, value: any) => Promise<boolean>;
  onSave: () => Promise<boolean>;
  onReset: () => Promise<void>;
  profiles: DownloadProfile[];
  activeProfile: string;
  onSaveProfile: (profile: DownloadProfile) => Promise<DownloadProfile | null>;
  onDeleteProfile: (profileId: string) => Promise<boolean>;
  onActivateProfile: (profileId: string) => Promise<boolean>;
  themePreset: ThemePreset;
  onThemeChange: (theme: ThemePreset) => Promise<void>;
  themeMode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => Promise<void>;
  customTheme: CustomTheme;
  onCustomThemeChange: (theme: CustomTheme) => Promise<void>;
  savedCustomThemes: SavedCustomTheme[];
  onSaveCustomTheme: (name: string) => Promise<boolean>;
  onLoadCustomTheme: (theme: SavedCustomTheme) => Promise<void>;
  onDeleteCustomTheme: (id: string) => Promise<void>;
}

export type SettingsSection =
  | "general"
  | "audio"
  | "profiles"
  | "video"
  | "metadata"
  | "search"
  | "display"
  | "backup";

type FormatterKey = "track_path_formatter" | "playlist_path_formatter";

const APPLICATION_LANGUAGES = [
  { value: "en_US", label: "English (United States)" },
  { value: "en_GB", label: "English (United Kingdom)" },
  { value: "es_ES", label: "Español (España)" },
  { value: "fr_FR", label: "Français (France)" },
  { value: "de_DE", label: "Deutsch (Deutschland)" },
  { value: "it_IT", label: "Italiano (Italia)" },
  { value: "nl_NL", label: "Nederlands (Nederland)" },
  { value: "pl_PL", label: "Polski (Polska)" },
  { value: "pt_BR", label: "Português (Brasil)" },
  { value: "ja_JP", label: "日本語" },
  { value: "ko_KR", label: "한국어" },
  { value: "zh_CN", label: "简体中文" },
  { value: "zh_TW", label: "繁體中文" },
  { value: "pt_PT", label: "Português (Portugal)" },
  { value: "tr_TR", label: "Türkçe (Türkiye)" },
  { value: "uk_UA", label: "Українська" },
] as const;

const SETTINGS_NAV_ITEMS: Array<{ id: SettingsSection; icon: React.ElementType; label: string }> = [
  { id: "search", icon: Search, label: "API config" },
  { id: "audio", icon: Music, label: "Audio Outputs" },
  { id: "backup", icon: Archive, label: "Backup & Restore" },
  { id: "display", icon: Eye, label: "Display Settings" },
  { id: "profiles", icon: Download, label: "Download Profiles" },
  { id: "general", icon: Cpu, label: "General & Workers" },
  { id: "metadata", icon: Tag, label: "ID3 Tagging" },
  { id: "video", icon: Film, label: "Video Media" },
];

const readSettingsNavOrder = (): SettingsSection[] => {
  try {
    const stored = JSON.parse(window.localStorage.getItem("ots-settings-nav-order") || "[]");
    if (Array.isArray(stored)) {
      const valid = stored.filter((id): id is SettingsSection => SETTINGS_NAV_ITEMS.some((item) => item.id === id));
      if (valid.length === SETTINGS_NAV_ITEMS.length) return valid;
    }
  } catch { /* Use the default order. */ }
  return SETTINGS_NAV_ITEMS.map((item) => item.id);
};

export const SettingsPage: React.FC<SettingsPageProps> = ({
  initialSection,
  config,
  onUpdateValue,
  onSave,
  onReset,
  profiles,
  activeProfile,
  onSaveProfile,
  onDeleteProfile,
  onActivateProfile,
  themePreset,
  onThemeChange,
  themeMode,
  onThemeModeChange,
  customTheme,
  onCustomThemeChange,
  savedCustomThemes,
  onSaveCustomTheme,
  onLoadCustomTheme,
  onDeleteCustomTheme,
}) => {
  const [section, setSection] = useState<SettingsSection>(initialSection || "general");
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [customThemeName, setCustomThemeName] = useState("");
  const [customThemeMessage, setCustomThemeMessage] = useState("");
  const [backupMessage, setBackupMessage] = useState("");
  const [formatterTarget, setFormatterTarget] = useState<FormatterKey>("track_path_formatter");
  const [settingsNavOrder, setSettingsNavOrder] = useState<SettingsSection[]>(readSettingsNavOrder);
  const [editingSettingsNav, setEditingSettingsNav] = useState(false);
  const [draggedSettingsNav, setDraggedSettingsNav] = useState<SettingsSection | null>(null);
  const activeCustomPalette = customTheme[themeMode];

  useEffect(() => {
    if (initialSection) setSection(initialSection);
  }, [initialSection]);

  if (!config) {
    return (
      <div className="p-20 flex justify-center items-center text-gray-500 dark:text-neutral-500 font-sans text-sm">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        Loading configuration...
      </div>
    );
  }

  const handleToggle = async (key: string, currentVal: boolean) => {
    await onUpdateValue(key, !currentVal);
  };

  const handleTextChange = (key: string, val: string | number) => {
    onUpdateValue(key, val);
  };

  const handleApplicationLanguageChange = async (language: string) => {
    const languageIndex = APPLICATION_LANGUAGES.findIndex((option) => option.value === language);
    await onUpdateValue("language", language);
    await onUpdateValue("language_index", Math.max(languageIndex, 0));
  };

  const insertFormatterVariable = async (variable: string) => {
    const input = document.getElementById(`setting-${formatterTarget}`) as HTMLInputElement | null;
    const current = String(config[formatterTarget] ?? "");
    const start = input?.selectionStart ?? current.length;
    const end = input?.selectionEnd ?? start;
    const token = `{${variable}}`;
    const next = `${current.slice(0, start)}${token}${current.slice(end)}`;
    await onUpdateValue(formatterTarget, next);
    window.requestAnimationFrame(() => {
      const updatedInput = document.getElementById(`setting-${formatterTarget}`) as HTMLInputElement | null;
      updatedInput?.focus();
      updatedInput?.setSelectionRange(start + token.length, start + token.length);
    });
  };

  const handleCustomPaletteColorChange = (key: keyof CustomThemePalette, value: string) => {
    void onCustomThemeChange({
      ...customTheme,
      mode: themeMode,
      [themeMode]: {
        ...activeCustomPalette,
        [key]: value,
      },
    });
  };

  const handleSaveNamedCustomTheme = async () => {
    const saved = await onSaveCustomTheme(customThemeName);
    if (!saved) {
      setCustomThemeMessage("Enter a name before saving this palette.");
      return;
    }
    setCustomThemeMessage("Theme saved. Saving the same name updates it.");
    setCustomThemeName("");
  };

  const triggerSave = async () => {
    setSaving(true);
    const ok = await onSave();
    setSaving(false);
    if (ok) {
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 3000);
    }
  };

  const triggerReset = async () => {
    if (confirm("Are you sure you want to reset all settings to defaults?")) {
      setResetting(true);
      await onReset();
      setResetting(false);
    }
  };

  const triggerExport = async () => {
    const data = await exportBackup();
    if (!data) return;
    const themes = {
      preset: window.localStorage.getItem("ots-theme-preset"),
      mode: window.localStorage.getItem("ots-theme-mode"),
      custom: window.localStorage.getItem("ots-custom-theme"),
      saved: window.localStorage.getItem("ots-custom-themes"),
    };
    const path = await saveBackupFile({ ...data, themes }, config?.export_folder_path || "");
    setBackupMessage(path ? `Backup saved to ${path}` : "Could not save the backup. Check the default export folder and try again.");
  };

  const triggerImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const data = JSON.parse(await file.text());
      if (await importBackup(data)) {
        const themes = data?.themes;
        if (themes && typeof themes === "object") {
          const bundle = themes as Record<string, unknown>;
          if (typeof bundle.preset === "string") window.localStorage.setItem("ots-theme-preset", bundle.preset);
          if (typeof bundle.mode === "string") window.localStorage.setItem("ots-theme-mode", bundle.mode);
          if (typeof bundle.custom === "string") window.localStorage.setItem("ots-custom-theme", bundle.custom);
          if (typeof bundle.saved === "string") window.localStorage.setItem("ots-custom-themes", bundle.saved);
        }
        window.location.reload();
      }
    } catch {
      window.alert("That settings file is not valid JSON.");
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  };

  // Material Design 3 Styled Switch
  const renderToggle = (
    key: string,
    label: string,
    desc?: string,
    disabled: boolean = false,
  ) => {
    const isChecked = config[key];
    return (
      <div key={key} className="flex items-start justify-between py-3">
        <div className="pr-4 flex-1">
          <label
            className="text-sm font-medium text-gray-900 dark:text-neutral-100 cursor-pointer select-none"
            onClick={() => !disabled && handleToggle(key, isChecked)}
          >
            {label}
          </label>
          {desc && (
            <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1 leading-relaxed">
              {desc}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => handleToggle(key, isChecked)}
          disabled={disabled}
          className={`ots-toggle ${isChecked ? "ots-toggle-on" : "ots-toggle-off"} ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <span
            className={`ots-toggle-thumb ${
              isChecked ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>
    );
  };

  // Material Design 3 Styled Input
  const renderInput = (
    key: string,
    label: string,
    type: "text" | "number" | "password" = "text",
    desc?: string,
  ) => (
    <div key={key} className="flex flex-col gap-1.5 py-2 w-full">
      <label className="text-sm font-medium text-gray-900 dark:text-neutral-100">
        {label}
      </label>
      <input
        id={`setting-${key}`}
        type={type}
        value={config[key] ?? ""}
        onFocus={() => {
          if (key === "track_path_formatter" || key === "playlist_path_formatter") {
            setFormatterTarget(key);
          }
        }}
        onChange={(e) =>
          handleTextChange(
            key,
            type === "number" ? Number(e.target.value) : e.target.value,
          )
        }
        className="ots-input w-full text-sm"
      />
      {desc && (
        <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5 leading-relaxed">
          {desc}
        </p>
      )}
    </div>
  );

  // Material Design 3 Styled Select
  const renderSelect = (
    key: string,
    label: string,
    options: { val: string | number; text: string }[],
    desc?: string,
  ) => (
    <div key={key} className="flex flex-col gap-1.5 py-2 w-full">
      <label className="text-sm font-medium text-gray-900 dark:text-neutral-100">
        {label}
      </label>
      <select
        value={config[key] ?? options[0].val}
        onChange={(e) => handleTextChange(key, e.target.value)}
        className="ots-select w-full cursor-pointer appearance-none text-sm"
      >
        {options.map((opt) => (
          <option key={String(opt.val)} value={opt.val}>
            {opt.text}
          </option>
        ))}
      </select>
      {desc && (
        <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5 leading-relaxed">
          {desc}
        </p>
      )}
    </div>
  );

  const NavButton = ({
    id,
    icon: Icon,
    label,
  }: {
    id: SettingsSection;
    icon: any;
    label: string;
  }) => {
    const isActive = section === id;
    return (
      <button
        draggable={editingSettingsNav}
        onDragStart={() => setDraggedSettingsNav(id)}
        onDragOver={(event) => { if (editingSettingsNav) event.preventDefault(); }}
        onDrop={(event) => { event.preventDefault(); if (!draggedSettingsNav || draggedSettingsNav === id) return; setSettingsNavOrder((current) => { const next = [...current]; const from = next.indexOf(draggedSettingsNav); const to = next.indexOf(id); next.splice(from, 1); next.splice(to, 0, draggedSettingsNav); window.localStorage.setItem("ots-settings-nav-order", JSON.stringify(next)); return next; }); setDraggedSettingsNav(null); }}
        onDragEnd={() => setDraggedSettingsNav(null)}
        onClick={() => setSection(id)}
        className={`ots-nav-item flex w-full shrink-0 items-center gap-3 text-left text-sm font-bold transition-colors lg:shrink ${editingSettingsNav ? "cursor-grab" : ""} ${
          isActive
            ? "ots-nav-item-active"
            : "text-[#8f8f8f] hover:bg-[#242424] hover:text-white"
        }`}
      >
        {editingSettingsNav && <GripVertical className="h-4 w-4 shrink-0 text-[#777]" aria-label="Drag to reorder" />}
        <Icon className="w-[18px] h-[18px]" />
        <span>{label}</span>
      </button>
    );
  };

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">
      {/* App Bar / Header */}
      <div className="ots-hero flex flex-col justify-between gap-4 p-6 md:flex-row md:items-center">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-white">
            <Sliders className="h-5 w-5 text-[#1ed760]" />
            System Configuration
          </h2>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            Configurations sync automatically with the OnTheSpot service •
            Version {config.version}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={triggerReset}
            disabled={resetting}
            className="ots-button ots-button-danger"
          >
            <RotateCcw className="w-4 h-4" />
            <span>{resetting ? "Resetting..." : "Factory Reset"}</span>
          </button>

          <button
            onClick={triggerSave}
            disabled={saving}
            className="ots-button ots-button-primary px-6 text-sm"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : savedSuccess ? (
              <Check className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>{savedSuccess ? "Config Saved!" : "Save Config"}</span>
          </button>
        </div>
      </div>

      {/* Main Layout Grid */}
      <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-4">
        {/* Navigation Sidebar */}
        <div className="lg:sticky lg:top-8 lg:col-span-1">
          <div className="ots-panel flex flex-row gap-1 overflow-x-auto p-2 shadow-xl shadow-black/10 lg:flex-col">
            {settingsNavOrder.map((id) => { const item = SETTINGS_NAV_ITEMS.find((candidate) => candidate.id === id)!; return <NavButton key={item.id} {...item} />; })}
          </div>
          <button
            type="button"
            onClick={() => setEditingSettingsNav((current) => !current)}
            className={`ots-nav-item mt-2 hidden w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-semibold transition-colors focus:outline-none lg:flex ${
              editingSettingsNav
                ? "bg-[#282828] text-white"
                : "text-[#b3b3b3] hover:bg-[#1f1f1f] hover:text-white"
            }`}
            aria-pressed={editingSettingsNav}
          >
            <GripVertical className="h-5 w-5" />
            <span>{editingSettingsNav ? translate(config.language, "done_editing", "Done editing") : translate(config.language, "edit_sections", "Edit sections")}</span>
          </button>
        </div>

        {/* Content Panels */}
        <div className="ots-panel ots-settings-content flex flex-col p-5 md:p-6 lg:col-span-3">
          {/* GENERAL SECTION */}
          {section === "general" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
                  System Variables & Workers
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Configure worker threads, download delays, and global
                  application options.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6">
                {renderInput(
                  "maximum_download_workers",
                  "Maximum Download Workers",
                  "number",
                  "Concurrent song conversion threads",
                )}
                {renderInput(
                  "maximum_queue_workers",
                  "Maximum Queue Workers",
                  "number",
                  "Concurrent playlist item parsing threads",
                )}
                {renderInput(
                  "download_delay",
                  "Download Delay (seconds)",
                  "number",
                  "Wait time between consecutive download requests",
                )}
                {renderInput(
                  "download_chunk_size",
                  "Download Chunk Size (bytes)",
                  "number",
                  "Streaming media chunk size",
                )}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 border-t border-gray-100 dark:border-neutral-800/60">
                {renderToggle(
                  "raw_media_download",
                  "Raw Media Download",
                  "Skip media conversion and ID3 metadata writing",
                )}
                {renderToggle(
                  "enable_retry_worker",
                  "Enable Retry Worker",
                  "Automatically retry failed downloads",
                )}
                {renderInput(
                  "retry_worker_delay",
                  "Retry Worker Delay (minutes)",
                  "number",
                  "Delay between retry attempts in minutes",
                )}
                {renderToggle(
                  "use_double_digit_path_numbers",
                  "Double Digit Track Numbers",
                  "Format track numbers as 01, 02 instead of 1, 2",
                )}
                {renderToggle(
                  "debug_mode",
                  "Enable Debug Mode",
                  "Enables verbose logging and internal application debugging features",
                )}
                {renderToggle(
                  "rotate_active_account_number",
                  "Rotate Active Account Number",
                  "Cycle through available accounts automatically",
                )}
                <div className="py-2">
                  {renderInput(
                    "download_delay_variance",
                    "Download Delay Variance (s)",
                    "number",
                    "Random variance added to base download delay",
                  )}
                </div>
                {renderToggle(
                  "check_for_updates",
                  "Automatically check for updates",
                  "Check the configured release feed in the background and notify you when a new version is available",
                )}
                <div className="flex flex-col gap-1.5 py-4">
                  <label
                    htmlFor="application-language"
                    className="text-sm font-medium text-gray-900 dark:text-neutral-100"
                  >
                    {translate(config.language, "application_language", "Application Language")}
                  </label>
                  <select
                    id="application-language"
                    value={APPLICATION_LANGUAGES.some((option) => option.value === config.language) ? config.language : "en_US"}
                    onChange={(event) => void handleApplicationLanguageChange(event.target.value)}
                    className="ots-select w-full cursor-pointer appearance-none text-sm"
                  >
                    {APPLICATION_LANGUAGES.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5 leading-relaxed">
                    Uses the bundled application language pack. Your library metadata and filenames are never sent to a translation service.
                  </p>
                </div>
                <div className="py-2">
                  {renderInput(
                    "ffmpeg_args",
                    "FFmpeg Arguments (Experimental)",
                    "text",
                    "List [] of custom ffmpeg arguments",
                  )}
                  {renderInput(
                    "explicit_label",
                    "Explicit Label",
                    "text",
                    "Label to apply to explicit songs",
                  )}
                  {renderInput(
                    "illegal_character_replacement",
                    "Illegal Character Replacement",
                    "text",
                    "Replace illegal characters in filenames with this string",
                  )}
                </div>
              </div>
              <UpdatePanel currentVersion={config.version} />
            </div>
          )}

          {/* AUDIO SECTION */}
          {section === "audio" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
                  Audio Formatting & Output
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Set root music folder, preferred codecs, bitrates, and folder
                  formatters.
                </p>
              </div>

              <div className="mb-6">
                {renderInput(
                  "audio_download_path",
                  "Audio Download Root Path",
                  "text",
                  "Absolute folder path on host filesystem",
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                <div className="sm:col-span-2 divide-y divide-gray-100 dark:divide-neutral-800/60 mb-2 border-b border-gray-100 dark:border-neutral-800/60">
                  {renderToggle(
                    "use_source_format",
                    "Use Source Format",
                    "Uses the best source quality and format directly",
                  )}
                  {renderToggle(
                    "use_custom_file_bitrate",
                    "Use Custom Bitrate",
                    "Enforces files to output using target bitrate selections",
                  )}
                </div>
                {renderSelect(
                  "track_file_format",
                  "Track Media Format",
                  [
                    { val: "flac", text: "FLAC (Lossless HiRes)" },
                    { val: "mp3", text: "MP3 (Universal 320k)" },
                    { val: "m4a", text: "M4A / AAC" },
                    { val: "opus", text: "Opus (High Efficiency)" },
                    { val: "wav", text: "WAV (Uncompressed)" },
                    { val: "ogg", text: "Vorbis Ogg" },
                  ],
                  "Download container if standard source formats are disabled.",
                )}
                {renderSelect(
                  "file_bitrate",
                  "Converted Track File Bitrate",
                  [
                    { val: "320k", text: "320 kbps (Maximum Quality)" },
                    { val: "256k", text: "256 kbps (High)" },
                    { val: "192k", text: "192 kbps (Medium)" },
                    { val: "128k", text: "128 kbps (Standard)" },
                  ],
                  "Download bitrate conversion output when custom bitrates are enabled.",
                )}
                {renderSelect(
                  "podcast_file_format",
                  "Podcast File Format",
                  [
                    { val: "mp3", text: "MP3 (Medium Quality)" },
                    { val: "ogg", text: "Vorbis Ogg (High Quality)" },
                    { val: "wav", text: "WAV (Compatible)" },
                  ],
                  "Download format for podcast files.",
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                {renderInput(
                  "track_path_formatter",
                  "Track Path Formatter",
                  "text",
                  "Variables: {album_artist}, {album}, {year}, {track_number}, {name}",
                )}
                {renderInput(
                  "playlist_path_formatter",
                  "Playlist Path Formatter",
                  "text",
                  "Variables: {playlist_name}, {playlist_owner}, {playlist_number}, {artist}",
                )}
                {renderInput(
                  "podcast_path_formatter",
                  "Podcast Path Formatter",
                  "text",
                  "Variables: {podcast_name}, {podcast_owner}, {episode_number}, {artist}",
                )}
                {renderInput(
                  "m3u_path_formatter",
                  "M3U Playlist Path Formatter",
                  "text",
                  "Variables: {playlist_name}, {playlist_owner}, {playlist_number}",
                )}
              </div>

              <div className="mb-6 border-t border-gray-100 pt-6 dark:border-neutral-800/60">
                <div className="mb-4">
                  <h4 className="flex items-center gap-2 text-base font-bold text-gray-900 dark:text-neutral-100">Playlist folder organization</h4>
                  <p className="mt-1 text-xs text-gray-500 dark:text-neutral-400">Keep playlist downloads together and choose the folder and filename pattern used for tracks from playlists.</p>
                </div>
                {renderToggle(
                  "use_playlist_path",
                  "Organize playlist downloads into folders",
                  "Enable this to use the Playlist Path Formatter below instead of the regular track formatter for playlist downloads.",
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <span className="w-full text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-neutral-400">Track template presets</span>
                  {[
                    ["Artist / Album / Track", "Tracks/{album_artist}/{album}/{track_number} - {name}"],
                    ["Album / Track", "Tracks/{album}/{track_number} - {name}"],
                  ].map(([label, value]) => <button key={value} type="button" onClick={() => void onUpdateValue("track_path_formatter", value)} className="ots-button ots-button-secondary text-xs">{label}</button>)}
                  <span className="mt-2 w-full text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-neutral-400">Playlist folder presets</span>
                  {[
                    ["Playlist / Artist", "Playlists/{playlist_name}/{artist}/{track_number} - {name}"],
                    ["Playlist / Album", "Playlists/{playlist_name}/{album}/{track_number} - {name}"],
                  ].map(([label, value]) => <button key={value} type="button" onClick={() => void onUpdateValue("playlist_path_formatter", value)} className="ots-button ots-button-secondary text-xs">{label}</button>)}
                </div>
                <div className="mt-4 border-t border-gray-100 pt-4 dark:border-neutral-800/60">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-full text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-neutral-400">Build a custom formatter</span>
                    {(["track_path_formatter", "playlist_path_formatter"] as FormatterKey[]).map((key) => (
                      <button key={key} type="button" onClick={() => { setFormatterTarget(key); document.getElementById(`setting-${key}`)?.focus(); }} className={`ots-button text-xs ${formatterTarget === key ? "ots-button-primary" : "ots-button-secondary"}`}>
                        {key === "track_path_formatter" ? "Track formatter" : "Playlist formatter"}
                      </button>
                    ))}
                    <span className="text-xs text-gray-500 dark:text-neutral-400">Click a variable to insert it into the selected formatter.</span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(formatterTarget === "track_path_formatter"
                      ? ["album_artist", "artist", "album", "year", "track_number", "name"]
                      : ["playlist_name", "playlist_owner", "playlist_number", "artist", "album", "track_number", "name"]
                    ).map((variable) => (
                      <button key={variable} type="button" onClick={() => void insertFormatterVariable(variable)} className="ots-button ots-button-secondary text-xs font-mono">&#123;{variable}&#125;</button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                <div className="py-2">
                  {renderSelect(
                    "m3u_format",
                    "M3U Playlist Format",
                    [
                      { val: "m3u8", text: "M3U8" },
                      { val: "m3u", text: "M3U (Standard)" },
                    ],
                    "Format wrapper for generated local playlist files",
                  )}
                </div>
                {renderToggle(
                  "create_m3u_file",
                  "Create M3U Playlist File",
                  "Generate playlist index files next to downloaded items",
                )}
                {renderToggle(
                  "save_album_cover",
                  "Save Cover Art To Folder",
                  "Save folder.jpg or cover.png inside album directories",
                )}
                {renderToggle(
                  "windows_10_explorer_thumbnails",
                  "Windows 10 Explorer Thumbnails",
                  "Enable Windows 10 thumbnail support for downloaded tracks",
                )}
                {renderToggle(
                  "download_lyrics",
                  "Download Lyrics",
                  "Fetch synchronized or plain-text lyric files",
                )}
                {config.download_lyrics && (
                  <div>
                    {renderToggle(
                      "save_lrc_file",
                      "Save .LRC Lyrics File",
                      "Export synced lyric timestamps as standalone .lrc assets",
                    )}
                    {renderToggle(
                      "only_download_synced_lyrics",
                      "Only Download Synced Lyrics",
                      "Download only synced lyrics files (if available)",
                    )}
                    {renderToggle(
                      "only_download_plain_lyrics",
                      "Only Download Plain Text Lyrics",
                      "Download only plain-text lyric files (if available)",
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* DOWNLOAD PROFILES SECTION */}
          {section === "profiles" && (
            <DownloadProfilesPanel
              profiles={profiles}
              activeProfile={activeProfile}
              onSave={onSaveProfile}
              onDelete={onDeleteProfile}
              onActivate={onActivateProfile}
            />
          )}

          {/* VIDEO SECTION */}
          {section === "video" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
                  Video, Movies & Anime Settings
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Configure resolution preferences and container formatting for
                  video media.
                </p>
              </div>

              <div className="mb-6">
                {renderInput(
                  "video_download_path",
                  "Video Download Root Path",
                  "text",
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6">
                {renderSelect("movie_file_format", "Movie Container Format", [
                  { val: "mkv", text: "MKV (Matroska Container)" },
                  { val: "mp4", text: "MP4 (Standard Video)" },
                ])}
                {renderSelect(
                  "preferred_video_resolution",
                  "Preferred Video Resolution",
                  [
                    { val: 1080, text: "1080p (Full HD)" },
                    { val: 720, text: "720p (HD)" },
                    { val: 2160, text: "4K (Ultra HD)" },
                  ],
                )}
                {renderSelect("show_file_format", "Show Container Format", [
                  { val: "mkv", text: "MKV (Matroska Container)" },
                  { val: "mp4", text: "MP4 (Standard Video)" },
                ])}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                {renderInput(
                  "movie_path_formatter",
                  "Movie Path Formatter",
                  "text",
                )}
                {renderInput(
                  "show_path_formatter",
                  "TV Show Path Formatter",
                  "text",
                )}
                {renderInput(
                  "preferred_audio_language",
                  "Preferred Audio Language Code",
                  "text",
                  "Target stream language code (e.g., en-US)",
                )}
                {renderInput(
                  "preferred_subtitle_language",
                  "Preferred Subtitle Language Code",
                  "text",
                  "Target subtitle language code (e.g., en-US)",
                )}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                {renderToggle(
                  "download_subtitles",
                  "Download Subtitles",
                  "Extract and embed soft subtitles or save external .srt components",
                )}
                {renderToggle(
                  "download_chapters",
                  "Download Video Chapters",
                  "Preserve internal chapter segment markers",
                )}
                {renderToggle(
                  "download_all_available_audio",
                  "Download All Available Audio Tracks",
                  "Include alternative language audio dubs",
                )}
                {renderToggle(
                  "download_all_available_subtitles",
                  "Download All Available Subtitles",
                  "Include alternative language subtitles dubs",
                )}
              </div>

              {/* V2A Section */}
              <div className="mt-8 pt-8 border-t border-gray-100 dark:border-neutral-800/60">
                <div className="bg-blue-50 dark:bg-blue-900/10 rounded-2xl p-6 border border-blue-100 dark:border-blue-900/30">
                  <h4 className="text-base font-medium text-gray-900 dark:text-neutral-100 mb-1">
                    Video to Audio Extraction (V2A)
                  </h4>
                  <p className="text-sm text-gray-500 dark:text-neutral-400 mb-4">
                    Strip output and save audio streams only when downloading
                    video sources.
                  </p>

                  {renderToggle(
                    "v2a_enable",
                    "Enable Audio Extraction",
                    "Discard video components and convert tracks to designated format",
                  )}

                  {config.v2a_enable && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 mt-6 pt-6 border-t border-blue-200/50 dark:border-blue-800/30 animate-[fadeIn_0.2s_ease-out]">
                      {renderSelect(
                        "v2a_preferred_codec",
                        "Preferred Audio Codec",
                        [
                          { val: "opus", text: "Opus (High Efficiency)" },
                          { val: "m4a", text: "M4A / AAC" },
                          { val: "mp3", text: "MP3 (Standard)" },
                          { val: "flac", text: "FLAC (Lossless)" },
                          { val: "wav", text: "WAV (Uncompressed)" },
                        ],
                        "Output file compression profile",
                      )}
                      {renderInput(
                        "v2a_preferred_bitrate",
                        "Preferred Audio Bitrate (kbps)",
                        "number",
                        "Target bitrate limit (e.g., 256, 320)",
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* METADATA SECTION */}
          {section === "metadata" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
                  ID3 Metadata Tagging
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Select exactly which metadata tags to inject into downloaded
                  music tracks.
                </p>
              </div>

              <div className="mb-6 max-w-md">
                {renderSelect(
                  "album_cover_format",
                  "Cover Art Compression Format",
                  [
                    { val: "png", text: "PNG (Lossless Quality, Larger Size)" },
                    {
                      val: "jpeg",
                      text: "JPEG (Efficient Compression, Smaller Size)",
                    },
                  ],
                )}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 divide-y sm:divide-y-0 divide-gray-100 dark:divide-neutral-800/60 mb-8 border-t border-gray-100 dark:border-neutral-800/60 pt-4">
                {renderToggle("embed_cover", "Embed Cover Art")}
                {renderToggle("embed_artist", "Embed Artist")}
                {renderToggle("embed_album", "Embed Album")}
                {renderToggle("embed_albumartist", "Embed Album Artist")}
                {renderToggle("embed_name", "Embed Title")}
                {renderToggle("embed_year", "Embed Release Year")}
                {renderToggle("embed_length", "Embed Duration")}

                {renderToggle("embed_tracknumber", "Embed Track Number")}
                {renderToggle("embed_discnumber", "Embed Disc Number")}
                {renderToggle("embed_genre", "Embed Genre")}
                {renderToggle("embed_lyrics", "Embed Lyrics")}
                {renderToggle("embed_label", "Embed Record Label")}
                {renderToggle("embed_copyright", "Embed Copyright")}
                {renderToggle("embed_isrc", "Embed ISRC Code")}
                {renderToggle("embed_upc", "Embed UPC ")}
                {renderToggle("embed_service_id", "Embed Service ID")}
                {renderToggle("embed_bpm", "Embed BPM / Tempo")}
                {renderToggle("embed_key", "Embed Musical Key")}
                {renderToggle("embed_producers", "Embed Producers")}
                {renderToggle("embed_writers", "Embed Writers")}
                {renderToggle("embed_explicit", "Embed Explicit Tag")}
                {renderToggle("embed_composer", "Embed Composer")}
                {renderToggle(
                  "prefer_composer_as_album_artist",
                  "Use Composer as Album Artist",
                )}
                {renderToggle("embed_performers", "Embed Performers")}
                {renderToggle("embed_description", "Embed Description")}
                {renderToggle("embed_language", "Embed Language")}
                {renderToggle("embed_url", "Embed URL")}
              </div>
              <div className="mb-6">
                {renderToggle(
                  "overwrite_existing_metadata",
                  "Overwrite Existing Metadata",
                  "Overwrite existing metadata tags if file exists",
                )}
              </div>
              <div className="pt-6 border-t border-gray-100 dark:border-neutral-800/60 mb-6">
                <h4 className="text-sm font-medium text-blue-600 dark:text-blue-400 mb-4">
                  Spotify Specific Fields (Requires Audio Features API)
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 divide-y sm:divide-y-0 divide-gray-100 dark:divide-neutral-800/60">
                  {renderToggle("embed_timesignature", "Embed Time Signature")}
                  {renderToggle("embed_acousticness", "Embed Acousticness")}
                  {renderToggle("embed_danceability", "Embed Danceability")}
                  {renderToggle("embed_energy", "Embed Energy")}
                  {renderToggle(
                    "embed_instrumentalness",
                    "Embed Instrumentalness",
                  )}
                  {renderToggle("embed_liveness", "Embed Liveness")}
                  {renderToggle("embed_loudness", "Embed Loudness")}
                  {renderToggle("embed_speechiness", "Embed Speechiness")}
                  {renderToggle("embed_valence", "Embed Valence")}
                </div>
              </div>

              <div className="w-full border-t border-gray-100 pt-6 dark:border-neutral-800/60">
                {renderInput(
                  "metadata_separator",
                  "Metadata Value Separator",
                  "text",
                  'Separation character for multi-value tags (e.g. "; ")',
                )}
              </div>
            </div>
          )}

          {/* SEARCH SECTION */}
          {section === "search" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
                  API Configuration
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Optimize third-party platform API limits and toggle library
                  source scopes.
                </p>
              </div>

              <div className="ots-settings-section mb-8">
                <h4 className="ots-settings-section-title mb-4 flex items-center gap-2">
                  <Sliders className="w-4 h-4" /> API Call Reduction Settings
                </h4>
                <div className="ots-settings-divider">
                  {renderToggle(
                    "cache_api_calls",
                    "Cache API Calls",
                    "Reuses safe public catalogue responses to reduce API usage",
                  )}
                  {renderToggle(
                    "fetch_genre_metadata",
                    "Fetch Genre from Artist Endpoint",
                    "Requires +1 additional query per processed track",
                  )}
                  {renderToggle(
                    "fetch_extended_album_metadata",
                    "Fetch Extra Album Metadata",
                    "Requires +1 additional query per processed track",
                  )}
                  {renderToggle(
                    "fetch_audio_features",
                    "Fetch Audio Features",
                    "Requires +1 additional query per processed track",
                  )}
                  {renderToggle(
                    "fetch_track_credits",
                    "Fetch Record Label & Copyright",
                    "Requires +1 additional query per processed track",
                  )}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4">
                    {renderInput(
                      "spotify_search_cache_ttl_seconds",
                      "Spotify Search Cache (seconds)",
                      "number",
                      "Cache public catalogue searches for this long",
                    )}
                    {renderInput(
                      "spotify_metadata_cache_ttl_seconds",
                      "Spotify Metadata Cache (seconds)",
                      "number",
                      "Cache public track, album, artist, and episode data",
                    )}
                    {renderInput(
                      "api_response_cache_ttl_seconds",
                      "Other Public API Cache (seconds)",
                      "number",
                      "Cache unauthenticated public API responses",
                    )}
                    {renderInput(
                      "playlist_automation_cache_ttl_seconds",
                      "Playlist Sorting Cache (seconds)",
                      "number",
                      "Keep playlist reads in memory per signed-in account",
                    )}
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4">
                    {renderInput(
                      "spotify_webapi_override_client_id",
                      "Spotify Client ID",
                      "text",
                    )}
                    {renderInput(
                      "spotify_webapi_override_client_secret",
                      "Spotify Client Secret",
                      "password",
                      config.spotify_webapi_override_client_secret_configured
                        ? "A secret is configured. Enter a value only to replace it."
                        : "Required for Spotify catalogue and playlist-sorting API access.",
                    )}
                  </div>
                </div>
              </div>

              <div className="mb-8">
                <h4 className="text-base font-medium text-gray-900 dark:text-neutral-100 mb-4">
                  Enabled Search Categories
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 divide-y sm:divide-y-0 divide-gray-100 dark:divide-neutral-800/60 border border-gray-200 dark:border-neutral-800/60 rounded-xl p-4">
                  {renderToggle("enable_search_tracks", "Search Tracks")}
                  {renderToggle("enable_search_albums", "Search Albums")}
                  {renderToggle("enable_search_playlists", "Search Playlists")}
                  {renderToggle("enable_search_artists", "Search Artists")}
                  {renderToggle("enable_search_podcasts", "Search Podcasts")}
                  {renderToggle("enable_search_episodes", "Search Episodes")}
                  {renderToggle(
                    "enable_search_audiobooks",
                    "Search Audiobooks",
                  )}
                </div>
              </div>

              <div className="pt-6 border-t border-gray-100 dark:border-neutral-800/60 max-w-md">
                {renderInput(
                  "search_prefix",
                  "Default Search Prefix",
                  "text",
                  'Fallback search prefix parameter (e.g., "the")',
                )}
              </div>
            </div>
          )}

          {/* DISPLAY SECTION */}
          {section === "display" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">
                  Web UI & Display Controls
                </h3>
                <p className="text-sm text-gray-500 mt-1">
                  Customize dashboard thumbnails, action controls, and
                  notification popups.
                </p>
              </div>

              <div className="mb-8 border-b border-gray-200 pb-6 dark:border-neutral-800/60">
                <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <h4 className="text-base font-medium text-gray-900 dark:text-neutral-100">Theme</h4>
                    <p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">
                      Choose a colour palette for the whole app. The Light/Dark control changes the mode for every palette, and your selection is saved in this browser.
                    </p>
                  </div>
                  <div className="ots-segmented" role="group" aria-label="Theme mode">
                    <button
                      type="button"
                      aria-pressed={themeMode === "dark"}
                      className={`ots-segment ${themeMode === "dark" ? "ots-segment-active" : ""}`}
                      onClick={() => void onThemeModeChange("dark")}
                    >
                      Dark
                    </button>
                    <button
                      type="button"
                      aria-pressed={themeMode === "light"}
                      className={`ots-segment ${themeMode === "light" ? "ots-segment-active" : ""}`}
                      onClick={() => void onThemeModeChange("light")}
                    >
                      Light
                    </button>
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {THEME_PRESETS.map((theme) => {
                    const isSelected = themePreset === theme.id;
                    const swatches = theme.id === "custom"
                      ? [activeCustomPalette.background, activeCustomPalette.accent, activeCustomPalette.text] as [string, string, string]
                      : theme.swatches;
                    const mode = themeMode;
                    return (
                      <button
                        key={theme.id}
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => void onThemeChange(theme.id)}
                        className={`ots-theme-option ${isSelected ? "ots-theme-option-active" : ""}`}
                      >
                        <span className="ots-theme-preview" aria-hidden="true">
                          {swatches.map((swatch) => <span key={swatch} style={{ backgroundColor: swatch }} />)}
                        </span>
                        <span className="min-w-0 text-left">
                          <span className="flex items-center gap-2 text-sm font-bold">
                            {theme.label}
                            <span className="ots-theme-mode">{mode}</span>
                          </span>
                          <span className="mt-1 block text-xs text-gray-500 dark:text-neutral-400">{theme.description}</span>
                        </span>
                        <span className={`ots-theme-check ${isSelected ? "ots-theme-check-visible" : ""}`} aria-hidden="true">✓</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {themePreset === "custom" && (
                <div className="mb-8 border-b border-gray-200 pb-6 dark:border-neutral-800/60">
                  <div className="mb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <Palette className="h-4 w-4 text-[var(--spotify-green)]" />
                        <h4 className="text-base font-medium text-gray-900 dark:text-neutral-100">Custom palette</h4>
                      </div>
                      <p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">
                        Pick the colors that should shape the app. Changes apply immediately and are saved in this browser.
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {([
                      ["background", "Background", "The page background."],
                      ["surface", "Panels", "Cards and main surfaces."],
                      ["elevated", "Elevated", "Raised controls and active cards."],
                      ["accent", "Accent", "Highlights and primary actions."],
                      ["text", "Text", "Main readable text."],
                      ["muted", "Muted text", "Secondary labels and hints."],
                    ] as Array<[keyof CustomThemePalette, string, string]>).map(([key, label, description]) => (
                      <label key={key} className="ots-color-control">
                        <span className="min-w-0">
                          <span className="block text-sm font-semibold text-gray-900 dark:text-neutral-100">{label}</span>
                          <span className="mt-1 block text-xs text-gray-500 dark:text-neutral-400">{description}</span>
                        </span>
                        <span className="flex items-center gap-2">
                          <input
                            aria-label={label}
                            type="color"
                            value={activeCustomPalette[key]}
                            onChange={(event) => handleCustomPaletteColorChange(key, event.target.value)}
                          />
                          <code>{activeCustomPalette[key].toUpperCase()}</code>
                        </span>
                      </label>
                    ))}
                  </div>

                  <div className="mt-5 border-t border-gray-200 pt-5 dark:border-neutral-800/60">
                    <div className="mb-3">
                      <h5 className="text-sm font-semibold text-gray-900 dark:text-neutral-100">Saved custom themes</h5>
                      <p className="mt-1 text-xs text-gray-500 dark:text-neutral-400">
                        Save this palette with a name so you can switch back to it later. Saving an existing name updates that theme.
                      </p>
                    </div>

                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        type="text"
                        value={customThemeName}
                        onChange={(event) => {
                          setCustomThemeName(event.target.value);
                          if (customThemeMessage) setCustomThemeMessage("");
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") void handleSaveNamedCustomTheme();
                        }}
                        placeholder="e.g. Warm studio"
                        aria-label="Saved theme name"
                        className="ots-input min-w-0 flex-1 text-sm"
                      />
                      <button
                        type="button"
                        className="ots-button ots-button-primary sm:min-w-[8rem]"
                        onClick={() => void handleSaveNamedCustomTheme()}
                        disabled={!customThemeName.trim()}
                      >
                        <Save className="h-3.5 w-3.5" />
                        Save theme
                      </button>
                    </div>

                    {customThemeMessage && (
                      <p className="mt-2 text-xs text-[var(--spotify-green)]" role="status">
                        {customThemeMessage}
                      </p>
                    )}

                    <div className="mt-4 space-y-2">
                      {savedCustomThemes.length === 0 ? (
                        <p className="ots-card p-3 text-xs text-gray-500 dark:text-neutral-400">
                          No saved custom themes yet.
                        </p>
                      ) : (
                        savedCustomThemes.map((savedTheme) => {
                          const savedPalette = savedTheme.theme[themeMode];
                          return (
                            <div key={savedTheme.id} className="ots-card flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
                              <div className="flex min-w-0 items-center gap-3">
                                <span className="ots-theme-preview" aria-hidden="true">
                                  {[savedPalette.background, savedPalette.accent, savedPalette.text].map((swatch) => (
                                    <span key={swatch} style={{ backgroundColor: swatch }} />
                                  ))}
                                </span>
                                <div className="min-w-0">
                                  <p className="truncate text-sm font-semibold text-gray-900 dark:text-neutral-100">{savedTheme.name}</p>
                                  <p className="mt-0.5 text-xs text-gray-500 dark:text-neutral-400">
                                    Updated {new Date(savedTheme.updatedAt).toLocaleDateString()}
                                  </p>
                                </div>
                              </div>
                              <div className="flex shrink-0 items-center gap-2">
                                <button
                                  type="button"
                                  className="ots-button ots-button-secondary ots-button-sm"
                                  onClick={() => void onLoadCustomTheme(savedTheme)}
                                >
                                  Load
                                </button>
                                <button
                                  type="button"
                                  className="ots-button ots-button-danger ots-button-sm"
                                  aria-label={`Delete ${savedTheme.name}`}
                                  onClick={() => void onDeleteCustomTheme(savedTheme.id)}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                  Delete
                                </button>
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  </div>

                  <button
                    type="button"
                    className="ots-button ots-button-secondary mt-4"
                    onClick={() => void onCustomThemeChange({
                      mode: themeMode,
                      dark: { ...DEFAULT_CUSTOM_THEME.dark },
                      light: { ...DEFAULT_CUSTOM_THEME.light },
                    })}
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Reset custom palette
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 mb-8">
                {renderInput("thumbnail_size", "Thumbnail Size (px)", "number")}
                {renderInput(
                  "max_search_results",
                  "Max Search Results per Category",
                  "number",
                )}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 pt-4 border-t border-gray-100 dark:border-neutral-800/60">
                {renderToggle(
                  "show_search_thumbnails",
                  "Show Thumbnails in Search View",
                )}
                {renderToggle(
                  "show_download_thumbnails",
                  "Show Thumbnails in Download Queue",
                )}
                {renderToggle(
                  "download_open_btn",
                  'Show "Open File" Button in Queue',
                )}
                {renderToggle(
                  "download_locate_btn",
                  'Show "Locate Folder" Button in Queue',
                )}
                {renderToggle(
                  "download_copy_btn",
                  'Show "Copy Path" Button in Queue',
                )}
                {renderToggle(
                  "download_delete_btn",
                  'Show "Cancel / Delete" Button in Queue',
                )}
                {renderToggle(
                  "disable_download_popups",
                  "Disable Download Popups / Toasts",
                )}
              </div>
            </div>
          )}

          {section === "backup" && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">Backup & Restore</h3>
                <p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">Back up settings, profiles, themes, queue history, and local-library metadata in one portable JSON file.</p>
              </div>
              <div className="mb-5 border border-[var(--ots-border)] bg-[var(--spotify-surface-elevated)] p-4">
                {renderInput("export_folder_path", "Default export folder", "text", "CSV exports, automation-config exports, and general backups use this folder. Leave blank to use Documents/OnTheSpot Exports.")}
                {renderInput("playlist_backup_folder_path", "Playlist backup folder", "text", "Optional separate folder for Playlist sorting backups and restores. Leave blank to use a Playlist backups subfolder inside the default export folder.")}
                <p className="mt-2 text-xs text-[#777]">Click Save Config after changing this default. Restore can still import a backup file from any folder.</p>
                {backupMessage && <p className="mt-3 text-sm text-[var(--spotify-green)]">{backupMessage}</p>}
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="ots-card p-5"><Archive className="h-5 w-5 text-[var(--spotify-green)]" /><h4 className="mt-3 font-bold text-gray-900 dark:text-neutral-100">Create a backup</h4><p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">Includes your saved themes, download profiles, statistics history, and library index.</p><button type="button" onClick={() => void triggerExport()} className="ots-button ots-button-primary mt-4"><Download className="h-4 w-4" /> Export backup</button></div>
                <div className="ots-card p-5"><Upload className="h-5 w-5 text-[var(--spotify-green)]" /><h4 className="mt-3 font-bold text-gray-900 dark:text-neutral-100">Restore a backup</h4><p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">Restore settings and history without overwriting account credentials.</p><label className="ots-button ots-button-secondary mt-4 cursor-pointer"><Upload className="h-4 w-4" /> {importing ? "Restoring…" : "Choose backup"}<input type="file" accept="application/json,.json" className="hidden" onChange={triggerImport} /></label></div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
