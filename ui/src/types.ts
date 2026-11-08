export interface OTSConfig {
  version: string;
  debug_mode: boolean;
  language_index: number;
  language: string;
  total_downloaded_items: number;
  total_downloaded_data: number;
  m3u_format: string;
  use_double_digit_path_numbers: boolean;
  ffmpeg_args: string[];
  active_account_number: number;
  accounts: AccountItem[];
  use_webui_login: boolean;
  webui_username: string;
  webui_password: string;
  theme: string;
  active_download_profile?: string;
  export_folder_path?: string;
  playlist_backup_folder_path?: string;
  youtube_auth_mode?: "none" | "browser" | "cookie_file";
  youtube_cookies_browser?: string;
  youtube_cookies_file?: string;
  download_profiles?: DownloadProfile[];
  explicit_label: string;
  download_copy_btn: boolean;
  download_open_btn: boolean;
  download_locate_btn: boolean;
  download_delete_btn: boolean;
  show_search_thumbnails: boolean;
  show_download_thumbnails: boolean;
  thumbnail_size: number;
  max_search_results: number;
  disable_download_popups: boolean;
  windows_10_explorer_thumbnails: boolean;
  mirror_spotify_playback: boolean;
  close_to_tray: boolean;
  check_for_updates: boolean;
  update_repository?: string;
  update_check_interval_hours?: number;
  illegal_character_replacement: string;
  raw_media_download: boolean;
  rotate_active_account_number: boolean;
  download_delay: number;
  download_delay_variance: number;
  download_chunk_size: number;
  maximum_queue_workers: number;
  maximum_download_workers: number;
  enable_retry_worker: boolean;
  retry_worker_delay: number;
  api_retry_max_attempts: number;
  api_retry_base_delay: number;
  api_retry_max_delay: number;
  api_request_delay: number;
  cache_api_calls: boolean;
  api_response_cache_ttl_seconds: number;
  spotify_metadata_cache_ttl_seconds: number;
  spotify_search_cache_ttl_seconds: number;
  playlist_automation_cache_ttl_seconds: number;
  spotify_connect_port: number;
  spotify_webapi_override_client_id: string;
  spotify_webapi_override_client_secret: string;
  spotify_webapi_override_client_secret_configured?: boolean;
  cache_metadata_in_queue: boolean;
  fetch_genre_metadata: boolean;
  fetch_extended_album_metadata: boolean;
  fetch_audio_features: boolean;
  fetch_track_credits: boolean;
  enable_search_tracks: boolean;
  enable_search_albums: boolean;
  enable_search_playlists: boolean;
  enable_search_artists: boolean;
  enable_search_episodes: boolean;
  enable_search_podcasts: boolean;
  enable_search_audiobooks: boolean;
  f_search_tracks: boolean;
  f_search_albums: boolean;
  f_search_artists: boolean;
  f_search_playlists: boolean;
  search_prefix: string;
  download_queue_show_waiting: boolean;
  download_queue_show_failed: boolean;
  download_queue_show_cancelled: boolean;
  download_queue_show_unavailable: boolean;
  download_queue_show_completed: boolean;
  audio_download_path: string;
  track_path_formatter: string;
  podcast_file_format: string;
  podcast_path_formatter: string;
  use_playlist_path: boolean;
  playlist_path_formatter: string;
  create_m3u_file: boolean;
  m3u_path_formatter: string;
  extinf_separator: string;
  extinf_label: string;
  save_album_cover: boolean;
  album_cover_format: string;
  file_hertz: number;
  use_custom_file_bitrate: boolean;
  use_source_format: boolean,
  prefer_best_source_format: boolean,
  download_lyrics: boolean;
  only_download_synced_lyrics: boolean;
  only_download_plain_lyrics: boolean;
  save_lrc_file: boolean;
  translate_file_path: boolean;
  metadata_separator: string;
  overwrite_existing_metadata: boolean;
  embed_branding: boolean;
  embed_cover: boolean;
  embed_artist: boolean;
  embed_album: boolean;
  embed_albumartist: boolean;
  embed_name: boolean;
  embed_year: boolean;
  embed_discnumber: boolean;
  embed_tracknumber: boolean;
  embed_genre: boolean;
  embed_performers: boolean;
  embed_producers: boolean;
  embed_writers: boolean;
  embed_composer: boolean;
  prefer_composer_as_album_artist: boolean;
  shorten_composer_tag: boolean;
  embed_label: boolean;
  embed_copyright: boolean;
  embed_description: boolean;
  embed_language: boolean;
  embed_isrc: boolean;
  embed_length: boolean;
  embed_url: boolean;
  embed_key: boolean;
  embed_bpm: boolean;
  embed_compilation: boolean;
  embed_lyrics: boolean;
  embed_explicit: boolean;
  embed_upc: boolean;
  embed_service_id: boolean;
  video_download_path: string;
  movie_file_format: string;
  movie_path_formatter: string;
  show_file_format: string;
  show_path_formatter: string;
  preferred_video_resolution: number;
  download_subtitles: boolean;
  download_chapters: boolean;
  preferred_audio_language: string;
  preferred_subtitle_language: string;
  download_all_available_audio: boolean;
  download_all_available_subtitles: boolean;
  v2a_enable: boolean;
  v2a_preferred_codec: string;
  v2a_preferred_bitrate: number;
  [key: string]: any;
}
export interface AccountItem {
  uuid: string;
  service: string;
  active: boolean;
  username?: string;
  token?: string;
  login?: Record<string, any>;
  added_at?: string;
  status?: "online" | "degraded" | "rate_limited" | "offline";
}

