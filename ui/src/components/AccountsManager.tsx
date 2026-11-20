import {
  Activity,
  AlertCircle,
  Check,
  CirclePlay,
  Cloud,
  Copy,
  Disc3,
  Download,
  Film,
  Headphones,
  Heart,
  Loader2,
  Music2,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  Users,
  Waves,
} from "lucide-react";
import React, { useEffect, useRef, useState } from "react";
import {
  cancelSpotifyDeviceAuth,
  configureYouTubeAuthentication,
  fetchYouTubeAuthenticationStatus,
  getSpotifyDeviceAuthStatus,
  reconnectAccounts,
  startSpotifyDeviceAuth,
  uploadYouTubeCookies,
} from "../lib/api";
import {
  SERVICE_OPTIONS,
  getServiceInfo
} from "../lib/catalogServices";
import { cn } from "../lib/cn";
import { notify } from "../lib/notifications";
import {
  AccountHealth,
  AccountItem,
  SpotifyDeviceAuthStatus,
  YouTubeAuthenticationStatus,
  YouTubeSetupMode,
} from "../types";
import { Button, Dialog, Select, TextInput, focusRing } from "./ui";

const SPOTIFY_AUTH_POLL_MS = 2000;
// The server refills its account pool in the background after a sign-in, so
// refresh the list once more after this delay.
const SPOTIFY_ACCOUNT_RECHECK_MS = 3000;

const spotifyAuthFailureMessage = (status: SpotifyDeviceAuthStatus): string => {
  if (status.message) return status.message;
  switch (status.state) {
    case "denied":
      return "Sign-in was declined in Spotify. Get a new code to try again.";
    case "expired":
      return "The sign-in code expired. Get a new code to try again.";
    case "cancelled":
      return "Sign-in was cancelled. Get a new code to try again.";
    default:
      break;
  }
  switch (status.error_code) {
    case "not_premium":
      return "Spotify Premium is required for this account.";
    case "login_timeout":
      return "Spotify did not answer in time. Try again.";
    default:
      return "Spotify sign-in failed. Try again.";
  }
};

const formatCountdown = (seconds: number): string => {
  const clamped = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(clamped / 60);
  return `${minutes}:${String(clamped % 60).padStart(2, "0")}`;
};

interface ServicePresentation {
  label: string;
  accountType: string;
  maxBitrate: string;
  Icon: React.ElementType;
  /** Brand colour from catalogServices; undefined means neutral roles. */
  color?: string;
}

const brandColor = (serviceId: string): string => getServiceInfo(serviceId).color;

const getServicePresentation = (service: string): ServicePresentation => {
  switch (service.toLowerCase()) {
    case "spotify":
      return {
        label: "Spotify",
        accountType: "Premium",
        maxBitrate: "320k",
        Icon: Music2,
        color: brandColor("spotify"),
      };
    case "tidal":
      return {
        label: "Tidal",
        accountType: "Premium",
        maxBitrate: "1411k",
        Icon: Waves,
        color: brandColor("tidal"),
      };
    case "apple_music":
    case "applemusic":
      return {
        label: "Apple Music",
        accountType: "Premium",
        maxBitrate: "Lossless",
        Icon: Music2,
        color: brandColor("applemusic"),
      };
    case "soundcloud":
      return {
        label: "SoundCloud",
        accountType: "Public",
        maxBitrate: "128k",
        Icon: Cloud,
        color: brandColor("soundcloud"),
      };
    case "bandcamp":
      return {
        label: "Bandcamp",
        accountType: "Public",
        maxBitrate: "Source",
        Icon: Disc3,
        color: brandColor("bandcamp"),
      };
    case "youtube_music":
    case "youtube":
      return {
        label: "YouTube Music",
        accountType: "Public",
        maxBitrate: "256k",
        Icon: CirclePlay,
        color: brandColor("youtube_music"),
      };
    case "deezer":
      return {
        label: "Deezer",
        accountType: "Premium",
        maxBitrate: "1411k",
        Icon: Heart,
        color: brandColor("deezer"),
      };
    case "qobuz":
      return {
        label: "Qobuz",
        accountType: "Premium",
        maxBitrate: "1411k",
        Icon: Headphones,
        color: brandColor("qobuz"),
      };
    case "crunchyroll":
      return {
        label: "Crunchyroll",
        accountType: "Premium",
        maxBitrate: "Video",
        Icon: Film,
        color: brandColor("crunchyroll"),
      };
    default:
      return {
        label: "Generic",
        accountType: "Free",
        maxBitrate: "Source",
        Icon: Download,
      };
  }
};

export interface AccountsManagerProps {
  accounts: AccountItem[];
  health?: AccountHealth | null;
  onAddAccount: (
    service: string,
    credentials: { username?: string; token?: string; password?: string }
  ) => Promise<AccountItem | null>;
  onRemoveAccount: (uuid: string) => Promise<boolean>;
  onRefreshAccounts: () => Promise<AccountItem[]>;
  onReconnect?: () => Promise<boolean>;
  onConfigureYouTubeAuthentication?: (authentication: {
    mode: "none" | "browser" | "cookie_file";
    browser?: string;
    cookie_file?: string;
  }) => Promise<boolean>;
  onUploadYouTubeCookies?: (file: File) => Promise<YouTubeAuthenticationStatus | null>;
  youtubeAuthenticationMode?: "none" | "browser" | "cookie_file";
  youtubeBrowser?: string;
  youtubeCookieFile?: string;
}

