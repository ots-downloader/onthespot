import React, { useCallback, useEffect, useState } from "react";
import { CheckCircle2, Download, ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
import {
  fetchUpdateInfo,
  installApplicationUpdate,
  UpdateInfo,
} from "../lib/api";

interface UpdatePanelProps {
  currentVersion: string;
}

const formatSize = (bytes: number) => {
  if (!bytes) return "";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
};

export const UpdatePanel: React.FC<UpdatePanelProps> = ({ currentVersion }) => {
  const [status, setStatus] = useState<UpdateInfo | null>(null);
  const [checking, setChecking] = useState(true);
  const [installing, setInstalling] = useState(false);
  const [message, setMessage] = useState("");

  const check = useCallback(async (force = false) => {
    setChecking(true);
    const result = await fetchUpdateInfo(force);
    if (result) setStatus(result);
    setChecking(false);
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const install = async () => {
    setInstalling(true);
    setMessage("");
    const result = await installApplicationUpdate();
    setInstalling(false);
    if (!result) {
      setMessage("The update service could not be reached.");
      return;
    }
    if (result.success) {
      setMessage(result.message || "The update is ready. Restarting…");
      return;
    }
    setMessage(result.message || "Automatic installation is not available for this installation.");
  };

  const assetUrl = status?.recommended_asset?.download_url || status?.release_url || "";
  const checkedAt = status?.checked_at ? new Date(status.checked_at * 1000).toLocaleString() : "";

  return (
    <section className="ots-panel mt-6 border border-gray-200 p-5 dark:border-neutral-800">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <p className="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] text-[#1ed760]">
            <Sparkles className="h-4 w-4" /> Application updates
          </p>
          <h3 className="mt-2 text-lg font-bold text-gray-900 dark:text-neutral-100">Keep OnTheSpot current</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-neutral-400">
            Current version {currentVersion || "unknown"}. Automatic checks run in the background when enabled above.
          </p>
        </div>
        <button type="button" onClick={() => void check(true)} disabled={checking} className="ots-button ots-button-secondary shrink-0">
          <RefreshCw className={`h-4 w-4 ${checking ? "animate-spin" : ""}`} />
          {checking ? "Checking…" : "Check now"}
        </button>
      </div>

      <div className="mt-5 border-t border-gray-200 pt-4 dark:border-neutral-800">
        {checking && !status ? (
          <p className="flex items-center gap-2 text-sm text-gray-500 dark:text-neutral-400"><Loader2 className="h-4 w-4 animate-spin" /> Checking the release feed…</p>
        ) : status?.error ? (
          <p className="text-sm text-gray-500 dark:text-neutral-400">{status.error} You can still open the release page below.</p>
        ) : status?.update_available ? (
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="flex items-center gap-2 text-sm font-bold text-[#1ed760]"><Download className="h-4 w-4" /> Update available: {status.latest_version}</p>
              <p className="mt-1 text-xs text-gray-500 dark:text-neutral-400">{status.release_name}{status.recommended_asset?.name ? ` · ${status.recommended_asset.name}` : ""}{status.recommended_asset?.size ? ` · ${formatSize(status.recommended_asset.size)}` : ""}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              {status.install_supported && (
                <button type="button" onClick={() => void install()} disabled={installing} className="ots-button ots-button-primary">
                  {installing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                  {installing ? "Installing…" : "Install and restart"}
                </button>
              )}
              <a href={assetUrl} target="_blank" rel="noopener noreferrer" className="ots-button ots-button-secondary">
                <ExternalLink className="h-4 w-4" /> {status.install_supported ? "Release details" : "Download update"}
              </a>
            </div>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-sm text-gray-600 dark:text-neutral-300"><CheckCircle2 className="h-4 w-4 text-[#1ed760]" /> You’re up to date.</p>
        )}
        {message && <p className="mt-3 text-xs text-gray-500 dark:text-neutral-400">{message}</p>}
        {checkedAt && <p className="mt-3 text-[11px] text-gray-400 dark:text-neutral-600">Last checked {checkedAt} · {status?.repository}</p>}
      </div>
    </section>
  );
};

