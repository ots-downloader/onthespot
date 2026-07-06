import React, { useState } from 'react';
import { Save, RotateCcw, Sliders, Music, Film, Tag, Search, Eye, Cpu, Check, Loader2 } from 'lucide-react';
import { OTSConfig } from '../types';

interface SettingsPageProps {
  config: OTSConfig | null;
  onUpdateValue: (key: string, value: any) => Promise<boolean>;
  onSave: () => Promise<boolean>;
  onReset: () => Promise<void>;
}

type SettingsSection = 'general' | 'audio' | 'video' | 'metadata' | 'search' | 'display';

export const SettingsPage: React.FC<SettingsPageProps> = ({
  config,
  onUpdateValue,
  onSave,
  onReset
}) => {
  const [section, setSection] = useState<SettingsSection>('general');
  const [saving, setSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [resetting, setResetting] = useState(false);

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

  // Material Design 3 Styled Switch
  const renderToggle = (key: string, label: string, desc?: string, disabled: boolean = false) => {
    const isChecked = config[key];
    return (
      <div key={key} className="flex items-start justify-between py-3">
        <div className="pr-4 flex-1">
          <label className="text-sm font-medium text-gray-900 dark:text-neutral-100 cursor-pointer select-none" onClick={() => !disabled && handleToggle(key, isChecked)}>
            {label}
          </label>
          {desc && <p className="text-xs text-gray-500 dark:text-neutral-400 mt-1 leading-relaxed">{desc}</p>}
        </div>
        <button
          type="button"
          onClick={() => handleToggle(key, isChecked)}
          disabled={disabled}
          className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer shrink-0 mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:ring-offset-2 dark:focus:ring-offset-[#1a1a1a] ${
            isChecked 
              ? 'bg-blue-600' 
              : 'bg-gray-300 dark:bg-neutral-600'
          } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
          <span
            className={`absolute top-[2px] left-[2px] w-5 h-5 rounded-full bg-white transition-transform duration-200 shadow-sm ${
              isChecked ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>
    );
  };

  // Material Design 3 Styled Input
  const renderInput = (key: string, label: string, type: 'text' | 'number' = 'text', desc?: string) => (
    <div key={key} className="flex flex-col gap-1.5 py-2 w-full">
      <label className="text-sm font-medium text-gray-900 dark:text-neutral-100">{label}</label>
      <input
        type={type}
        value={config[key] ?? ""}
        onChange={(e) => handleTextChange(key, type === 'number' ? Number(e.target.value) : e.target.value)}
        className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-neutral-100 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-500 transition-all placeholder-gray-400"
      />
      {desc && <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5 leading-relaxed">{desc}</p>}
    </div>
  );

  // Material Design 3 Styled Select
  const renderSelect = (key: string, label: string, options: { val: string | number; text: string }[], desc?: string) => (
    <div key={key} className="flex flex-col gap-1.5 py-2 w-full">
      <label className="text-sm font-medium text-gray-900 dark:text-neutral-100">{label}</label>
      <select
        value={config[key] ?? options[0].val}
        onChange={(e) => handleTextChange(key, e.target.value)}
        className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-neutral-100 outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 dark:focus:border-blue-500 transition-all cursor-pointer appearance-none"
      >
        {options.map((opt) => (
          <option key={String(opt.val)} value={opt.val}>{opt.text}</option>
        ))}
      </select>
      {desc && <p className="text-xs text-gray-500 dark:text-neutral-400 mt-0.5 leading-relaxed">{desc}</p>}
    </div>
  );

  const NavButton = ({ id, icon: Icon, label }: { id: SettingsSection, icon: any, label: string }) => {
    const isActive = section === id;
    return (
      <button
        onClick={() => setSection(id)}
        className={`flex items-center gap-3 px-4 py-3 rounded-full text-sm font-medium transition-colors w-full text-left shrink-0 lg:shrink ${
          isActive 
            ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300' 
            : 'text-gray-600 hover:bg-gray-100 dark:text-neutral-400 dark:hover:bg-neutral-800'
        }`}
      >
        <Icon className="w-[18px] h-[18px]" />
        <span>{label}</span>
      </button>
    );
  };

  return (
    <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8 flex flex-col gap-6 font-sans">
      
      {/* App Bar / Header */}
      <div className="bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 shadow-sm">
        <div>
          <h2 className="text-xl font-medium text-gray-900 dark:text-neutral-100 flex items-center gap-2">
            <Sliders className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            System Configuration
          </h2>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            Configurations sync automatically with FastAPI engine state • Version {config.version}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={triggerReset}
            disabled={resetting}
            className="px-5 py-2.5 rounded-full text-red-600 bg-red-50 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-400 dark:hover:bg-red-500/20 text-sm font-medium transition-colors flex items-center gap-2"
          >
            <RotateCcw className="w-4 h-4" />
            <span>{resetting ? 'Resetting...' : 'Factory Reset'}</span>
          </button>

          <button
            onClick={triggerSave}
            disabled={saving}
            className="px-6 py-2.5 rounded-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors flex items-center gap-2 shadow-sm"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : savedSuccess ? (
              <Check className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>{savedSuccess ? 'Config Saved!' : 'Save Config'}</span>
          </button>
        </div>
      </div>

      {/* Main Layout Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-start">
        
        {/* Navigation Sidebar */}
        <div className="lg:col-span-1 flex flex-row lg:flex-col overflow-x-auto no-scrollbar gap-1 bg-white dark:bg-[#1a1a1a] p-2 rounded-2xl border border-gray-200 dark:border-neutral-800/60 shadow-sm lg:sticky top-24">
          <NavButton id="general" icon={Cpu} label="General & Workers" />
          <NavButton id="audio" icon={Music} label="Audio Outputs" />
          <NavButton id="video" icon={Film} label="Video Media" />
          <NavButton id="metadata" icon={Tag} label="ID3 Tagging" />
          <NavButton id="search" icon={Search} label="Search API" />
          <NavButton id="display" icon={Eye} label="Display Settings" />
        </div>

        {/* Content Panels */}
        <div className="lg:col-span-3 bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-6 md:p-8 shadow-sm flex flex-col">
          
          {/* GENERAL SECTION */}
          {section === 'general' && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">System Variables & Workers</h3>
                <p className="text-sm text-gray-500 mt-1">Configure worker threads, download delays, and global application options.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6">
                {renderInput('maximum_download_workers', 'Maximum Download Workers', 'number', 'Concurrent song conversion threads')}
                {renderInput('maximum_queue_workers', 'Maximum Queue Workers', 'number', 'Concurrent playlist item parsing threads')}
                {renderInput('download_delay', 'Download Delay (seconds)', 'number', 'Wait time between consecutive download requests')}
                {renderInput('download_chunk_size', 'Download Chunk Size (bytes)', 'number', 'Streaming media chunk size')}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 border-t border-gray-100 dark:border-neutral-800/60">
                {renderToggle('raw_media_download', 'Raw Media Download', 'Skip media conversion and ID3 metadata writing')}
                {renderToggle('mirror_spotify_playback', 'Mirror Spotify Playback', 'Mirror active Spotify client playback')}
                {renderToggle('enable_retry_worker', 'Enable Retry Worker', 'Automatically retry failed downloads')}
                {renderToggle('use_double_digit_path_numbers', 'Double Digit Track Numbers', 'Format track numbers as 01, 02 instead of 1, 2')}
                {renderToggle('debug_mode', 'Enable Debug Mode', 'Enables verbose logging and internal application debugging features')}
                {renderToggle('close_to_tray', 'Close to System Tray', 'Minimize application to system tray on exit')}
                {renderToggle('rotate_active_account_number', 'Rotate Active Account Number', 'Cycle through available accounts automatically')}
                <div className="py-2">
                  {renderInput('download_delay_variance', 'Download Delay Variance (s)', 'number', 'Random variance added to base download delay')}
                </div>
                {renderToggle('check_for_updates', 'Check for Updates', 'Automatically check for new application versions', false)}
                {renderToggle('use_webui_login', 'Require Web UI Login', 'Protect dashboard with credential authorization (Coming Soon)', true)}
                <div className="py-2">
                  {renderInput('language', 'Application Language', 'text', 'Default interface locale (e.g., en_US)')}
                </div>
              </div>
            </div>
          )}

          {/* AUDIO SECTION */}
          {section === 'audio' && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">Audio Formatting & Output</h3>
                <p className="text-sm text-gray-500 mt-1">Set root music folder, preferred codecs, bitrates, and folder formatters.</p>
              </div>

              <div className="mb-6">
                {renderInput('audio_download_path', 'Audio Download Root Path', 'text', 'Absolute folder path on host filesystem')}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6">
                <div className="sm:col-span-2 divide-y divide-gray-100 dark:divide-neutral-800/60 mb-2 border-b border-gray-100 dark:border-neutral-800/60">
                  {renderToggle('use_source_format', 'Use Source Format', 'Uses the best source quality and format directly')}
                  {renderToggle('use_custom_file_bitrate', 'Use Custom Bitrate', 'Enforces files to output using target bitrate selections')}
                </div>
                {renderSelect('track_file_format', 'Track Media Format', [
                  { val: 'flac', text: 'FLAC (Lossless HiRes)' },
                  { val: 'mp3', text: 'MP3 (Universal 320k)' },
                  { val: 'm4a', text: 'M4A / AAC' },
                  { val: 'opus', text: 'Opus (High Efficiency)' },
                  { val: 'wav', text: 'WAV (Uncompressed)' },
                  { val: 'ogg', text: 'Vorbis Ogg' }
                ], "Download container if standard source formats are disabled.")}
                {renderSelect('file_bitrate', 'Converted File Bitrate', [
                  { val: '320k', text: '320 kbps (Maximum Quality)' },
                  { val: '256k', text: '256 kbps (High)' },
                  { val: '192k', text: '192 kbps (Medium)' },
                  { val: '128k', text: '128 kbps (Standard)' }
                ], "Download bitrate conversion output when custom bitrates are enabled.")}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                {renderInput('track_path_formatter', 'Track Path Formatter', 'text', 'Variables: {album_artist}, {album}, {year}, {track_number}, {name}')}
                {renderInput('playlist_path_formatter', 'Playlist Path Formatter', 'text', 'Variables: {playlist_name}, {playlist_owner}, {playlist_number}, {artist}')}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                <div className="py-2">
                  {renderSelect('m3u_format', 'M3U Playlist Format', [
                    { val: 'm3u8', text: 'M3U8' },
                    { val: 'm3u', text: 'M3U (Standard)' }
                  ], 'Format wrapper for generated local playlist files')}
                </div>
                {renderToggle('create_m3u_file', 'Create M3U Playlist File', 'Generate playlist index files next to downloaded items')}
                {renderToggle('save_album_cover', 'Save Cover Art To Folder', 'Save folder.jpg or cover.png inside album directories')}
                {renderToggle('download_lyrics', 'Download Lyrics', 'Fetch synchronized or plain-text lyric files')}
                {config.download_lyrics && renderToggle('save_lrc_file', 'Save .LRC Lyrics File', 'Export synced lyric timestamps as standalone .lrc assets')}
              </div>
            </div>
          )}

          {/* VIDEO SECTION */}
          {section === 'video' && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">Video, Movies & Anime Settings</h3>
                <p className="text-sm text-gray-500 mt-1">Configure resolution preferences and container formatting for video media.</p>
              </div>

              <div className="mb-6">
                {renderInput('video_download_path', 'Video Download Root Path', 'text')}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6">
                {renderSelect('movie_file_format', 'Movie Container Format', [
                  { val: 'mkv', text: 'MKV (Matroska Container)' },
                  { val: 'mp4', text: 'MP4 (Standard Video)' }
                ])}
                {renderSelect('preferred_video_resolution', 'Preferred Video Resolution', [
                  { val: 1080, text: '1080p (Full HD)' },
                  { val: 720, text: '720p (HD)' },
                  { val: 2160, text: '4K (Ultra HD)' }
                ])}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 mb-6 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                {renderInput('movie_path_formatter', 'Movie Path Formatter', 'text')}
                {renderInput('show_path_formatter', 'TV Show Path Formatter', 'text')}
                {renderInput('preferred_audio_language', 'Preferred Audio Language Code', 'text', 'Target stream language code (e.g., en-US)')}
                {renderInput('preferred_subtitle_language', 'Preferred Subtitle Language Code', 'text', 'Target subtitle language code (e.g., en-US)')}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 pt-6 border-t border-gray-100 dark:border-neutral-800/60">
                {renderToggle('download_subtitles', 'Download Subtitles', 'Extract and embed soft subtitles or save external .srt components')}
                {renderToggle('download_chapters', 'Download Video Chapters', 'Preserve internal chapter segment markers')}
                {renderToggle('download_all_available_audio', 'Download All Available Audio Tracks', 'Include alternative language audio dubs')}
              </div>

              {/* V2A Section */}
              <div className="mt-8 pt-8 border-t border-gray-100 dark:border-neutral-800/60">
                <div className="bg-blue-50 dark:bg-blue-900/10 rounded-2xl p-6 border border-blue-100 dark:border-blue-900/30">
                  <h4 className="text-base font-medium text-gray-900 dark:text-neutral-100 mb-1">Video to Audio Extraction (V2A)</h4>
                  <p className="text-sm text-gray-500 dark:text-neutral-400 mb-4">Strip output and save audio streams only when downloading video sources.</p>
                  
                  {renderToggle('v2a_enable', 'Enable Audio Extraction', 'Discard video components and convert tracks to designated format')}

                  {config.v2a_enable && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4 mt-6 pt-6 border-t border-blue-200/50 dark:border-blue-800/30 animate-[fadeIn_0.2s_ease-out]">
                      {renderSelect('v2a_preferred_codec', 'Preferred Audio Codec', [
                        { val: 'opus', text: 'Opus (High Efficiency)' },
                        { val: 'm4a', text: 'M4A / AAC' },
                        { val: 'mp3', text: 'MP3 (Standard)' },
                        { val: 'flac', text: 'FLAC (Lossless)' },
                        { val: 'wav', text: 'WAV (Uncompressed)' }
                      ], 'Output file compression profile')}
                      {renderInput('v2a_preferred_bitrate', 'Preferred Audio Bitrate (kbps)', 'number', 'Target bitrate limit (e.g., 256, 320)')}
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* METADATA SECTION */}
          {section === 'metadata' && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">ID3 Metadata Tagging</h3>
                <p className="text-sm text-gray-500 mt-1">Select exactly which metadata tags to inject into downloaded music tracks.</p>
              </div>

              <div className="mb-6 max-w-md">
                {renderSelect('album_cover_format', 'Cover Art Compression Format', [
                  { val: 'png', text: 'PNG (Lossless Quality, Larger Size)' },
                  { val: 'jpeg', text: 'JPEG (Efficient Compression, Smaller Size)' }
                ])}
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 divide-y sm:divide-y-0 divide-gray-100 dark:divide-neutral-800/60 mb-8 border-t border-gray-100 dark:border-neutral-800/60 pt-4">
                {renderToggle('embed_cover', 'Embed Cover Art')}
                {renderToggle('embed_artist', 'Embed Artist')}
                {renderToggle('embed_album', 'Embed Album')}
                {renderToggle('embed_albumartist', 'Embed Album Artist')}
                {renderToggle('embed_name', 'Embed Title')}
                {renderToggle('embed_year', 'Embed Release Year')}
                {renderToggle('embed_tracknumber', 'Embed Track Number')}
                {renderToggle('embed_discnumber', 'Embed Disc Number')}
                {renderToggle('embed_genre', 'Embed Genre')}
                {renderToggle('embed_lyrics', 'Embed Lyrics')}
                {renderToggle('embed_label', 'Embed Record Label')}
                {renderToggle('embed_copyright', 'Embed Copyright')}
                {renderToggle('embed_isrc', 'Embed ISRC Code')}
                {renderToggle('embed_bpm', 'Embed BPM / Tempo')}
                {renderToggle('embed_key', 'Embed Musical Key')}
                {renderToggle('embed_producers', 'Embed Producers')}
                {renderToggle('embed_writers', 'Embed Writers')}
                {renderToggle('embed_explicit', 'Embed Explicit Tag')}
                {renderToggle('embed_composer', 'Embed Composer')}
                {renderToggle('embed_description', 'Embed Description')}
                {renderToggle('embed_language', 'Embed Language')}
                {renderToggle('embed_url', 'Embed URL')}
              </div>

              <div className="pt-6 border-t border-gray-100 dark:border-neutral-800/60 mb-6">
                <h4 className="text-sm font-medium text-blue-600 dark:text-blue-400 mb-4">Spotify Specific Fields (Requires Audio Features API)</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 divide-y sm:divide-y-0 divide-gray-100 dark:divide-neutral-800/60">
                  {renderToggle('embed_timesignature', 'Embed Time Signature')}
                  {renderToggle('embed_acousticness', 'Embed Acousticness')}
                  {renderToggle('embed_danceability', 'Embed Danceability')}
                  {renderToggle('embed_energy', 'Embed Energy')}
                  {renderToggle('embed_instrumentalness', 'Embed Instrumentalness')}
                  {renderToggle('embed_liveness', 'Embed Liveness')}
                  {renderToggle('embed_loudness', 'Embed Loudness')}
                  {renderToggle('embed_speechiness', 'Embed Speechiness')}
                  {renderToggle('embed_valence', 'Embed Valence')}
                </div>
              </div>

              <div className="pt-6 border-t border-gray-100 dark:border-neutral-800/60 max-w-md">
                {renderInput('metadata_separator', 'Metadata Value Separator', 'text', 'Separation character for multi-value tags (e.g. "; ")')}
              </div>
            </div>
          )}

          {/* SEARCH SECTION */}
          {section === 'search' && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">Search & API Configuration</h3>
                <p className="text-sm text-gray-500 mt-1">Optimize third-party platform API limits and toggle library source scopes.</p>
              </div>

              <div className="bg-orange-50 dark:bg-orange-900/10 border border-orange-100 dark:border-orange-900/30 rounded-2xl p-6 mb-8">
                <h4 className="text-base font-medium text-orange-800 dark:text-orange-400 mb-4 flex items-center gap-2">
                  <Sliders className="w-4 h-4" /> API Call Reduction Settings
                </h4>
                <div className="divide-y divide-orange-100 dark:divide-orange-900/30">
                  {renderToggle('cache_metadata_in_queue', 'Cache API Calls', 'Reduces target client catalog queries by up to 50%')}
                  {renderToggle('fetch_genre_metadata', 'Fetch Genre from Artist Endpoint', 'Requires +1 additional query per processed track')}
                  {renderToggle('fetch_extended_album_metadata', 'Fetch Extra Album Metadata', 'Requires +1 additional query per processed track')}
                  {renderToggle('fetch_audio_features', 'Fetch Audio Features', 'Requires +1 additional query per processed track')}
                  {renderToggle('fetch_track_credits', 'Fetch Record Label & Copyright', 'Requires +1 additional query per processed track')}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4">
                    {renderInput('spotify_webapi_override_client_id', 'Spotify Client ID Override', 'text')}
                    {renderInput('spotify_webapi_override_client_secret', 'Spotify Client Secret Override', 'text')}
                  </div>
                </div>
              </div>

              <div className="mb-8">
                <h4 className="text-base font-medium text-gray-900 dark:text-neutral-100 mb-4">Enabled Search Categories</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 divide-y sm:divide-y-0 divide-gray-100 dark:divide-neutral-800/60 border border-gray-200 dark:border-neutral-800/60 rounded-xl p-4">
                  {renderToggle('enable_search_tracks', 'Search Tracks')}
                  {renderToggle('enable_search_albums', 'Search Albums')}
                  {renderToggle('enable_search_playlists', 'Search Playlists')}
                  {renderToggle('enable_search_artists', 'Search Artists')}
                  {renderToggle('enable_search_podcasts', 'Search Podcasts')}
                  {renderToggle('enable_search_episodes', 'Search Episodes')}
                  {renderToggle('enable_search_audiobooks', 'Search Audiobooks')}
                </div>
              </div>

              <div className="pt-6 border-t border-gray-100 dark:border-neutral-800/60 max-w-md">
                {renderInput('search_prefix', 'Default Search Prefix', 'text', 'Fallback search prefix parameter (e.g., "the")')}
              </div>
            </div>
          )}

          {/* DISPLAY SECTION */}
          {section === 'display' && (
            <div className="animate-[fadeIn_0.2s_ease-out]">
              <div className="mb-6">
                <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">Web UI & Display Controls</h3>
                <p className="text-sm text-gray-500 mt-1">Customize dashboard thumbnails, action controls, and notification popups.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 mb-8 max-w-2xl">
                {renderInput('thumbnail_size', 'Thumbnail Size (px)', 'number')}
                {renderInput('max_search_results', 'Max Search Results per Category', 'number')}
              </div>

              <div className="divide-y divide-gray-100 dark:divide-neutral-800/60 pt-4 border-t border-gray-100 dark:border-neutral-800/60">
                {renderToggle('show_search_thumbnails', 'Show Thumbnails in Search View')}
                {renderToggle('show_download_thumbnails', 'Show Thumbnails in Download Queue')}
                {renderToggle('download_open_btn', 'Show "Open File" Button in Queue')}
                {renderToggle('download_locate_btn', 'Show "Locate Folder" Button in Queue')}
                {renderToggle('download_copy_btn', 'Show "Copy Path" Button in Queue')}
                {renderToggle('download_delete_btn', 'Show "Cancel / Delete" Button in Queue')}
                {renderToggle('disable_download_popups', 'Disable Download Popups / Toasts')}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
};