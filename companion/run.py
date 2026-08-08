"""Run the OnTheSpot Spotify Connect companion on the Spotify user's LAN.

The companion keeps the ZeroConf/mDNS part local to the desktop or home LAN
and forwards only the short-lived pairing payload to the remote OnTheSpot API.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

# librespot currently ships protobuf files generated for the compatibility
# runtime. Set this before importing librespot so a fresh companion venv works
# with both older and newer protobuf package versions.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

import requests
import librespot.zeroconf as librespot_zeroconf
from librespot.zeroconf import ZeroconfServer

# Carrier-grade NAT. Tailscale hands out addresses from this range, and the
# setup docs recommend Tailscale, but Python does not treat it as private.
_CGNAT_V4 = ipaddress.ip_network("100.64.0.0/10")


class InsecureServerURL(Exception):
    """Raised when --server-url would send the login payload in the clear."""


def _is_trusted_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when *address* cannot leave the local network."""
    if address.is_loopback or address.is_private or address.is_link_local:
        return True
    return address.version == 4 and address in _CGNAT_V4


def validate_server_url(raw_url: str, allow_insecure: bool = False) -> str:
    """Return *raw_url* trimmed, refusing plain HTTP to a non-local host.

    The companion posts a reusable Spotify login blob to this URL, so the one
    thing it must not do is send it over the open internet unencrypted. HTTPS
    is always accepted. Plain HTTP is accepted only when the host resolves
    entirely to loopback, private, link-local or CGNAT addresses.

    A hostname that cannot be resolved is rejected rather than assumed local,
    so a typo or a dead DNS entry fails loudly instead of leaking credentials.
    """
    url = raw_url.strip().rstrip("/")
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise InsecureServerURL(
            f"--server-url must be an http or https URL, got {parsed.scheme or url!r}"
        )
    if not parsed.hostname:
        raise InsecureServerURL(f"--server-url has no host: {raw_url!r}")
    if parsed.scheme == "https":
        return url
    if allow_insecure:
        print(
            "Warning: sending the Spotify login over plain HTTP because "
            "--allow-insecure was passed.",
            file=sys.stderr,
            flush=True,
        )
        return url

    host = parsed.hostname
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {
                ipaddress.ip_address(info[4][0])
                for info in socket.getaddrinfo(host, parsed.port or None)
            }
        except (socket.gaierror, ValueError) as exc:
            raise InsecureServerURL(
                f"Refusing plain HTTP to {host!r}: the name could not be resolved "
                f"({exc}), so it cannot be confirmed as local. Use https, or pass "
                f"--allow-insecure if you are certain the network is trusted."
            ) from exc

    if addresses and all(_is_trusted_address(address) for address in addresses):
        return url

    raise InsecureServerURL(
        f"Refusing to send the Spotify login to {host!r} over plain HTTP. "
        f"Use an https URL, a loopback/LAN address, or Tailscale. "
        f"Pass --allow-insecure to override."
    )


def choose_interface(configured: str | None) -> str | None:
    if configured:
        return configured.strip() or None
    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        candidates = []
    usable: list[str] = []
    for value in candidates:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if not address.is_private or address.is_loopback or address.is_link_local:
            continue
        # Do not advertise common Docker/Hyper-V/Tailscale addresses when a
        # normal private LAN address is available.
        if str(address).startswith("172.17.") or str(address).startswith("192.168.56."):
            continue
        if address not in usable:
            usable.append(str(address))
    if usable:
        return next((value for value in usable if value.startswith("192.168.")), usable[0])

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def choose_available_port(preferred: int, attempts: int = 32) -> int:
    """Return the preferred local TCP port or the next available one.

    A previous companion can still be shutting down when a user retries the
    pairing flow. Scanning a small consecutive range avoids a Windows
    ``WinError 10048`` without terminating an unrelated process.
    """
    if preferred < 1 or preferred > 65535:
        raise ValueError("The companion port must be between 1 and 65535.")

    final_port = min(65535, preferred + max(1, attempts) - 1)
    for candidate in range(preferred, final_port + 1):
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("0.0.0.0", candidate))
        except OSError:
            continue
        finally:
            probe.close()
        return candidate

    raise OSError(
        f"No available Spotify Connect port was found between {preferred} and {final_port}."
    )


def create_server(name: str, port: int, state_file: Path, interface: str | None):
    ZeroconfServer._ZeroconfServer__default_get_info_fields["clientID"] = "65b708073fc0480ea92a077233ca87bd"
    builder = ZeroconfServer.Builder()
    builder.device_name = name
    builder.set_listen_port(port)
    builder.conf.stored_credentials_file = str(state_file)

    original_zeroconf = librespot_zeroconf.zeroconf.Zeroconf
    original_hostname = ZeroconfServer.get_useful_hostname
    if interface:
        librespot_zeroconf.zeroconf.Zeroconf = lambda *args, **kwargs: original_zeroconf(
            *args, interfaces=[interface], **kwargs
        )
        ZeroconfServer.get_useful_hostname = lambda self: interface
    try:
        return builder.create()
    finally:
        librespot_zeroconf.zeroconf.Zeroconf = original_zeroconf
        ZeroconfServer.get_useful_hostname = original_hostname


