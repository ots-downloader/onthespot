import { CheckCircle2, Download, ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import { fetchUpdateInfo } from "../lib/api";
import { UpdateInfo } from "../types";

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
    try {
      const result = await fetchUpdateInfo(force);
      if (result) setStatus(result);
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const install = async () => {
    setInstalling(true);
    setMessage("");
    try {
      const result = await installApplicationUpdate();
      if (!result) {
        setMessage("The update service could not be reached.");
        return;
      }
      if (result.success) {
        setMessage(result.message || "The update is ready. Daemon restarting…");
        return;
      }
      setMessage(result.message || "Automatic installation is not available for this environment.");
    } finally {
      setInstalling(false);
    }
  };

  const assetUrl = status?.recommended_asset?.download_url || status?.release_url || "";
  const checkedAt = status?.checked_at ? new Date(status.checked_at * 1000).toLocaleTimeString() : "";

  return (
    <section className="mt-6 rounded-xl border border-neutral-200 dark:border-neutral-800 bg-white dark:bg-neutral-900/60 p-5 shadow-xs">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
            <Sparkles className="h-3.5 w-3.5" /> Application Release & Updates
          </p>
          <h3 className="mt-1.5 text-base font-bold text-neutral-900 dark:text-neutral-100">
            Keep OnTheSpot Current
          </h3>
          <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">
            Running version <span className="font-mono font-medium text-neutral-700 dark:text-neutral-300">{currentVersion || "unknown"}</span>. Background checks occur periodically.
          </p>
        </div>
        <button
          type="button"
          id="btn-check-updates-now"
          onClick={() => void check(true)}
          disabled={checking}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-750 text-neutral-800 dark:text-neutral-200 transition cursor-pointer shrink-0 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${checking ? "animate-spin" : ""}`} />
          {checking ? "Checking…" : "Check Now"}
        </button>
      </div>

      <div className="mt-4 border-t border-neutral-200 dark:border-neutral-800 pt-4">
        {checking && !status ? (
          <p className="flex items-center gap-2 text-xs text-neutral-500 dark:text-neutral-400">
            <Loader2 className="h-4 w-4 animate-spin text-emerald-500" />
            Connecting to release feed…
          </p>
        ) : status?.error ? (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {status.error} You can inspect the release repository directly below.
          </p>
        ) : status?.development_build ? (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Development build: no update prompts.
            {status.latest_version ? ` The latest release is ${status.latest_version}.` : ""}
          </p>
        ) : status?.update_available ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-3">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-400">
                <Download className="h-4 w-4" />
                New Version Available: {status.latest_version}
              </p>
              <p className="mt-0.5 text-[11px] text-neutral-600 dark:text-neutral-400">
                {status.release_name}
                {status.recommended_asset?.name ? ` · ${status.recommended_asset.name}` : ""}
                {status.recommended_asset?.size ? ` · ${formatSize(status.recommended_asset.size)}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {status.install_supported && (
                <button
                  type="button"
                  id="btn-install-restart-update"
                  onClick={() => void install()}
                  disabled={installing}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium transition cursor-pointer shadow-xs"
                >
                  {installing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                  {installing ? "Installing…" : "Install & Restart"}
                </button>
              )}
              {assetUrl && (
                <a
                  href={assetUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 text-xs font-medium hover:bg-neutral-50 dark:hover:bg-neutral-700 transition"
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {status.install_supported ? "Release Details" : "Download Update"}
                </a>
              )}
            </div>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-300">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <span>You are on the latest release of OnTheSpot.</span>
          </p>
        )}

        {message && (
          <p className="mt-2.5 text-xs font-mono text-neutral-500 dark:text-neutral-400">
            {message}
          </p>
        )}

        {checkedAt && (
          <p className="mt-2 text-[10px] text-neutral-400 dark:text-neutral-500">
            Last checked {checkedAt} · Repository: {status?.repository || "ots-downloader/onthespot"}
          </p>
        )}
      </div>
    </section>
  );
};
