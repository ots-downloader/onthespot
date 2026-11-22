"""
api/metadata_enrichment.py
~~~~~~~~~~~~~~~~~~~~~~~~~~

Registry for optional metadata providers that enrich the dict returned by a
service's ``*_get_track_metadata`` call.

Providers are service-agnostic: they receive the metadata dict (and the queue
item as a fallback) regardless of which service produced it. Each provider has
its own enable/disable config key, and any provider error is logged as a
warning and ignored so downloads are never blocked by optional enrichment.
"""

from collections.abc import Mapping

from ..otsconfig import config
from ..runtimedata import get_logger
from .itunes import itunes_get_metadata

logger = get_logger("api.metadata_enrichment")


def _itunes_options() -> dict:
    return {
        "overwrite": bool(config.get("itunes_metadata_overwrite", False)),
        "country": config.get("itunes_metadata_country", "US"),
    }


# name -> (config flag, callable, callable returning per-call options)
METADATA_ENRICHMENT_PROVIDERS = {
    "itunes": ("enable_itunes_metadata", itunes_get_metadata, _itunes_options),
}


def enrich_metadata(metadata, item=None, item_type: str = "track"):
    """Return *metadata* enriched by every enabled provider.

    Non-track items and disabled providers are ignored. The original object is
    returned untouched when no provider changes it or when a provider fails.
    """
    if item_type != "track" or not isinstance(metadata, Mapping):
        return metadata

    for name, (enabled_key, provider, options_fn) in METADATA_ENRICHMENT_PROVIDERS.items():
        if not config.get(enabled_key, False):
            continue
        try:
            enriched = provider(metadata, item, **options_fn())
            if not isinstance(enriched, Mapping):
                logger.warning("Metadata provider '%s' returned invalid data; keeping original metadata", name)
                continue
            metadata = dict(enriched)
        except Exception as exc:
            logger.warning("Metadata provider '%s' failed; keeping original metadata: %s", name, exc)

    return metadata
