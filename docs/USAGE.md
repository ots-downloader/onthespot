# OnTheSpot web-app usage

This guide describes the FastAPI web application on the `fastapi-dev` branch.
The API and UI are served by one OnTheSpot process and normally use the same
address, such as `http://127.0.0.1:6767` or your Docker/Unraid URL.

For installation, persistent folders, Docker, and Unraid setup, see
[INSTALLATION.md](INSTALLATION.md).

## First start

1. Open OnTheSpot in a browser.
2. Go to **Accounts** and add at least one service worker.
3. If you use Spotify catalogue search or Playlist sorting, open
   **Settings → API config** and save your Spotify Client ID and Client Secret.
4. Choose an output profile in **Download queue** or create one in
   **Settings → Download Profiles**.
5. Search for media or paste a supported URL in **Search & discover**.

The status shown in **Accounts** describes worker authentication. It is
separate from Spotify Web API credentials and Playlist sorting authorization.

## Accounts and service requirements

Open **Accounts → Add Account**. The available workers are listed A–Z and the
form changes to show the fields required by the selected service.

| Service | Account setup | Notes |
| --- | --- | --- |
| Apple Music | Media User Token | A valid Apple Music session and subscription may be required for protected content. |
| Bandcamp | None | Uses public Bandcamp access. |
| Crunchyroll | Email and password | Used for supported video content. |
| Deezer | ARL cookie value | A valid Deezer session is required. |
| Generic | None | Uses the generic/yt-dlp worker for supported URLs. |
| Qobuz | Email and password | A valid Qobuz account is required. |
| SoundCloud | Optional OAuth token | Public content works without a token; add one for account-specific access. |
| Spotify | Spotify Connect sign-in | Requires Spotify Premium. See the Spotify worker section below. |
| Tidal | Device-link sign-in | Follow the link shown by OnTheSpot. |
| YouTube Music | Optional cookies | Public videos may work without cookies. Sign-in or bot-protected videos require a Netscape-format `cookies.txt` file. |

Only use accounts and session data you are authorized to use. Secrets are
stored in OnTheSpot's persistent configuration directory and must not be
committed to Git.

### Spotify worker account

The Spotify worker supplies Spotify media access. It is not the same as the
Spotify Web API credentials used for catalogue metadata.

- **Local network:** choose this when OnTheSpot and the Spotify app are on the
  same LAN. Start sign-in, open Spotify's **Connect to a device** menu, and
  select **OnTheSpot**.
- **Remote access:** choose this when OnTheSpot is on another machine, such as
  Docker on Unraid. Create a short-lived pairing code and run the displayed
  companion command on the computer where Spotify is open. The companion must
  share a LAN with Spotify for Connect discovery, while its server URL must be
  reachable from that computer. See [the companion guide](../companion/README.md).

The companion is a one-time helper. A successful pairing saves the Spotify
worker on the server and the generated cleanup command removes the temporary
local companion checkout.

### Spotify API credentials

Spotify catalogue search and Playlist sorting need a Spotify Developer app:

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Copy its Client ID and Client Secret into **Settings → API config**.
3. Save the configuration.

These credentials identify the developer app; they do not sign in a Spotify
worker and do not grant access to a user's private playlists by themselves.

### YouTube cookies

YouTube does not provide a yt-dlp OAuth login. When a video requires sign-in:

1. Sign in to YouTube in a browser on your own computer.
2. Export that YouTube session as a Netscape-format `cookies.txt` file using a
   trusted browser-cookie export method.
3. In **Accounts**, add or reconfigure **YouTube Music** and choose
   **Upload cookies.txt**.
4. Upload the file. OnTheSpot copies it into its protected configuration
   directory; the browser upload is not retained as a separate temporary file.
5. Delete the exported local file when setup succeeds.

The **Read a browser on the OnTheSpot host** option only works when that browser
profile exists on the same machine as the OnTheSpot process. It cannot read a
desktop browser from inside a Docker container.

## Search & discover

Use this page for text searches and direct links.

1. Select one or more media categories: Tracks, Albums, Playlists, Artists,
   Podcasts, or Movies.
2. Select one or more entries under **Search services**. **All services** uses
   every currently available search worker.
3. Enter a query and click **Search**.
4. Confirm the service badge on a result, then click **Download**.

When multiple services are selected, OnTheSpot requests them independently,
isolates a failed provider, and interleaves successful provider results so one
large result set cannot hide the others. The result header shows a count for
each returned service. Results still come from each provider's own catalogue,
so matches and metadata can differ.

Changing the selected services or media categories clears stale results. A
direct supported URL is parsed and sent to the queue using its detected
service.

## Download queue

The queue shows the source service, media type, artwork, state, progress,
speed, and ETA when the downloader can report them.

- Choose the active download profile from the queue header.
- Pause or resume queue processing.
- Retry failed entries, clear completed entries, or clear failed entries.
- Cancel an active or waiting item.
- Select visible entries for batch pause, resume, retry, cancel, delete,
  priority, or profile changes.
- Drag waiting entries to change their queue order.
- Use **Verify files** to check completed entries against files on disk.

