class TrackUnavailableError(Exception):
    """Raised when a track has no playable version (not a connection issue)."""


class DownloadCancelled(Exception):
    """Raised when user cancels the download"""

class SpotifyPlaylistUnavailableError(Exception):
    """Raised when a Spotify playlist cannot be loaded."""

class SpotifyAPIUnavailableError(Exception):
    """Raised when Spotify API is unavailable (connection issue)."""


class UnsupportedItemError(Exception):
    """Raised when a recognised URL points to something OnTheSpot cannot download."""


class QueueFullError(Exception):
    """Raised when a new item is refused because the queue reached max_queue_size."""
