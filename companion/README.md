# OnTheSpot Spotify companion

Use this when the OnTheSpot API runs remotely (for example, in Docker on
Unraid) but Spotify runs on a desktop or phone on the local LAN.

This is a small helper for the Spotify computer. Do **not** run it inside the
OnTheSpot Docker container: the container cannot receive Spotify's local mDNS
discovery from a different network. Run it on the Windows, macOS, or Linux
computer where Spotify is open.

The companion runs Spotify Connect discovery locally, so Spotify can find it.
After the user selects it, the companion sends the one-time login payload to
the OnTheSpot URL over HTTPS or Tailscale. The Spotify credentials are not
printed or stored on the remote server until pairing succeeds.

## Windows

From the repository root:

```powershell
py -m venv .companion-venv
.\.companion-venv\Scripts\python.exe -m pip install -r companion\requirements.txt
.\.companion-venv\Scripts\python.exe companion\run.py `
  --server-url https://your-onthe-spot-url.example `
  --pairing-token YOUR_ONE_TIME_TOKEN
```

The command is also shown in Playlist Sorting after selecting Remote access
and creating a companion pairing code.

## Linux/macOS

```bash
python3 -m venv .companion-venv
. .companion-venv/bin/activate
python -m pip install -r companion/requirements.txt
python companion/run.py \
  --server-url https://your-onthe-spot-url.example \
  --pairing-token YOUR_ONE_TIME_TOKEN
```

The pairing token expires after ten minutes and can only be used once. The
desktop and Spotify must be on the same LAN; Tailscale carries the API request
but does not carry Spotify's mDNS discovery packets.
