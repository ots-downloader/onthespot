# Release feature matrix

This matrix tracks the `fastapi-dev` web application. It separates behaviour
verified in this repository from behaviour that depends on a third-party
account, catalogue, or network response.

Status meanings:

- **Verified** — exercised by an automated test, a successful production
  build, or a live local workflow during the release audit.
- **Implemented** — wired through the UI and API, with contract coverage, but
  not exercised against every external provider in this environment.
- **Conditional** — implemented correctly but requires an external account,
  subscription, session, HTTPS callback, or provider availability.

## Application and deployment

| Area | Status | Evidence / notes |
| --- | --- | --- |
| FastAPI serves the compiled React UI and API from one process | Verified | Production UI build succeeds; deployment-contract tests assert the Docker build stages and Uvicorn command. |
| Windows source startup | Verified | Local production build served successfully on `127.0.0.1:6767`. |
| Docker/Compose bridge deployment | Implemented | Static deployment-contract tests validate portable port and volume mappings; the CI workflow performs a real image build after publication because Docker is not available on the audit host. |
| Unraid persistence layout | Implemented | Compose uses configurable media/config bind mounts; restart-persistence tests prove settings and playlist state survive a new process. A real Unraid image pull remains a post-publication deployment check. |
| Secrets excluded from public config/API/build context | Verified | Config redaction, `.dockerignore`, and deployment tests cover credentials and runtime data. |
| Health and diagnostics endpoints | Verified | Smoke tests cover core reads; live UI connected to the local service. |

## Accounts and authentication

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Account add/remove/reconnect UI and API | Implemented | Frontend/API route contract is complete; service-specific validation is present. |
| Spotify worker, local Connect discovery | Conditional | Lifecycle tests cover clean thread/port shutdown; live pairing requires Premium and same-LAN Spotify Connect discovery. |
| Spotify worker, remote companion | Conditional | Pairing, expiry, server completion, automatic modal close, and cleanup command are implemented; requires a reachable server URL and a companion beside Spotify. |
| Spotify API Client ID/Secret | Verified | Saved settings are redacted from public config and survive restart. |
| Playlist sorting Spotify OAuth | Verified | Local loopback callback normalization, insecure-LAN rejection, saved authorization reuse, and a live signed-in local session were verified. Remote use requires HTTPS. |
| YouTube cookie upload | Verified | Tests reject invalid exports, retain only YouTube/Google cookie domains, store managed state privately, and avoid browser-database scanning. |
| Apple Music, Crunchyroll, Deezer, Qobuz, Tidal logins | Conditional | Service-specific forms and backend workers are wired; end-to-end success depends on valid external accounts and provider behaviour. |
| Bandcamp, Generic, SoundCloud public workers | Implemented | Workers are available without mandatory credentials; SoundCloud token remains optional for account-specific access. |

## Search and catalogue

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Select one or multiple search services | Verified | Live UI selection and API tests confirm the exact selected providers are requested. |
| Multi-provider result visibility | Verified | Provider batches are round-robin interleaved; regression coverage plus a live search showed 40 SoundCloud and 36 Spotify results with alternating first cards. |
| Bandcamp catalogue search | Verified | Uses Bandcamp's current JSON catalogue endpoint; live checks returned tracks, albums, and artists. |
| YouTube catalogue search | Verified | Uses yt-dlp catalogue search and falls back to public search when a configured browser-cookie source is locked or unavailable on the server. |
| Per-provider result counts | Verified | Live result header displayed service totals. |
| Provider failure isolation | Verified | Search orchestration returns successful providers without failing the entire request. |
| Provider/media-type compatibility | Verified | Tests ensure unsupported categories are not sent to a provider. |
| Direct URL parsing and enqueue | Implemented | UI/API route contract is complete; actual extraction depends on URL/provider support. |
| Spotify public response cache | Verified | Disk reuse, concurrent request coalescing, private-route allowlist, and global disable behaviour have automated coverage. |
| Playlist sorting cache | Implemented | Per-account playlist cache and configurable TTL are exposed; mutation paths invalidate relevant data. |

