import assert from "node:assert/strict";
import { test } from "node:test";
import type { DownloadQueueItem } from "../types";
import { downloadQueueFailures, formatQueueFailures } from "./queueExport";

const capturedAt = new Date("2026-01-02T03:04:05Z");

function item(overrides: Partial<DownloadQueueItem> = {}): DownloadQueueItem {
  return {
    local_id: 1, name: "Ação", artist: "Björk; 坂本龍一", album: "Álbum",
    item_service: "spotify", item_type: "track", item_id: "abc123",
    item_url: "https://api.spotify.com/v1/tracks/abc123", item_status: "Failed",
    playlist_name: "Favorites", playlist_by: "Listener", playlist_number: "10",
    parent_category: "playlist", progress: 0, target_format: "mp3",
    download_format: "mp3", file_path: "", temp_path: "",
    download_profile: { id: "default", name: "Default", format: "mp3", bitrate: "320", download_path: "", is_default: true },
    error: "Connection timed out", ...overrides,
  };
}

test("exports only failures and unavailable entries without changing the queue", () => {
  const statuses: DownloadQueueItem["item_status"][] = [
    "Downloaded", "Failed", "Waiting", "Unavailable", "Already Exists",
    "Cancelled", "Downloading", "Converting", "Paused", "Deleted",
  ];
  const queue = statuses.map((status, i) => item({ local_id: i + 1, item_status: status, name: `Title ${status}` }));
  const before = structuredClone(queue);
  const report = formatQueueFailures(queue, capturedAt);
  assert.match(report, /Captured: 2026-01-02T03:04:05.000Z/);
  assert.match(report, /Total: 2\r\n/);
  assert.match(report, /FAILED \(1\)/);
  assert.match(report, /UNAVAILABLE \(1\)/);
  assert.match(report, /Title Failed/);
  assert.match(report, /Title Unavailable/);
  for (const status of statuses.filter((status) => status !== "Failed" && status !== "Unavailable")) {
    assert.ok(!report.includes(`Title ${status}`));
  }
  assert.deepEqual(queue, before);
});

test("preserves Unicode, search metadata and separate occurrences of the same track", () => {
  const report = formatQueueFailures([item(), item({ local_id: 2, playlist_number: "25" })], capturedAt);
  for (const detail of ["Ação", "Björk; 坂本龍一", "Album: Álbum", "Playlist: Favorites", "Playlist by: Listener", "Error: Connection timed out"]) {
    assert.ok(report.includes(detail), detail);
  }
  assert.equal(report.match(/Link: https:\/\/open.spotify.com\/track\/abc123/g)?.length, 2);
  assert.match(report, /Playlist position: 10/);
  assert.match(report, /Playlist position: 25/);
  assert.match(report, /Queue ID: 1/);
  assert.match(report, /Queue ID: 2/);
});

test("retains unnamed entries and keeps multiline metadata within its field", () => {
  const report = formatQueueFailures([item({ name: " ", artist: "", album: undefined, playlist_number: "3018", error: "first line\r\nsecond line" })], capturedAt);
  assert.match(report, /1\. \[Title not available\]/);
  assert.match(report, /Artist \/ band: Not available/);
  assert.match(report, /Album: Not available/);
  assert.match(report, /Source ID: abc123/);
  assert.match(report, /Playlist position: 3018/);
  assert.match(report, /Error: first line second line\r\n/);
});

test("keeps other service links and handles missing links and an empty queue", () => {
  const report = formatQueueFailures([
    item({ item_service: "bandcamp", item_url: "https://example.bandcamp.com/track/song" }),
    item({ item_service: "generic", item_url: "", error: "" }),
    item({ item_type: "episode", item_id: "episode123" }),
  ], capturedAt);
  assert.match(report, /Link: https:\/\/example.bandcamp.com\/track\/song/);
  assert.match(report, /Link: Not available/);
  assert.match(report, /Error: No error details provided/);
  assert.match(report, /Link: https:\/\/open.spotify.com\/episode\/episode123/);
  const empty = formatQueueFailures([], capturedAt);
  assert.match(empty, /Total: 0\r\n/);
  assert.match(empty, /FAILED \(0\)/);
  assert.match(empty, /UNAVAILABLE \(0\)/);
});

test("downloads a UTF-8 TXT and releases the temporary browser objects", async (t) => {
  let blob: Blob | undefined;
  let clicked = false;
  let removed = false;
  let release: (() => void) | undefined;
  const anchor = { href: "", download: "", click() { clicked = true; }, remove() { removed = true; } };
  t.mock.method(URL, "createObjectURL", (value: Blob) => { blob = value; return "blob:test"; });
  const revoke = t.mock.method(URL, "revokeObjectURL", () => {});
  t.mock.method(globalThis, "setTimeout", (callback: () => void) => { release = callback; return 1; });
  Object.defineProperty(globalThis, "document", { configurable: true, value: {
    createElement: () => anchor,
    body: { appendChild: (element: unknown) => assert.equal(element, anchor) },
  } });
  t.after(() => Reflect.deleteProperty(globalThis, "document"));

  downloadQueueFailures([item()]);
  assert.ok(clicked && removed);
  assert.equal(anchor.href, "blob:test");
  assert.match(anchor.download, /^onthespot-failed-unavailable-[\dTZ-]+\.txt$/);
  assert.equal(blob?.type, "text/plain;charset=utf-8");
  const bytes = new Uint8Array(await blob!.arrayBuffer());
  assert.deepEqual([...bytes.slice(0, 3)], [0xef, 0xbb, 0xbf]);
  assert.match(await blob!.text(), /Björk; 坂本龍一/);
  assert.equal(revoke.mock.callCount(), 0);
  release!();
  assert.deepEqual(revoke.mock.calls[0].arguments, ["blob:test"]);
});