export type MediaItemType =
  | "track"
  | "album"
  | "playlist"
  | "artist"
  | "podcast"
  | "episode"
  | "movie"
  | "show";

export interface SearchResultItem {
  id: string;
  item_service: string;
  item_type: MediaItemType;
  name: string;
  artist: string;
  album?: string;
  duration?: string;
  release_year?: number;
  thumbnail?: string;
  url: string;
  explicit?: boolean;
  bitrate?: string;
  item_count?: number;
}

export type ParsingStatus = "parsing" | "completed" | "failed" | "queued";

export interface ParsingJob {
  id: string;
  url: string;
  source: string;
  type: "track" | "album" | "playlist" | "artist";
  title: string;
  subtitle?: string;
  progress: number;
  items_found: number;
  total_expected?: number;
  status: ParsingStatus;
  current_step?: string;
  created_at: string;
  error?: string;
  profile_id?: string;
  profile_name?: string;
}

export type PendingItemStatus = "ready" | "parsing" | "checking" | "error" | "queued";

export interface PendingQueueItem {
  id: string;
  job_id?: string;
  name: string;
  artist: string;
  album?: string;
  playlist_name?: string;
  thumbnail?: string;
  item_service: string;
  item_type: string;
  duration?: string;
  format?: string;
  bitrate?: string;
  profile_id?: string;
  profile_name?: string;
  url?: string;
  status: PendingItemStatus;
  created_at: string;
  error?: string;
  isrc?: string;
  explicit?: boolean;
}

export type QueueItemStatus =
    | "Waiting"
    | "Downloading"
    | "Paused"
    | "Converting"
    | "Decrypting"
    | "Getting Lyrics"
    | "Setting Thumbnail"
    | "Adding To M3U"
    | "Downloading Subtitles"
    | "Downloading Chapters"
    | "Downloading Video"
    | "Downloading Audio"
    | "Downloaded"
    | "Already Exists"
    | "Failed"
    | "Cancelled"
    | "Unavailable"
    | "Deleted"

  export interface DownloadQueueItem {
      name: string;
      artist: string;
      thumbnail?: string;
      album?: string;
      length?: number;
      file_size?: string;
      bitrate?: number;
      local_id: number;
      item_service: string;
      item_type: string;
      item_id: string;
      item_url: string;
      playlist_name: string;
      playlist_by: string;
      playlist_number?: string;
      parent_category: string;
      item_status: QueueItemStatus;
      progress: number;
      download_profile: DownloadProfile
      target_format: string;
      download_format: string;
      temp_path: string;
      file_path: string;
      error?:string;
      retry_count?: number;
    }


