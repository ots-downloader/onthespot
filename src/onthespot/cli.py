import os

# Required for librespot-python
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
import curses
import logging
import random
import threading
import time
import traceback
import argparse
from cmd import Cmd
from .accounts import FillAccountPool, get_account_token
from .api.apple_music import apple_music_get_track_metadata, apple_music_add_account
from .api.bandcamp import bandcamp_get_track_metadata, bandcamp_add_account
from .api.deezer import deezer_get_track_metadata, deezer_add_account
from .api.qobuz import qobuz_get_track_metadata, qobuz_add_account
from .api.soundcloud import soundcloud_get_track_metadata, soundcloud_add_account
from .api.generic import generic_get_track_metadata, generic_add_account
from .api.spotify import (
    MirrorSpotifyPlayback,
    spotify_new_session,
    spotify_get_track_metadata,
    spotify_get_podcast_episode_metadata,
)
from .api.tidal import (
    tidal_get_track_metadata,
    tidal_add_account_pt1,
    tidal_add_account_pt2,
)
from .api.youtube_music import (
    youtube_music_get_track_metadata,
    youtube_music_add_account,
)
from .api.crunchyroll import crunchyroll_get_episode_metadata, crunchyroll_add_account
from .downloader import DownloadWorker, RetryWorker
from .otsconfig import config_dir, config
from .parse_item import parsingworker, parse_url
from .runtimedata import (
    account_pool,
    pending,
    download_queue,
    download_queue_lock,
    pending_lock,
)
from .search import get_search_results

if not config.get("debug_mode"):
    logging.disable(logging.CRITICAL)
else:
    logger = logging.getLogger("cli")


def parse_args():
    parser = argparse.ArgumentParser(description="OnTheSpot CLI Downloader")
    parser.add_argument("--download", help="Parse and download the URL specified")
    args, unknown_args = parser.parse_known_args()

    if args.download:
        if not (
            args.download.startswith("http://") or args.download.startswith("https://")
        ):
            parser.error("Parameter --download only accept URLs.")

    return args


class QueueWorker(threading.Thread):
    def __init__(self):
        super().__init__()

    def run(self):
        while True:
            try:
                if pending:
                    local_id = next(iter(pending))
                    with pending_lock:
                        item = pending.pop(local_id)
                    token = get_account_token(item["item_service"])
                    item_metadata = globals()[
                        f"{item['item_service']}_get_{item['item_type']}_metadata"
                    ](token, item["item_id"])
                    if item_metadata:
                        with download_queue_lock:
                            download_queue[local_id] = {
                                "local_id": local_id,
                                "available": True,
                                "item_service": item["item_service"],
                                "item_type": item["item_type"],
                                "item_id": item["item_id"],
                                "item_status": "Waiting",
                                "file_path": None,
                                "item_name": item_metadata["title"],
                                "item_by": item_metadata["artists"],
                                "parent_category": item["parent_category"],
                                "playlist_name": item.get("playlist_name"),
                                "playlist_by": item.get("playlist_by"),
                                "playlist_number": item.get("playlist_number"),
                            }
                else:
                    time.sleep(0.2)
            except Exception as e:
                logger.error(
                    f"Unknown Exception for {item}: {str(e)}\nTraceback: {traceback.format_exc()}"
                )
                with pending_lock:
                    pending[local_id] = item


