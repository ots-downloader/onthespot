"""
accounts.py
~~~~~~~~~~~

Account pool management and token retrieval.

:class:`AccountPoolLoader` is a QThread that iterates the saved account list,
logs each one in via the appropriate service function, and emits progress
signals for the GUI.

:func:`get_account_token` returns a valid auth token for a given service,
optionally rotating to the next available account.
"""

from time import sleep
import threading

from .api.registry import SERVICE_LOGIN_FUNCTIONS, SERVICE_TOKEN_FUNCTIONS
from .otsconfig import config
from .runtimedata import get_logger, account_pool

logger = get_logger("accounts")

# Services that use no authentication token (return None from get_account_token)
_TOKENLESS_SERVICES = frozenset({"bandcamp", "youtube_music", "generic"})


class AccountPoolLoader:
    """Thread that authenticates every active account from the config.

    Emits :attr:`progress` for each account attempt and :attr:`finished` when
    all accounts have been processed.
    """

    def __init__(self, gui: bool = False) -> None:
        super().__init__()
        self.gui = gui
        self.is_running = True
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> None:
        logger.info("Starting AccountPool Worker")
        self.thread.start()

    def stop(self) -> None:
        logger.info("Stopping AccountPool Worker")
        self.is_running = False
        self.thread.join()

    def run(self) -> None:
        """Iterate saved accounts, log each one in, and emit progress."""
        for account in config.get("accounts"):
            service = account["service"]
            if not account["active"]:
                continue

            login_fn = SERVICE_LOGIN_FUNCTIONS.get(service)
            if login_fn is None:
                logger.warning(f"No login function registered for service '{service}'")
                continue

            login_succeeded = login_fn(account)
        if login_succeeded:
            logger.info("Logins Completed")


# Backwards-compatible alias used by the GUI code.
FillAccountPool = AccountPoolLoader


def get_account_token(service: str, rotate: bool = False):
    """Return an auth token for *service*.

    For services that require no token (bandcamp, youtube_music, generic)
    ``None`` is returned immediately.

    When *rotate* is ``False`` and the currently active account matches
    *service*, the token for that account is returned directly.  Otherwise
    the pool is scanned (round-robin from the current index) for the next
    matching account.

    Parameters
    ----------
    service:
        Service name string as stored in ``account_pool`` entries.
    rotate:
        If ``True``, always rotate to the next matching account even if the
        current one already matches.
    """
    if service in _TOKENLESS_SERVICES:
        return None

    token_fn = SERVICE_TOKEN_FUNCTIONS.get(service)
    if token_fn is None:
        logger.error(f"No token function registered for service '{service}'")
        return None

    current_index = config.get("active_account_number")

    # Fast path: current account matches and we don't want to rotate.
    if account_pool[current_index]["service"] == service and not rotate:
        return token_fn(current_index)

    # Scan the pool round-robin for the next matching account.
    pool_size = len(account_pool)
    for offset in range(1, pool_size + 1):
        index = (current_index + offset) % pool_size
        if account_pool[index]["service"] == service:
            if config.get("rotate_active_account_number"):
                logger.debug(
                    f"Rotating to {account_pool[index]['service']} account "
                    f"#{index}: {account_pool[index]['uuid']}"
                )
                config.set("active_account_number", index)
                config.save()
            return token_fn(index)

    return None
