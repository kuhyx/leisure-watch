"""Steam, launcher and counted-process detection over /proc.

Moved out of steam-backlog-enforcer so the root enforcer and the user
watcher share one scanner. The public names match the enforcer's originals
1:1 (``enforcer.get_running_steam_game_pids``, ``_playtime_procs.*``,
``_counted_procs.*``, ``_total_block_launchers.*``).
"""

from leisure_watch.procscan._cmdline import get_pids_by_cmdline_names, process_name
from leisure_watch.procscan._counted import (
    DEFAULT_CONFIG_FILE,
    DEFAULT_COUNTED_PROCESSES,
    FORBIDDEN_NAMES,
    CountedProcess,
    load_counted_processes,
    parse_counted_processes,
)
from leisure_watch.procscan._counted_views import (
    counted_process_names,
    key_by_name,
    kill_target_names,
    labels_by_key,
)
from leisure_watch.procscan._launchers import (
    LAUNCHER_PROCESS_NAMES,
    STEAM_CLIENT_PROCESS_NAMES,
)
from leisure_watch.procscan._qualifying import (
    CountsLaunchers,
    attributed_key,
    qualifying_pids,
)
from leisure_watch.procscan._steam import (
    get_pids_by_process_names,
    get_running_steam_game_pids,
)

__all__ = [
    "DEFAULT_CONFIG_FILE",
    "DEFAULT_COUNTED_PROCESSES",
    "FORBIDDEN_NAMES",
    "LAUNCHER_PROCESS_NAMES",
    "STEAM_CLIENT_PROCESS_NAMES",
    "CountedProcess",
    "CountsLaunchers",
    "attributed_key",
    "counted_process_names",
    "get_pids_by_cmdline_names",
    "get_pids_by_process_names",
    "get_running_steam_game_pids",
    "key_by_name",
    "kill_target_names",
    "labels_by_key",
    "load_counted_processes",
    "parse_counted_processes",
    "process_name",
    "qualifying_pids",
]