def main():
    args = parse_args()

    print("\033[32mLogging In...\033[0m\n", end="", flush=True)

    fill_account_pool = FillAccountPool()
    fill_account_pool.finished.connect(lambda: print("Finished filling account pool."))
    fill_account_pool.progress.connect(
        lambda message, status: print(f"{message} {'Success' if status else 'Failed'}")
    )
    fill_account_pool.start()

    thread = threading.Thread(target=parsingworker)
    thread.daemon = True
    thread.start()

    for i in range(config.get("maximum_queue_workers")):
        queue_worker = QueueWorker()
        queue_worker.start()

    for i in range(config.get("maximum_download_workers")):
        downloadworker = DownloadWorker()
        downloadworker.start()

    if config.get("enable_retry_worker"):
        retryworker = RetryWorker()
        retryworker.start()

    fill_account_pool.wait()

    if config.get("mirror_spotify_playback"):
        mirrorplayback = MirrorSpotifyPlayback()
        mirrorplayback.start()

    if args.download:
        failed_download = False
        print(f"\033[32mParsing URL: {args.download}\033[0m")
        parse_url(args.download)
        while not download_queue:
            time.sleep(1)

            while any(
                item["item_status"]
                not in ("Downloaded", "Already Exists", "Failed", "Unavailable")
                for item in download_queue.values()
            ):
                time.sleep(1)

            for item in download_queue.values():
                if item["item_status"] in ("Unavailable", "Failed"):
                    print(
                        f"\033[31mItem ID {item['item_id']} {item['item_status']}'\033[0m"
                    )
                    failed_download = True

        if failed_download:
            print(
                "\033[31mAt least one track download failed. Exiting with failure...\033[0m"
            )
            os._exit(1)
        else:
            print("\033[32mDownload Completed. Exiting...\033[0m")
            os._exit(0)

    CLI().cmdloop()


