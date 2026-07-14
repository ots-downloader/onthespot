import { AccountItem } from "../types";

export const CATALOG_SERVICE_LABELS: Record<string, string> = {
  apple_music: "Apple Music",
  bandcamp: "Bandcamp",
  crunchyroll: "Crunchyroll",
  deezer: "Deezer",
  qobuz: "Qobuz",
  soundcloud: "SoundCloud",
  spotify: "Spotify",
  tidal: "Tidal",
  youtube_music: "YouTube Music",
};

export const getCatalogServiceLabel = (service: string): string =>
  CATALOG_SERVICE_LABELS[service] || service.replaceAll("_", " ");

export const getAvailableCatalogServices = (accounts: AccountItem[]): string[] =>
  Array.from(
    new Set(
      accounts
        .filter((account) => account.active && account.service in CATALOG_SERVICE_LABELS)
        .map((account) => account.service),
    ),
  ).sort((left, right) =>
    getCatalogServiceLabel(left).localeCompare(getCatalogServiceLabel(right)),
  );
