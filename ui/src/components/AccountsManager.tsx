import React, { useState } from 'react';
import { Users, Plus, Trash2, Key, Shield, Loader2, Server } from 'lucide-react';
import { AccountItem } from '../types';

interface AccountsManagerProps {
  accounts: AccountItem[];
  onAddAccount: (service: string, credentials: { username?: string; token?: string }) => Promise<AccountItem | null>;
  onRemoveAccount: (uuid: string) => Promise<boolean>;
}

export const AccountsManager: React.FC<AccountsManagerProps> = ({
  accounts,
  onAddAccount,
  onRemoveAccount
}) => {
  const [showModal, setShowModal] = useState(false);
  const [service, setService] = useState('generic');
  const [username, setUsername] = useState('');
  const [token, setToken] = useState('');
  const [loading, setLoading] = useState(false);

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
    <div className="max-w-7xl mx-auto p-4 md:p-6 lg:p-8 flex flex-col gap-6 font-sans">
      
      {/* Top Banner */}
      <div className="bg-white dark:bg-[#1a1a1a] rounded-2xl p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm border border-gray-200 dark:border-neutral-800/60">
        <div>
          <h2 className="text-xl font-medium text-gray-900 dark:text-neutral-100 flex items-center gap-2">
            <Users className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            Account Pool Manager
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-300 ml-2">
              {accounts.length} active workers
            </span>
          </h2>
          <p className="text-sm text-gray-500 dark:text-neutral-400 mt-1">
            Accounts are automatically rotated to distribute API load and bypass rate limits.
          </p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-full transition-colors flex items-center justify-center gap-2 text-sm font-medium shrink-0 focus:ring-2 focus:ring-blue-500/50 outline-none"
        >
          <Plus className="w-4 h-4" />
          <span>Add Account</span>
        </button>
      </div>

      {/* Account Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {accounts.map((acc) => {
          const colorClass = getServiceColor(acc.service);

          return (
            <div
              key={acc.uuid}
              className="bg-white dark:bg-[#1a1a1a] border border-gray-200 dark:border-neutral-800/60 rounded-2xl p-5 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow"
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
                  <div className="w-12 h-12 rounded-full bg-gray-100 dark:bg-neutral-800 flex items-center justify-center text-lg font-medium text-gray-700 dark:text-neutral-300">
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
                  className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10 px-3 py-1.5 rounded-full transition-colors flex items-center gap-1.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-red-500/20"
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
          <div className="bg-white dark:bg-[#1c1c1c] rounded-3xl max-w-md w-full p-6 sm:p-8 shadow-2xl relative overflow-hidden animate-[slideIn_0.2s_ease-out]">
            <div className="flex items-center gap-3 mb-2">
              <div className="p-2 bg-blue-50 dark:bg-blue-500/10 rounded-full">
                <Server className="w-5 h-5 text-blue-600 dark:text-blue-400" />
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
                  className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-neutral-100 focus:ring-2 focus:ring-blue-500/50 outline-none transition-shadow"
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
                  className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-neutral-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-blue-500/50 transition-shadow"
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-700 dark:text-neutral-300 mb-1.5 block">Access Token / Cookie (Optional)</label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste secure token"
                  className="w-full bg-gray-50 dark:bg-neutral-900 border border-gray-300 dark:border-neutral-700 rounded-xl px-4 py-2.5 text-sm text-gray-900 dark:text-neutral-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-blue-500/50 transition-shadow"
                />
              </div>

              <div className="flex items-center justify-end gap-2 mt-6 pt-6 border-t border-gray-100 dark:border-neutral-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-5 py-2 rounded-full text-sm font-medium text-gray-600 hover:bg-gray-100 dark:text-neutral-300 dark:hover:bg-neutral-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="px-5 py-2 rounded-full bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
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