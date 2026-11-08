export interface CatalogServiceInfo {
  id: string;
  name: string;
  category: "music" | "video" | "misc";
  accountType: "Premium" | "Lossless Hi-Res" | "Free / Public" | "OAuth / Token";
  maxBitrate: string;
  color: string;
  badgeVariant: "success" | "warning" | "neutral" | "info" | "purple" | "teal" | "blue";
  description: string;
  authRequirement: string;
  authMode: "none" | "device" | "token" | "email-password" | "youtube";
  tokenLabel?: string;
  tokenRequired?: boolean;
}

export const CATALOG_SERVICES: CatalogServiceInfo[] = [
  {
    id: "spotify",
    name: "Spotify",
    category: "music",
    accountType: "Premium",
    maxBitrate: "320 kbps Ogg Vorbis",
    color: "#1ed760",
    badgeVariant: "success",
    description: "High quality streaming with complete metadata, canvas, and lyrics.",
    authRequirement: "Requires Spotify Premium and Dev API Keys. Needs additional setup",
    authMode: "device",
  },
  {
    id: "deezer",
    name: "Deezer",
    category: "music",
    accountType: "Lossless Hi-Res",
    maxBitrate: "1411 kbps FLAC (16-bit/44.1kHz)",
    color: "#a855f7",
    badgeVariant: "purple",
    description: "Lossless FLAC audio downloads with embedded synchronized lyrics.",
    authRequirement: "Paste the ARL value from your Deezer session.",
    authMode: "token",
    tokenLabel: "ARL Cookie",
    tokenRequired: true,
  },
  {
    id: "tidal",
    name: "Tidal",
    category: "music",
    accountType: "Lossless Hi-Res",
    maxBitrate: "Lossless Hi-Fi / MQA (up to 9216 kbps)",
    color: "#06b6d4",
    badgeVariant: "info",
    description: "Studio-master quality FLAC downloads directly from Tidal master catalog.",
    authRequirement: "Starts a Tidal device-link sign-in in your browser.",
    authMode: "device",
  },
  {
    id: "applemusic",
    name: "Apple Music",
    category: "music",
    accountType: "Lossless Hi-Res",
    maxBitrate: "Lossless ALAC / AAC 256",
    color: "#f43f5e",
    badgeVariant: "blue",
    description: "Apple Music catalog downloads including Dolby Atmos spatial masters when available.",
    authRequirement: "Paste a valid Apple Music media-user token.",
    authMode: "token",
    tokenLabel: "Media User Token",
    tokenRequired: true,
  },
  {
    id: "qobuz",
    name: "Qobuz",
    category: "music",
    accountType: "Lossless Hi-Res",
    maxBitrate: "Studio Hi-Res 24-bit / 192kHz FLAC",
    color: "#38bdf8",
    badgeVariant: "teal",
    description: "Audiophile-grade 24-bit uncompressed studio masters with digital booklet support.",
    authRequirement: "Use your Qobuz email address and password.",
    authMode: "email-password",
  },
  {
    id: "soundcloud",
    name: "SoundCloud",
    category: "music",
    accountType: "Free / Public",
    maxBitrate: "128k MP3 / 256k AAC Go+",
    color: "#f97316",
    badgeVariant: "warning",
    description: "Independent tracks, remixes, DJ mixes, and public releases.",
    authRequirement: "Optional for public content; add an OAuth token for account access.",
    authMode: "token",
    tokenLabel: "OAuth Token",
    tokenRequired: false,
  },
  {
    id: "bandcamp",
    name: "Bandcamp",
    category: "music",
    accountType: "Free / Public",
    maxBitrate: "Source Original / 128k MP3",
    color: "#0ea5e9",
    badgeVariant: "teal",
    description: "Direct artist music releases and community discographies.",
    authRequirement: "Uses the public Bandcamp worker. No sign-in is required.",
    authMode: "none",
  },
  {
    id: "youtube_music",
    name: "YouTube Music",
    category: "music",
    accountType: "Free / Public",
    maxBitrate: "256 kbps m4a",
    color: "#ef4444",
    badgeVariant: "neutral",
    description: "YouTube Music tracks, music videos, and audio streams.",
    authRequirement: "Configure an explicit local YouTube session for videos that require sign-in or add public account.",
    authMode: "youtube",
  },
  {
    id: "crunchyroll",
    name: "Crunchyroll",
    category: "video",
    accountType: "Premium",
    maxBitrate: "1080p AVC / AAC Video Stream",
    color: "#f59e0b",
    badgeVariant: "warning",
    description: "Anime soundtracks, OP/ED themes, and episode media.",
    authRequirement: "Use your Crunchyroll email address and password.",
    authMode: "email-password",
  },
  {
    id: "generic",
    name: "Generic",
    category: "misc",
    accountType: "Free / Public",
    maxBitrate: "Source Stream",
    color: "#6b7280",
    badgeVariant: "neutral",
    description: "Uses the public generic worker for yt-dlp supported audio & video sites.",
    authRequirement: "Uses the public generic worker. No sign-in is required.",
    authMode: "none",
  },
];

export type CredentialMode = "none" | "device" | "token" | "email-password" | "youtube";

export interface ServiceOption {
  value: string;
  label: string;
  mode: CredentialMode;
  requirement: string;
  tokenLabel?: string;
  tokenRequired?: boolean;
}

export const SERVICE_OPTIONS: ReadonlyArray<ServiceOption> = [
  { value: "applemusic", label: "Apple Music", mode: "token", tokenLabel: "Media User Token", requirement: "Paste a valid Apple Music media-user token.", tokenRequired: true },
  { value: "bandcamp", label: "Bandcamp", mode: "none", requirement: "Uses the public Bandcamp worker. No sign-in is required." },
  { value: "crunchyroll", label: "Crunchyroll", mode: "email-password", requirement: "Use your Crunchyroll email address and password." },
  { value: "deezer", label: "Deezer", mode: "token", tokenLabel: "ARL Cookie", requirement: "Paste the ARL value from your Deezer session.", tokenRequired: true },
  { value: "generic", label: "Generic", mode: "none", requirement: "Uses the public generic worker. No sign-in is required." },
  { value: "qobuz", label: "Qobuz", mode: "email-password", requirement: "Use your Qobuz email address and password." },
  { value: "soundcloud", label: "SoundCloud", mode: "token", tokenLabel: "OAuth Token", requirement: "Optional for public content; add a token for account access.", tokenRequired: false },
  { value: "spotify", label: "Spotify", mode: "device", requirement: "Requires Spotify Premium. Sign in with a code at spotify.com/pair from any device." },
  { value: "tidal", label: "Tidal", mode: "device", requirement: "Starts a Tidal device-link sign-in in your browser." },
  { value: "youtube_music", label: "YouTube Music", mode: "youtube", requirement: "Configure an explicit local YouTube session for videos that require sign-in or add public account" },
];

export function getServiceInfo(serviceId: string): CatalogServiceInfo {
  const normalized = serviceId.toLowerCase().replace(/[-_]/g, "");
  return (
    CATALOG_SERVICES.find((s) => s.id.toLowerCase().replace(/[-_]/g, "") === normalized) || {
      id: serviceId,
      name: serviceId.charAt(0).toUpperCase() + serviceId.slice(1),
      category: "misc",
      accountType: "Free / Public",
      maxBitrate: "Source stream",
      color: "#9ca3af",
      badgeVariant: "neutral",
      description: "Generic media worker",
      authRequirement: "No authentication required.",
      authMode: "none",
    }
  );
}
