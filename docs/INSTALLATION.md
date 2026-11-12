# Installation

OnTheSpot's production web build is a single application: one FastAPI process
serves the API and the compiled React UI on port `6767`.

## Docker Compose (recommended)

Requirements:

- Docker Engine or Docker Desktop with Docker Compose v2
- Enough free space for the selected media and config folders

Make a folder, download `compose.yml` into it, and start:

```bash
mkdir onthespot
cd onthespot
curl -LO https://raw.githubusercontent.com/ots-downloader/onthespot/fastapi-dev/compose.yml
docker compose up -d
docker compose ps
```

In Windows PowerShell, type `curl.exe` instead of `curl`.

Compose pulls the published image. On first start the container makes the
`otsdata` folders next to `compose.yml` and makes sure user and group `1000`
can write to them. A `.env` file is optional; every setting has a default.

Open `http://127.0.0.1:6767` on the Docker host, or
`http://SERVER-IP:6767` from another device on the same private network. API
documentation is available at `/docs` on the same address.

Follow startup logs with:

```bash
docker compose logs -f onthespot
```

Stop the container without deleting persisted data:

```bash
docker compose down
```

### Persistent folders

By default, data is stored under `./otsdata`. To use other folders, create a
`.env` file next to `compose.yml` and set the paths there.
[`.env.example`](../.env.example) lists every value. To start from it, download
it as `.env`:

```bash
curl -L -o .env https://raw.githubusercontent.com/ots-downloader/onthespot/fastapi-dev/.env.example
```

The folder variables are:

| Variable | Container destination | Contents |
| --- | --- | --- |
| `ONTHESPOT_MUSIC_DIR` | `/root/Music/OnTheSpot` | downloaded audio |
| `ONTHESPOT_VIDEO_DIR` | `/root/Videos/OnTheSpot` | downloaded video |
| `ONTHESPOT_CONFIG_DIR` | `/root/.config/onthespot` | settings, accounts, cached sessions, playlist automation, statistics, and uploaded YouTube cookies |
| `ONTHESPOT_WEB_PORT` | container port `6767` | host port used to open the application |

Back up the configured host folders, especially `ONTHESPOT_CONFIG_DIR`. API
credentials and account sessions are stored in that private folder, not in the
Git repository or Docker image.

### Other settings

Set these in `.env` as well:

| Variable | Default | Use |
| --- | --- | --- |
| `PUID` | `1000` | user ID the app runs as; it must be able to write to the data folders |
| `PGID` | `1000` | group ID the app runs as |
| `ONTHESPOT_IMAGE` | `moddroid94/ots-dl:latest` | image to run |
| `ONTHESPOT_BGUTIL_URL` | blank | URL of the bgutil PO token server for YouTube Music; blank means the `bgutil-provider` service in `compose.yml` |

On each start the container checks that the app user (`PUID:PGID`) can write
to each data folder. A folder it can already write to is left alone. If it
cannot, the container changes the owner of the config folder, with its
contents, and of the top music and video folders only, never the files inside
your library. If that fails, for example on some network shares, the container
logs a warning and starts anyway. A container started with `user:` in your own
compose file, or with `docker run --user`, skips this step.

With rootless Docker or Podman, set `PUID=0` and `PGID=0`, because root in the
container is already your own user.

### Images

| Image | Tags |
| --- | --- |
| `moddroid94/ots-dl` (Docker Hub) | the version on each release; `latest` on each full release (not a pre-release) |
| `ghcr.io/ots-downloader/onthespot` | the version on each release; `latest` on each full release (not a pre-release); `edge` on each push to `fastapi-dev` |

Both are built for `linux/amd64` and `linux/arm64`. To run the newest
development build, set `ONTHESPOT_IMAGE=ghcr.io/ots-downloader/onthespot:edge`.

### Build the image from source

A clone of the repository has a `compose.override.yml` file, which Compose
loads by itself, so the usual command builds the image from your checkout:

