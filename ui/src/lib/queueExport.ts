import type { DownloadQueueItem } from "../types";

const exportStatuses = ["Failed", "Unavailable"] as const;

function text(value: string | undefined, fallback = "Not available"): string {
  return value?.replace(/\s+/g, " ").trim() || fallback;
}

function sourceUrl(item: DownloadQueueItem): string {
  // Playlist entries can contain an API URL instead of a link users can open.
  if (
    item.item_service === "spotify" &&
    ["track", "episode"].includes(item.item_type) &&
    /^[a-zA-Z0-9]+$/.test(item.item_id)
  ) {
    return `https://open.spotify.com/${item.item_type}/${item.item_id}`;
  }
  return text(item.item_url);
}

export function formatQueueFailures(
  queue: readonly DownloadQueueItem[],
  capturedAt = new Date(),
): string {
  const groups = exportStatuses.map((status) => ({
    status,
    items: queue.filter((item) => item.item_status === status),
  }));
  const lines = [
    "OnTheSpot - Failed and unavailable downloads",
    `Captured: ${capturedAt.toISOString()}`,
    `Total: ${groups.reduce((total, group) => total + group.items.length, 0)}`,
    "",
    "Snapshot of all failed and unavailable entries in the download queue.",
    "Statuses may change after retries; missing metadata is marked as not available.",
    "",
  ];

  for (const { status, items } of groups) {
    lines.push(`${status.toUpperCase()} (${items.length})`, "");
    items.forEach((item, index) => {
      lines.push(
        `${index + 1}. ${text(item.name, "[Title not available]")}`,
        `Artist / band: ${text(item.artist)}`,
        `Album: ${text(item.album)}`,
        `Service: ${text(item.item_service)}`,
        `Media type: ${text(item.item_type)}`,
        `Source ID: ${text(item.item_id)}`,
        `Link: ${sourceUrl(item)}`,
        `Playlist: ${text(item.playlist_name)}`,
        `Playlist by: ${text(item.playlist_by)}`,
        `Playlist position: ${text(item.playlist_number)}`,
        `Queue ID: ${item.local_id}`,
        `Error: ${text(item.error, "No error details provided")}`,
        "",
      );
    });
  }
  return lines.join("\r\n");
}

export function downloadQueueFailures(queue: readonly DownloadQueueItem[]): void {
  const capturedAt = new Date();
  const blob = new Blob(["\uFEFF", formatQueueFailures(queue, capturedAt)], {
    type: "text/plain;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `onthespot-failed-unavailable-${capturedAt.toISOString().replace(/[:.]/g, "-")}.txt`;
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    // Give the browser time to start reading the Blob before releasing it.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
