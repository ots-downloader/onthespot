import { AlertTriangle, Check, CheckCircle2, Copy, Download, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import React, { useEffect, useState } from "react";
import { copyToClipboard } from "../lib/clipboard";
import { UpdateInfo } from "../types";

interface UpdatePanelProps {
  currentVersion: string;
  status: UpdateInfo | null;
  onCheckNow: () => Promise<void>;
  autoCheckEnabled: boolean;
}

const DOCKER_UPDATE_COMMANDS = "docker compose pull\ndocker compose up -d";
const SOURCE_UPDATE_DOCS_URL =
  "https://github.com/ots-downloader/onthespot/blob/fastapi-dev/docs/INSTALLATION.md#updating";

export const UpdatePanel: React.FC<UpdatePanelProps> = ({ currentVersion, status, onCheckNow, autoCheckEnabled }) => {
  const [checking, setChecking] = useState(false);
  const [requestError, setRequestError] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (copyState === "idle") return;
    const timer = window.setTimeout(() => setCopyState("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [copyState]);

  // "Checked less than a minute ago" stops being true after a minute, so the
  // line goes away then. The server's floor is 60 seconds.
  const [reusedNoteShown, setReusedNoteShown] = useState(false);
  useEffect(() => {
    setReusedNoteShown(Boolean(status?.reused_recent_check));
    if (!status?.reused_recent_check) return;
    const timer = window.setTimeout(() => setReusedNoteShown(false), 60_000);
    return () => window.clearTimeout(timer);
  }, [status]);

  const checkNow = async () => {
    setChecking(true);
    setRequestError("");
    try {
      await onCheckNow();
    } catch {
      setRequestError("Could not reach the OnTheSpot server to check for updates.");
    } finally {
      setChecking(false);
    }
  };

  const copyCommands = async () => {
    setCopyState((await copyToClipboard(DOCKER_UPDATE_COMMANDS)) ? "copied" : "failed");
  };

  const error = requestError || status?.error || "";
  // The background checker retries a failed check after an hour, but only when
  // automatic checks are on and the build is not a development build.
  const willRetry = !requestError && Boolean(status?.error) && autoCheckEnabled && !status?.development_build;
  const checkedAt = status?.checked_at ? new Date(status.checked_at * 1000).toLocaleString() : "";

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
            Running version <span className="font-mono font-medium text-neutral-700 dark:text-neutral-300">{currentVersion || "unknown"}</span>.{" "}
            {autoCheckEnabled
              ? "The server checks GitHub for a new release at startup and once a day."
              : "Automatic checks are off in Settings. Check Now still works."}
          </p>
        </div>
        <button
          type="button"
          id="btn-check-updates-now"
          onClick={() => void checkNow()}
          disabled={checking}
          className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg border border-neutral-300 dark:border-neutral-700 bg-neutral-50 dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-750 text-neutral-800 dark:text-neutral-200 transition cursor-pointer shrink-0 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${checking ? "animate-spin" : ""}`} />
          {checking ? "Checking…" : "Check Now"}
        </button>
      </div>

      <div className="mt-4 border-t border-neutral-200 dark:border-neutral-800 pt-4 space-y-3">
        {reusedNoteShown && !requestError && (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Checked less than a minute ago. Showing that result.
          </p>
        )}

        {error && (
          <p className="flex items-center gap-2 text-xs text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>
              {error}
              {willRetry ? " The server tries again in about an hour." : ""}
            </span>
          </p>
        )}

        {status?.development_build ? (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Development build: no update prompts.
            {status.latest_version ? ` The latest release is ${status.latest_version}.` : ""}
          </p>
        ) : status?.update_available ? (
          <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-3">
            <p className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 dark:text-emerald-400">
              <Download className="h-4 w-4" />
              New Version Available: {status.latest_version}
            </p>
            <p className="mt-2 text-[11px] text-neutral-600 dark:text-neutral-400">
              To update a Docker install, run these commands in the folder that holds your <span className="font-mono">compose.yml</span>:
            </p>
            <code className="mt-1 block overflow-x-auto whitespace-pre rounded-md bg-neutral-900 dark:bg-black/40 p-2 font-mono text-[11px] text-emerald-400">
              {DOCKER_UPDATE_COMMANDS}
            </code>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                id="btn-copy-update-commands"
                onClick={() => void copyCommands()}
                className="inline-flex items-center gap-1 rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-2.5 py-1 text-xs font-semibold text-neutral-700 dark:text-neutral-200 cursor-pointer"
              >
                {copyState === "copied" ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {copyState === "copied" ? "Copied" : copyState === "failed" ? "Copy failed, select the text" : "Copy commands"}
              </button>
              {status.release_url && (
                <a
                  href={status.release_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-800 px-2.5 py-1 text-xs font-semibold text-neutral-700 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-700 transition"
                >
                  <ExternalLink className="w-3 h-3" /> Release notes
                </a>
              )}
            </div>
            <p className="mt-2 text-[11px] text-neutral-600 dark:text-neutral-400">
              Built from source? Follow{" "}
              <a
                href={SOURCE_UPDATE_DOCS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-emerald-700 dark:text-emerald-400 underline"
              >
                Updating in the install guide
              </a>
              .
            </p>
          </div>
        ) : !status?.checked_at ? (
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            Not checked yet. Press Check Now to ask GitHub for the latest release.
          </p>
        ) : !error ? (
          <p className="flex items-center gap-2 text-xs text-neutral-600 dark:text-neutral-300">
            <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            <span>You are on the latest release of OnTheSpot.</span>
          </p>
        ) : null}

        {checkedAt && (
          <p className="text-[10px] text-neutral-400 dark:text-neutral-500">
            Last checked {checkedAt} · Repository: {status?.repository || "ots-downloader/onthespot"}
          </p>
        )}
      </div>
    </section>
  );
};
