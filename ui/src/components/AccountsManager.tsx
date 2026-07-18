import React, { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Users, Plus, Trash2, Loader2, Server, RefreshCw, CircleCheck, AlertTriangle, Music2, Waves, Cloud, Disc3, CirclePlay, Heart, Headphones, Film, Download, Globe2, Wifi } from 'lucide-react';
import { AccountItem } from '../types';
import { createSpotifyCompanionPairing, fetchYouTubeAuthenticationStatus, getTargetBackendUrl } from '../lib/api';
import type { AccountHealth, YouTubeAuthenticationStatus } from '../lib/api';

interface AccountsManagerProps {
  accounts: AccountItem[];
  onAddAccount: (service: string, credentials: { username?: string; token?: string }) => Promise<AccountItem | null>;
  onRemoveAccount: (uuid: string) => Promise<boolean>;
  onRefreshAccounts: () => Promise<AccountItem[]>;
  health: AccountHealth | null;
  onReconnect: () => Promise<boolean>;
  onConfigureYouTubeAuthentication: (authentication: { mode: "none" | "browser" | "cookie_file"; browser?: string; cookie_file?: string }) => Promise<boolean>;
  onUploadYouTubeCookies: (file: File) => Promise<YouTubeAuthenticationStatus | null>;
  youtubeAuthenticationMode: "none" | "browser" | "cookie_file";
  youtubeBrowser?: string;
  youtubeCookieFile?: string;
}

type ServicePresentation = {
  label: string;
  accountType: string;
  maxBitrate: string;
  Icon: React.ElementType;
  iconClass: string;
};

type CredentialMode = 'none' | 'device' | 'token' | 'email-password' | 'youtube';
type SpotifyAccessMode = 'local' | 'remote';
type YouTubeSetupMode = 'upload' | 'browser' | 'cookie_file';

const SERVICE_OPTIONS = [
  { value: 'applemusic', label: 'Apple Music', mode: 'token', tokenLabel: 'Media User Token', requirement: 'Paste a valid Apple Music media-user token.', tokenRequired: true },
  { value: 'bandcamp', label: 'Bandcamp', mode: 'none', requirement: 'Uses the public Bandcamp worker. No sign-in is required.' },
  { value: 'crunchyroll', label: 'Crunchyroll', mode: 'email-password', requirement: 'Use your Crunchyroll email address and password.' },
  { value: 'deezer', label: 'Deezer', mode: 'token', tokenLabel: 'ARL Cookie', requirement: 'Paste the ARL value from your Deezer session.', tokenRequired: true },
  { value: 'generic', label: 'Generic', mode: 'none', requirement: 'Uses the public generic worker. No sign-in is required.' },
  { value: 'qobuz', label: 'Qobuz', mode: 'email-password', requirement: 'Use your Qobuz email address and password.' },
  { value: 'soundcloud', label: 'SoundCloud', mode: 'token', tokenLabel: 'OAuth Token', requirement: 'Optional for public content; add a token for account access.', tokenRequired: false },
  { value: 'spotify', label: 'Spotify', mode: 'device', requirement: 'Requires Spotify Premium. Start sign-in, then open Spotify’s Connect to a device menu and select OnTheSpot.' },
  { value: 'tidal', label: 'Tidal', mode: 'device', requirement: 'Starts a Tidal device-link sign-in in your browser.' },
  { value: 'youtube', label: 'YouTube Music', mode: 'youtube', requirement: 'Configure an explicit local YouTube session for videos that require sign-in.' },
] as const satisfies ReadonlyArray<{ value: string; label: string; mode: CredentialMode; requirement: string; tokenLabel?: string; tokenRequired?: boolean }>;

