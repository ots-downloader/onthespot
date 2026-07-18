import React, { useEffect, useState } from "react";
import { Check, FolderOpen, Plus, Save, Trash2 } from "lucide-react";
import { DownloadProfile } from "../lib/api";

interface DownloadProfilesPanelProps {
  profiles: DownloadProfile[];
  activeProfile: string;
  onSave: (profile: DownloadProfile) => Promise<DownloadProfile | null>;
  onDelete: (profileId: string) => Promise<boolean>;
  onActivate: (profileId: string) => Promise<boolean>;
}

const emptyProfile: DownloadProfile = {
  id: "",
  name: "",
  format: "mp3",
  bitrate: "320k",
  download_path: "",
};

export const DownloadProfilesPanel: React.FC<DownloadProfilesPanelProps> = ({
  profiles,
  activeProfile,
  onSave,
  onDelete,
  onActivate,
}) => {
  const [draft, setDraft] = useState<DownloadProfile>(emptyProfile);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [selectedProfile, setSelectedProfile] = useState(activeProfile);

  useEffect(() => {
    setSelectedProfile(activeProfile);
  }, [activeProfile]);

  useEffect(() => {
    if (draft.id && profiles.some((profile) => profile.id === draft.id)) return;
    if (!draft.id && profiles[0]) setDraft(profiles[0]);
  }, [profiles, draft.id]);

  const edit = (profile: DownloadProfile) => {
    setDraft({ ...profile });
    setMessage("");
  };

  const newProfile = () => {
    setDraft({ ...emptyProfile, id: `profile-${Date.now()}`, name: "New profile" });
    setMessage("");
  };

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim()) {
      setMessage("Give the profile a name first.");
      return;
    }
    setSaving(true);
    const saved = await onSave({ ...draft, id: draft.id || draft.name });
    setSaving(false);
    setMessage(saved ? "Profile saved. New downloads will use it when selected." : "Could not save the profile.");
    if (saved) setDraft(saved);
  };

  const selectProfile = async (profile: DownloadProfile) => {
    edit(profile);
    if (selectedProfile === profile.id) return;
    setSelectedProfile(profile.id);
    const ok = await onActivate(profile.id);
    if (!ok) {
      setSelectedProfile(activeProfile);
      setMessage("Could not activate this profile.");
    }
  };

  const remove = async (profile: DownloadProfile) => {
    if (profiles.length <= 1 || !window.confirm(`Delete the ${profile.name} profile?`)) return;
    const ok = await onDelete(profile.id);
    if (ok) {
      setMessage("Profile deleted.");
      setDraft(profiles.find((item) => item.id !== profile.id) || emptyProfile);
    } else {
      setMessage("The active profile cannot be deleted until another profile exists.");
    }
  };

  return (
    <div className="animate-[fadeIn_0.2s_ease-out]">
      <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
        <div>
          <h3 className="text-lg font-medium text-gray-900 dark:text-neutral-100">Download profiles</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">Choose the audio format, quality, and destination for future downloads.</p>
        </div>
        <button type="button" onClick={newProfile} className="ots-button ots-button-primary"><Plus className="h-4 w-4" /> New profile</button>
      </div>

      <div className="mb-6 grid gap-3 sm:grid-cols-2">
        {profiles.map((profile) => (
          <div key={profile.id} onClick={() => void selectProfile(profile)} className={`ots-card cursor-pointer p-4 transition ${selectedProfile === profile.id ? "ots-card-active" : ""}`}>
            <div className="flex items-start justify-between gap-3">
              <button type="button" onClick={(event) => { event.stopPropagation(); void selectProfile(profile); }} className="min-w-0 text-left">
                <p className="truncate font-bold text-gray-900 dark:text-neutral-100">{profile.name}</p>
                <p className="mt-1 text-xs text-gray-500 dark:text-neutral-400">{profile.format.toUpperCase()} · {profile.bitrate} · {profile.download_path || "Default music folder"}</p>
              </button>
              {selectedProfile === profile.id && <Check className="h-4 w-4 shrink-0 text-[var(--spotify-green)]" />}
            </div>
            <div className="mt-3 flex items-center gap-2">
              <button type="button" onClick={(event) => { event.stopPropagation(); void selectProfile(profile); }} disabled={selectedProfile === profile.id} className="ots-button ots-button-primary h-9 px-3 text-xs">{selectedProfile === profile.id ? "Active" : "Use profile"}</button>
              <button type="button" onClick={(event) => { event.stopPropagation(); edit(profile); }} className="ots-button ots-button-ghost h-9 px-3 text-xs">Edit</button>
              <button type="button" onClick={(event) => { event.stopPropagation(); void remove(profile); }} className="ots-button ots-button-danger ml-auto h-9 w-9 px-0" title="Delete profile"><Trash2 className="h-4 w-4" /></button>
            </div>
          </div>
        ))}
      </div>

      <form onSubmit={save} className="border-t border-gray-200 pt-6 dark:border-neutral-800">
        <div className="mb-4 flex items-center gap-2 text-sm font-bold text-gray-900 dark:text-neutral-100"><FolderOpen className="h-4 w-4 text-[var(--spotify-green)]" /> Edit profile</div>
        <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-neutral-400">Profile name<input value={draft.name} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} className="ots-input w-full text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-neutral-400">Profile ID<input value={draft.id} onChange={(event) => setDraft((current) => ({ ...current, id: event.target.value }))} className="ots-input w-full text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-neutral-400">Audio format<select value={draft.format} onChange={(event) => setDraft((current) => ({ ...current, format: event.target.value }))} className="ots-select w-full text-sm"><option value="mp3">MP3</option><option value="flac">FLAC</option><option value="m4a">M4A</option><option value="opus">Opus</option><option value="ogg">OGG</option><option value="wav">WAV</option></select></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-neutral-400">Bitrate / quality<input value={draft.bitrate} onChange={(event) => setDraft((current) => ({ ...current, bitrate: event.target.value }))} placeholder="320k or 1411k" className="ots-input w-full text-sm" /></label>
          <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 dark:text-neutral-400 sm:col-span-2">Custom folder (leave blank for the default audio folder)<input value={draft.download_path} onChange={(event) => setDraft((current) => ({ ...current, download_path: event.target.value }))} placeholder="C:\\Music\\FLAC" className="ots-input w-full text-sm" /></label>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3"><button type="submit" disabled={saving} className="ots-button ots-button-primary">{saving ? "Saving…" : <><Save className="h-4 w-4" /> Save profile</>}</button>{message && <span className="text-sm text-gray-500 dark:text-neutral-400">{message}</span>}</div>
      </form>
    </div>
  );
};