export interface DownloadProfile {
  id: string;
  name: string;
  format: "flac" | "mp3" | "aac" | "ogg" | "opus" | "alac" | "wav";
  bitrate: string;
  download_path: string;
  is_default?: boolean;
}

export type SpotifyDeviceAuthState =
  | "pending"
  | "authorizing"
  | "approved"
  | "denied"
  | "expired"
  | "cancelled"
  | "error";

export interface SpotifyDeviceAuthStatus {
  flow_id: string;
  state: SpotifyDeviceAuthState;
  user_code: string;
  verification_uri: string;
  verification_uri_complete: string;
  /** Unix seconds. */
  expires_at: number;
  /** Seconds between polls that Spotify asks for. */
  interval: number;
  username: string;
  error_code: string;
  message: string;
}

export type YouTubeSetupMode = "upload" | "browser" | "cookie_file" | "none";

export interface YouTubeAuthentication {
  mode: "none" | "browser" | "cookie_file";
  browser?: string;
  cookie_file?: string;
}

export interface YouTubeAuthenticationStatus {
  mode: "none" | "browser" | "cookie_file";
  configured: boolean;
  ready: boolean;
  source: string;
  error: string;
}

export interface AccountHealth {
  healthy?: boolean;
  overall_status: "healthy" | "degraded" | "critical";
  total_accounts: number;
  active_accounts: number;
  authenticated_accounts?: number;
  configured_accounts?: number;
  missing_services?: string[];
  spotify?: {
    configured: boolean;
    connected: boolean;
    status: string;
  };
  services: Record<
    string,
    {
      status: "online" | "degraded" | "rate_limited" | "offline";
      count: number;
      last_active: string;
    }
  >;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: "INFO" | "WARNING" | "ERROR" | "GUI";
  message: string;
  service?: string;
}

export interface NotificationBannerItem {
  id: string;
  title: string;
  message: string;
  status: "Completed" | "Failed" | "Cancelled" | "Downloading" | "success" | "warning" | "error" | "info" | string;
  thumbnail?: string;
  timestamp?: Date | string;
  url?: string;
}

export interface UpdateAsset {
  name: string;
  size: number;
  download_url: string;
  platform: string;
}

export interface UpdateInfo {
  repository: string;
  current_version: string;
  latest_version: string;
  update_available: boolean;
  release_name: string;
  release_url?: string;
  recommended_asset?: UpdateAsset;
  checked_at?: number;
  install_supported?: boolean;
  error?: string;
}

export interface SystemDiagnostics {
  status: "online" | "offline";
  version: string;
  target: string;
  uptime_seconds: number;
  backend: {
    status: string;
    version: string;
  };
  memory_usage: {
    rss_mb: number;
    heap_total_mb: number;
    heap_used_mb: number;
  };
  workers: {
    queue_worker_active: boolean;
    download_workers_running: number;
    max_download_workers: number;
    retry_worker_active: boolean;
    active_workers_map: Record<string, boolean>;
  };
  queue: {
    total: number;
    downloads: number;
    pending: number;
    parsing: number;
    paused: boolean;
    statuses: Record<string, number>;
  };
  ffmpeg: {
    available: boolean;
    path: string;
    version?: string;
  };
  disk: {
    total: number;
    free: number;
    used: number;
  };
  rate_limit: {
    active: boolean;
    host: string;
    seconds_remaining: number;
    count: number;
  };
  cache: {
    hits: number;
    misses: number;
    size_mb: number;
  };
  spotify_api: {
    configured: boolean;
    connected: boolean;
    status: string;
    rate_limited: boolean;
    seconds_remaining: number;
    connect_service?: {
      running: boolean;
      device_name: string;
      port: number;
    };
  };
}

export type QueueBatchAction =
  | "cancel"
  | "delete"
  | "retry"
  | "priority"
  | "profile"
  | "pause"
  | "resume";
