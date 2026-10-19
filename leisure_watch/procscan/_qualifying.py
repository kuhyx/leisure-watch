"""Which processes bill the gaming budget, and who a tick belongs to.

Moved from steam-backlog-enforcer's ``_playtime_procs``. ``rules`` is typed
against a :class:`~typing.Protocol`, so the enforcer's ``PlaytimeRules`` (or
anything with ``count_launchers``) fits structurally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from leisure_watch.procscan._cmdline import get_pids_by_cmdline_names
from leisure_watch.procscan._counted import load_counted_processes
from leisure_watch.procscan._counted_views import key_by_name
from leisure_watch.procscan._launchers import LAUNCHER_PROCESS_NAMES
from leisure_watch.procscan._steam import (
    get_pids_by_process_names,
    get_running_steam_game_pids,
)

if TYPE_CHECKING:
    from pathlib import Path


class CountsLaunchers(Protocol):
    """The one policy switch :func:`qualifying_pids` reads."""

    @property
    def count_launchers(self) -> bool:
        """Whether the hardcoded launcher table bills the budget."""
        ...


def _merge_named(found: dict[int, str], keys: dict[str, str]) -> None:
    """Add name-matched PIDs to *found* without displacing existing keys.

    ``setdefault`` is the point: a Steam game already attributed by its
    ``SteamAppId`` must keep that key even if its ``comm`` also happens to match
    a launcher name.

    A scanner can only return names it was asked for, so an unmapped name is
    unreachable in production — it is skipped rather than raising, because the
    alternative is a ``KeyError`` inside the enforce loop.

    Args:
        found: Accumulating PID-to-key mapping, mutated in place.
        keys: Program basename to attribution key.
    """
    names = frozenset(keys)
    for source in (get_pids_by_process_names(names), get_pids_by_cmdline_names(names)):
        for pid, name in source.items():
            key = keys.get(name)
            if key is not None:
                found.setdefault(pid, key)


def qualifying_pids(
    rules: CountsLaunchers, config_file: Path | None = None
) -> dict[int, str]:
    """Return PIDs whose runtime counts against the daily budget, with owners.

    Steam games are identified by the ``SteamAppId`` environment variable, using
    the same ``!= 0`` predicate the enforcer's ``enforce_allowed_game`` uses to exclude
    the Steam client tree — browsing the store is not gaming.

    The value is an attribution key (``app:<id>``, ``launcher:<name>`` or
    ``proc:<id>``) so that the budget can record *which* game it billed. The
    app id was previously destructured and dropped on the first line here, one
    step before accumulation.

    ``counted_processes`` is deliberately *not* gated on ``count_launchers``:
    that switch covers the sixteen hardcoded launchers, and turning it off must
    not silently stop billing a game the user explicitly listed.

    Args:
        rules: Policy for this tick.
        config_file: The enforcer's config holding ``counted_processes``.

    Returns:
        Mapping of qualifying PID to its attribution key.
    """
    found: dict[int, str] = {
        pid: f"app:{app_id}"
        for pid, app_id in get_running_steam_game_pids().items()
        if app_id != 0
    }
    if rules.count_launchers:
        _merge_named(
            found, {name: f"launcher:{name}" for name in LAUNCHER_PROCESS_NAMES}
        )

    counted = key_by_name(load_counted_processes(config_file))
    if counted:
        _merge_named(found, counted)
    return found


def attributed_key(qualifying: dict[int, str]) -> str:
    """Return the single attribution key this tick should be credited to.

    With exactly one game qualifying, it gets the credit. With two or more
    running at once there is no honest way to say which one earned the tick,
    so this returns ``""``: the tick still bills, and the gap shows up as
    Unattributed rather than being charged to a guess.

    Args:
        qualifying: Mapping of qualifying PID to attribution key.

    Returns:
        The attribution key, or ``""`` if none can be determined.
    """
    distinct = set(qualifying.values())
    return distinct.pop() if len(distinct) == 1 else ""
