"""Projections of the counted-process list the billing and kill paths consume.

Split from :mod:`leisure_watch.procscan._counted` at the 250-line cap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leisure_watch.procscan._counted import CountedProcess, load_counted_processes

if TYPE_CHECKING:
    from pathlib import Path


def counted_process_names(entries: tuple[CountedProcess, ...]) -> frozenset[str]:
    """Return every matchable name across *entries*.

    Args:
        entries: Configured entries.

    Returns:
        The union of their names.
    """
    if not entries:
        return frozenset()
    return frozenset().union(*(entry.names for entry in entries))


def key_by_name(entries: tuple[CountedProcess, ...]) -> dict[str, str]:
    """Map each matchable name to its ``proc:<id>`` attribution key.

    Args:
        entries: Configured entries.

    Returns:
        Mapping of process name to attribution key.
    """
    return {name: f"proc:{entry.id}" for entry in entries for name in entry.names}


def labels_by_key(entries: tuple[CountedProcess, ...]) -> dict[str, str]:
    """Map each ``proc:<id>`` key to its display label.

    Args:
        entries: Configured entries.

    Returns:
        Mapping of attribution key to label.
    """
    return {f"proc:{entry.id}": entry.label for entry in entries}


def kill_target_names(config_file: Path | None = None) -> frozenset[str]:
    """Return the counted-process names the kill paths should also target.

    The budget cutoff and the total block kill these; the
    ``kill_unauthorized_games`` path does not — it matches on ``SteamAppId``,
    which a non-Steam game never sets, so it excludes them for free.

    Args:
        config_file: The enforcer's config; ``None`` = :data:`DEFAULT_CONFIG_FILE`.

    Returns:
        Every configured matchable name.
    """
    return counted_process_names(load_counted_processes(config_file))
