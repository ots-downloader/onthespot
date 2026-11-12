<div align="center">

<div style="text-align: center;">
  <picture>
    <img src="assets/logos/repository_logo.png" alt="Repository Logo" width="350px">
  </picture>
</div>

[![Issues Badge][issues-shield]][issues-url]
[![Stars Badge][stars-shield]][stars-url]
[![Downloads Badge][downloads-shield]][downloads-url]
[![License Badge][license-shield]][license-url]

   <p>
      Welcome to OnTheSpot!
      <br />
      <a href="https://discord.gg/GCQwRBFPk9">Join Discord</a>
      ·
      <a href="https://github.com/ots-downloader/onthespot/issues/new?assignees=&labels=bug&projects=&template=bug-report.yml">Report Bug</a>
      ·
      <a href="https://github.com/ots-downloader/onthespot/issues/new?assignees=&labels=enhancement&projects=&template=feature_request.yml">Request Feature</a>
   </p>
   <br>
</div>

This branch provides OnTheSpot as a single-process web application: FastAPI
serves both the API and the compiled Web UI on port `6767`. 


Quick start with Docker Compose:

```bash
mkdir onthespot
cd onthespot
curl -LO https://raw.githubusercontent.com/ots-downloader/onthespot/fastapi-dev/compose.yml
docker compose up -d
```

In Windows PowerShell, type `curl.exe` instead of `curl`.

Open `http://127.0.0.1:6767`, or the mapped address of the Docker/Unraid host.
See the installation guide before deploying so media, configuration, account
sessions, and playlist automation are stored in persistent folders.

Documentation:

1. [**Installation Guide**](docs/INSTALLATION.md)
2. [**Basic Usage Instructions**](docs/USAGE.md)

### Adding a Spotify account

OnTheSpot signs in to Spotify by itself. Open **Accounts → Add account →
Spotify** and choose **Sign in with Spotify**. OnTheSpot shows a short code and
a link. On any device, such as your phone or laptop, open
https://spotify.com/pair, enter the code, and approve the sign-in. This works
in Docker, on Unraid, and over Tailscale or any other remote setup. It needs no
open port, no helper script, and no Spotify developer app. The account must be
Spotify Premium. The older Spotify Connect companion is deprecated,
and its helper script is no longer in this repository.

> [!CAUTION]
> Currently 1 user has reported having their Spotify account locked, the account was returned to them by emailing support. This notice will be updated if any further cases come to our attention.

## Screenshots

![Search](assets/images/search.png)
![Download Queue](assets/images/download_queue.png)
![Settings](assets/images/settings.png)

## Need More Help?

If you have any questions or run into issues while using OnTheSpot, feel free to ask for assistance by:

- [**Opening an Issue**](https://github.com/ots-downloader/onthespot/issues)
- [**Joining Our Discord**](https://discord.gg/GCQwRBFPk9)

## Contributing

If you encounter bugs, have suggestions, or would like to help translate the app to your native language don't hesitate to [**open an issue**](https://github.com/ots-downloader/onthespot/issues) or submit a pull request.

## Disclaimer

OnTheSpot is intended to be used in compliance with DMCA, Section 1201, for educational, private and fair use.
OnTheSpot contributors are not responsible for any misuse of the program or source code.

For further information, please see the following [**disclaimer**](DISCLAIMER.md).

<!-- Issues Badge -->

[issues-shield]: https://img.shields.io/github/issues/ots-downloader/onthespot?style=flat&label=Issues&labelColor=001224&color=1DB954
[issues-url]: https://github.com/ots-downloader/onthespot/issues

<!-- Stars Badge -->

[stars-shield]: https://img.shields.io/github/stars/ots-downloader/onthespot?style=flat&label=Stars&labelColor=001224&color=1DB954
[stars-url]: https://github.com/ots-downloader/onthespot/stargazers

<!-- Downloads Badge -->

[downloads-shield]: https://img.shields.io/github/downloads/ots-downloader/onthespot/total.svg?style=flat&label=Downloads&labelColor=001224&color=1DB954
[downloads-url]: https://github.com/ots-downloader/onthespot/releases/

<!-- License Badge -->

[license-shield]: https://img.shields.io/github/license/justin025/onthespot?style=flat&label=License&labelColor=001224&color=1DB954
[license-url]: https://github.com/ots-downloader/onthespot/blob/main/LICENSE
