import React, { useState } from 'react';
import { Users, Plus, Trash2, Loader2, Server, RefreshCw, CircleCheck, AlertTriangle, Music2, Waves, Cloud, Disc3, CirclePlay, Heart, Headphones, Film, Download } from 'lucide-react';
import { AccountItem } from '../types';
import type { AccountHealth } from '../lib/api';

interface AccountsManagerProps {
  accounts: AccountItem[];
  onAddAccount: (service: string, credentials: { username?: string; token?: string }) => Promise<AccountItem | null>;
  onRemoveAccount: (uuid: string) => Promise<boolean>;
  health: AccountHealth | null;
  onReconnect: () => Promise<boolean>;
  onConfigureYouTubeAuthentication: (authentication: { mode: "none" | "browser" | "cookie_file"; browser?: string; cookie_file?: string }) => Promise<boolean>;
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
  health,
  onReconnect,
  onConfigureYouTubeAuthentication,
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
  const [youtubeAuthMode, setYoutubeAuthMode] = useState<'browser' | 'cookie_file'>('browser');
  const [youtubeBrowser, setYoutubeBrowser] = useState('edge');
  const [youtubeCookieFile, setYoutubeCookieFile] = useState('');
  const sortedAccounts = [...accounts].sort((left, right) =>
    getServicePresentation(left.service).label.localeCompare(getServicePresentation(right.service).label),
  );
  const selectedService = SERVICE_OPTIONS.find((option) => option.value === service) ?? SERVICE_OPTIONS[0];