```bash
git clone --branch fastapi-dev --single-branch https://github.com/ots-downloader/onthespot.git
cd onthespot
docker compose up -d --build
```

Building needs BuildKit, the default in Docker Engine 23+ and Compose v2. To
run the published image from a clone instead, use
`docker compose -f compose.yml up -d`.

## Unraid

Put `compose.yml` in its own folder as above, and use absolute Unraid paths in
a `.env` file next to it, for example:

```dotenv
PUID=99
PGID=100
ONTHESPOT_WEB_PORT=6769
ONTHESPOT_MUSIC_DIR=/mnt/user/Music/OnTheSpot
ONTHESPOT_VIDEO_DIR=/mnt/user/Videos/OnTheSpot
ONTHESPOT_CONFIG_DIR=/mnt/user/appdata/onthespot
```

`PUID=99` and `PGID=100` are Unraid's usual `nobody:users`.

Then run `docker compose up -d` and open
`http://UNRAID-IP:6769`. The default Compose deployment uses bridge networking
and exposes only the web port.

To add a Spotify account, open **Accounts → Add account → Spotify** and choose
**Sign in with Spotify**. OnTheSpot shows a short code and a link. On any
device, open https://spotify.com/pair, enter the code, and approve the
sign-in. OnTheSpot then stores the account. This works in Docker, on Unraid, and
over Tailscale or any remote setup. It needs no open port and no helper script.
The account must be Spotify Premium. To replace saved credentials that no
longer work, sign in again with the same account.

The older "Remote access" companion option is deprecated. It still works in this
release and goes away in the next one.

Playlist sorting uses Spotify OAuth, which is separate from the download
worker login. Local installations can use the displayed `127.0.0.1` callback.
A remotely opened installation needs a private HTTPS address or HTTPS reverse
proxy; enter the exact callback shown by OnTheSpot in the Spotify Developer
Dashboard. Do not make the whole application public merely to complete OAuth.

## Run the production build from source

Requirements:

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 with npm
- FFmpeg available on `PATH`

Build the UI and start the same single-process server used by Docker:

```bash
cd ui
npm ci
npm run build
cd ..
uv run --project api uvicorn onthespot.main:app --app-dir api/src --host 127.0.0.1 --port 6767
```

Open `http://127.0.0.1:6767`.

On Windows, settings are stored under `%APPDATA%\onthespot` and media defaults
to the current user's Music and Videos folders. On Linux, settings default to
`~/.config/onthespot`.

## Frontend development

Run the backend command above, then start Vite in a second terminal:

```bash
cd ui
npm ci
npm run dev
```

The development UI opens on port `3000` and talks to the API on port `6767`.
The production Docker image does not run Vite and does not require a separate
frontend port.

## Updating

Keep the configured data folders, pull the new image, and restart:

```bash
docker compose pull
docker compose up -d
```

If you build from source, pull the branch and rebuild instead:

```bash
git pull --ff-only
docker compose up -d --build
```

The bundled application version replaces stale version values from older
config volumes during startup.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Container is unhealthy | `docker compose logs onthespot`; confirm port 6767 is not already in use and the config folder is writable |
| Permission errors in the data folders | `docker compose logs onthespot` for a "not writable" warning; set `PUID` and `PGID` to the host user that owns the folders |
| UI opens but requests fail | Use the same origin that served the page; do not configure a separate API URL for production |
| Spotify worker is not visible | Use **Sign in with Spotify** in Accounts; enter the code at spotify.com/pair on any device |
| Playlist OAuth returns elsewhere | Save the exact callback currently shown in Playlist sorting and in the Spotify Developer Dashboard |
| YouTube asks for sign-in | Upload a fresh Netscape-format `cookies.txt` through the YouTube Music account setup; browser-profile import only works when the browser runs on the API host |
| Settings disappear after rebuild | Confirm `ONTHESPOT_CONFIG_DIR` is an existing persistent host path mounted at `/root/.config/onthespot` |