def schedule_repository_cleanup() -> None:
    """Remove the one-shot cloned companion after this process exits.

    The cleanup is deliberately limited to a directory named
    ``OnTheSpot-companion`` so a user cannot accidentally delete an arbitrary
    working directory by enabling the one-shot cleanup option.
    """
    repository = Path(__file__).resolve().parents[1]
    if repository.name.lower() != "onthespot-companion":
        print("Cleanup skipped: the companion folder is not named OnTheSpot-companion.", flush=True)
        return

    process_id = os.getpid()
    if os.name == "nt":
        def powershell_literal(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"

        script = "\n".join(
            [
                "$target = " + powershell_literal(str(repository)),
                "$parent = " + str(process_id),
                "Set-Location -LiteralPath $env:TEMP",
                "while (Get-Process -Id $parent -ErrorAction SilentlyContinue) { Start-Sleep -Milliseconds 500 }",
                "Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue",
            ]
        )
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
            cwd=tempfile.gettempdir(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) | 0x00000008,
            close_fds=True,
        )
        return

    import shlex

    command = (
        f"while kill -0 {process_id} 2>/dev/null; do sleep 0.5; done; "
        f"rm -rf -- {shlex.quote(str(repository))}"
    )
    subprocess.Popen(
        ["sh", "-c", command],
        cwd=tempfile.gettempdir(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the OnTheSpot Spotify Connect companion")
    parser.add_argument("--server-url", required=True, help="HTTPS/Tailscale URL of the remote OnTheSpot server")
    parser.add_argument("--pairing-token", required=True, help="One-time token generated by Playlist Sorting")
    parser.add_argument("--interface", help="LAN IPv4 address to advertise; auto-detected by default")
    parser.add_argument(
        "--port",
        type=int,
        default=6768,
        help="Preferred local Spotify Connect HTTP port; the next available port is used automatically",
    )
    parser.add_argument(
        "--allow-insecure",
        action="store_true",
        help="Permit plain HTTP to a non-local host; sends the Spotify login unencrypted",
    )
    parser.add_argument("--name", default="OnTheSpot Companion", help="Name shown in Spotify Connect")
    parser.add_argument(
        "--state-file",
        default="",
        help="Local credential state path; defaults to the user's OnTheSpot companion directory",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the cloned OnTheSpot-companion folder after successful pairing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        server_url = validate_server_url(args.server_url, args.allow_insecure)
    except InsecureServerURL as exc:
        print(str(exc), file=sys.stderr, flush=True)
        return 1
    state_file = Path(args.state_file).expanduser() if args.state_file else Path.home() / ".onthespot" / "companion" / "spotify_connect_login.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        state_file.unlink()
    except FileNotFoundError:
        pass

    interface = choose_interface(args.interface)
    try:
        port = choose_available_port(args.port)
    except (OSError, ValueError) as exc:
        print(f"Could not select a Spotify Connect port: {exc}", file=sys.stderr, flush=True)
        return 1
    if port != args.port:
        print(f"Port {args.port} is already in use; using {port} instead.", flush=True)
    print(f"Starting {args.name} on {interface or 'all local interfaces'}:{port}", flush=True)
    print("Open Spotify → Connect to a device and select the companion.", flush=True)
    try:
        server = create_server(args.name, port, state_file, interface)
    except Exception as exc:
        print(f"Could not start Spotify Connect discovery: {exc}", file=sys.stderr, flush=True)
        return 1

    try:
        while not server.has_valid_session():
            time.sleep(1)
        deadline = time.time() + 10
        while not state_file.is_file() and time.time() < deadline:
            time.sleep(0.25)
        if not state_file.is_file():
            print("Spotify connected, but no login payload was written.", file=sys.stderr, flush=True)
            return 1
        with state_file.open("r", encoding="utf-8") as handle:
            login = json.load(handle)
        response = requests.post(
            f"{server_url}/accounts/spotify/companion/complete",
            json={"pairing_token": args.pairing_token, "login": login},
            timeout=30,
        )
        if not response.ok:
            print(f"OnTheSpot rejected the companion login: {response.text}", file=sys.stderr, flush=True)
            return 1
        print("Spotify account delivered to OnTheSpot successfully.", flush=True)
        if args.cleanup:
            print("Pairing complete. The temporary companion folder will be removed.", flush=True)
            schedule_repository_cleanup()
        return 0
    except KeyboardInterrupt:
        print("Stopped.", flush=True)
        return 130
    except (OSError, ValueError, requests.RequestException) as exc:
        print(f"Companion failed: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        try:
            server.close_session()
        except Exception:
            pass
        try:
            server.close()
        except Exception:
            pass
        # The login file contains the Spotify Connect credentials that were
        # just forwarded to OnTheSpot. It is only needed while this one-shot
        # pairing process is running, so do not leave it on the desktop.
        try:
            state_file.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"Warning: could not remove temporary login state: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
