import React, { useState } from 'react';
import { Users, Plus, Trash2, Key, Shield, CheckCircle2, RefreshCw, Sparkles, ExternalLink, Music2, Disc, Lock } from 'lucide-react';
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
    switch (srv.toLowerCase()) {
      case 'spotify': return 'border-[#1DB954]/50 bg-[#1DB954]/10 text-[#1ed760]';
      case 'tidal': return 'border-cyan-500/50 bg-cyan-500/10 text-cyan-400';
      case 'soundcloud': return 'border-orange-500/50 bg-orange-500/10 text-orange-400';
      case 'bandcamp': return 'border-blue-500/50 bg-blue-500/10 text-blue-400';
      case 'apple_music':
      case 'applemusic': return 'border-rose-500/50 bg-rose-500/10 text-rose-400';
      case 'youtube_music':
      case 'youtube': return 'border-red-500/50 bg-red-500/10 text-red-400';
      default: return 'border-zinc-700 bg-zinc-800 text-zinc-300';
    }
  };

  return (
    <div className="max-w-7xl mx-auto p-4 lg:p-8 flex flex-col gap-8 animate-[fadeIn_0.3s_ease-out]">

      {/* Top Banner */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 lg:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-xl">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-white font-sans flex items-center gap-2.5">
            <Users className="w-6 h-6 text-emerald-400" />
            <span>Account Pool Manager</span>
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
              {accounts.length} active workers
            </span>
          </h2>
          <p className="text-xs text-zinc-400 font-mono mt-1">
            Accounts in this pool are rotated to parse metadata and download audio streams without hitting IP rate limits.
          </p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-bold px-5 py-3 rounded-xl transition-all shadow-lg shadow-emerald-500/20 flex items-center gap-2 cursor-pointer shrink-0 text-xs font-mono"
        >
          <Plus className="w-4 h-4" />
          <span>Add Service Account</span>
        </button>
      </div>

      {/* Account Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {accounts.map((acc) => {
          const colorClass = getServiceColor(acc.service);

          return (
            <div
              key={acc.uuid}
              className="bg-zinc-900/90 border border-zinc-800 rounded-2xl p-6 flex flex-col justify-between shadow-xl transition-all hover:border-zinc-700 relative group"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold uppercase border ${colorClass}`}>
                    {acc.service.replace('_', ' ')}
                  </span>

                  <div className="flex items-center gap-1.5 text-xs font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    <span>Active</span>
                  </div>
                </div>

                <div className="flex items-center gap-3 mb-4">
                  <div className="w-12 h-12 rounded-xl bg-zinc-950 border border-zinc-800 flex items-center justify-center font-bold font-mono text-lg text-zinc-300">
                    {acc.service.charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <h4 className="font-bold text-white text-base font-sans truncate">
                      {acc.username || `${acc.service}_public_worker`}
                    </h4>
                    <p className="text-xs text-zinc-500 font-mono truncate">
                      UUID: {acc.uuid}
                    </p>
                  </div>
                </div>

                {acc.login && (
                  <div className="bg-zinc-950 rounded-xl p-3 border border-zinc-800/80 mb-4 text-[11px] font-mono text-zinc-400 flex flex-col gap-1">
                    {Object.entries(acc.login).map(([k, v]) => (
                      <div key={k} className="flex justify-between truncate">
                        <span className="text-zinc-600">{k}:</span>
                        <span className="text-zinc-300 truncate pl-2">{String(v)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Action Footer */}
              <div className="flex items-center justify-between pt-4 border-t border-zinc-800/80 text-xs font-mono">
                <span className="text-zinc-500 flex items-center gap-1">
                  <Shield className="w-3.5 h-3.5 text-emerald-500" /> Auth Token Stored
                </span>

                <button
                  onClick={() => onRemoveAccount(acc.uuid)}
                  className="text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 p-2 rounded-lg transition-colors cursor-pointer flex items-center gap-1"
                  title="Remove worker account"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Remove</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add Account Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
          <div className="bg-zinc-900 border border-zinc-800 rounded-2xl max-w-md w-full p-6 lg:p-8 shadow-2xl relative">
            <h3 className="text-xl font-bold text-white font-sans mb-2 flex items-center gap-2">
              <Key className="w-5 h-5 text-emerald-400" />
              <span>Add Account to Worker Pool</span>
            </h3>
            <p className="text-xs text-zinc-400 font-mono mb-6 leading-relaxed">
              Authenticate Spotify Librespot, Tidal OAuth, Apple Music Developer Token, SoundCloud OAuth, Qobuz, Deezer, or Crunchyroll.
            </p>

            <form onSubmit={handleAddSubmit} className="flex flex-col gap-4">
              <div>
                <label className="text-xs font-mono font-bold text-zinc-400 uppercase mb-1 block">Platform Service</label>
                <select
                  value={service}
                  onChange={(e) => setService(e.target.value)}
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-sm text-white font-mono outline-none focus:border-emerald-500 cursor-pointer"
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
                <label className="text-xs font-mono font-bold text-zinc-400 uppercase mb-1 block">Username / Account Email (Optional)</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. samuel.brizzi94"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-sm text-white font-mono outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="text-xs font-mono font-bold text-zinc-400 uppercase mb-1 block">OAuth Bearer Token / Cookie (Optional)</label>
                <input
                  type="password"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Paste personal access token or leave blank for browser session"
                  className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-sm text-white font-mono outline-none focus:border-emerald-500"
                />
              </div>

              <div className="flex items-center gap-3 mt-4 pt-4 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-4 py-3 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-mono font-bold transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading}
                  className="flex-1 px-4 py-3 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-bold transition-all shadow-lg shadow-emerald-600/30 cursor-pointer disabled:opacity-50"
                >
                  {loading ? 'Adding...' : 'Save Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
};
