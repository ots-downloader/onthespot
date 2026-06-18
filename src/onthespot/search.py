"""
search.py
~~~~~~~~~

Search entry point used by both the GUI and the CLI.

:func:`get_search_results` handles three distinct input forms:

1. A plain URL — delegated to :func:`~onthespot.parse_item.parse_url`.
2. A local file path — each ``https://`` line is parsed in bulk.
3. A search query string — forwarded to the active service's search API.
"""

import os

from .accounts import get_account_token
from .api.registry import SERVICE_SEARCH_FUNCTIONS
from .otsconfig import config
from .parse_item import parse_url
from .runtimedata import account_pool, get_logger

logger = get_logger("search")


def get_search_results(
    search_term: str,
    content_types=None,
    filter_tracks: bool = True,
    filter_albums: bool = True,
    filter_artists: bool = True,
    filter_playlists: bool = True,
    search_prefix: str = "the",
):
    """Resolve *search_term* and return results appropriate for the active service.

    Parameters
    ----------
    search_term:
        A URL, a local file path containing one URL per line, or a plain
        search query string.
    content_types:
        Optional list of content type strings passed through to the service
        search function (e.g. ``["track", "album"]``).
    filter_tracks, filter_albums, filter_artists, filter_playlists:
        Spotify-specific result-type filters (ignored by other services).
    search_prefix:
        Spotify-specific query prefix (ignored by other services).

    Returns
    -------
    Search results from the service API, ``True`` if a URL/file was handled
    without producing a result set, or ``False`` on error / empty input.
    """
    if not account_pool:
        return None

    if not search_term:
        logger.warning("Returning empty data — search query is empty.")
        return False

    # --- URL input -----------------------------------------------------------
    if search_term.startswith("https://") or search_term.startswith("http://"):
        logger.info(f"Search term is a URL: {search_term}")
        result = parse_url(search_term)
        return False if result is False else True

    # --- Local file input (one URL per line) ---------------------------------
    if os.path.isfile(search_term):
        logger.info(f"Search term is a local file: {search_term}")
        with open(search_term, "r", encoding="utf-8") as link_file:
            for line in link_file:
                link = line.strip()
                if link.startswith("https://"):
                    logger.debug(f"Parsing link from file '{search_term}': {link}")
                    parse_url(link)
        return True

    # --- Plain text search ---------------------------------------------------
    logger.info(f"Text search for '{search_term}'")

    service = account_pool[config.get("active_account_number")]["service"]
    if service == "generic":
        return False

    token = get_account_token(service)
    search_fn = SERVICE_SEARCH_FUNCTIONS.get(service)

    if search_fn is None:
        logger.warning(f"No search function registered for service '{service}'")
        return False

    if service == "spotify":
        return search_fn(
            token,
            search_term,
            content_types,
            filter_tracks,
            filter_albums,
            filter_artists,
            filter_playlists,
            search_prefix,
        )

    return search_fn(token, search_term, content_types)
