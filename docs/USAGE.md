# OnTheSpot web-app usage

This guide describes the FastAPI web application on the `fastapi-dev` branch.
The API and UI are served by one OnTheSpot process and normally use the same
address, such as `http://127.0.0.1:6767` or your Docker/Unraid URL.

For installation, persistent folders, Docker, and Unraid setup, see
[INSTALLATION.md](INSTALLATION.md).

## First start

1. Open OnTheSpot in a browser.
2. Go to **Accounts** and add at least one service worker.
3. If you download from Spotify, open **Settings → API config** and save
   your Spotify Client ID and Client Secret. OnTheSpot uses them to fetch
   track and album details.
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
| Spotify | Sign in with Spotify (code at spotify.com/pair) and Dev API Keys | Requires Spotify Premium and WebAPI Dev Keys. |
| Tidal | Device-link sign-in | Follow the link shown by OnTheSpot. |
| YouTube Music | Optional cookies | Public videos works without cookies. Sign-in or private videos require a Netscape-format `cookies.txt` file. |

Only use accounts and session data you are authorized to use. 

Secrets are stored in and encrypted file inside the root folder, with the encryption key on the side, it's not ideal but better than clean secrets, a password protection will be implemented in the stable 2.0 or 2.1.

### Spotify account

1. Open **Accounts → Add account → Spotify** and choose **Sign in with Spotify**.
2. OnTheSpot shows a short code and a link.
3. On any device, open https://spotify.com/pair, enter the code, and approve.

OnTheSpot then stores the account. This works with Docker, Unraid, and remote
setups. A free account is refused with a message; Spotify Premium is required.
To replace saved credentials that stopped working, sign in again with the same
account.

> [!WARNING] Spotify has restriced API calls, be careful of the delay time, also some new accounts report to have basically no API call at all, so results may vary.

The companion helper is deprecated, and its `/companion` folder is no longer in this repository.


### Spotify Dev WebAPI credentials

Spotify needs a Spotify Developer app:

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Copy its Client ID and Client Secret into **Settings → API config**.
3. Save the configuration.

These credentials identify the developer app; they do not sign in a Spotify
worker.

OnTheSpot reads playlists through the signed-in Spotify worker, so public
playlists, playlists made by Spotify and your own private playlists all load.
It then fetches each track's details with these credentials, so a large
playlist makes many Web API calls. If Spotify starts to refuse requests,
turn off metadata options you do not need in **Settings**.

Local files in a playlist are skipped. Liked Songs and Your Episodes are not
supported: OnTheSpot refuses those links and tells you why.

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
- If the Spotify sign-in fails, check that the account has Premium and that the
  code was entered before it expired. Start a new sign-in to get a new code.
- A Spotify account that is not Premium (including one whose Premium lapsed)
  is rejected. The account list does not mark it yet; the server log names the
  account type. Downloads use another Premium account if one is set up. Log in
  again after you upgrade the account.
- Use **Diagnostics**, **Notification history**, and **Server logs** for the
  exact backend error before retrying or changing credentials.