class CLI(Cmd):
    intro = "\033[32mWelcome to OnTheSpot. Type help or ? to list commands.\033[0m"
    prompt = "(OTS) "

    def do_help(self, arg):
        print("\033[32mAvailable commands:\033[0m")
        print("  help                - Show this help message")
        print("  config              - Display configuration options")
        print("  search [term]/[url] - Search for a term or parse a url")
        print("  download_queue      - View the download queue")
        print("  casualsnek          - Something to pass the time")
        print("  exit                - Exit the CLI application")

    def do_config(self, arg):
        parts = arg.split(maxsplit=1)

        if arg == "reset_settings":
            config.reset()
            print("\033[32mSettings reset, please restart the app.\033[0m")
            return

        if len(parts) > 1 and parts[0] == "set":
            try:
                key, value = parts[1].split(maxsplit=1)
                if key in config.__dict__["_Config__config"]:
                    try:
                        if value.lower() in ["true", "false"]:
                            value = value.lower() == "true"
                        elif value.isdigit():
                            value = int(value)
                    except ValueError:
                        pass

                    config.set(key, value)
                    config.save()
                    print(f"\033[32mUpdated {key} to {value}.\033[0m")
                else:
                    print(
                        f"\033[31mError: {key} is not a valid configuration key.\033[0m"
                    )
            except ValueError:
                print("\033[31mUsage: config set <key> <value>\033[0m")
            return

        if len(parts) > 1 and parts[0] == "get":
            try:
                key = parts[1]
                value = config.get(key)
                if value is not None:
                    print(f"\033[32m{key} = {value}\033[0m")
                else:
                    print(
                        f"\033[31mError: {key} is not a valid configuration key.\033[0m"
                    )
            except ValueError:
                print("\033[31mUsage: config get <key>\033[0m")
            return

        if arg == "list":
            print("\033[32mConfiguration Parameters:\033[0m")
            for key, value in config.__dict__["_Config__template_data"].items():
                print(f"  {key} = {config.get(key)}")
            return

        if arg == "list_accounts":
            print(
                "\033[32mLegend:\033[0m\n\033[34m>\033[0mSelected: Service, Status\n\n\033[32mAccounts:\033[0m"
            )
            accounts = config.get("accounts")
            active_account_index = config.get("active_account_number")

            for index, account in enumerate(accounts):
                status = "active" if account.get("active", False) else "inactive"
                selected = "\033[34m>\033[0m" if index == active_account_index else " "
                print(
                    f"{selected}[{index}] {account['uuid']}: {account['service']}, {status}"
                )
            return

        if arg.startswith("add_account"):
            parts = arg.split(maxsplit=2)
            if len(parts) == 1:
                print(
                    "Incorrect usage. Please provide a service among the following: apple_music, bandcamp, crunchyroll, deezer, generic, qobuz, soundcloud, spotify, tidal, youtube_music."
                )
            elif parts[1] == "apple_music":
                print("\033[32mInitializing Apple Music account login...\033[0m")

                if len(parts) == 3:
                    media_user_token = parts[2]

                    try:
                        apple_music_add_account(media_user_token)
                        print(
                            "\033[32mApple Music account added successfully. Please restart the app.\033[0m"
                        )
                    except Exception as e:
                        print(
                            f"\033[31mError while adding Apple Music account: {e}\033[0m"
                        )
                else:
                    print(
                        "\033[31mUsage: add_account apple_music <media-user-token>\033[0m"
                    )
                return
            elif parts[1] == "bandcamp":
                print("\033[32mInitializing Bandcamp account login...\033[0m")

                try:
                    bandcamp_add_account()
                    print(
                        "\033[32mBandcamp account added successfully. Please restart the app.\033[0m"
                    )
                except Exception as e:
                    print(f"\033[31mError while adding Bandcamp account: {e}\033[0m")
            elif parts[1] == "crunchyroll":
                print("\033[32mInitializing Crunchyroll account login...\033[0m")

                if len(parts) == 4:
                    email = parts[2]
                    password = parts[3]

                    try:
                        crunchyroll_add_account(email, password)
                        print(
                            "\033[32mCrunchyroll account added successfully. Please restart the app.\033[0m"
                        )
                    except Exception as e:
                        print(
                            f"\033[31mError while adding Crunchyroll account: {e}\033[0m"
                        )
                else:
                    print(
                        "\033[31mUsage: add_account crunchyroll <email> <password>\033[0m"
                    )
                return
            elif parts[1] == "deezer":
                if len(parts) == 3 and parts[2] != "public_deezer":
                    print(
                        "\033[32mAdding Deezer account with provided ARL token...\033[0m"
                    )
                    arl = parts[2]
                    try:
                        deezer_add_account(arl)
                        print(
                            "\033[32mDeezer account added successfully. Please restart the app.\033[0m"
                        )
                    except Exception as e:
                        print(f"\033[31mError while adding Deezer account: {e}\033[0m")
                else:
                    print("\033[31mUsage: add_account deezer <arl>\033[0m")
                return
            elif parts[1] == "generic":
                print("\033[32mInitializing Generic platform support...\033[0m")
                try:
                    generic_add_account()
                    print(
                        "\033[32mGeneric platform support added successfully. Please restart the app.\033[0m"
                    )
                except Exception as e:
                    print(
                        f"\033[31mError while adding Generic platform support: {e}\033[0m"
                    )
                return
            elif parts[1] == "qobuz":
                print("\033[32mInitializing Qobuz account login...\033[0m")

                if len(parts) == 4:
                    email = parts[2]
                    password = parts[3]

                    try:
                        qobuz_add_account(email, password)
                        print(
                            "\033[32mQobuz account added successfully. Please restart the app.\033[0m"
                        )
                    except Exception as e:
                        print(f"\033[31mError while adding Qobuz account: {e}\033[0m")
                else:
                    print("\033[31mUsage: add_account qobuz <email> <password>\033[0m")
                return
            elif parts[1] == "soundcloud":
                if len(parts) == 3 and parts[2] != "public_soundcloud":
                    print(
                        "\033[32mAdding SoundCloud account with provided OAuth token...\033[0m"
                    )
                    oauth_token = parts[2]
                    try:
                        soundcloud_add_account(oauth_token)
                        print(
                            "\033[32mSoundCloud account added successfully. Please restart the app.\033[0m"
                        )
                    except Exception as e:
                        print(
                            f"\033[31mError while adding SoundCloud account: {e}\033[0m"
                        )
                else:
                    print("\033[31mUsage: add_account soundcloud <arl>\033[0m")
                return
            elif parts[1] == "spotify":
                print(
                    "\033[32mLogin service started, select 'OnTheSpot' under devices in the Spotify Desktop App.\033[0m"
                )

                def add_spotify_account_worker():
                    session = spotify_new_session()
                    if session:
                        print("\033[32mAccount added, please restart the app.\n\033[0m")
                    else:
                        print("\033[31mAccount already exists.\033[0m")

                login_worker = threading.Thread(target=add_spotify_account_worker)
                login_worker.daemon = True
                login_worker.start()
            elif parts[1] == "tidal":
                print("\033[32mInitializing Tidal account login...\033[0m")

                def add_tidal_account_worker():
                    try:
                        device_code, verification_url = tidal_add_account_pt1()
                        print(
                            f"\033[32mPlease visit the following URL to complete login: {verification_url}\033[0m"
                        )

                        result = tidal_add_account_pt2(device_code)
                        if result:
                            print(
                                "\033[32mTidal account added successfully. Please restart the app.\033[0m"
                            )

                        else:
                            print("\033[31mFailed to add Tidal account.\033[0m")
                    except Exception as e:
                        print(f"\033[31mError while adding Tidal account: {e}\033[0m")

                login_worker = threading.Thread(target=add_tidal_account_worker)
                login_worker.daemon = True
                login_worker.start()
            elif parts[1] == "youtube_music":
                print("\033[32mInitializing YouTube Music account login...\033[0m")

                try:
                    youtube_music_add_account()
                    print(
                        "\033[32mYouTube Music public account added successfully. Please restart the app.\033[0m"
                    )
                except Exception as e:
                    print(
                        f"\033[31mError while adding YouTube Music account: {e}\033[0m"
                    )
                return
            else:
                print("\033[31mUnknown service.\033[0m")
                return
            config.set("active_account_number", config.get("active_account_number") + 1)
            config.save()
            return

        if arg.startswith("select_account"):
            parts = arg.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    account_number = int(parts[1])
                    if not isinstance(account_number, int) or account_number > len(
                        config.get("accounts")
                    ):
                        raise ValueError
                    config.set("active_account_number", account_number)
                    config.save()
                    print(f"\033[32mSelected account number: {account_number}\033[0m")
                except ValueError:
                    print(
                        "\033[31mInvalid account number. Please enter a valid integer.\033[0m"
                    )
            else:
                print("\033[31mUsage: select_account <index>\033[0m")
            return

        if arg.startswith("delete_account"):
            parts = arg.split(maxsplit=1)
            if len(parts) == 2:
                try:
                    account_number = parts[1]
                    if not isinstance(account_number, int) or account_number > len(
                        config.get("accounts")
                    ):
                        raise ValueError
                    accounts = config.get("accounts").copy()
                    del accounts[account_number]
                    config.set("accounts", accounts)
                    config.save()
                    del account_pool[account_number]
                    print(f"\033[32mDeleted account number: {account_number}\033[0m")
                except ValueError:
                    print(
                        "\033[31mInvalid account number. Please enter a valid integer.\033[0m"
                    )
                except Exception as e:
                    print(
                        f"\033[31mAn error occurred while deleting the account: {e}\033[0m"
                    )
            else:
                print("\033[31mUsage: delete_account <index>\033[0m")
            return

        print("\033[32mConfiguration options:\033[0m")
        print(
            "  list                                   - Display all configuration parameters"
        )
        print(
            "  get <key>                              - Get the value of a specific parameter"
        )
        print(
            "  set <key> <value>                      - Set the value of a specific parameter"
        )
        print("  list_accounts                          - List all accounts")
        print("  add_account <service> [credentials]    - Add a new account")
        print("  select_account <index>                 - Select an account")
        print("  delete_account <index>                 - Delete an account")
        print(
            "  reset_settings                         - Reset all settings to default"
        )
        print(
            f"  \033[36mAdditional options can be found at {config_dir()}{os.path.sep}otsconfig.json\033[0m"
        )

    def do_search(self, arg):
        """Search for a term."""
        if arg:
            print(f"\033[32mSearching for: {arg}\033[0m")
            results = get_search_results(arg)

            if results is True:
                print(f"\033[32mParsing Item...\033[0m")
                return
            elif results:
                print("\033[32mSearch Results:\033[0m")
                for index, item in enumerate(results):
                    print(
                        f"[{index + 1}] {item['item_type']}: {item['item_name']} by {item['item_by']}"
                    )
                print(f"[0] Exit")
                choice = input(
                    "\033[32mEnter the number of the item you want to download: \033[0m"
                )
                try:
                    choice_index = int(choice) - 1
                    if 0 <= choice_index < len(results):
                        selected_item = results[choice_index]
                        parse_url(selected_item["item_url"])
                    else:
                        print("Invalid number entered, exiting.")
                except ValueError:
                    print("Please enter a valid number.")
            else:
                print("No results found.")
        else:
            print("Please provide a term to search.")

    def do_casualsnek(self, arg):
        curses.wrapper(start_snake_game)

    def do_download_queue(self, arg):
        curses.wrapper(self.display_queue)

    def display_queue(self, stdscr):
        keep_running = True
        # curses.curs_set(0)
        curses.start_color()
        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)

        stdscr.addstr(0, 0, "Download Queue", curses.color_pair(1) | curses.A_BOLD)
        stdscr.addstr(
            1,
            0,
            "(Press 'c' to cancel pending downloads, 'd' to clear completed, 'q' to exit.)",
        )

        current_row = 2
        max_height = curses.LINES - 3
        selected_index = 0
        first_item_index = 0

        def refresh_queue():
            while keep_running:
                time.sleep(0.2)
                stdscr.clear()
                stdscr.addstr(
                    0, 0, "Download Queue", curses.color_pair(1) | curses.A_BOLD
                )
                stdscr.addstr(
                    1,
                    0,
                    "(Press 'c' to cancel pending downloads, 'd' to clear completed, 'q' to exit.)",
                )

                keys = list(download_queue.keys())
                num_items = len(keys)

                num_items_to_display = min(max_height, num_items)

                for idx in range(num_items_to_display):
                    key = keys[first_item_index + idx]
                    status = download_queue[key]["item_status"]
                    item_name = download_queue[key]["item_name"]
                    item_by = download_queue[key]["item_by"]
                    if idx == selected_index:
                        stdscr.addstr(
                            current_row + idx,
                            0,
                            f"{item_name} by {item_by}: {status}",
                            curses.color_pair(2),
                        )
                    else:
                        stdscr.addstr(
                            current_row + idx, 0, f"{item_name} by {item_by}: {status}"
                        )

                stdscr.refresh()

        threading.Thread(target=refresh_queue, daemon=True).start()

        while True:
            key = stdscr.getch()
            keys = list(download_queue.keys())
            num_items = len(keys)

            num_items_to_display = min(max_height, num_items)

            if key == curses.KEY_UP:
                if selected_index > 0:
                    selected_index -= 1
                elif first_item_index > 0:
                    first_item_index -= 1
                    selected_index = min(selected_index, num_items_to_display - 1)
            elif key == curses.KEY_DOWN:
                if selected_index < num_items_to_display - 1:
                    selected_index += 1
                elif first_item_index + num_items_to_display < num_items:
                    first_item_index += 1
                    selected_index = min(selected_index, num_items_to_display - 1)
            elif key == ord("q"):
                keep_running = False
                break
            elif key == ord("c"):
                with download_queue_lock:
                    for key in list(download_queue.keys()):
                        if download_queue[key]["item_status"] == "Waiting":
                            download_queue[key]["item_status"] = "Cancelled"
            elif key == ord("d"):
                with download_queue_lock:
                    selected_index = 0
                    first_item_index = 0
                    for key in list(download_queue.keys()):
                        if download_queue[key]["item_status"] in (
                            "Cancelled",
                            "Downloaded",
                            "Already Exists",
                        ):
                            download_queue.pop(key)
            elif key == ord("r"):
                with download_queue_lock:
                    for key in list(download_queue.keys()):
                        if download_queue[key]["item_status"] == "Failed":
                            download_queue[key]["item_status"] = "Waiting"
        time.sleep(0.3)
        stdscr.clear()
        stdscr.refresh()

    def do_exit(self, arg):
        """Exit the CLI application."""
        print("Exiting the CLI application.")
        os._exit(0)