  const openYouTubeSetup = () => {
    setService('youtube');
    setYoutubeAuthMode(youtubeAuthenticationMode === 'cookie_file' ? 'cookie_file' : 'browser');
    setYoutubeBrowser(configuredYoutubeBrowser || 'edge');
    setYoutubeCookieFile(configuredYoutubeCookieFile || '');
    setFormError('');
    setSignInStarted('');
    setShowModal(true);
  };

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    setSignInStarted('');
    if (selectedService.mode === 'email-password' && (!username.trim() || !token.trim())) {
      setFormError('Enter both your email address and password to continue.');
      return;
    }
    if (selectedService.mode === 'token' && selectedService.tokenRequired && !token.trim()) {
      setFormError(`Enter your ${selectedService.tokenLabel?.toLowerCase() || 'access token'} to continue.`);
      return;
    }
    if (selectedService.mode === 'youtube') {
      if (youtubeAuthMode === 'cookie_file' && !youtubeCookieFile.trim()) {
        setFormError('Enter an absolute path to your Netscape-format cookies file.');
        return;
      }
      setLoading(true);
      const configured = await onConfigureYouTubeAuthentication({
        mode: youtubeAuthMode,
        browser: youtubeAuthMode === 'browser' ? youtubeBrowser : undefined,
        cookie_file: youtubeAuthMode === 'cookie_file' ? youtubeCookieFile : undefined,
      });
      setLoading(false);
      if (configured) {
        setShowModal(false);
        setYoutubeCookieFile('');
      } else {
        setFormError('Could not save the YouTube authentication setup. Check the browser profile or cookies-file path.');
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

      <div className={`ots-health-banner flex flex-col justify-between gap-4 border p-4 sm:flex-row sm:items-center ${health?.spotify.connected ? 'ots-health-banner--connected' : 'ots-health-banner--warning'}`}>
        <div className="flex items-start gap-3">
          {health?.spotify.connected ? <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#1ed760]" /> : <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-[#f6b94a]" />}
          <div><p className="text-sm font-bold text-white">Spotify API: {health?.spotify.status || 'Checking…'}</p><p className="mt-1 text-xs text-[#b3b3b3]">{health ? `${health.authenticated_accounts} authenticated workers · ${health.missing_services.length ? `Missing: ${health.missing_services.join(', ')}` : 'All configured services available'}` : 'Checking account pool health…'}</p></div>
        </div>
        <button type="button" onClick={async () => { setReconnecting(true); await onReconnect(); setReconnecting(false); }} disabled={reconnecting} className="ots-button ots-button-secondary h-10"><RefreshCw className={`h-4 w-4 ${reconnecting ? 'animate-spin' : ''}`} /> Reconnect accounts</button>
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
                const youtubeSessionConfigured = youtubeAuthenticationMode !== 'none';
                const statusLabel = isYoutubeWorker
                  ? (youtubeSessionConfigured ? 'Session configured' : 'Needs session')
                  : isPublicWorker
                  ? (connected ? 'Ready (no sign-in)' : 'Disabled')
                  : (connected ? 'Authenticated' : 'Needs sign-in');
                const statusReady = isYoutubeWorker ? youtubeSessionConfigured : connected;
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
                      <span className={`inline-flex items-center gap-2 text-xs font-semibold ${statusReady ? 'text-[#1ed760]' : 'text-[#f6b94a]'}`}>
                        <span className={`h-2 w-2 rounded-full ${statusReady ? 'bg-[#1ed760]' : 'bg-[#f6b94a]'}`} />
                        {statusLabel}
                      </span>
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
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
          <div className="ots-panel relative w-full max-w-md overflow-hidden bg-[#1c1c1c] p-6 shadow-2xl sm:p-8">
            <div className="flex items-center gap-3 mb-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#173b25]">
                <Server className="h-5 w-5 text-[#1ed760]" />
              </div>
              <h3 className="text-xl font-medium text-gray-900 dark:text-neutral-100">
                Add Worker Account
              </h3>
            </div>
            
            <p className="text-sm text-gray-500 dark:text-neutral-400 mb-6">
              Authenticate Spotify Librespot, Tidal OAuth, Apple Music, SoundCloud, or other supported services.
            </p>

            <form onSubmit={handleAddSubmit} className="flex flex-col gap-4">
              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">Platform Service</label>
                <select
                  value={service}
                  onChange={(e) => { setService(e.target.value); setFormError(''); setSignInStarted(''); setUsername(''); setToken(''); setYoutubeCookieFile(''); }}
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
              {selectedService.mode === 'device' && (
                <div className="rounded-lg border border-[#3a3a3a] bg-[#242424] px-4 py-3 text-sm text-[#b3b3b3]">Click Start sign-in, then follow the service prompt. You do not need to enter credentials here.</div>
              )}
              {selectedService.mode === 'youtube' && (
                <div className="space-y-3 rounded-lg border border-[#3a3a3a] bg-[#242424] p-4">
                  <p className="text-sm font-medium text-white">YouTube session source</p>
                  <p className="text-xs leading-relaxed text-[#b3b3b3]">Authentication stays on this computer. OnTheSpot stores only your chosen browser name or local file path, never the cookies themselves.</p>
                  <select value={youtubeAuthMode} onChange={(event) => setYoutubeAuthMode(event.target.value as 'browser' | 'cookie_file')} className="ots-select w-full">
                    <option value="browser">Use a local browser session</option>
                    <option value="cookie_file">Use a local cookies file</option>
                  </select>
                  {youtubeAuthMode === 'browser' ? (
                    <select value={youtubeBrowser} onChange={(event) => setYoutubeBrowser(event.target.value)} className="ots-select w-full">
                      <option value="edge">Microsoft Edge</option>
                      <option value="chrome">Google Chrome</option>
                      <option value="brave">Brave</option>
                      <option value="firefox">Firefox</option>
                      <option value="vivaldi">Vivaldi</option>
                      <option value="opera">Opera</option>
                    </select>
                  ) : (
                    <input type="text" value={youtubeCookieFile} onChange={(event) => setYoutubeCookieFile(event.target.value)} placeholder="C:\\path\\to\\youtube-cookies.txt" className="ots-input w-full" />
                  )}
                </div>
              )}
              {formError && <p className="text-sm font-medium text-red-400">{formError}</p>}
              {signInStarted && <p className="rounded-lg border border-green-500/30 bg-green-500/10 px-4 py-3 text-sm text-green-300">{signInStarted}</p>}

              <div className="flex items-center justify-end gap-2 mt-6 pt-6 border-t border-gray-100 dark:border-neutral-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="ots-button ots-button-ghost"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="ots-button ots-button-primary"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                  {loading ? 'Starting…' : selectedService.mode === 'device' ? 'Start sign-in' : selectedService.mode === 'youtube' ? 'Save YouTube setup' : 'Add Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