const getServicePresentation = (service: string): ServicePresentation => {
  switch (service.toLowerCase()) {
    case 'spotify': return { label: 'Spotify', accountType: 'Premium', maxBitrate: '320k', Icon: Music2, iconClass: 'text-[#1ed760]' };
    case 'tidal': return { label: 'Tidal', accountType: 'Premium', maxBitrate: '1411k', Icon: Waves, iconClass: 'text-cyan-400' };
    case 'apple_music':
    case 'applemusic': return { label: 'Apple Music', accountType: 'Premium', maxBitrate: 'Lossless', Icon: Music2, iconClass: 'text-rose-400' };
    case 'soundcloud': return { label: 'SoundCloud', accountType: 'Public', maxBitrate: '128k', Icon: Cloud, iconClass: 'text-orange-400' };
    case 'bandcamp': return { label: 'Bandcamp', accountType: 'Public', maxBitrate: 'Source', Icon: Disc3, iconClass: 'text-sky-400' };
    case 'youtube_music':
    case 'youtube': return { label: 'YouTube Music', accountType: 'Public', maxBitrate: '256k', Icon: CirclePlay, iconClass: 'text-red-400' };
    case 'deezer': return { label: 'Deezer', accountType: 'Premium', maxBitrate: '1411k', Icon: Heart, iconClass: 'text-violet-400' };
    case 'qobuz': return { label: 'Qobuz', accountType: 'Premium', maxBitrate: '1411k', Icon: Headphones, iconClass: 'text-sky-300' };
    case 'crunchyroll': return { label: 'Crunchyroll', accountType: 'Premium', maxBitrate: 'Video', Icon: Film, iconClass: 'text-amber-400' };
    default: return { label: 'Generic', accountType: 'Free', maxBitrate: 'Source', Icon: Download, iconClass: 'text-[#b3b3b3]' };
  }
};

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
  const [service, setService] = useState('generic');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [formError, setFormError] = useState('');
  const [signInStarted, setSignInStarted] = useState('');
  const [youtubeAuthMode, setYoutubeAuthMode] = useState<YouTubeSetupMode>('upload');
  const [youtubeBrowser, setYoutubeBrowser] = useState('edge');
  const [youtubeCookieFile, setYoutubeCookieFile] = useState('');
  const [youtubeCookieUpload, setYoutubeCookieUpload] = useState<File | null>(null);
  const [youtubeStatus, setYoutubeStatus] = useState<YouTubeAuthenticationStatus | null>(null);
  const [youtubeUploadComplete, setYoutubeUploadComplete] = useState(false);
  const [spotifyAccessMode, setSpotifyAccessMode] = useState<SpotifyAccessMode>('local');
  const [companionPairing, setCompanionPairing] = useState<{ pairing_token: string; expires_at: number; expires_in: number; device_name: string } | null>(null);
  const [companionWaiting, setCompanionWaiting] = useState(false);
  const initialSpotifyCount = useRef(0);
  const sortedAccounts = [...accounts].sort((left, right) =>
    getServicePresentation(left.service).label.localeCompare(getServicePresentation(right.service).label),
  );
  const selectedService = SERVICE_OPTIONS.find((option) => option.value === service) ?? SERVICE_OPTIONS[0];

  const openYouTubeSetup = () => {
    setService('youtube');
    // Upload is the portable choice for Docker/Unraid and is also the most
    // useful starting point when replacing an unavailable browser profile.
    setYoutubeAuthMode('upload');
    setYoutubeBrowser(configuredYoutubeBrowser || 'edge');
    setYoutubeCookieFile(configuredYoutubeCookieFile || '');
    setYoutubeCookieUpload(null);
    setYoutubeUploadComplete(false);
    setFormError('');
    setSignInStarted('');
    setShowModal(true);
    void fetchYouTubeAuthenticationStatus().then(setYoutubeStatus);
  };

  useEffect(() => {
    let cancelled = false;
    void fetchYouTubeAuthenticationStatus().then((status) => {
      if (!cancelled) setYoutubeStatus(status);
    });
    return () => { cancelled = true; };
  }, [youtubeAuthenticationMode, configuredYoutubeBrowser, configuredYoutubeCookieFile]);

  const createCompanionPairing = async () => {
    initialSpotifyCount.current = accounts.filter((account) => account.service.toLowerCase() === 'spotify').length;
    setLoading(true);
    const pairing = await createSpotifyCompanionPairing();
    setLoading(false);
    if (!pairing) {
      setFormError('Could not create a companion pairing code.');
      return;
    }
    setCompanionPairing(pairing);
    setCompanionWaiting(true);
    setSignInStarted('Pairing code created. Run the command below on the computer where Spotify is open.');
  };

  useEffect(() => {
    if (!companionWaiting) return undefined;

    let cancelled = false;
    const checkForCompletedPairing = async () => {
      const freshAccounts = await onRefreshAccounts();
      if (cancelled) return;
      const spotifyCount = freshAccounts.filter((account) => account.service.toLowerCase() === 'spotify').length;
      if (spotifyCount > initialSpotifyCount.current) {
        setCompanionWaiting(false);
        setCompanionPairing(null);
        setSignInStarted('Spotify connected.');
        setShowModal(false);
        setFormError('');
      }
    };

    void checkForCompletedPairing();
    const interval = window.setInterval(() => void checkForCompletedPairing(), 2000);
    const timeout = window.setTimeout(() => {
      if (!cancelled) setCompanionWaiting(false);
    }, 10 * 60 * 1000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      window.clearTimeout(timeout);
    };
  }, [companionWaiting, onRefreshAccounts]);

  const companionCommand = companionPairing ? `.\\.companion-venv\\Scripts\\python.exe companion\\run.py --server-url "${getTargetBackendUrl()}" --pairing-token "${companionPairing.pairing_token}" --cleanup` : '';
  const companionCloneCommand = "cd $HOME\ngit clone --branch fastapi-dev --single-branch https://github.com/JamyPatch44/onthespot.git OnTheSpot-companion\ncd .\\OnTheSpot-companion";
  const companionSetupCommand = "py -m venv .companion-venv\n.\\.companion-venv\\Scripts\\python.exe -m pip install -r companion\\requirements.txt";
  const youtubeExportInstallCommand = '$otsYtDlp = Join-Path $env:TEMP "OnTheSpot-youtube-auth"\npy -m venv $otsYtDlp\n& (Join-Path $otsYtDlp "Scripts\\python.exe") -m pip install --disable-pip-version-check --quiet --upgrade yt-dlp';
  const youtubeExportCommand = `$otsYtDlp = Join-Path $env:TEMP "OnTheSpot-youtube-auth"\n& (Join-Path $otsYtDlp "Scripts\\python.exe") -m yt_dlp --cookies-from-browser ${youtubeBrowser} --cookies "$HOME\\Downloads\\youtube-cookies.txt"`;
  const youtubeCleanupCommand = 'Remove-Item -LiteralPath "$HOME\\Downloads\\youtube-cookies.txt" -Force -ErrorAction SilentlyContinue\nRemove-Item -LiteralPath (Join-Path $env:TEMP "OnTheSpot-youtube-auth") -Recurse -Force -ErrorAction SilentlyContinue';
  const copyText = async (value: string, success: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setSignInStarted(success);
    } catch {
      setSignInStarted('Copy was blocked by the browser. Select the command and copy it manually.');
    }
  };

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setSignInStarted('');
    if (selectedService.value === 'spotify' && spotifyAccessMode === 'remote') {
      await createCompanionPairing();
      return;
    }
    if (selectedService.mode === 'email-password' && (!username.trim() || !token.trim())) {
      setFormError('Enter both your email address and password to continue.');
      return;
    }
    if (selectedService.mode === 'token' && selectedService.tokenRequired && !token.trim()) {
      setFormError(`Enter your ${selectedService.tokenLabel?.toLowerCase() || 'access token'} to continue.`);
      return;
    }
    if (selectedService.mode === 'youtube') {
      if (youtubeAuthMode === 'upload' && !youtubeCookieUpload) {
        setFormError('Choose a Netscape-format cookies.txt file exported from YouTube.');
        return;
      }
      if (youtubeAuthMode === 'cookie_file' && !youtubeCookieFile.trim()) {
        setFormError('Enter an absolute path to a Netscape-format cookies file on the OnTheSpot server.');
        return;
      }
      setLoading(true);
      try {
        if (youtubeAuthMode === 'upload' && youtubeCookieUpload) {
          const status = await onUploadYouTubeCookies(youtubeCookieUpload);
          if (!status?.ready) throw new Error(status?.error || 'The uploaded YouTube session is not usable.');
          setYoutubeStatus(status);
          setYoutubeCookieUpload(null);
          setYoutubeUploadComplete(true);
          setSignInStarted('YouTube cookies installed on OnTheSpot. Run the cleanup command below to remove the temporary local files.');
        } else {
          const configuredMode = youtubeAuthMode === 'browser' ? 'browser' : 'cookie_file';
          const configured = await onConfigureYouTubeAuthentication({
            mode: configuredMode,
            browser: configuredMode === 'browser' ? youtubeBrowser : undefined,
            cookie_file: configuredMode === 'cookie_file' ? youtubeCookieFile : undefined,
          });
          if (!configured) throw new Error('The selected YouTube session source is not usable.');
          setYoutubeStatus(await fetchYouTubeAuthenticationStatus());
          setShowModal(false);
          setYoutubeCookieFile('');
        }
      } catch (error) {
        setFormError(error instanceof Error ? error.message : 'Could not configure YouTube authentication.');
      } finally {
        setLoading(false);
      }
      return;
    }
    setLoading(true);
    const res = await onAddAccount(service, { username, token });
    setLoading(false);
    if (res) {
      if (selectedService.mode === 'device') {
        setSignInStarted('Spotify Connect is waiting. In the Spotify app, open Connect to a device and select OnTheSpot, then refresh Accounts.');
        return;
      }
      setShowModal(false);
      setUsername('');
      setToken('');
    }
  };

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">
      
      {/* Top Banner */}
      <div className="ots-hero flex flex-col justify-between gap-4 p-6 sm:flex-row sm:items-center">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-white">
            <Users className="h-5 w-5 text-[#1ed760]" />
            Accounts
            <span className="ots-accent-badge ml-2 px-2 py-1 text-xs font-bold">
              {accounts.length} active workers
            </span>
          </h2>
          <p className="mt-1 text-sm text-[#8f8f8f]">
            Accounts are automatically rotated to distribute API load and bypass rate limits.
          </p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="ots-button ots-button-primary h-11 shrink-0 px-5 text-sm"
        >
          <Plus className="w-4 h-4" />
          <span>Add Account</span>
        </button>
      </div>

      <div className={`ots-health-banner flex flex-col justify-between gap-4 border p-4 sm:flex-row sm:items-center ${health?.healthy ? 'ots-health-banner--connected' : 'ots-health-banner--warning'}`}>
        <div className="flex items-start gap-3">
          {health?.healthy ? <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#1ed760]" /> : <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[#f6b94a]" />}
          <div><p className="text-sm font-bold text-white">Worker pool: {health ? (health.healthy ? 'Ready' : 'Needs attention') : 'Checking…'}</p><p className="mt-1 text-xs text-[#b3b3b3]">{health ? `${health.authenticated_accounts} active workers · ${health.missing_services.length ? `Missing: ${health.missing_services.join(', ')}` : 'All configured services available'}` : 'Checking account pool health…'}</p></div>
        </div>
        <button type="button" onClick={async () => { setReconnecting(true); await onReconnect(); setReconnecting(false); }} disabled={reconnecting} className="ots-button ots-button-secondary h-10"><RefreshCw className={`h-4 w-4 ${reconnecting ? 'animate-spin' : ''}`} /> Reconnect workers</button>
      </div>

      <div className="ots-panel overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-[#3a3a3a] bg-[#282828] text-[11px] font-bold uppercase tracking-[0.08em] text-[#a7a7a7]">
              <tr>
                <th className="px-5 py-3">Account</th>
                <th className="px-5 py-3">Service</th>
                <th className="px-5 py-3">Account type</th>
                <th className="px-5 py-3">Max bitrate</th>
                <th className="px-5 py-3">Status</th>
                <th className="px-5 py-3 text-right"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#303030]">
              {sortedAccounts.map((acc) => {
                const presentation = getServicePresentation(acc.service);
                const { Icon } = presentation;
                const connected = acc.active;
                const isPublicWorker = ['generic', 'bandcamp', 'youtube', 'youtube_music'].includes(acc.service.toLowerCase()) || acc.uuid.startsWith('public_');
                const isYoutubeWorker = acc.service.toLowerCase() === 'youtube_music';
                const youtubeSessionConfigured = Boolean(youtubeStatus?.configured);
                const youtubeSessionReady = Boolean(youtubeStatus?.ready);
                const statusLabel = isYoutubeWorker
                  ? (youtubeSessionReady
                    ? youtubeStatus?.mode === 'browser' ? 'Browser configured' : 'Cookies loaded'
                    : youtubeSessionConfigured ? 'Session unavailable' : youtubeStatus ? 'Needs cookies' : 'Session unverified')
                  : isPublicWorker
                  ? (connected ? 'Ready (no sign-in)' : 'Disabled')
                  : (connected ? 'Authenticated' : 'Needs sign-in');
                const statusReady = isYoutubeWorker ? youtubeSessionReady : connected;
                const accountLabel = isPublicWorker
                  ? (acc.service.toLowerCase() === 'generic' ? 'General media worker' : isYoutubeWorker ? 'YouTube catalogue worker' : `${presentation.label} public worker`)
                  : `${presentation.label} account`;
                const accountDetail = isPublicWorker
                  ? (acc.service.toLowerCase() === 'generic' ? 'yt-dlp fallback for other supported sites' : isYoutubeWorker ? 'Searches and downloads YouTube links' : 'Built-in public access')
                  : (acc.username || 'Signed-in account');
                return (
                  <tr key={acc.uuid} className="transition-colors hover:bg-white/[0.025]">
                    <td className="px-5 py-4">
                      <div className="min-w-0">
                        <p className="max-w-48 truncate font-semibold text-white">{accountLabel}</p>
                        <p className="mt-0.5 max-w-48 truncate text-xs text-[#8f8f8f]" title={isPublicWorker ? acc.uuid : accountDetail}>{accountDetail}</p>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-2.5 font-semibold text-[#e7e7e7]">
                        <Icon className={`h-4 w-4 shrink-0 ${presentation.iconClass}`} />
                        {presentation.label}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-[#b3b3b3]">{presentation.accountType}</td>
                    <td className="px-5 py-4 font-medium text-[#e7e7e7]">{presentation.maxBitrate}</td>
                    <td className="px-5 py-4">
                      <span title={isYoutubeWorker ? youtubeStatus?.error || youtubeStatus?.source : undefined} className={`inline-flex items-center gap-2 text-xs font-semibold ${statusReady ? 'text-[#1ed760]' : 'text-[#f6b94a]'}`}>
                        <span className={`h-2 w-2 rounded-full ${statusReady ? 'bg-[#1ed760]' : 'bg-[#f6b94a]'}`} />
                        {statusLabel}
                      </span>
                      {isYoutubeWorker && youtubeStatus?.error && <p className="mt-1 max-w-64 text-[11px] leading-snug text-[#a7a7a7]">{youtubeStatus.error}</p>}
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex min-w-52 items-center justify-end gap-2 whitespace-nowrap">
                      {isYoutubeWorker && (
                        <button onClick={openYouTubeSetup} className="ots-button ots-button-secondary h-9 px-3 text-xs">
                          {youtubeSessionConfigured ? 'Reconfigure' : 'Set up'}
                        </button>
                      )}
                      <button onClick={() => onRemoveAccount(acc.uuid)} className="ots-button ots-button-danger h-9 px-3 text-xs">
                        <Trash2 className="h-4 w-4" /> Remove
                      </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {accounts.length === 0 && (
                <tr><td colSpan={6} className="px-5 py-12 text-center text-sm text-[#8f8f8f]">No connected worker accounts yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Standard Material Dialog */}
      {showModal && createPortal(
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 backdrop-blur-sm sm:items-center">
          <div className={`ots-panel relative flex w-full flex-col overflow-hidden bg-[#1c1c1c] p-0 shadow-2xl ${service === 'spotify' && spotifyAccessMode === 'remote' ? 'max-h-[calc(100dvh_-_2rem)] max-w-3xl' : service === 'youtube' ? 'max-h-[calc(100dvh_-_2rem)] max-w-xl' : 'max-h-[calc(100dvh_-_2rem)] max-w-md'}`}>
            <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[#353535] px-6 py-5 sm:px-8">
              <div className="flex min-w-0 items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#173b25]">
                  <Server className="h-5 w-5 text-[#1ed760]" />
                </div>
                <div className="min-w-0">
                  <h3 className="text-xl font-medium text-white">Add Worker Account</h3>
                  <p className="mt-2 text-sm text-[#8f8f8f]">Authenticate Spotify Librespot, Tidal OAuth, Apple Music, SoundCloud, or other supported services.</p>
                </div>
              </div>
              <button type="button" onClick={() => { setCompanionWaiting(false); setCompanionPairing(null); setShowModal(false); }} className="ots-icon-button shrink-0" aria-label="Close add account dialog" title="Close">
                <span aria-hidden="true" className="text-xl leading-none">×</span>
              </button>
            </div>

            <form onSubmit={handleAddSubmit} className="flex min-h-0 flex-1 flex-col">
              <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-6 py-5 sm:px-8">
                <div className="flex flex-col gap-4">
              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">Platform Service</label>
                <select
                  value={service}
                  onChange={(e) => { setService(e.target.value); setFormError(''); setSignInStarted(''); setUsername(''); setToken(''); setYoutubeCookieFile(''); setCompanionPairing(null); setCompanionWaiting(false); setSpotifyAccessMode('local'); }}
                  className="ots-select w-full"
                >
                  {SERVICE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>{option.label}</option>
                  ))}
                </select>
                <p className="mt-2 text-xs leading-relaxed text-[#8f8f8f]">{selectedService.requirement}</p>
              </div>

              {selectedService.mode === 'email-password' && <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">Email address</label>
                <input
                  type="email"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. user@example.com"
                  className="ots-input w-full"
                />
              </div>}

              {(selectedService.mode === 'token' || selectedService.mode === 'email-password') && <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">
                  {selectedService.mode === 'email-password' ? 'Password' : `${selectedService.tokenLabel}${selectedService.tokenRequired ? '' : ' (optional)'}`}
                </label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder={selectedService.mode === 'email-password' ? 'Enter your password' : `Paste ${selectedService.tokenLabel?.toLowerCase() || 'secure token'}`}
                  className="ots-input w-full"
                />
              </div>}

              {selectedService.mode === 'none' && (
                <div className="rounded-lg border border-[#3a3a3a] bg-[#242424] px-4 py-3 text-sm text-[#b3b3b3]">This worker is ready to add without credentials.</div>
              )}
              {selectedService.value === 'spotify' && (
                <div className="space-y-3 border border-[#3a3a3a] bg-[#242424] p-4">
                  <div>
                    <p className="text-sm font-semibold text-white">Where is Spotify running?</p>
                    <p className="mt-1 text-xs leading-relaxed text-[#b3b3b3]">Choose local if OnTheSpot and Spotify share a network. Choose remote if the server is elsewhere and you can reach it through a private network, VPN, or secure HTTPS address.</p>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <button type="button" aria-pressed={spotifyAccessMode === 'local'} onClick={() => { setSpotifyAccessMode('local'); setCompanionPairing(null); setCompanionWaiting(false); setSignInStarted(''); }} className={spotifyAccessMode === 'local' ? 'border border-[#1ed760] bg-[#173b25] p-3 text-left' : 'border border-[#3a3a3a] p-3 text-left hover:border-[#666]'}>
                      <span className="flex items-center gap-2 font-semibold text-white"><Wifi className="h-4 w-4 text-[#1ed760]" /> Local network</span>
                      <span className="mt-1 block text-xs text-[#b3b3b3]">Use Spotify Connect directly.</span>
                    </button>
                    <button type="button" aria-pressed={spotifyAccessMode === 'remote'} onClick={() => { setSpotifyAccessMode('remote'); setSignInStarted(''); }} className={spotifyAccessMode === 'remote' ? 'border border-[#f6b94a] bg-[#3b321d] p-3 text-left' : 'border border-[#3a3a3a] p-3 text-left hover:border-[#666]'}>
                      <span className="flex items-center gap-2 font-semibold text-white"><Globe2 className="h-4 w-4 text-[#f6b94a]" /> Remote access</span>
                      <span className="mt-1 block text-xs text-[#b3b3b3]">Use the local companion over a private network or secure HTTPS connection.</span>
                    </button>
                  </div>
                  {spotifyAccessMode === 'remote' && <div className="border-l-4 border-[#f6b94a] bg-[#3b321d] p-3 text-xs leading-relaxed text-[#f6b94a]">
                    <p className="font-semibold text-white">Run this on the computer where Spotify is open—not Unraid.</p>
                    <p className="mt-1">Spotify and the companion computer must be on the same LAN for Spotify Connect discovery. The companion then sends the completed login to this OnTheSpot server over the address you opened here. Tailscale is one option; a VPN or secure HTTPS reverse proxy can work too.</p>
                    <ol className="mt-2 list-decimal space-y-1 pl-4 text-[#b3b3b3]"><li>Download or clone this repository on the Spotify computer.</li><li>Open PowerShell in the repository folder.</li><li>Run the setup commands below once.</li><li>Create a pairing code, run the generated command, then select OnTheSpot Companion in Spotify.</li></ol>
                    <p className="mt-3 text-[11px] text-[#b3b3b3]">This is a one-time helper. The generated command includes automatic cleanup: after successful pairing it exits and removes the <span className="font-semibold text-white">OnTheSpot-companion</span> folder, including its virtual environment. The account stays saved on this server.</p>
                    <p className="mt-3 font-semibold text-white">If you need to download it:</p>
                    <code className="mt-1 block overflow-x-auto whitespace-pre-wrap bg-black/30 p-2 text-[11px] text-white">{companionCloneCommand}</code>
                    <button type="button" onClick={() => void copyText(`${companionCloneCommand}\n`, 'Download commands copied. Paste them into PowerShell as one block.')} className="ots-button ots-button-secondary mt-2 h-8 px-3 text-xs">Copy download commands</button>
                    <p className="mt-3 font-semibold text-white">One-time Windows setup:</p>
                    <code className="mt-1 block overflow-x-auto whitespace-pre-wrap bg-black/30 p-2 text-[11px] text-white">{companionSetupCommand}</code>
                    <button type="button" onClick={() => void copyText(`${companionSetupCommand}\n`, 'Setup commands copied. Paste them into PowerShell as one block.')} className="ots-button ots-button-secondary mt-2 h-8 px-3 text-xs">Copy setup commands</button>
                    <p className="mt-2 text-[11px]">Run these setup commands first. Do not paste them together with the pairing command.</p>
                    <p className="mt-2 text-[11px] font-semibold text-[#f6b94a]">Important: create the pairing code on this same OnTheSpot address. Do not switch between localhost, a LAN address, or a remote URL; the address must be reachable from the Spotify computer and should use HTTPS or a private VPN. Each code expires after ten minutes.</p>
                    {companionPairing && <><p className="mt-3 font-semibold text-white">Final step: copy this into PowerShell</p><p className="mt-1 text-[11px]">The browser cannot run PowerShell automatically. Click the button, switch to the PowerShell window from step 2, and paste the command there.</p><code className="mt-2 block overflow-x-auto whitespace-pre-wrap break-all border border-[#f6b94a]/50 bg-black/30 p-2 text-[11px] text-white">{companionCommand}</code><div className="mt-2 flex flex-wrap items-center gap-2"><button type="button" onClick={() => void copyText(`${companionCommand}\n`, 'PowerShell command copied. Paste it into the companion PowerShell window.')} className="ots-button ots-button-secondary h-8 px-3 text-xs">Copy command for PowerShell</button><span>Expires in {Math.max(0, Math.ceil((companionPairing.expires_at * 1000 - Date.now()) / 60000))} minutes.</span></div>{companionWaiting && <p className="mt-2 text-[11px] font-semibold text-[var(--spotify-green)]">Waiting for the companion to finish. This window will close automatically when the Spotify account appears.</p>}</>}
                  </div>}
                </div>
              )}
              {selectedService.mode === 'device' && selectedService.value !== 'spotify' && (
                <div className="rounded-lg border border-[#3a3a3a] bg-[#242424] px-4 py-3 text-sm text-[#b3b3b3]">Click Start sign-in, then follow the service prompt. You do not need to enter credentials here.</div>
              )}
              {selectedService.mode === 'youtube' && (
                <div className="space-y-3 rounded-lg border border-[#3a3a3a] bg-[#242424] p-4">
                  <p className="text-sm font-medium text-white">YouTube session source</p>
                  <p className="text-xs leading-relaxed text-[#b3b3b3]">YouTube does not support yt-dlp OAuth sign-in. For Docker or Unraid, upload a Netscape-format cookies.txt file so the server can use your session.</p>
                  <select value={youtubeAuthMode} onChange={(event) => { setYoutubeAuthMode(event.target.value as YouTubeSetupMode); setYoutubeUploadComplete(false); setFormError(''); }} className="ots-select w-full">
                    <option value="upload">Upload cookies.txt (recommended)</option>
                    <option value="browser">Read a browser on the OnTheSpot host</option>
                    <option value="cookie_file">Use a file path on the OnTheSpot host</option>
                  </select>
                  {youtubeAuthMode === 'upload' ? (
                    <div className="space-y-3">
                      <div className="border-l-4 border-[#f6b94a] bg-[#3b321d] p-3 text-xs leading-relaxed text-[#f6b94a]">
                        <p className="font-semibold text-white">Create cookies.txt on the computer where you use YouTube</p>
                        <ol className="mt-2 list-decimal space-y-1 pl-4 text-[#d2d2d2]">
                          <li>Sign in to YouTube in your normal browser.</li>
                          <li>Open PowerShell on that computer.</li>
                          <li>Run the temporary setup command once, then run the export command.</li>
                          <li>Return here and select <span className="font-semibold text-white">Downloads\youtube-cookies.txt</span>.</li>
                          <li>After the upload succeeds, run the cleanup command shown below.</li>
                        </ol>
                        <label className="mt-3 block font-semibold text-white" htmlFor="youtube-export-browser">Browser containing your YouTube session</label>
                        <select id="youtube-export-browser" value={youtubeBrowser} onChange={(event) => setYoutubeBrowser(event.target.value)} className="ots-select mt-1 w-full">
                          <option value="edge">Microsoft Edge</option>
                          <option value="chrome">Google Chrome</option>
                          <option value="brave">Brave</option>
                          <option value="firefox">Firefox</option>
                          <option value="vivaldi">Vivaldi</option>
                          <option value="opera">Opera</option>
                        </select>
                        <p className="mt-3 font-semibold text-white">1. Create a temporary yt-dlp environment</p>
                        <code className="mt-1 block overflow-x-auto whitespace-pre-wrap bg-black/30 p-2 text-[11px] text-white">{youtubeExportInstallCommand}</code>
                        <button type="button" onClick={() => void copyText(youtubeExportInstallCommand, 'Temporary yt-dlp setup command copied.')} className="ots-button ots-button-secondary mt-2 h-8 px-3 text-xs">Copy setup command</button>
                        <p className="mt-3 font-semibold text-white">2. Export the browser cookies</p>
                        <code className="mt-1 block overflow-x-auto whitespace-pre-wrap break-all bg-black/30 p-2 text-[11px] text-white">{youtubeExportCommand}</code>
                        <button type="button" onClick={() => void copyText(youtubeExportCommand, 'YouTube cookie export command copied.')} className="ots-button ots-button-secondary mt-2 h-8 px-3 text-xs">Copy export command</button>
                        <p className="mt-3 text-[11px] font-semibold">Keep the exported file private. Browser exports can contain cookies for other sites; OnTheSpot removes every row except YouTube and Google when the file is uploaded.</p>
                      </div>
                      <input
                        type="file"
                        accept=".txt,text/plain"
                        onChange={(event) => { setYoutubeCookieUpload(event.target.files?.[0] || null); setYoutubeUploadComplete(false); }}
                        className="ots-input w-full cursor-pointer file:mr-3 file:border-0 file:bg-transparent file:text-sm file:font-semibold file:text-white"
                      />
                      <p className="text-[11px] leading-relaxed text-[#a7a7a7]">The filtered file is stored privately in OnTheSpot app data and is never returned to the browser or written to logs. <a href="https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp" target="_blank" rel="noreferrer" className="font-semibold text-white underline underline-offset-2">Official yt-dlp cookie help</a></p>
                      {youtubeUploadComplete && (
                        <div className="border-l-4 border-[var(--spotify-green)] bg-[color-mix(in_srgb,var(--spotify-green)_10%,var(--spotify-surface))] p-3 text-xs leading-relaxed text-[var(--spotify-text)]">
                          <p className="font-semibold text-white">3. Clean up the local helper files</p>
                          <p className="mt-1 text-[#b3b3b3]">OnTheSpot now has its private filtered copy. Run this once in PowerShell to delete the exported cookie file and the temporary yt-dlp environment from your computer.</p>
                          <code className="mt-2 block overflow-x-auto whitespace-pre-wrap break-all bg-black/30 p-2 text-[11px] text-white">{youtubeCleanupCommand}</code>
                          <button type="button" onClick={() => void copyText(youtubeCleanupCommand, 'Cleanup command copied. Run it in PowerShell to remove the local helper files.')} className="ots-button ots-button-secondary mt-2 h-8 px-3 text-xs">Copy cleanup command</button>
                        </div>
                      )}
                    </div>
                  ) : youtubeAuthMode === 'browser' ? (
                    <div className="space-y-2">
                      <select value={youtubeBrowser} onChange={(event) => setYoutubeBrowser(event.target.value)} className="ots-select w-full">
                        <option value="edge">Microsoft Edge</option>
                        <option value="chrome">Google Chrome</option>
                        <option value="brave">Brave</option>
                        <option value="firefox">Firefox</option>
                        <option value="vivaldi">Vivaldi</option>
                        <option value="opera">Opera</option>
                      </select>
                      <p className="text-[11px] leading-relaxed text-[#f6b94a]">Only use this when that browser is installed on the same machine as the OnTheSpot process. It cannot read a browser on your desktop from inside Docker.</p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <input type="text" value={youtubeCookieFile} onChange={(event) => setYoutubeCookieFile(event.target.value)} placeholder="/config/youtube-cookies.txt" className="ots-input w-full" />
                      <p className="text-[11px] leading-relaxed text-[#a7a7a7]">This must be an absolute path visible inside the OnTheSpot container, not a path on the computer running your browser.</p>
                    </div>
                  )}
                  {youtubeStatus && (
                    <div className={`border px-3 py-2 text-xs ${youtubeStatus.ready ? 'border-[#1ed760]/35 bg-[#1ed760]/10 text-[#77ef9f]' : 'border-[#f6b94a]/35 bg-[#f6b94a]/10 text-[#f6b94a]'}`}>
                      <p className="font-semibold">{youtubeStatus.ready ? `Session source configured · ${youtubeStatus.source}` : youtubeStatus.configured ? 'Current session is unavailable' : 'No usable YouTube session configured'}</p>
                      {youtubeStatus.error && <p className="mt-1 leading-relaxed">{youtubeStatus.error}</p>}
                      {!youtubeStatus.ready && youtubeAuthMode !== 'upload' && <button type="button" onClick={() => { setYoutubeAuthMode('upload'); setFormError(''); }} className="ots-button ots-button-secondary mt-2 h-8 px-3 text-xs">Show cookies.txt instructions</button>}
                    </div>
                  )}
                </div>
              )}
              {formError && <p className="text-sm font-medium text-red-400">{formError}</p>}
              {signInStarted && <p
                className="rounded-lg border px-4 py-3 text-sm"
                style={{
                  borderColor: 'color-mix(in srgb, var(--spotify-green) 38%, transparent)',
                  backgroundColor: 'color-mix(in srgb, var(--spotify-green) 12%, var(--spotify-surface))',
                  color: 'var(--spotify-green-bright)',
                }}
              >{signInStarted}</p>}
                </div>
              </div>

              <div className="flex shrink-0 items-center justify-end gap-2 border-t border-[#353535] bg-[#1c1c1c] px-6 py-4 sm:px-8">
                <button
                  type="button"
                  onClick={() => { setCompanionWaiting(false); setCompanionPairing(null); setShowModal(false); }}
                  className="ots-button ots-button-ghost"
                >
                  Cancel
                </button>
                {selectedService.mode === 'youtube' && youtubeUploadComplete ? (
                  <button type="button" onClick={() => { setYoutubeUploadComplete(false); setShowModal(false); }} className="ots-button ots-button-primary">Done</button>
                ) : (
                  <button
                    type="submit"
                    disabled={loading || companionWaiting}
                    className="ots-button ots-button-primary"
                  >
                    {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                    {loading ? 'Working…' : companionWaiting ? 'Waiting for Spotify…' : selectedService.value === 'spotify' && spotifyAccessMode === 'remote' ? 'Create pairing code' : selectedService.mode === 'device' ? 'Start sign-in' : selectedService.mode === 'youtube' ? 'Save YouTube setup' : 'Add Account'}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>,
        document.querySelector<HTMLElement>('#root > [class*="theme-"]') ?? document.body,
      )}
    </div>
  );
};