def start_snake_game(win):
    curses.curs_set(0)
    win.timeout(100)
    win.keypad(1)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)

    while True:
        snake = [(4, 10), (4, 9), (4, 8)]
        food = (
            random.randint(3, win.getmaxyx()[0] - 2),
            random.randint(1, win.getmaxyx()[1] - 3),
        )
        direction = curses.KEY_RIGHT
        score = 0

        while True:
            win.clear()
            draw_borders(win)
            update_header(win, score)

            for y, x in snake:
                win.addch(y, x, "█", curses.color_pair(2))

            win.addch(food[0], food[1], "■", curses.color_pair(3))

            new_dir = win.getch()
            if new_dir in [
                curses.KEY_RIGHT,
                curses.KEY_LEFT,
                curses.KEY_UP,
                curses.KEY_DOWN,
            ]:
                direction = new_dir

            head_y, head_x = snake[0]
            if direction == curses.KEY_RIGHT:
                head_x += 1
            elif direction == curses.KEY_LEFT:
                head_x -= 1
            elif direction == curses.KEY_UP:
                head_y -= 1
            elif direction == curses.KEY_DOWN:
                head_y += 1

            if (
                head_x in [0, win.getmaxyx()[1] - 2]
                or head_y in [0, win.getmaxyx()[0] - 1]
                or head_y == 2
                or (head_y, head_x) in snake
            ):
                display_game_over(win, score)
                break

            if (head_y, head_x) == food:
                score += 1
                food = (
                    random.randint(3, win.getmaxyx()[0] - 2),
                    random.randint(1, win.getmaxyx()[1] - 3),
                )
            else:
                snake.pop()

            snake.insert(0, (head_y, head_x))

        while True:
            key = win.getch()
            if key == ord("r"):
                break
            elif key == ord("q"):
                return


