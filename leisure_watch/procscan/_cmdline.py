"""Identifying processes by their /proc cmdline.

Process-name matching alone misses launchers run through an interpreter
(``lutris`` is a Python script; several Minecraft launchers are ``java -jar``),
so this reads argv and looks past the interpreter to the real program.
Moved from steam-backlog-enforcer's ``_playtime_procs`` with identical
behaviour.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROC = Path("/proc")

# argv[0] basenames that tell us nothing: the real program is argv[1].
_INTERPRETERS = frozenset({"bash", "env", "java", "perl", "python", "python3", "sh"})

# An interpreter invocation needs at least `<interp> <script>` to name a program.
_MIN_ARGV_FOR_INTERPRETER = 2


def get_pids_by_cmdline_names(names: frozenset[str]) -> dict[int, str]:
    """Scan ``/proc/*/cmdline`` for processes whose program name is in *names*.

    Complements :func:`get_pids_by_process_names`, which matches on
    ``comm`` and therefore cannot see interpreter-launched programs: the kernel
    records ``/usr/bin/lutris`` as ``python3``. When ``argv[0]``'s basename is a
    known interpreter this falls through to ``argv[1]``.

    The daemon itself runs under ``python3``, so its own PID is skipped.

    Args:
        names: Program basenames to match.

    Returns:
        Mapping of PID to the matched name.
    """
    own_pid = os.getpid()
    found: dict[int, str] = {}

    for entry in _PROC.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == own_pid:
            continue
        matched = _match_cmdline(entry, names)
        if matched is not None:
            found[pid] = matched

    return found


def _match_cmdline(entry: Path, names: frozenset[str]) -> str | None:
    """Return the name in *names* that *entry*'s cmdline runs, if any.

    Args:
        entry: A ``/proc/<pid>`` directory.
        names: Program basenames to match.

    Returns:
        The matched name, or ``None``.
    """
    try:
        raw = (entry / "cmdline").read_bytes()
    except OSError, ValueError:
        return None

    argv = [
        part for part in raw.decode("utf-8", errors="replace").split("\x00") if part
    ]
    if not argv:
        return None

    first = Path(argv[0]).name
    if first in names:
        return first
    if first not in _INTERPRETERS or len(argv) < _MIN_ARGV_FOR_INTERPRETER:
        return None
    second = Path(argv[1]).name
    return second if second in names else None


def process_name(pid: int) -> str | None:
    """Return *pid*'s program name, or ``None`` if it is no longer running.

    Existence is the point as much as the name: callers resolve PIDs recorded
    earlier, and a PID that has since been recycled would otherwise be reported
    under whatever process now holds the number.

    Args:
        pid: Process id to look up.

    Returns:
        The contents of ``/proc/<pid>/comm``, or ``None``.
    """
    try:
        return (_PROC / str(pid) / "comm").read_text(encoding="utf-8").strip() or None
    except OSError, ValueError:
        return None
