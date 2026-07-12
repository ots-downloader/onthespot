import React, { useState } from 'react';
import { Users, Plus, Trash2, Key, Shield, Loader2, Server, RefreshCw, CircleCheck, AlertTriangle } from 'lucide-react';
import { AccountItem } from '../types';
import type { AccountHealth } from '../lib/api';

interface AccountsManagerProps {
  accounts: AccountItem[];
  onAddAccount: (service: string, credentials: { username?: string; token?: string }) => Promise<AccountItem | null>;
  onRemoveAccount: (uuid: string) => Promise<boolean>;
  health: AccountHealth | null;
  onReconnect: () => Promise<boolean>;
}

export const AccountsManager: React.FC<AccountsManagerProps> = ({
  accounts,
  onAddAccount,
  onRemoveAccount,
  health,
  onReconnect
}) => {
  const [showModal, setShowModal] = useState(false);
  const [service, setService] = useState('generic');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    const res = await onAddAccount(service, { username, token });
    setLoading(false);
    if (res) {
      setShowModal(false);
      setUsername('');
      setToken('');
    }
  };

  const getServiceColor = (srv: string) => {
    const base = "font-medium capitalize text-xs px-2.5 py-0.5 rounded-full";
    switch (srv.toLowerCase()) {
      case 'spotify': return `${base} bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300`;
      case 'tidal': return `${base} bg-cyan-100 text-cyan-800 dark:bg-cyan-900/30 dark:text-cyan-300`;
      case 'soundcloud': return `${base} bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300`;
      case 'bandcamp': return `${base} bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300`;
      case 'apple_music':
      case 'applemusic': return `${base} bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-300`;
      case 'youtube_music':
      case 'youtube': return `${base} bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300`;
      default: return `${base} bg-gray-100 text-gray-800 dark:bg-neutral-800 dark:text-neutral-300`;
    }
  };

  return (
    <div className="spotify-fade-up ots-page flex flex-col gap-6 font-sans">
      
      {/* Top Banner */}
      <div className="ots-hero flex flex-col justify-between gap-4 p-6 sm:flex-row sm:items-center">
        <div>
          <h2 className="flex items-center gap-2 text-xl font-bold text-white">
            <Users className="h-5 w-5 text-[#1ed760]" />
            Account Pool Manager
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

      {/* Account Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {accounts.map((acc) => {
          const colorClass = getServiceColor(acc.service);

          return (
            <div
              key={acc.uuid}
              className="ots-card flex flex-col justify-between p-5 shadow-xl shadow-black/10 transition-colors hover:bg-[#242424]"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className={colorClass}>
                    {acc.service.replace('_', ' ')}
                  </span>
                  <div className="flex items-center gap-1.5 text-[11px] font-medium text-green-700 dark:text-green-400 bg-green-50 dark:bg-green-900/10 px-2.5 py-0.5 rounded-full">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                    Active
                  </div>
                </div>

                <div className="flex items-center gap-4 mb-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-[#282828] text-lg font-medium text-[#b3b3b3]">
                    {acc.service.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="font-medium text-gray-900 dark:text-neutral-100 text-base truncate">
                      {acc.username || `${acc.service}_public_worker`}
                    </h4>
                    <p className="text-xs text-gray-500 dark:text-neutral-500 truncate mt-0.5" title={acc.uuid}>
                      {acc.uuid}
                    </p>
                  </div>
                </div>

                
              </div>

              {/* Action Footer */}
              <div className="flex items-center justify-between pt-4 border-t border-gray-100 dark:border-neutral-800">
                <span className="text-gray-500 dark:text-neutral-500 text-xs flex items-center gap-1.5">
                  <Shield className="w-4 h-4 text-gray-400" /> Authenticated
                </span>

                <button
                  onClick={() => onRemoveAccount(acc.uuid)}
                  className="ots-button ots-button-danger h-9 px-3 text-xs"
                >
                  <Trash2 className="w-4 h-4" />
                  Remove
                </button>
              </div>
            </div>
          );
        })}
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
                  onChange={(e) => setService(e.target.value)}
                  className="ots-select w-full"
                >
                  <option value="generic">Generic (Free)</option>
                  <option value="spotify">Spotify (zeroconf - Premium + DevAPI)</option>
                  <option value="tidal">Tidal HiFi (Link - Premium)</option>
                  <option value="soundcloud">SoundCloud (OAuth Token)</option>
                  <option value="bandcamp">Bandcamp (Cookie / Free)</option>
                  <option value="applemusic">Apple Music Lossless</option>
                  <option value="youtube">YouTube Music</option>
                  <option value="qobuz">Qobuz Studio</option>
                  <option value="deezer">Deezer HiFi</option>
                  <option value="crunchyroll">Crunchyroll Video</option>
                </select>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">Username / Email (Optional)</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. user@example.com"
                  className="ots-input w-full"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">Access Token / Cookie (Optional)</label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste secure token"
                  className="ots-input w-full"
                />
              </div>

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
                  {loading ? 'Saving...' : 'Add Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