def draw_borders(win):
    height, width = win.getmaxyx()
    if width < 2 or height < 2:
        return
    for y in range(height):
        win.addch(y, 0, "┃", curses.color_pair(1))
        win.addch(y, width - 2, "┃", curses.color_pair(1))
    width = win.getmaxyx()[1]
    if width > 2:
        win.addstr(0, 0, "┏" + "━" * (width - 3) + "┓", curses.color_pair(1))
        win.addstr(2, 0, "┣" + "━" * (width - 3) + "┫", curses.color_pair(1))
    if height > 1 and width > 2:
        win.addstr(height - 1, 0, "┗" + "━" * (width - 3) + "┛", curses.color_pair(1))


def update_header(win, score):
    win.addstr(1, 2, f"Score: {score}", curses.A_BOLD)
    if not download_queue:
        item_label = "Download Queue Empty :("
    else:
        current_item = download_queue[next(iter(download_queue))]
        item_label = f"{current_item['item_name']} by {current_item['item_by']}: {current_item['item_status']}"

    win.addstr(1, 15, item_label, curses.A_BOLD)


def display_game_over(win, score):
    win.clear()
    if score > config.get("snake_high_score", 0):
        config.set("snake_high_score", score)
        config.save()
    win.addstr(
        win.getmaxyx()[0] // 2 - 1,
        win.getmaxyx()[1] // 2 - 10,
        "Game Over!",
        curses.color_pair(1),
    )
    win.addstr(
        win.getmaxyx()[0] // 2,
        win.getmaxyx()[1] // 2 - 10,
        f"Score: {score}",
        curses.A_BOLD,
    )
    win.addstr(
        win.getmaxyx()[0] // 2 + 1,
        win.getmaxyx()[1] // 2 - 10,
        f"High Score: {config.get('snake_high_score', 0)}",
        curses.A_BOLD,
    )
    win.addstr(
        win.getmaxyx()[0] // 2 + 2,
        win.getmaxyx()[1] // 2 - 10,
        "Press r to retry or q to quit.",
    )
    win.refresh()


if __name__ == "__main__":
    main()
