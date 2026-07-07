class TrackUnavailableError(Exception):
    """Raised when a track has no playable version (not a connection issue)."""


class DownloadCancelled(Exception):
    """Raised when user cancels the download"""

class SpotifyPlaylistUnavailableError(Exception):
    """Raised when Spotify is unavailable (connection issue)."""

class SpotifyAPIUnavailableError(Exception):
    """Raised when Spotify API is unavailable (connection issue)."""