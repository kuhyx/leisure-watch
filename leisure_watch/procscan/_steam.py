"""SteamAppId and ``comm`` scanners over /proc.

Moved from steam-backlog-enforcer's ``enforcer.py`` with identical behaviour.
``/proc`` is a module constant (``_PROC``) so tests can point it elsewhere.
"""

from __future__ import annotations

from pathlib import Path

_PROC = Path("/proc")

# The kernel stores at most 15 characters of a process name in comm.
_COMM_LEN = 15


def get_running_steam_game_pids() -> dict[int, int]:
    """Scan /proc to find running Steam game processes.

    Returns:
        Mapping of PID to SteamAppId.
    """
    running: dict[int, int] = {}

    for entry in _PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            environ = (entry / "environ").read_bytes()
            pairs = environ.split(b"\x00")
            for pair in pairs:
                if pair.startswith(b"SteamAppId="):
                    value = pair.split(b"=", 1)[1].decode("utf-8", errors="replace")
                    if value.isdigit():
                        running[int(entry.name)] = int(value)
                    break
        except PermissionError, OSError, ValueError:
            continue

    return running


def get_pids_by_process_names(names: frozenset[str]) -> dict[int, str]:
    """Scan /proc/*/comm for processes whose command name is in *names*.

    The kernel truncates ``/proc/[pid]/comm`` to 15 characters, so *names*
    longer than that (e.g. ``EpicGamesLauncher``) are matched against their
    own first 15 characters -- how the kernel actually stores them.

    Args:
        names: Program names to match.

    Returns:
        Mapping of PID to the matched (untruncated) name.
    """
    truncated = {name[:_COMM_LEN]: name for name in names}
    running: dict[int, str] = {}

    for entry in _PROC.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
        except PermissionError, OSError, ValueError:
            continue
        if comm in truncated:
            running[int(entry.name)] = truncated[comm]

    return running
