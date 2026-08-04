# Installation

OnTheSpot's production web build is a single application: one FastAPI process
serves the API and the compiled React UI on port `6767`.

## Docker Compose (recommended)

Requirements:

- Docker Engine or Docker Desktop with Docker Compose v2
- Enough free space for the selected media and config folders

Clone the repository and select this branch:

```bash
git clone --branch fastapi-dev --single-branch https://github.com/JamyPatch44/onthespot.git
cd onthespot
```

Copy the example environment file, review the paths, then build and start:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

PowerShell uses `Copy-Item .env.example .env` instead of `cp`.

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

The default `.env.example` stores data under `./otsdata`:

| Variable | Container destination | Contents |
| --- | --- | --- |
| `ONTHESPOT_MUSIC_DIR` | `/root/Music/OnTheSpot` | downloaded audio |
| `ONTHESPOT_VIDEO_DIR` | `/root/Videos/OnTheSpot` | downloaded video |
| `ONTHESPOT_CONFIG_DIR` | `/root/.config/onthespot` | settings, accounts, cached sessions, playlist automation, statistics, and uploaded YouTube cookies |
| `ONTHESPOT_WEB_PORT` | container port `6767` | host port used to open the application |

Back up the configured host folders, especially `ONTHESPOT_CONFIG_DIR`. API
credentials and account sessions are stored in that private folder, not in the
Git repository or Docker image.

## Unraid

Use absolute Unraid paths in `.env`, for example:

```dotenv
ONTHESPOT_WEB_PORT=6769
ONTHESPOT_MUSIC_DIR=/mnt/user/Music/OnTheSpot
ONTHESPOT_VIDEO_DIR=/mnt/user/Videos/OnTheSpot
ONTHESPOT_CONFIG_DIR=/mnt/user/appdata/onthespot
```

Then run `docker compose up -d --build` and open
`http://UNRAID-IP:6769`. The default Compose deployment uses bridge networking
and exposes only the web port.

Spotify Connect discovery does not cross Docker bridge, VPN, or routed-network
boundaries. To add a Spotify worker when Spotify is running on another
computer, open **Accounts → Add account → Spotify → Remote access** and follow
the generated companion instructions. The helper runs beside Spotify for the
one-time pairing and removes itself when `--cleanup` is used.

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

Preserve the configured volume folders, pull the branch, and rebuild:

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
| UI opens but requests fail | Use the same origin that served the page; do not configure a separate API URL for production |
| Spotify worker is not visible | Use the generated companion when Spotify and Docker are not on the same LAN broadcast domain |
| Playlist OAuth returns elsewhere | Save the exact callback currently shown in Playlist sorting and in the Spotify Developer Dashboard |
| YouTube asks for sign-in | Upload a fresh Netscape-format `cookies.txt` through the YouTube Music account setup; browser-profile import only works when the browser runs on the API host |
| Settings disappear after rebuild | Confirm `ONTHESPOT_CONFIG_DIR` is an existing persistent host path mounted at `/root/.config/onthespot` |
