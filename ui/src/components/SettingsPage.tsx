import React, { useState } from 'react';
import { Save, RotateCcw, Sliders, Music, Film, Tag, Search, Eye, Cpu, Shield, Check, Loader2 } from 'lucide-react';
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
      <div className="p-20 text-center text-zinc-500 font-mono">
        Loading OTSConfig from FastAPI endpoint...
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
    if (confirm("⚠️ Are you sure you want to reset all OnTheSpot settings to factory template defaults?")) {
      setResetting(true);
      await onReset();
      setResetting(false);
    }
  };

  const renderToggle = (key: string, label: string, desc?: string, disabled: boolean = false) => (
    <div key={key} className="flex items-center justify-between p-3.5 rounded-xl bg-zinc-950 border border-zinc-800/80 hover:border-zinc-700 transition-colors">
      <div className="pr-4">
        <label className="text-sm font-semibold text-zinc-200 font-sans cursor-pointer">{label}</label>
        {desc && <p className="text-xs text-zinc-400 font-mono mt-0.5">{desc}</p>}
      </div>
      <button
        type="button"
        onClick={() => handleToggle(key, config[key])}
        disabled={disabled}
        className={`w-11 h-6 rounded-full transition-colors relative cursor-pointer shrink-0 ${config[key] ? 'bg-emerald-500 shadow-lg shadow-emerald-500/20' : 'bg-zinc-800'
          }`}
      >
        <span
          className={`w-5 h-5 rounded-full absolute top-0.5 transition-transform shadow ${config[key] ? 'left-5.5' : 'left-0.5'
            } ${disabled ? ' bg-gray-600' : ' bg-white'}`}
        />
      </button>
    </div>
  );

  const renderInput = (key: string, label: string, type: 'text' | 'number' = 'text', desc?: string) => (
    <div key={key} className="flex flex-col gap-1.5 p-3.5 rounded-xl bg-zinc-950 border border-zinc-800/80">
      <label className="text-sm font-semibold text-zinc-200 font-sans">{label}</label>
      {desc && <p className="text-xs text-zinc-400 font-mono mb-1">{desc}</p>}
      <input
        type={type}
        value={config[key] ?? ""}
        onChange={(e) => handleTextChange(key, type === 'number' ? Number(e.target.value) : e.target.value)}
        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs font-mono text-emerald-400 outline-none focus:border-emerald-500"
      />
    </div>
  );

  const renderSelect = (key: string, label: string, options: { val: string | number; text: string }[], desc?: string) => (
    <div key={key} className="flex flex-col gap-1.5 p-3.5 rounded-xl bg-zinc-950 border border-zinc-800/80">
      <label className="text-sm font-semibold text-zinc-200 font-sans">{label}</label>
      {desc && <p className="text-xs text-zinc-400 font-mono mb-1">{desc}</p>}
      <select
        value={config[key] ?? options[0].val}
        onChange={(e) => handleTextChange(key, e.target.value)}
        className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs font-mono text-emerald-400 outline-none focus:border-emerald-500 cursor-pointer"
      >
        {options.map((opt) => (
          <option key={String(opt.val)} value={opt.val}>{opt.text}</option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="max-w-7xl mx-auto p-4 lg:p-8 flex flex-col gap-8 animate-[fadeIn_0.3s_ease-out]">

      {/* Header Bar */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-xl">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white font-sans flex items-center gap-2">
            <Sliders className="w-6 h-6 text-emerald-400" />
            <span>OTSConfig Settings Sync</span>
          </h2>
          <p className="text-xs text-zinc-400 font-mono mt-1">
            All modifications sync automatically with FastAPI engine state • {config.version}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={triggerReset}
            disabled={resetting}
            className="px-4 py-2.5 rounded-xl bg-zinc-800 hover:bg-rose-600/30 text-zinc-300 hover:text-rose-200 border border-zinc-700/80 hover:border-rose-500/50 text-xs font-mono font-bold transition-all flex items-center gap-2 cursor-pointer"
          >
            <RotateCcw className="w-4 h-4" />
            <span>{resetting ? 'Resetting...' : 'Factory Reset'}</span>
          </button>

          <button
            onClick={triggerSave}
            disabled={saving}
            className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white text-xs font-mono font-bold transition-all shadow-lg shadow-emerald-500/20 flex items-center gap-2 cursor-pointer"
          >
            {saving ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : savedSuccess ? (
              <Check className="w-4 h-4 text-white" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            <span>{savedSuccess ? 'Config Saved!' : 'Save Config'}</span>
          </button>
        </div>
      </div>

      {/* Settings Navigation Sidebar + Content */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">

        {/* Navigation Tabs */}
        <div className="lg:col-span-1 flex lg:flex-col overflow-x-auto no-scrollbar gap-2 bg-zinc-900/60 p-2 rounded-2xl border border-zinc-800 h-fit sticky top-24">

          <button
            onClick={() => setSection('general')}
            className={`flex items-center gap-3 p-3 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer shrink-0 w-auto lg:w-full text-left ${section === 'general' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
          >
            <Cpu className="w-4 h-4" />
            <span>General & Workers</span>
          </button>

          <button
            onClick={() => setSection('audio')}
            className={`flex items-center gap-3 p-3 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer shrink-0 w-auto lg:w-full text-left ${section === 'audio' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
          >
            <Music className="w-4 h-4" />
            <span>Audio & Formats</span>
          </button>

          <button
            onClick={() => setSection('video')}
            className={`flex items-center gap-3 p-3 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer shrink-0 w-auto lg:w-full text-left ${section === 'video' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
          >
            <Film className="w-4 h-4" />
            <span>Video & Subtitles</span>
          </button>

          <button
            onClick={() => setSection('metadata')}
            className={`flex items-center gap-3 p-3 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer shrink-0 w-auto lg:w-full text-left ${section === 'metadata' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
          >
            <Tag className="w-4 h-4" />
            <span>ID3 Metadata Embedding</span>
          </button>

          <button
            onClick={() => setSection('search')}
            className={`flex items-center gap-3 p-3 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer shrink-0 w-auto lg:w-full text-left ${section === 'search' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
          >
            <Search className="w-4 h-4" />
            <span>Search & API Limits</span>
          </button>

          <button
            onClick={() => setSection('display')}
            className={`flex items-center gap-3 p-3 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer shrink-0 w-auto lg:w-full text-left ${section === 'display' ? 'bg-emerald-600 text-white shadow-lg' : 'text-zinc-400 hover:bg-zinc-800'
              }`}
          >
            <Eye className="w-4 h-4" />
            <span>WebUI Display Buttons</span>
          </button>

        </div>

        {/* Section Panels */}
        <div className="lg:col-span-3 bg-zinc-900 border border-zinc-800 rounded-2xl p-6 lg:p-8 shadow-xl flex flex-col gap-6">

          {section === 'general' && (
            <>
              <div className="border-b border-zinc-800 pb-4">
                <h3 className="text-lg font-bold text-white font-sans">System Variables & Workers</h3>
                <p className="text-xs text-zinc-400 font-mono mt-1">Configure worker threads, download delays, and global application options.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {renderInput('maximum_download_workers', 'Maximum Download Workers', 'number', 'Concurrent song conversion threads')}
                {renderInput('maximum_queue_workers', 'Maximum Queue Workers', 'number', 'Concurrent playlist item parsing threads')}
                {renderInput('download_delay', 'Download Delay (seconds)', 'number', 'Wait time between consecutive download requests')}
                {renderInput('download_chunk_size', 'Download Chunk Size (bytes)', 'number', 'Streaming media chunk size')}
              </div>

              <div className="flex flex-col gap-3 pt-2">
                {renderToggle('raw_media_download', 'Raw Media Download', 'Skip media conversion and ID3 metadata writing')}
                {renderToggle('mirror_spotify_playback', 'Mirror Spotify Playback', 'Mirror active Spotify desktop/mobile client playback')}
                {renderToggle('enable_retry_worker', 'Enable Retry Worker', 'Automatically retry failed downloads after a set interval')}
                {renderToggle('use_double_digit_path_numbers', 'Double Digit Track Numbers', 'Format track numbers as 01, 02 instead of 1, 2')}
                {renderToggle('use_webui_login', 'Require Web UI Login', 'Protect this dashboard with username and password - Coming Soon', true)}
              </div>

              {config.use_webui_login && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-zinc-800">
                  {renderInput('webui_username', 'Web UI Username', 'text')}
                  {renderInput('webui_password', 'Web UI Password', 'text')}
                </div>
              )}
            </>
          )}

          {section === 'audio' && (
            <>
              <div className="border-b border-zinc-800 pb-4">
                <h3 className="text-lg font-bold text-white font-sans">Audio Formatting & Output Paths</h3>
                <p className="text-xs text-zinc-400 font-mono mt-1">Set root music folder, preferred codecs, bitrates, and folder formatters.</p>
              </div>

              {renderInput('audio_download_path', 'Audio Download Root Path', 'text', 'Absolute folder path on host filesystem')}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {renderSelect('track_file_format', 'Track Media Format', [
                  { val: 'flac', text: 'FLAC (Lossless HiRes)' },
                  { val: 'mp3', text: 'MP3 (Universal 320k)' },
                  { val: 'm4a', text: 'M4A / AAC' },
                  { val: 'opus', text: 'Opus (High Efficiency)' },
                  { val: 'wav', text: 'WAV (Uncompressed)' },
                  { val: 'ogg', text: 'Vorbis Ogg' }
                ])}

                {renderSelect('file_bitrate', 'Converted File Bitrate', [
                  { val: '320k', text: '320 kbps (Maximum Quality)' },
                  { val: '256k', text: '256 kbps (High)' },
                  { val: '192k', text: '192 kbps (Medium)' },
                  { val: '128k', text: '128 kbps (Standard)' }
                ])}
              </div>

              {renderInput('track_path_formatter', 'Track Path Formatter', 'text', 'Available variables: {album_artist}, {album}, {year}, {track_number}, {name}')}
              {renderInput('playlist_path_formatter', 'Playlist Path Formatter', 'text', 'Available variables: {playlist_name}, {playlist_owner}, {playlist_number}, {artist}')}

              <div className="flex flex-col gap-3 pt-2">
                {renderToggle('create_m3u_file', 'Create M3U Playlist File', 'Generate standard M3U8 file alongside playlist items')}
                {renderToggle('save_album_cover', 'Save Cover Art File', 'Save folder.jpg or cover.png inside album directory')}
                {renderToggle('download_lyrics', 'Download Lyrics', 'Fetch synchronized or plain lyrics')}
                {config.download_lyrics && renderToggle('save_lrc_file', 'Save .LRC Lyrics File', 'Export synced lyrics as standalone .lrc file next to track')}
              </div>
            </>
          )}

          {section === 'video' && (
            <>
              <div className="border-b border-zinc-800 pb-4">
                <h3 className="text-lg font-bold text-white font-sans">Video, Movies & Anime Settings</h3>
                <p className="text-xs text-zinc-400 font-mono mt-1">Configure resolution preferences and container formatting for Crunchyroll and Generic video.</p>
              </div>

              {renderInput('video_download_path', 'Video Download Root Path', 'text')}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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

              {renderInput('movie_path_formatter', 'Movie Path Formatter', 'text')}
              {renderInput('show_path_formatter', 'TV Show Path Formatter', 'text')}

              <div className="flex flex-col gap-3 pt-2">
                {renderToggle('download_subtitles', 'Download Subtitles', 'Extract and multiplex subtitles or save .srt')}
                {renderToggle('download_chapters', 'Download Video Chapters', 'Preserve chapter markers in MKV/MP4 files')}
                {renderToggle('download_all_available_audio', 'Download All Available Audio Tracks', 'Include multi-language dubs if present')}
              </div>

              <div className="border-t border-zinc-800 pt-5 mt-2">
                <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-2xl p-4 flex flex-col gap-4">
                  <div>
                    <h4 className="text-sm font-bold text-white font-sans">Video to Audio Extraction (V2A)</h4>
                    <p className="text-xs text-zinc-400 font-mono mt-0.5">Extract and save only the audio stream when downloading video sources.</p>
                  </div>

                  <div className="flex flex-col gap-3">
                    {renderToggle('v2a_enable', 'Save Only Audio from Video (V2A)', 'Discard video stream and convert output to audio format')}

                    {config.v2a_enable && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-zinc-800/80 animate-[fadeIn_0.2s_ease-out]">
                        {renderSelect('v2a_preferred_codec', 'Preferred Audio Codec', [
                          { val: 'opus', text: 'Opus (High Efficiency)' },
                          { val: 'm4a', text: 'M4A / AAC' },
                          { val: 'mp3', text: 'MP3 (Standard)' },
                          { val: 'flac', text: 'FLAC (Lossless)' },
                          { val: 'wav', text: 'WAV (Uncompressed)' }
                        ], 'Format of extracted audio track')}
                        {renderInput('v2a_preferred_bitrate', 'Preferred Audio Bitrate (kbps)', 'number', 'e.g. 192, 256, 320')}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}

          {section === 'metadata' && (
            <>
              <div className="border-b border-zinc-800 pb-4">
                <h3 className="text-lg font-bold text-white font-sans">ID3 Metadata Tag Embedding</h3>
                <p className="text-xs text-zinc-400 font-mono mt-1">Select exactly which metadata tags to inject into downloaded music tracks.</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
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
              </div>

              <div className="pt-4 border-t border-zinc-800">
                {renderInput('metadata_separator', 'Metadata Value Separator', 'text', 'Separator for multi-value tags (e.g. "; " for multiple artists)')}
              </div>
            </>
          )}

          {section === 'search' && (
            <>
              <div className="border-b border-zinc-800 pb-4">
                <h3 className="text-lg font-bold text-white font-sans">Search Categories & API Call Reduction</h3>
                <p className="text-xs text-zinc-400 font-mono mt-1">Optimize Spotify/Tidal API rate limits and toggle enabled catalog categories.</p>
              </div>

              <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-4 mb-2">
                <h4 className="text-xs font-mono font-bold text-emerald-400 mb-2">⚡ API Rate Limit Optimization</h4>
                <div className="flex flex-col gap-2.5">
                  {renderToggle('cache_metadata_in_queue', 'Pass Metadata from Queue to Download Worker', 'Reduces Spotify API calls by ~50%')}
                  {renderToggle('fetch_genre_metadata', 'Fetch Genre from Artist Endpoint', 'Adds +1 API call per track')}
                  {renderToggle('fetch_extended_album_metadata', 'Fetch Record Label & Copyright', 'Adds +1 API call per track')}
                </div>
              </div>

              <h4 className="text-sm font-bold text-white font-sans mt-2">Enabled Search Categories</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {renderToggle('enable_search_tracks', 'Search Tracks')}
                {renderToggle('enable_search_albums', 'Search Albums')}
                {renderToggle('enable_search_playlists', 'Search Playlists')}
                {renderToggle('enable_search_artists', 'Search Artists')}
                {renderToggle('enable_search_podcasts', 'Search Podcasts')}
                {renderToggle('enable_search_episodes', 'Search Episodes')}
                {renderToggle('enable_search_audiobooks', 'Search Audiobooks')}
              </div>
            </>
          )}

          {section === 'display' && (
            <>
              <div className="border-b border-zinc-800 pb-4">
                <h3 className="text-lg font-bold text-white font-sans">Web UI Display Buttons & Layout</h3>
                <p className="text-xs text-zinc-400 font-mono mt-1">Customize dashboard thumbnails, action icons, and notification popups.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {renderInput('thumbnail_size', 'Thumbnail Size (px)', 'number')}
                {renderInput('max_search_results', 'Max Search Results per Category', 'number')}
              </div>

              <div className="flex flex-col gap-3 pt-2">
                {renderToggle('show_search_thumbnails', 'Show Thumbnails in Search View')}
                {renderToggle('show_download_thumbnails', 'Show Thumbnails in Download Queue')}
                {renderToggle('download_open_btn', 'Show "Open File" Button in Queue')}
                {renderToggle('download_locate_btn', 'Show "Locate Folder" Button in Queue')}
                {renderToggle('download_copy_btn', 'Show "Copy Path" Button in Queue')}
                {renderToggle('download_delete_btn', 'Show "Cancel / Delete" Button in Queue')}
                {renderToggle('disable_download_popups', 'Disable Download Popups / Toasts')}
              </div>
            </>
          )}

        </div>

      </div>

    </div>
  );
};
