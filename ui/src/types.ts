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
  spotify_webapi_override_client_id: string;
  spotify_webapi_override_client_secret: string;
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
  track_file_format: string;
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
  file_bitrate: string;
  file_hertz: number;
  use_custom_file_bitrate: boolean;
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
}

export interface SearchResultItem {
  id: string;
  item_service: string;
  item_type: 'track' | 'album' | 'playlist' | 'artist' | 'podcast' | 'episode' | 'movie' | 'show';
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

export interface DownloadQueueItem {
  local_id: string;
  available: boolean;
  item_service: string;
  item_type: string;
  item_id: string;
  item_status: 'Waiting' | 'Downloading' | 'Downloaded' | 'Failed' | 'Cancelled';
  file_path: string | null;
  parent_category: string;
  playlist_name: string;
  playlist_by: string;
  playlist_number?: number;
  name: string;
  artist: string;
  album?: string;
  thumbnail?: string;
  progress: number;
  download_speed: string;
  length: number;
  format: string;
  bitrate?: number;
  url?: string;
}

export interface LogEntry {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'GUI';
  message: string;
}

export interface NotificationBannerItem {
  id: string;
  title: string;
  message: string;
  status: string;
  thumbnail?: string;
  timestamp?: Date;
  url?: string;
}


export interface NotificationContent {
  id: string;
  title: string;
  message?: string;
  url?: string;
}