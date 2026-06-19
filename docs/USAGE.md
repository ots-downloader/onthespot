# Usage Guide


## 1. Logging into your accounts
OnTheSpot supports various accounts and instructions for each are listed below, for further assistance please reach out for support on the community discord [here](https://discord.gg/GCQwRBFPk9).

- **Apple Music**: Enter your media-user-token. It can be obtained in chrome by logging into https://music.apple.com, pressing ctrl + shift + i to open inspect element, clicking the 'Application' or 'Storage' header, opening the music.apple.com cookie, and copying the media-user-token value. Please note a premium account is required to download music.

- **Bandcamp**: Bandcamp offers public downloads and does not require an account, simply click 'Add Bandcamp Account' and restart the app.

- **Deezer**: Paste your arl into the bar provided and click add account. To get your arl log into the deezer website, press ctrl + shift + i to open inspect element, navigate to the 'Application' or 'Storage' header, and open the www.deezer.com cookie. Your arl should be listed under one of the values provided.

- **Qobuz**: To login to your Qobuz account simply enter your email and password, and restart the app. If you would like to login using your user_auth_token you can append the following to the accounts section of your config file.
   ```python
   {
      # Random string of numbers and letters
      "uuid": "private_qobuz_1",
      "service": "qobuz",
      "active": true,
      "login": {
            # Email is not used during token logins
            "email": "email@example.com",
            # Password is not used during token logins
            "password": "n/a",
            "app_id": APP_ID,
            "app_secrets": [
               APP_SECRET
            ],
            "user_auth_token": USER_AUTH_TOKEN
      }
   }
   ```

- **Soundcloud**: Paste your oauth-token into the bar provided and click add account. To get your oauth-token log into the soundcloud website, press ctrl + shift + i to open inspect element, navigate to the 'Application' or 'Storage' header, and open the soundcloud.com cookie. Your oauth-token should be listed under one of the values provided.

- **Spotify**: Ensure that both OnTheSpot and the Spotify Desktop App are not restricted by a firewall or vpn so that they can communicate. Click add account and then head over to devices in the Spotify app. Under devices you should see 'OnTheSpot', select it. Once complete the app will prompt you to restart.

   > [!IMPORTANT]
   > **Spotify Web API credentials are strongly recommended** (and in practice
   > required if you hit rate limits). Spotify rate-limits the shared login that
   > OnTheSpot uses for its Web API (search and metadata) calls, returning
   > `HTTP 429` errors. Adding your own free Spotify app credentials runs those
   > calls on your own quota. If you leave the fields empty, OnTheSpot falls back
   > to the default shared login (which is frequently rate-limited):
   >
   > 1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and log in. Spotify's Feb 2026 Developer Mode rules may require a **Premium** account to create an app.
   > 2. Click **Create app**. Give it any name/description, set the **Redirect URI** to `http://127.0.0.1:8888/callback`, tick **Web API**, and save.
   > 3. Open the app's **Settings** and copy the **Client ID** and **Client Secret**.
   > 4. Add the credentials in OnTheSpot:
   >    - **Desktop GUI / Web UI:** go to **Settings → Spotify Web API Credentials**, paste both values, and **Save Settings**.
   >    - **CLI:** run `config set spotify_webapi_override_client_id <id>` then `config set spotify_webapi_override_client_secret <secret>`.
   >
   > These credentials are personal — do not share them. Leaving the fields empty
   > falls back to the default (rate-limited) login. This path covers search and
   > track/album/artist/playlist/podcast downloads; **Liked Songs** and **Your
   > Episodes** are not available through it, as the credentials have no access to
   > your private library.

- **Tidal**: The app will provide you a link, open the link and login in your browser.

- **Youtube Music**: Youtube Music offers public downloads and does not require an account, simply click 'Add Youtube Music Account' and restart the app.

- **Crunchyroll**: To login to your Crunchyroll account simply enter your email and password, and restart the app.

- **Generic Downloader**: Generic Downloader uses yt-dlp to rip any available music or videos from a given webpage. A list of supported services is available in the app or [here](https://github.com/yt-dlp/yt-dlp/tree/master/yt_dlp/extractor). Even if your given website is not listed the generic downloader may be able to rip media anyway, just paste your url in the search bar. To activate generic downloader simply click 'Add Generic Downloader'.


## 2. Searching and Downloading Music
The search bar is able to parse queries, urls, and text files.

If a query is provided, say 'Daft Punk' for instance, the app will provide results to the query seperated into categories: Tracks, Albums, Artists, Playlists, and depending on the music service Episodes, Podcasts, and Audiobooks.

If a url is provided the app will parse the url and immediately begin downloading.

If a file path is provided the app will parse each line in the file for urls beginning in either http:// or https:// and begin downloading the items listed.


## 4. Configuration

### General Settings
| **Option** | **Description** |
| ------ | ------ |
| **Theme** | Choose the application theme (`light` or `dark`). |
| **Explicit Label** | Customize how explicit content is labeled in file names and the app (default: 🅴). |
| **Download Buttons** | Adds extra functionalities to the download queue. |
| **Show Thumbnails In Search/Downloads**| Display thumbnails on respective page. |
| **Thumbnail Size**|Change the size of thumbnail icons. |
| **Max Search Results** | Limits the number of search results displayed for each media type (e.g., songs, albums). |
| **Disable Download Popups** | Disables pop-up messages while downloading items. |
| **Mirror Spotify Playback** | Download currently playing song on the selected Spotify account |
| **Windows 10 Explorer Thumbnails** | Embed thumbnails in a format that respects Windows 10 explorer and media player, this is an older format of ID3 and not widely supported. |
| **Close To Tray** | Close application to tray on exit. |
| **Check for Updates** | Automatically check for application updates. |
| **Illegal Character Replacement** | Replace illegal characters in the filepath with the value specified (e.g., `/`, `\`, `<`, `>`, `*`, etc.). |
| **Rotate Active Account** | Automatically rotate between added accounts for downloading to minimize the chance of hitting rate limits. |
| **Spotify Web API Credentials** | Optional (but recommended) Client ID / Client Secret from your own [Spotify Developer app](https://developer.spotify.com/dashboard). Spotify rate-limits the shared login, so supplying your own credentials runs search/metadata calls on your own quota. See the Spotify entry under [Logging into your accounts](#1-logging-into-your-accounts) for the full setup. |
| **Raw Media Download** | Downloads an unmodified file from whatever service is selected. With this enabled file conversion and the embedding of any metadata is skipped. Lyrics and cover art will still be downloaded. |
| **Download Delay (s)** | The time, in seconds, to wait before initiating the next download. Helps prevent rate limits. |
| **Download Delay Variance (±s)** | Random variance applied to the download delay. For example, with a delay of 60s and variance of 30s, each download will wait between 30–90 seconds. Set to 0 to disable. |
| **Download Chunk Size (b)** | The chunk size, in bytes, in which to download files. |
| **Maximum Queue Workers** | Set the maximum number of queue workers. Setting a higher number will queue songs faster, only change this setting if you know what you're doing. Changes to this setting require you to restart the app take effect. |
| **Maximum Download Workers** | Set the maximum number of download workers. Only change this setting if you know what you're doing. Changes to this setting require you to restart the app to take effect. |
| **Enable Retry Worker** | Creates a worker that automatically retries failed downloads after a specified amount of time. Changes to this setting require you to restart the app to take effect. |
| **Retry Delay (m)** | The time, in minutes, for the retry worker to wait before retrying failed items. |

### Audio Download Settings
| **Option** | **Description** |
| ------ | ------ |
| **Audio Download Path** | Root folder where all downloaded audio will be saved. |
| **Track/Episode Format** | Select the file format to output your downloaded tracks or podcasts (e.g. `mp3`, `m4a`, `flac`, `ogg`, `wav`). For a complete list of supported codecs please see the following [list](https://ffmpeg.org/ffmpeg-formats.html). |
| [**Track/Episode Path**](#media-path-format) | Customize the file naming pattern for tracks, episodes, and playlists using variables like `{artist}`, `{album}`, etc. |
| **Use Custom Playlist Path** | Enable the use of a custom path format for playlists. |
| [**Playlist Path**](#media-path-format) | Customize the file naming pattern for playlists using variables like `{artist}`, `{album}`, etc. |
| **Create M3U Files for Playlists** | If enabled create an M3U file for downloaded tracks in a playlist. |
| [**M3U Path**](#media-path-format) | Customize the download path of created M3U files using variables like `{artist}`, `{album}`, etc. |
| [**EXTINF Seperator**](#media-path-format) | M3U EXTINF metadata / list seperator. |
| [**EXTINF Path**](#media-path-format) | Customize the M3U EXTINF label using variables like `{artist}`, `{album}`, etc. |
| **Save Album Cover** | Save album cover as an image with a default format of cover.png |
| **Album Cover Format** | The image format to save album covers in (default: png) |
| **File Bitrate** | Set the bitrate of a converted file, default value is 320k. This setting is not respected by some lossless codecs, results may vary depending on your chosen filetype. |
| **File Hertz** | Set the hertz of a converted file, default value is 44100 |
| **Use Custom File Bitrate** | Use the user specified 'File Bitrate' field, if disabled the app will use the maximum value allowed by your account. |
| **Download Lyrics\*** | Enable downloading of lyrics for each track/episode. *This feature may require a premium account.* |
| **Download Synced Lyrics Only\*** | Only download synced lyrics for tracks. *This feature may require a premium account.*|
| **Save LRC File\*** | Save lyrics in an `.lrc` file alongside the track. *This feature may require a premium account.*|
| **Translate File Path** | Translate file paths into the application language. |

### Metadata Settings
| **Option** | **Description** |
| ------ | ------ |
| **Metadata Separator** | Set the separator for metadata fields with multiple values (default: `; `). |
| **Overwrite Existing Collection** | If a file already exists re-embed metadata in your selected format. |
| **Embed Metadata Tags** | Select which metadata tags to embed in downloaded files (e.g., `artist`, `album`, `year`, `lyrics`, etc.). |

### Video Download Settings
| **Option** | **Description** |
| ------ | ------ |
| **Video Download Path** | Root folder where all downloaded video will be saved. |
| **Movie/Episode Format** | Select the file format to output your downloaded movies or episodes (e.g. `mp4`, `mkv`). For a complete list of supported codecs please see the following [list](https://ffmpeg.org/ffmpeg-formats.html). |
| [**Movie/Episode Path**](#media-path-format) | Customize the file naming pattern for movies and episodes using variables like `{artist}`, `{album}`, etc. |
| **Preferred Video Resolution** | If available, videos downloaded  will use the resolution specified. |
| **Download Subtitles** | Specify whether you would like to download subtitles if available. |
| **Preferred Audio/Subtitle Language** | Preferred download language for the specified media format, formatted as en-US. Multiple languages can be added if seperated by a comma, (en-US, jp-JP)|
| **Download All Available Audio/Subtitles** | Download all available audio or subtitles for a given video. |

### Media Path Format

- **Customize File Names**
  - Define how downloaded media is named using variables enclosed in `{}`.

- **Universal Variables**
   | **Variable**      | **Description**                                     |
   | ----------------- | --------------------------------------------------- |
   | `{service}`       | The music service used to download your file.       |
   | `{service_id}`    | The track's native id on the selected music service.|
   | `{name}`          | Name of the track.                                  |
   | `{year}`          | Release year of the track.                          |
   | `{explicit}`      | Displays 'Explicit Label' if the song is marked explicit (default: 🅴). |

- **Audio Variables**
   | **Variable**      | **Description**                                     |
   | ----------------- | --------------------------------------------------- |
   | `{artist}`        | Name of the artist(s).                              |
   | `{album_artist}`  | Name of the album artist(s).                        |
   | `{album_type}`    | Name of the artist type (single, album, etc).       |
   | `{disc_number}`   | Disc number (if applicable).                        |
   | `{discccount}`    | Total number of discs in the album (if applicable). |
   | `{genre}`         | Genre of the song.                                  |
   | `{label}`         | Name of the record label.                           |
   | `{track_number}`  | Track number on the album.                          |
   | `{trackcount}`    | Total number of tracks in the album                 |
   | `{isrc}`          | ISRC of the currently playing track.                |
   | `{playlist_name}` | Name of the playlist (if part of a playlist).       |
   | `{playlist_owner}`| Name of the playlist owner (if part of a playlist). |
   | `{playlist_number}`| Item number in a playlist (if part of a playlist). |

- **Show Variables**
   | **Variable**      | **Description**                                     |
   | ----------------- | --------------------------------------------------- |
   | `{show_name}` | Name of the playlist (if part of a playlist).           |
   | `{season_number}`| Name of the playlist owner (if part of a playlist).  |
   | `{episode_number}`| Item number in a playlist (if part of a playlist).  |

> [!TIP]
> **Example:**
> Setting the format to `{artist} - {name}` will result in files named like `Artist Name - Song Title.mp3`.


## 6. Saving Your Configuration

- **Apply Changes**
  - After adjusting any settings, click the 'Save Settings' button to apply your changes. Some configuration changes may require restarting the app to take effect.
