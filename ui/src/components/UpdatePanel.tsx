import { CheckCircle2, Download, ExternalLink, Loader2, RefreshCw, Sparkles } from "lucide-react";
import React, { useCallback, useEffect, useState } from "react";
import { fetchUpdateInfo } from "../lib/api";
import { UpdateInfo } from "../types";
import { Button, focusRing } from "./ui";

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
    <section className="mt-6 rounded-xl border border-line bg-surface p-5 shadow-xs">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-accent">
            <Sparkles className="h-3.5 w-3.5" /> Application Release & Updates
          </p>
          <h3 className="mt-1.5 text-base font-bold text-fg">
            Keep OnTheSpot Current
          </h3>
          <p className="mt-1 text-xs text-fg-muted">
            Running version <span className="font-mono font-medium text-fg">{currentVersion || "unknown"}</span>. Background checks occur periodically.
          </p>
        </div>
        <Button
          id="btn-check-updates-now"
          variant="secondary"
          size="sm"
          label={checking ? "Checking…" : "Check Now"}
          icon={<RefreshCw className={`h-3.5 w-3.5 ${checking ? "animate-spin" : ""}`} />}
          onClick={() => void check(true)}
          isDisabled={checking}
        />
      </div>

      <div className="mt-4 border-t border-line pt-4">
        {checking && !status ? (
          <p className="flex items-center gap-2 text-xs text-fg-muted">
            <Loader2 className="h-4 w-4 animate-spin text-accent" />
            Connecting to release feed…
          </p>
        ) : status?.error ? (
          <p className="text-xs text-fg-muted">
            {status.error} You can inspect the release repository directly below.
          </p>
        ) : status?.development_build ? (
          <p className="text-xs text-fg-muted">
            Development build: no update prompts.
            {status.latest_version ? ` The latest release is ${status.latest_version}.` : ""}
          </p>
        ) : status?.update_available ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg bg-accent-subtle border border-accent/40 p-3">
            <div>
              <p className="flex items-center gap-1.5 text-xs font-bold text-accent">
                <Download className="h-4 w-4" />
                New Version Available: {status.latest_version}
              </p>
              <p className="mt-0.5 text-[11px] text-fg-muted">
                {status.release_name}
                {status.recommended_asset?.name ? ` · ${status.recommended_asset.name}` : ""}
                {status.recommended_asset?.size ? ` · ${formatSize(status.recommended_asset.size)}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              {status.install_supported && (
                <Button
                  id="btn-install-restart-update"
                  variant="accent"
                  size="sm"
                  label={installing ? "Installing…" : "Install & Restart"}
                  icon={<Download className="h-3.5 w-3.5" />}
                  onClick={() => void install()}
                  isLoading={installing}
                />
              )}
              {assetUrl && (
                <a
                  href={assetUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-line-strong bg-surface text-fg text-xs font-medium hover:bg-raised transition ${focusRing}`}
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  {status.install_supported ? "Release Details" : "Download Update"}
                </a>
              )}
            </div>
          </div>
        ) : (
          <p className="flex items-center gap-2 text-xs text-fg-muted">
            <CheckCircle2 className="h-4 w-4 text-success-fg" />
            <span>You are on the latest release of OnTheSpot.</span>
          </p>
        )}

        {message && (
          <p className="mt-2.5 text-xs font-mono text-fg-muted">
            {message}
          </p>
        )}

        {checkedAt && (
          <p className="mt-2 text-[10px] text-fg-subtle">
            Last checked {checkedAt} · Repository: {status?.repository || "ots-downloader/onthespot"}
          </p>
        )}
      </div>
    </section>
  );
};
