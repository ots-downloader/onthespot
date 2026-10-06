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
| ~~Crunchyroll~~ | Email and password | Used for supported video content. |
| Deezer | ARL cookie value | A valid Deezer session is required. |
| Generic | None | Uses the generic/yt-dlp worker for supported URLs. |
| Qobuz?? | Email and password | A valid Qobuz account is required. |
| SoundCloud | Optional OAuth token | Public content works without a token; add one for account-specific access. |
| Spotify | Spotify Connect sign-in and Dev API Keys | Requires Spotify Premium and WebAPI Dev Keys. |
| Tidal | Device-link sign-in | Follow the link shown by OnTheSpot. |
| YouTube Music | Optional cookies | Public videos works without cookies. Sign-in or private videos require a Netscape-format `cookies.txt` file. |

Only use accounts and session data you are authorized to use. 

Secrets are stored in and encrypted file inside the root folder, with the encryption key on the side, it's not ideal but better than clean secrets, a password protection will be implemented in the stable 2.0 or 2.1.

### Spotify Connect account

To login via connect and your desktop app you'll need to run the companion on the PC running spotify.

> [!WARNING] Spotify has restriced API calls, be careful of the delay time, also some new accounts report to have basically no API call at all, so results may vary.

More info can be found in the `/companion` folder.


### Spotify Dev WebAPI credentials

Spotify needs a Spotify Developer app:

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

The **Read a browser on the OnTheSpot host** option is not intended to work for now, do not use it.

## Search & discover

Use this page for ~~text searches and~~ direct links.

~~1. Select one or more media categories: Tracks, Albums, Playlists, Artists,
   Podcasts, or Movies.
2. Select one or more entries under **Search services**. **All services** uses
   every currently available search worker.~~

> [!WARNING] Search is disabled for now because of api limits and bot detection, use only URLs

3. Enter an URL copied from a service and click **Search**.
4. Confirm the service badge on a result, then click **Download**.


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

### Export failed and unavailable downloads

Click **Export Failed / Unavailable** in **Download queue** to save a UTF-8
`.txt` file for finding those items later. The button appears when either
status is present and exports both statuses across the entire queue,
regardless of the active tab or selected rows. Use the **Unavailable** tab
to inspect items the service marked as unavailable.

The report groups entries by status and includes the title, artist/band,
album, service, source link/ID, playlist name/owner/position, queue ID, and
reported error. Missing metadata is marked as not available; entries with
no title are still included. Repeated tracks keep their individual playlist
positions. The file uses the metadata already loaded in the queue and the
statuses at export time; exporting does not retry, remove, or change items.

### Download profiles

Create profiles in **Settings → Download Profiles** for combinations such as
MP3 320 kbps, FLAC/lossless, or a custom destination. Activating a profile
changes the defaults used by future queue entries. Existing entries keep the
profile assigned when they were queued unless changed with a batch action.

## Local library

Coming Soon


## Settings

Settings sections are listed A–Z by default and can be reordered with
**Edit sections**.

- **API config:** Spotify credentials, search categories, cache behaviour, and
  playlist-automation cache lifetime.
- **Audio Outputs:** download roots, filename/folder formatters, playlist folder
  organization, M3U files, cover art, conversion, and lyrics.
  playlist-backup folders.
- **Display Settings:** theme preset, light/dark mode, custom/saved themes,
  language, thumbnails, and display preferences.
- **Download Profiles:** named format, quality, and destination presets.
- **General & Workers:** worker counts, delays, retry behaviour, update checks,
  and application options.
- **ID3 Tagging:** embedded metadata fields and metadata behaviour.
- **Video Media:** video output paths, formats, resolution, audio, and subtitles.

> [NOTE] Click **Save Config** after changing backend settings. 

Navigation and some display preferences save immediately in the browser.

## Diagnostics, notifications, and logs

- **Diagnostics** shows the OnTheSpot process, queue, disk, FFmpeg, worker, and
  Spotify API/rate-limit state.
- **Notification history** keeps user-visible success, warning, and error
  messages for the current installation.
- **Server logs** can be filtered by severity and cleared from the view.
- **Updates** check if a new update is available from source.


## Troubleshooting

- A service filter only appears when a matching worker is available.
- If Spotify Connect is missing, verify Premium access, same-LAN discovery, and
  local firewall rules; use the companion for a remote server.
- Use **Diagnostics**, **Notification history**, and **Server logs** for the
  exact backend error before retrying or changing credentials.
