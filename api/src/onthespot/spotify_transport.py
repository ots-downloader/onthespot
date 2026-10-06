"""Bound waits in the bundled librespot transport without abandoning threads."""

import threading

from requests.adapters import HTTPAdapter


_client_lock = threading.Lock()
# Bundled librespot shares the audio-key callback queue between requests.
# Serialize stream setup only; reading the resulting CDN streams stays parallel.
spotify_stream_lock = threading.Lock()


class SpotifyHTTPAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (10, 30)
        return super().send(request, **kwargs)


def bound_spotify_requests(token):
    client = token.client()
    if client is None:
        raise RuntimeError("Spotify session was closed; retry with the current session")
    with _client_lock:
        if not isinstance(client.get_adapter("https://"), SpotifyHTTPAdapter):
            client.mount("https://", SpotifyHTTPAdapter())
            client.mount("http://", SpotifyHTTPAdapter())


class SpotifyChunkCondition(threading.Condition):
    """librespot's predicate ignores failed chunks and stream closure."""

    def __init__(self, stream, timeout=60):
        super().__init__()
        self.stream = stream
        self.chunk_timeout = timeout

    def wait_for(self, predicate, timeout=None):
        ready = super().wait_for(
            lambda: predicate() or self.stream.closed or self.stream.chunk_exception is not None,
            timeout=self.chunk_timeout if timeout is None else min(timeout, self.chunk_timeout),
        )
        if self.stream.closed:
            raise OSError("Spotify stream closed while waiting for audio")
        if self.stream.chunk_exception is not None:
            raise OSError("Spotify audio chunk failed") from self.stream.chunk_exception
        if not ready:
            raise TimeoutError(f"Spotify audio stalled for {self.chunk_timeout} seconds")
        return True