export const AccountsManager: React.FC<AccountsManagerProps> = ({
  accounts,
  onAddAccount,
  onRemoveAccount,
  onRefreshAccounts,
  health,
  onReconnect,
  onConfigureYouTubeAuthentication,
  onUploadYouTubeCookies,
  youtubeAuthenticationMode,
  youtubeBrowser: configuredYoutubeBrowser,
  youtubeCookieFile: configuredYoutubeCookieFile,
}) => {
  const [showModal, setShowModal] = useState(false);
  const [service, setService] = useState<string>("spotify");
  const [username, setUsername] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [formError, setFormError] = useState("");
  const [signInStarted, setSignInStarted] = useState("");
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  // YouTube setup state
  const [youtubeAuthMode, setYoutubeAuthMode] = useState<YouTubeSetupMode>("upload");
  const [youtubeBrowser, setYoutubeBrowser] = useState("edge");
  const [youtubeCookieFile, setYoutubeCookieFile] = useState("");
  const [youtubeCookieUpload, setYoutubeCookieUpload] = useState<File | null>(null);
  const [youtubeStatus, setYoutubeStatus] = useState<YouTubeAuthenticationStatus | null>(null);
  const [youtubeUploadComplete, setYoutubeUploadComplete] = useState(false);

  // Spotify device-code sign-in state
  const [spotifyAuth, setSpotifyAuth] = useState<SpotifyDeviceAuthStatus | null>(null);
  const [now, setNow] = useState(() => Date.now() / 1000);
  const spotifyAuthActive =
    spotifyAuth?.state === "pending" || spotifyAuth?.state === "authorizing";
  // Approved but still refreshing the account list before the modal closes.
  const spotifyAuthFinishing = spotifyAuth?.state === "approved";
  const activeSpotifyFlowId = spotifyAuthActive ? spotifyAuth.flow_id : null;
  // Mirror state into refs so async poll results and cancel-on-unmount see the latest flow.
  const spotifyAuthRef = useRef(spotifyAuth);
  spotifyAuthRef.current = spotifyAuth;
  const activeSpotifyFlowRef = useRef<string | null>(null);
  activeSpotifyFlowRef.current = activeSpotifyFlowId;
  // App passes a new function on every render; keep the latest without restarting the poll.
  const refreshAccountsRef = useRef(onRefreshAccounts);
  refreshAccountsRef.current = onRefreshAccounts;
  const accountRecheckRef = useRef<number | null>(null);

  const selectedService =
    SERVICE_OPTIONS.find((option) => option.value === service) ?? SERVICE_OPTIONS[0];

  const sortedAccounts = [...accounts].sort((left, right) =>
    getServicePresentation(left.service).label.localeCompare(
      getServicePresentation(right.service).label
    )
  );

  const stopSpotifySignIn = () => {
    const flowId = activeSpotifyFlowRef.current;
    activeSpotifyFlowRef.current = null;
    if (flowId) {
      void cancelSpotifyDeviceAuth(flowId).catch(() => undefined);
    }
    setSpotifyAuth(null);
  };

  const closeModal = () => {
    stopSpotifySignIn();
    setShowModal(false);
  };

  const openAddModalForService = (serviceId: string) => {
    stopSpotifySignIn();
    setService(serviceId);
    setUsername("");
    setToken("");
    setFormError("");
    setSignInStarted("");
    if (serviceId === "youtube") {
      setYoutubeAuthMode("upload");
      setYoutubeBrowser(configuredYoutubeBrowser || "edge");
      setYoutubeCookieFile(configuredYoutubeCookieFile || "");
      setYoutubeCookieUpload(null);
      setYoutubeUploadComplete(false);
      void (onConfigureYouTubeAuthentication
        ? fetchYouTubeAuthenticationStatus()
        : fetchYouTubeAuthenticationStatus()
      ).then(setYoutubeStatus);
    }
    setShowModal(true);
  };

  const openYouTubeSetup = () => {
    openAddModalForService("youtube");
  };

  useEffect(() => {
    let cancelled = false;
    void fetchYouTubeAuthenticationStatus().then((status) => {
      if (!cancelled) setYoutubeStatus(status);
    });
    return () => {
      cancelled = true;
    };
  }, [youtubeAuthenticationMode, configuredYoutubeBrowser, configuredYoutubeCookieFile]);

  const startSpotifySignIn = async () => {
    setLoading(true);
    try {
      const status = await startSpotifyDeviceAuth();
      setNow(Date.now() / 1000);
      setSpotifyAuth(status);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not start Spotify sign-in.");
    } finally {
      setLoading(false);
    }
  };

  // Cancel a live flow if the page goes away mid sign-in.  The server ignores
  // this once Spotify has granted the sign-in, and the result is not used.
  useEffect(
    () => () => {
      const flowId = activeSpotifyFlowRef.current;
      if (flowId) void cancelSpotifyDeviceAuth(flowId).catch(() => undefined);
      if (accountRecheckRef.current !== null) window.clearTimeout(accountRecheckRef.current);
    },
    []
  );

  // Tick the countdown only while a code is live.
  useEffect(() => {
    if (!activeSpotifyFlowId) return undefined;
    setNow(Date.now() / 1000);
    const tick = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(tick);
  }, [activeSpotifyFlowId]);

  // Poll the server until the flow leaves pending/authorizing.
  useEffect(() => {
    if (!activeSpotifyFlowId) return undefined;
    const flowId = activeSpotifyFlowId;
    let cancelled = false;
    let inFlight = false;

    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        let status: SpotifyDeviceAuthStatus | null;
        try {
          status = await getSpotifyDeviceAuthStatus(flowId);
        } catch {
          return; // network blip; try again on the next tick
        }
        if (cancelled) return;

        if (!status) {
          setSpotifyAuth((prev) =>
            prev && prev.flow_id === flowId ? { ...prev, state: "expired", message: "" } : prev
          );
          setFormError("The sign-in code expired. Get a new code to try again.");
          return;
        }

        if (status.state === "approved") {
          // Leaving the active states stops this poll and means a close no longer cancels.
          setSpotifyAuth(status);
          await refreshAccountsRef.current().catch(() => undefined);
          if (accountRecheckRef.current !== null) window.clearTimeout(accountRecheckRef.current);
          accountRecheckRef.current = window.setTimeout(() => {
            accountRecheckRef.current = null;
            void refreshAccountsRef.current().catch(() => undefined);
          }, SPOTIFY_ACCOUNT_RECHECK_MS);
          const who = status.username ? ` as ${status.username}` : "";
          notify({ title: "Spotify connected", message: `Spotify connected${who}.`, status: "success" });
          // Close only if the user has not already closed or moved on to another flow.
          if (spotifyAuthRef.current?.flow_id === flowId) {
            setSpotifyAuth(null);
            setFormError("");
            setShowModal(false);
          }
          return;
        }

        setSpotifyAuth(status);
        if (status.state !== "pending" && status.state !== "authorizing") {
          setFormError(spotifyAuthFailureMessage(status));
        }
      } finally {
        inFlight = false;
      }
    };

    const interval = window.setInterval(() => void poll(), SPOTIFY_AUTH_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [activeSpotifyFlowId]);

  const youtubeExportInstallCommand = `$otsYtDlp = Join-Path $env:TEMP "OnTheSpot-youtube-auth"\npy -m venv $otsYtDlp\n& (Join-Path $otsYtDlp "Scripts\\python.exe") -m pip install --disable-pip-version-check --quiet --upgrade yt-dlp`;
  const youtubeExportCommand = `$otsYtDlp = Join-Path $env:TEMP "OnTheSpot-youtube-auth"\n& (Join-Path $otsYtDlp "Scripts\\python.exe") -m yt_dlp --cookies-from-browser ${youtubeBrowser} --cookies "$HOME\\Downloads\\youtube-cookies.txt"`;
  const youtubeCleanupCommand = `Remove-Item -LiteralPath "$HOME\\Downloads\\youtube-cookies.txt" -Force -ErrorAction SilentlyContinue\nRemove-Item -LiteralPath (Join-Path $env:TEMP "OnTheSpot-youtube-auth") -Recurse -Force -ErrorAction SilentlyContinue`;

  const copyText = async (value: string, message: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopyFeedback(message);
      setSignInStarted(message);
      setTimeout(() => setCopyFeedback(null), 3000);
    } catch {
      setSignInStarted("Copy was blocked by the browser. Select the command and copy it manually.");
    }
  };

  const handleReconnect = async () => {
    setReconnecting(true);
    try {
      if (onReconnect) {
        await onReconnect();
      } else {
        await reconnectAccounts();
      }
      await onRefreshAccounts();
    } finally {
      setReconnecting(false);
    }
  };

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError("");
    setSignInStarted("");

    if (selectedService.value === "spotify") {
      await startSpotifySignIn();
      return;
    }

    if (selectedService.mode === "email-password" && (!username.trim() || !token.trim())) {
      setFormError("Enter both your email address and password to continue.");
      return;
    }

    if (selectedService.mode === "token" && selectedService.tokenRequired && !token.trim()) {
      setFormError(`Enter your ${selectedService.tokenLabel?.toLowerCase() || "access token"} to continue.`);
      return;
    }

    if (selectedService.mode === "youtube") {
      if (youtubeAuthMode === "upload" && !youtubeCookieUpload) {
        setFormError("Choose a Netscape-format cookies.txt file exported from YouTube.");
        return;
      }
      if (youtubeAuthMode === "cookie_file" && !youtubeCookieFile.trim()) {
        setFormError("Enter an absolute path to a Netscape-format cookies file on the OnTheSpot server.");
        return;
      }

      setLoading(true);
      try {
        if (youtubeAuthMode === "upload" && youtubeCookieUpload) {
          const uploadFn = onUploadYouTubeCookies || uploadYouTubeCookies;
          const status = await uploadFn(youtubeCookieUpload);
          if (!status?.ready) {
            throw new Error(status?.error || "The uploaded YouTube session is not usable.");
          }
          setYoutubeStatus(status);
          setYoutubeCookieUpload(null);
          setYoutubeUploadComplete(true);
          setSignInStarted("YouTube cookies installed on OnTheSpot. Run the cleanup command below to remove temporary local files.");
          await onAddAccount("youtube", { username: "YouTube Session (Cookies)", token: "cookies" });
        } else {
          const configureFn = onConfigureYouTubeAuthentication || configureYouTubeAuthentication;
          const configured = await configureFn({
            mode: youtubeAuthMode as "none" | "browser" | "cookie_file",
            browser: youtubeAuthMode === "browser" ? youtubeBrowser : undefined,
            cookie_file: youtubeAuthMode === "cookie_file" ? youtubeCookieFile : undefined,
          });
          if (!configured) {
            throw new Error("The selected YouTube session source is not usable.");
          }
          const freshStatus = await fetchYouTubeAuthenticationStatus();
          setYoutubeStatus(freshStatus);
          await onAddAccount("youtube", {
            username:
              youtubeAuthMode === "browser"
                ? `Browser (${youtubeBrowser})`
                : youtubeAuthMode === "cookie_file"
                ? `File (${youtubeCookieFile})`
                : "Public YouTube worker",
          });
          setShowModal(false);
          setYoutubeCookieFile("");
        }
      } catch (error) {
        setFormError(error instanceof Error ? error.message : "Could not configure YouTube authentication.");
        return;
      } finally {
        setLoading(false);
      }
      return;
    }

    setLoading(true);
    try {
      const res = await onAddAccount(service, { username, token });
      if (res) {
        if (selectedService.mode === "device") {
          setSignInStarted(
            "Sign-in started. Follow the service's device-link prompt, then refresh Accounts."
          );
          return;
        }
        setShowModal(false);
        setUsername("");
        setToken("");
      } else {
        setShowModal(false);
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to add account.");
    } finally {
      setLoading(false);
    }
  };

  // Determine health details
  const isHealthy =
    health?.healthy ?? (accounts.filter((a) => a.active).length > 0);
  const authenticatedWorkers =
    health?.authenticated_accounts ?? accounts.filter((a) => a.active).length;
  const configuredWorkers =
    health?.configured_accounts ?? accounts.length;
  const missingServices = health?.missing_services ?? [];

  const browserOptions = [
    { value: "edge", label: "Microsoft Edge" },
    { value: "chrome", label: "Google Chrome" },
    { value: "brave", label: "Brave" },
    { value: "firefox", label: "Firefox" },
    { value: "vivaldi", label: "Vivaldi" },
    { value: "opera", label: "Opera" },
  ];

  return (
    <div className="space-y-6 font-sans" id="accounts-manager-view">
      {/* Top Hero Banner */}
      <div className="rounded-xl border border-line bg-surface p-6 shadow-xs">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-subtle text-accent">
                <Users className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-bold text-fg">
                Accounts & Workers
              </h2>
              <span className="inline-flex items-center rounded-full bg-accent-subtle px-2.5 py-0.5 text-xs font-semibold text-accent">
                {accounts.length} active {accounts.length === 1 ? "worker" : "workers"}
              </span>
            </div>
            <p className="mt-1.5 text-xs sm:text-sm text-fg-muted max-w-2xl">
              Accounts are automatically rotated to distribute API load, bypass rate limits, and provide lossless streaming endpoints if available.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <Button
              variant="secondary"
              size="sm"
              onClick={handleReconnect}
              isDisabled={reconnecting}
              id="btn-reconnect-workers"
              icon={
                <RefreshCw
                  className={cn("h-3.5 w-3.5", reconnecting && "animate-spin text-accent")}
                />
              }
              label={reconnecting ? "Reconnecting…" : "Reconnect"}
            />

            <Button
              variant="accent"
              size="sm"
              onClick={() => openAddModalForService("spotify")}
              id="btn-open-add-account"
              icon={<Plus className="h-4 w-4" />}
              label="Add Account"
            />
          </div>
        </div>
      </div>

      {/* Worker Pool Health Status Banner */}
      <div
        className={`flex flex-col justify-between gap-4 rounded-xl border p-4 sm:flex-row sm:items-center ${
          isHealthy
            ? "border-success/30 bg-success-subtle"
            : "border-warning/30 bg-warning-subtle"
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
              isHealthy ? "bg-success/20 text-success-fg" : "bg-warning/20 text-warning-fg"
            }`}
          >
            <Activity className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs font-semibold text-fg">
              Worker pool: {isHealthy ? "Ready" : "Needs attention"}
            </p>
            <p className="text-xs text-fg-muted mt-0.5">
              {authenticatedWorkers} authenticated · {configuredWorkers} configured
              {missingServices.length > 0 && (
                <span className="text-warning-fg ml-1.5 font-medium">
                  · Missing: {missingServices.join(", ")}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-fg-muted">
          <span className="font-medium">Spotify Connect:</span>
          <span
            className={`inline-flex items-center gap-1 font-semibold ${
              health?.spotify?.connected || accounts.some((a) => a.service === "spotify" && a.active)
                ? "text-success-fg"
                : "text-fg-muted"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                health?.spotify?.connected || accounts.some((a) => a.service === "spotify" && a.active)
                  ? "bg-success"
                  : "bg-line-strong"
              }`}
            />
            {health?.spotify?.status || (accounts.some((a) => a.service === "spotify" && a.active) ? "Ready" : "Standby")}
          </span>
        </div>
      </div>

      {/* Connected Accounts Table */}
      <div className="rounded-xl border border-line bg-surface overflow-hidden shadow-xs">
        <div className="border-b border-line px-5 py-4 flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-fg">
              Connected Workers & Sessions
            </h3>
            <p className="text-xs text-fg-muted">
              Active accounts rotated for music and metadata streaming
            </p>
          </div>
          <span className="text-xs text-fg-subtle font-mono">
            {accounts.length} total
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs sm:text-sm">
            <thead className="border-b border-line bg-sunken text-[11px] font-semibold uppercase tracking-wider text-fg-muted">
              <tr>
                <th className="px-5 py-3">Account</th>
                <th className="px-5 py-3">Service</th>
                <th className="px-5 py-3">Account type</th>
                <th className="px-5 py-3">Max bitrate</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {sortedAccounts.map((acc) => {
                const presentation = getServicePresentation(acc.service);
                const { Icon } = presentation;
                const connected = acc.active;
                const isPublicWorker =
                  ["generic", "bandcamp", "youtube", "youtube_music"].includes(
                    acc.service.toLowerCase()
                  ) || acc.uuid.startsWith("public_");
                const isYoutubeWorker =
                  acc.service.toLowerCase() === "youtube" ||
                  acc.service.toLowerCase() === "youtube_music";

                const youtubeSessionConfigured = Boolean(youtubeStatus?.configured);
                const youtubeSessionReady = Boolean(youtubeStatus?.ready);

                const statusLabel = isYoutubeWorker
                  ? youtubeSessionReady
                    ? youtubeStatus?.mode === "browser"
                      ? "Browser configured"
                      : "Cookies loaded"
                    : youtubeSessionConfigured
                    ? "Session unavailable"
                    : youtubeStatus
                    ? "Ready (No cookies)"
                    : "Session unverified"
                  : isPublicWorker
                  ? connected
                    ? "Ready (no sign-in)"
                    : "Disabled"
                  : connected
                  ? "Authenticated"
                  : "Needs sign-in";

                const statusReady = isYoutubeWorker ? youtubeSessionReady : connected;

                const accountLabel = isPublicWorker
                  ? acc.service.toLowerCase() === "generic"
                    ? "General media worker"
                    : isYoutubeWorker
                    ? "YouTube catalogue worker"
                    : `${presentation.label} public worker`
                  : `${presentation.label} account`;

                const accountDetail = isPublicWorker
                  ? acc.service.toLowerCase() === "generic"
                    ? "yt-dlp fallback for other supported sites"
                    : isYoutubeWorker
                    ? "Searches and downloads YouTube links"
                    : "Built-in public access"
                  : acc.username || "Signed-in account";

                return (
                  <tr
                    key={acc.uuid}
                    className="transition-colors hover:bg-sunken"
                  >
                    <td className="px-5 py-4">
                      <div className="min-w-0">
                        <p className="max-w-48 truncate font-semibold text-fg">
                          {accountLabel}
                        </p>
                        <p
                          className="mt-0.5 max-w-48 truncate text-xs text-fg-muted font-mono"
                          title={isPublicWorker ? acc.uuid : accountDetail}
                        >
                          {accountDetail}
                        </p>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2.5 font-medium text-fg">
                        <Icon
                          className={cn("h-4 w-4 shrink-0", !presentation.color && "text-fg-subtle")}
                          style={presentation.color ? { color: presentation.color } : undefined}
                        />
                        <span>{presentation.label}</span>
                      </div>
                    </td>
                    <td className="px-5 py-4 text-fg-muted">
                      <span className="inline-flex items-center rounded-md px-2 py-0.5 text-xs bg-raised font-medium">
                        {presentation.accountType}
                      </span>
                    </td>
                    <td className="px-5 py-4 font-mono text-xs text-fg-muted">
                      {presentation.maxBitrate}
                    </td>
                    <td className="px-5 py-4">
                      <span
                        title={
                          isYoutubeWorker
                            ? youtubeStatus?.error || youtubeStatus?.source
                            : undefined
                        }
                        className={`inline-flex items-center gap-1.5 text-xs font-medium ${
                          statusReady ? "text-success-fg" : "text-warning-fg"
                        }`}
                      >
                        <span
                          className={`h-2 w-2 rounded-full ${
                            statusReady ? "bg-success" : "bg-warning"
                          }`}
                        />
                        {statusLabel}
                      </span>
                      {isYoutubeWorker && youtubeStatus?.error && (
                        <p className="mt-1 max-w-64 text-[11px] leading-snug text-fg-muted">
                          {youtubeStatus.error}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex items-center justify-end gap-2 whitespace-nowrap">
                        {isYoutubeWorker && (
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={openYouTubeSetup}
                            label={youtubeSessionConfigured ? "Reconfigure" : "Set up"}
                          />
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onRemoveAccount(acc.uuid)}
                          className="text-danger-fg hover:bg-danger-subtle"
                          title="Remove account"
                          icon={<Trash2 className="h-3.5 w-3.5" />}
                          label="Remove"
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
              {accounts.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-sm text-fg-muted">
                    No connected worker accounts yet. Click <strong>Add Account</strong> above to authenticate your first streaming platform.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Available Services Catalog Grid */}
      <div className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-fg">
            Available Service Integrations
          </h3>
          <p className="text-xs text-fg-muted">
            Click Connect on any service to add credentials, configure local sessions, or initialize background workers
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {SERVICE_OPTIONS.map((srvOption) => {
            const srv = getServiceInfo(srvOption.value);
            const presentation = getServicePresentation(srvOption.value);
            const { Icon } = presentation;
            const isConfigured = accounts.some(
              (a) => a.service.toLowerCase() === srvOption.value.toLowerCase()
            );

            return (
              <div
                key={srvOption.value}
                className="rounded-xl border border-line bg-surface p-4 shadow-xs flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div
                        className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-lg",
                          !presentation.color && "bg-raised"
                        )}
                        style={
                          presentation.color
                            ? { backgroundColor: `${presentation.color}1a` }
                            : undefined
                        }
                      >
                        <Icon
                          className={cn("h-5 w-5", !presentation.color && "text-fg-subtle")}
                          style={presentation.color ? { color: presentation.color } : undefined}
                        />
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold text-fg">
                          {srvOption.label}
                        </h4>
                        <span className="text-[11px] text-fg-muted">
                          {presentation.accountType} · {presentation.maxBitrate}
                        </span>
                      </div>
                    </div>

                    {isConfigured ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-success-subtle px-2 py-0.5 text-[11px] font-semibold text-success-fg">
                        <Check className="w-3 h-3" /> Configured
                      </span>
                    ) : (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => openAddModalForService(srvOption.value)}
                        label="Connect"
                      />
                    )}
                  </div>

                  <p className="mt-2.5 text-xs text-fg-muted leading-relaxed">
                    {srvOption.requirement}
                  </p>
                </div>

                <div className="mt-3 pt-3 border-t border-line flex items-center justify-between text-[11px] text-fg-subtle">
                  <span className="font-mono">
                    Mode:{" "}
                    <span className="text-fg-muted font-medium capitalize">
                      {srvOption.mode}
                    </span>
                  </span>
                  {srvOption.tokenLabel && (
                    <span className="font-medium text-fg-muted">
                      {srvOption.tokenLabel}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Add Account Dialog */}
      <Dialog
        isOpen={showModal}
        onClose={closeModal}
        dismissible={false}
        title="Add Worker Account"
        description="Authenticate Spotify Librespot, Tidal OAuth, Apple Music, SoundCloud, or other supported services."
        icon={<Server />}
        size={service === "youtube" ? "lg" : "md"}
        closeLabel="Close add account dialog"
        footer={
          <>
            <Button variant="ghost" onClick={closeModal} label="Cancel" size="sm" />

            {selectedService.mode === "youtube" && youtubeUploadComplete ? (
              <Button
                variant="accent"
                size="sm"
                onClick={() => {
                  setYoutubeUploadComplete(false);
                  setShowModal(false);
                }}
                label="Done"
              />
            ) : (
              <Button
                variant="accent"
                size="sm"
                type="submit"
                form="add-account-form"
                isLoading={loading}
                isDisabled={spotifyAuthActive || spotifyAuthFinishing}
                label={
                  loading
                    ? "Working…"
                    : selectedService.value === "spotify"
                    ? spotifyAuthActive || spotifyAuthFinishing
                      ? "Waiting for approval…"
                      : spotifyAuth
                      ? "Get a new code"
                      : "Sign in with Spotify"
                    : selectedService.mode === "device"
                    ? "Start sign-in"
                    : selectedService.mode === "youtube"
                    ? "Save YouTube setup"
                    : "Add Account"
                }
              />
            )}
          </>
        }
      >
        <form id="add-account-form" onSubmit={handleAddSubmit} className="space-y-4">
          {/* Platform Service Selector */}
          <div>
            <Select
              label="Platform Service"
              value={selectedService.value}
              onChange={(value) => {
                setService(value);
                setFormError("");
                setSignInStarted("");
                setUsername("");
                setToken("");
                setYoutubeCookieFile("");
                stopSpotifySignIn();
              }}
              options={SERVICE_OPTIONS.map((option) => ({
                value: option.value,
                label: `${option.label} (${option.mode})`,
              }))}
            />
            <p className="mt-2 text-xs leading-relaxed text-fg-muted">
              {selectedService.requirement}
            </p>
          </div>

          {/* Email & Password Mode */}
          {selectedService.mode === "email-password" && (
            <div className="space-y-3">
              <TextInput
                label="Email address"
                type="email"
                value={username}
                onChange={setUsername}
                placeholder="e.g. user@example.com"
              />
              <TextInput
                label="Password"
                type="password"
                value={token}
                onChange={setToken}
                placeholder="Enter your account password"
              />
            </div>
          )}

          {/* Token Mode (Apple Music, Deezer, SoundCloud) */}
          {selectedService.mode === "token" && (
            <div>
              <TextInput
                label={`${selectedService.tokenLabel ?? ""}${selectedService.tokenRequired ? "" : " (optional)"}`}
                type="password"
                value={token}
                onChange={setToken}
                placeholder={`Paste ${selectedService.tokenLabel?.toLowerCase() || "secure token"}`}
                className="font-mono"
              />
              <p className="mt-1.5 text-xs text-fg-muted">
                {selectedService.value === "deezer"
                  ? "Paste the 192-character 'arl' cookie found in your browser when logged into deezer.com."
                  : selectedService.value === "applemusic"
                  ? "Media-user-token obtained from Apple Music website cookies (inspect cookies for apple.com)."
                  : "Optional token for elevated bitrate and user library access."}
              </p>
            </div>
          )}

          {/* Public No-Credential Mode */}
          {selectedService.mode === "none" && (
            <div className="rounded-lg border border-line bg-sunken px-4 py-3 text-xs sm:text-sm text-fg-muted">
              This worker is ready to add without credentials. It will utilize public endpoints and yt-dlp scrapers.
            </div>
          )}

          {/* Device Mode - Non-Spotify (Tidal) */}
          {selectedService.mode === "device" && selectedService.value !== "spotify" && (
            <div className="rounded-lg border border-line bg-sunken px-4 py-3 text-xs sm:text-sm text-fg-muted">
              Click <strong>Start sign-in</strong>, then follow the service device-link prompt. You do not need to enter credentials here.
            </div>
          )}

          {/* Spotify device-code sign-in */}
          {selectedService.value === "spotify" && (
            <div className="space-y-3 rounded-xl border border-line bg-sunken p-4 text-xs sm:text-sm text-fg-muted">
              {spotifyAuth?.state === "pending" ? (
                <>
                  <p>
                    Open the pairing page on any device signed in to Spotify and enter this code.
                  </p>
                  <div className="flex flex-wrap items-center gap-3">
                    <code className="rounded-lg border border-line-strong bg-surface px-4 py-2 font-mono text-2xl font-bold tracking-[0.2em] text-fg">
                      {spotifyAuth.user_code}
                    </code>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void copyText(spotifyAuth.user_code, "Code copied.")}
                      icon={<Copy className="w-3 h-3" />}
                      label="Copy"
                    />
                  </div>
                  <a
                    href={spotifyAuth.verification_uri_complete || spotifyAuth.verification_uri}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`inline-flex items-center gap-1.5 rounded-md bg-accent hover:bg-accent-hover px-3 py-1.5 text-xs font-semibold text-fg-on-accent transition-colors ${focusRing}`}
                  >
                    Open spotify.com/pair
                  </a>
                  <p className="text-[11px] text-fg-muted">
                    Code expires in {formatCountdown(spotifyAuth.expires_at - now)}
                  </p>
                  <p className="flex items-center gap-1.5 text-[11px] font-semibold text-accent">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    Waiting for you to approve in Spotify…
                  </p>
                </>
              ) : spotifyAuth?.state === "authorizing" || spotifyAuthFinishing ? (
                <p className="flex items-center gap-1.5 font-semibold text-accent">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Signing in…
                </p>
              ) : (
                <p>OnTheSpot signs in through Spotify's pairing page. Spotify Premium is required.</p>
              )}
            </div>
          )}

          {/* YouTube Music Mode */}
          {selectedService.mode === "youtube" && (
            <div className="space-y-3.5 rounded-xl border border-line bg-sunken p-4">
              <div>
                <p className="text-sm font-semibold text-fg">
                  YouTube session source
                </p>
                <p className="mt-1 text-xs leading-relaxed text-fg-muted">
                  YouTube does not support yt-dlp OAuth sign-in. For Docker or Unraid, upload a Netscape-format cookies.txt file so the server can use your session.
                </p>
              </div>

              <Select
                label="YouTube session source"
                isLabelHidden
                value={youtubeAuthMode}
                onChange={(value) => {
                  setYoutubeAuthMode(value as YouTubeSetupMode);
                  setYoutubeUploadComplete(false);
                  setFormError("");
                }}
                options={[
                  { value: "none", label: "No Cookie file, only public videos (recommended)" },
                  { value: "upload", label: "Upload cookies.txt (recommended if you must access private videos)" },
                  { value: "browser", label: "Read a browser on the OnTheSpot host" },
                  { value: "cookie_file", label: "Use a file path on the OnTheSpot host" },
                ]}
              />

              {/* YouTube Upload Flow */}
              {youtubeAuthMode === "upload" && (
                <div className="space-y-3">
                  <div className="rounded-lg border-l-4 border-warning bg-warning-subtle p-3 text-xs leading-relaxed text-warning-fg space-y-2.5">
                    <p className="font-semibold text-fg">
                      Create cookies.txt on the computer where you use YouTube
                    </p>
                    <ol className="list-decimal space-y-1 pl-4 text-fg-muted">
                      <li>Sign in to YouTube in your normal browser.</li>
                      <li>Open PowerShell on that computer.</li>
                      <li>Run the temporary setup command once, then run the export command.</li>
                      <li>Return here and select <span className="font-semibold text-fg">Downloads\youtube-cookies.txt</span>.</li>
                      <li>After the upload succeeds, run the cleanup command shown below.</li>
                    </ol>

                    <Select
                      id="youtube-export-browser"
                      label="Browser containing your YouTube session"
                      size="sm"
                      value={youtubeBrowser}
                      onChange={setYoutubeBrowser}
                      options={browserOptions}
                    />

                    <div>
                      <p className="font-semibold text-fg">1. Create a temporary yt-dlp environment</p>
                      <code className="mt-1 block overflow-x-auto whitespace-pre-wrap rounded-md bg-console p-2 font-mono text-[11px] text-console-fg">
                        {youtubeExportInstallCommand}
                      </code>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void copyText(youtubeExportInstallCommand, "Temporary yt-dlp setup command copied.")}
                        className="mt-2"
                        icon={<Copy className="w-3 h-3" />}
                        label="Copy setup command"
                      />
                    </div>

                    <div>
                      <p className="font-semibold text-fg">2. Export the browser cookies</p>
                      <code className="mt-1 block overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-console p-2 font-mono text-[11px] text-console-fg">
                        {youtubeExportCommand}
                      </code>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void copyText(youtubeExportCommand, "YouTube cookie export command copied.")}
                        className="mt-2"
                        icon={<Copy className="w-3 h-3" />}
                        label="Copy export command"
                      />
                    </div>

                    <p className="text-[11px] font-semibold text-fg-muted">
                      Keep the exported file private. OnTheSpot removes every row except YouTube and Google when the file is uploaded.
                    </p>
                  </div>

                  <div>
                    <input
                      type="file"
                      accept=".txt,text/plain"
                      onChange={(e) => {
                        setYoutubeCookieUpload(e.target.files?.[0] || null);
                        setYoutubeUploadComplete(false);
                      }}
                      className={`w-full px-3 py-2 text-xs rounded-lg border border-line-strong bg-surface text-fg file:mr-3 file:py-1 file:px-3 file:rounded-md file:border-0 file:bg-accent file:text-fg-on-accent file:text-xs file:font-semibold hover:file:bg-accent-hover cursor-pointer ${focusRing}`}
                    />
                    <p className="mt-1 text-[11px] text-fg-muted">
                      The filtered file is stored privately in OnTheSpot app data.{" "}
                      <a
                        href="https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp"
                        target="_blank"
                        rel="noreferrer"
                        className="underline font-semibold text-fg"
                      >
                        Official yt-dlp cookie documentation
                      </a>
                    </p>
                  </div>

                  {youtubeUploadComplete && (
                    <div className="rounded-lg border-l-4 border-success bg-success-subtle p-3 text-xs leading-relaxed space-y-2">
                      <p className="font-semibold text-success-fg">
                        3. Clean up the local helper files
                      </p>
                      <p className="text-fg-muted">
                        OnTheSpot now has its private filtered copy. Run this in PowerShell to delete the exported cookie file and the temporary yt-dlp environment from your computer.
                      </p>
                      <code className="block overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-console p-2 font-mono text-[11px] text-console-fg">
                        {youtubeCleanupCommand}
                      </code>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => void copyText(youtubeCleanupCommand, "Cleanup command copied. Run it in PowerShell to remove local helper files.")}
                        icon={<Copy className="w-3 h-3" />}
                        label="Copy cleanup command"
                      />
                    </div>
                  )}
                </div>
              )}

              {/* YouTube Host Browser */}
              {youtubeAuthMode === "browser" && (
                <div className="space-y-2">
                  <Select
                    label="Browser on the OnTheSpot host"
                    isLabelHidden
                    value={youtubeBrowser}
                    onChange={setYoutubeBrowser}
                    options={browserOptions}
                  />
                  <p className="text-[11px] leading-relaxed text-warning-fg">
                    Only use this when that browser is installed on the same machine as the OnTheSpot process. It cannot read a browser on your desktop from inside Docker.
                  </p>
                </div>
              )}

              {/* YouTube Host Cookie File Path */}
              {youtubeAuthMode === "cookie_file" && (
                <div className="space-y-2">
                  <TextInput
                    label="Cookie file path on the OnTheSpot host"
                    isLabelHidden
                    value={youtubeCookieFile}
                    onChange={setYoutubeCookieFile}
                    placeholder="/config/youtube-cookies.txt"
                    className="font-mono"
                  />
                  <p className="text-[11px] leading-relaxed text-fg-muted">
                    This must be an absolute path visible inside the OnTheSpot container, not a path on the computer running your browser.
                  </p>
                </div>
              )}

              {/* YouTube Status Indicator */}
              {youtubeStatus && (
                <div
                  className={`rounded-lg border px-3 py-2 text-xs ${
                    youtubeStatus.ready
                      ? "border-success/30 bg-success-subtle text-success-fg"
                      : "border-warning/30 bg-warning-subtle text-warning-fg"
                  }`}
                >
                  <p className="font-semibold">
                    {youtubeStatus.ready
                      ? `Session source configured · ${youtubeStatus.source}`
                      : youtubeStatus.configured
                      ? "Current session is unavailable"
                      : "No usable YouTube session configured"}
                  </p>
                  {youtubeStatus.error && (
                    <p className="mt-1 leading-relaxed text-fg-muted">
                      {youtubeStatus.error}
                    </p>
                  )}
                  {!youtubeStatus.ready && youtubeAuthMode !== "upload" && (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        setYoutubeAuthMode("upload");
                        setFormError("");
                      }}
                      className="mt-2"
                      label="Show cookies.txt instructions"
                    />
                  )}
                </div>
              )}
            </div>
          )}

          {/* Form Error Banner */}
          {formError && (
            <div className="rounded-lg border border-danger/30 bg-danger-subtle p-3 text-xs font-medium text-danger-fg flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{formError}</span>
            </div>
          )}

          {/* Feedback / Sign In Notification Banner */}
          {signInStarted && (
            <div className="rounded-lg border border-success/30 bg-success-subtle p-3 text-xs font-medium text-success-fg flex items-center gap-2">
              <Check className="w-4 h-4 shrink-0" />
              <span>{signInStarted}</span>
            </div>
          )}
        </form>
      </Dialog>
    </div>
  );
};