Playlist downloads are expanded before progress is calculated. The Playlist
progress card shows overall completion and the current/next track; individual
tracks can be shown or hidden.

### Download profiles

Create profiles in **Settings → Download Profiles** for combinations such as
MP3 320 kbps, FLAC/lossless, or a custom destination. Activating a profile
changes the defaults used by future queue entries. Existing entries keep the
profile assigned when they were queued unless changed with a batch action.

## Local library

**Local library** indexes files saved by OnTheSpot.

- **Scan library** refreshes the index and artwork.
- Search by title, artist, album, or genre.
- Sort by artist, album, title, date added, or other available fields, then
  reverse the order with the A–Z/Z–A control.
- Filter by format, artist, genre, download date, duplicates, missing artwork,
  or metadata issues.
- Play a local file, open its folder, edit metadata, rename it, or delete it.
- Create an `.m3u` file from matching library items.
- **Verify files** detects incomplete, corrupt, or missing indexed files.

Missing-file entries can be re-downloaded when a source URL was saved, removed
individually from the index, or cleared together. Removing an index entry does
not recreate or delete an already missing file.

## Playlist sorting

Playlist sorting uses Spotify OAuth and is separate from the Spotify worker
account. The Client ID and Client Secret come from **Settings → API config**.

### Connect Spotify

1. Open Playlist sorting. OnTheSpot proposes a callback based on the address
   currently open in the browser.
2. Add that exact callback to the Spotify Developer Dashboard.
3. Save the redirect URI and click **Connect Spotify**.

For local development, Spotify accepts the loopback form
`http://127.0.0.1:<port>/playlist-automation/callback`; OnTheSpot converts
`localhost` to `127.0.0.1` automatically. A remote installation needs an HTTPS
callback that reaches that installation. The saved refresh token is reused, so
normal page loads should not require another authorization.

### Sorting tools

- **Sort tracks:** add and drag priority rules such as release date, artist,
  album, and title.
- **Manage duplicates:** choose which duplicate to retain by release date or
  playlist order.
- **Version replacer:** find older/newer or alternate versions, with same-artist
  or global search modes.
- **Dynamic playlists:** feed one or more source playlists into a target using
  replace, merge, or append behaviour, filters, sample limits, and optional
  local-file preservation. Drag configurations to set dependency order.
- **Schedules:** run a configuration or all dynamic playlists daily, on
  weekdays, weekly, or monthly.
- **Review changes:** approve or reject proposed removals and replacements
  before applying them.
- **Compare:** find tracks shared by two or more selected playlists and remove
  individual copies.
- **Ignored tracks:** inspect and restore items excluded from replacement or
  duplicate processing.
- **History / Undo:** review operations and undo supported changes.
- **Debug:** inspect searchable processing events and failures.

Playlist rows support click, Shift-click range selection, and click-drag
selection. Selected playlists can also be downloaded directly, exported to
CSV, backed up/restored, or included in an automation-config export. Export and
backup destinations are set in **Settings → Backup & Restore**.

## Download statistics

The statistics page summarizes completed and failed downloads, success rate,
storage represented by indexed downloads, formats, services, and history.
Clearing statistics removes the recorded statistics history; it does not
delete downloaded media.

## Settings

Settings sections are listed A–Z by default and can be reordered with
**Edit sections**.

- **API config:** Spotify credentials, search categories, cache behaviour, and
  playlist-automation cache lifetime.
- **Audio Outputs:** download roots, filename/folder formatters, playlist folder
  organization, M3U files, cover art, conversion, and lyrics.
- **Backup & Restore:** portable settings backup/restore plus default export and
  playlist-backup folders.
- **Display Settings:** theme preset, light/dark mode, custom/saved themes,
  language, thumbnails, and display preferences.
- **Download Profiles:** named format, quality, and destination presets.
- **General & Workers:** worker counts, delays, retry behaviour, update checks,
  and application options.
- **ID3 Tagging:** embedded metadata fields and metadata behaviour.
- **Video Media:** video output paths, formats, resolution, audio, and subtitles.

Click **Save Config** after changing backend settings. Theme, navigation, and
some display preferences save immediately in the browser.

## Diagnostics, notifications, and logs

- **Diagnostics** shows the OnTheSpot process, queue, disk, FFmpeg, worker, and
  Spotify API/rate-limit state.
- **Notification history** keeps user-visible success, warning, and error
  messages for the current installation.
- **Server logs** can be filtered by severity and cleared from the view.

If a service disappears briefly during a server restart, the UI preserves the
selected search-service choices and restores them after reconnecting.

## Troubleshooting

- A service filter only appears when a matching worker is available.
- If all search cards show one provider, confirm more than one service button
  is selected and inspect the per-service counts above the results.
- If Spotify Connect is missing, verify Premium access, same-LAN discovery, and
  local firewall rules; use the companion for a remote server.
- If Playlist sorting asks to connect again, confirm its persistent config
  directory is mounted and the saved callback exactly matches the Spotify app.
- If YouTube stalls or reports bot/sign-in protection, re-upload fresh cookies
  and retry the item.
- Use **Diagnostics**, **Notification history**, and **Server logs** for the
  exact backend error before retrying or changing credentials.