## Download queue and media

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Queue state, pause/resume, retry, clear, cancel | Implemented | API/UI contract coverage; actions update shared queue state. |
| Batch selection and actions | Implemented | Pause, resume, retry, cancel, delete, priority, and profile actions are wired. |
| Drag reorder | Implemented | Waiting-item reorder endpoint and UI drag handling are present. |
| Download profiles | Verified | Active profile changes are persisted and reflected in UI state. |
| Playlist expansion and overall progress | Implemented | Playlist items are represented individually with aggregate progress and collapsible track details. |
| Speed, ETA, size, and service labels | Implemented | UI displays values when emitted by the worker and avoids `NaN` placeholders. |
| File verification and retry | Implemented | Queue/library verification endpoints and requeue actions are available. |
| Actual media extraction/conversion | Conditional | Requires a valid service worker, reachable provider, FFmpeg, and authorization for the requested media. |

## Local library

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Scan, search, sort, reverse, and filters | Implemented | UI and API support format, artist, genre, date, duplicate, artwork, and metadata filters. |
| Artwork read/update | Implemented | Dedicated cover read/write routes and UI actions are wired. |
| Play/open folder/rename/delete | Implemented | File actions are validated against indexed paths; rename and index updates are handled together. |
| Metadata editor | Implemented | Artist, album artist, genre, track number, lyrics, release date, and related fields are supported by the editor/API. |
| Missing-file handling | Implemented | Verify, per-entry removal, clear-all, and re-download from a saved source are available. |
| M3U creation | Implemented | Filtered library entries can be written to a local playlist file. |

## Playlist sorting and automation

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Rule ordering by drag handles | Implemented | Rules persist in explicit priority order. |
| Duplicate management | Implemented | Release-date and playlist-order retention choices are available with review before apply. |
| Version replacement | Conditional | Same-artist/global search and oldest/newest preferences are implemented; candidate quality depends on Spotify catalogue data. |
| Dynamic playlists | Implemented | Source/target trees, filters, update modes, local-file preservation, reorder, create/edit/delete, and run-all are wired. |
| Schedules | Implemented | Daily, weekday, weekly, and monthly schedules persist and can target a config or run-all. |
| Review/apply changes | Implemented | Proposed duplicate removals and replacements can be approved individually before mutation. |
| Compare playlists | Implemented | Shared tracks, per-playlist removal, and CSV export are wired. |
| Backup/restore and export folders | Verified | Configured destinations persist; API/UI write, list, restore, and open-folder paths are connected. |
| History/undo, ignored tracks, debug log | Implemented | CRUD and restore routes are present with corresponding UI workflows. |

## Settings, appearance, and observability

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Reorderable navigation/settings sections | Implemented | Browser-local ordering and edit modes are available. |
| Light/dark themes, presets, custom saved themes | Verified | Production build and theme state paths pass lint/build; custom palettes are included in backup. |
| Bundled locale files | Verified | Locale generation/build validates all bundled JSON resources. Untranslated strings fall back to English. |
| Statistics and clear action | Implemented | Summary/history API and clear confirmation are wired. |
| Diagnostics, rate-limit state, notifications, logs | Implemented | Live status routes and UI panels are connected; user-visible errors are retained in notification history. |
| Update check/install controls | Conditional | Feed check is implemented; installation depends on deployment permissions and release source. |

## Current external limitations

- Provider APIs, catalogues, authentication formats, and anti-bot checks can
  change independently of OnTheSpot.
- Spotify local Connect discovery does not traverse Docker bridge, routed VPN,
  or internet boundaries; remote installations use the companion beside the
  Spotify app.
- Spotify OAuth callbacks on remote installations require an HTTPS address
  accepted by Spotify.
- YouTube may invalidate cookies or require a fresh browser session.
- A provider-dependent row is not considered an application P0/P1 defect when
  the external prerequisite is unavailable and the app reports it accurately.

## Validation commands

```powershell
uv run --project api --with pytest pytest api\tests -q
uvx ruff check api\src api\tests
cd ui
npm ci
npm run lint
npm run build
```

The GitHub Actions workflow repeats backend checks on Linux and Windows,
validates frontend locales/build/audit, and builds the production Docker image.
