#!/bin/sh
# Container entrypoint for OnTheSpot.
#
# Started as root (the default): make the data folders, make sure
# PUID:PGID (default 1000:1000) can write to them, then drop root and run
# the app as that user. Started as any other user (compose `user:` or
# `docker run --user`): run the app as it is and touch nothing.
set -e

if [ "$(id -u)" != "0" ]; then
    exec "$@"
fi

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

for value in "$PUID" "$PGID"; do
    case "$value" in
        *[!0-9]*)
            echo "entrypoint: PUID and PGID must be numbers, got PUID=$PUID PGID=$PGID" >&2
            exit 1
            ;;
    esac
done

warn() { echo "entrypoint: warning: $*" >&2; }
as_app() { setpriv --reuid "$PUID" --regid "$PGID" --clear-groups "$@"; }

CONFIG_DIR="${ONTHESPOTDIR:-/root/.config/onthespot}"
CACHE_DIR="${ONTHESPOTCACHEDIR:-/root/.config/onthespot/cache}"
MUSIC_DIR=/root/Music/OnTheSpot
VIDEO_DIR=/root/Videos/OnTheSpot

# 1. Make the four folders. A failure warns and does not stop the start.
for dir in "$CONFIG_DIR" "$CACHE_DIR" "$MUSIC_DIR" "$VIDEO_DIR"; do
    mkdir -p "$dir" 2>/dev/null || warn "could not create $dir"
done

# 2. /root is mode 700, so the app user must own the image's own parent
#    folders to reach the data folders. Not recursive.
chown "$PUID:$PGID" /root /root/Music /root/Videos /root/.config 2>/dev/null \
    || warn "could not change the owner of /root and its data parents"

# 3. Leave a folder alone when the app user can already write to it.
#    $2 is "-R" only for folders the app owns outright (config, cache).
#    Music and video get the top folder only: an existing library keeps
#    its owners.
ensure_writable() {
    as_app test -w "$1" && return 0
    chown $2 "$PUID:$PGID" "$1" 2>/dev/null || true
    as_app test -w "$1" \
        || warn "$1 is not writable by $PUID:$PGID; set PUID and PGID to the folder's owner"
}
ensure_writable "$CONFIG_DIR" -R
ensure_writable "$CACHE_DIR" -R
ensure_writable "$MUSIC_DIR"
ensure_writable "$VIDEO_DIR"

exec setpriv --reuid "$PUID" --regid "$PGID" --clear-groups "$@"
