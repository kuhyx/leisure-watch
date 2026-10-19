"""Small, failure-tolerant readers for one process's /proc entry.

Every reader returns an empty value instead of raising: the process may have
exited between being named (by X, by pipewire) and being read.
"""

from __future__ import annotations

from pathlib import Path

_PROC = Path("/proc")

# /proc/<pid>/stat: "pid (comm) state ppid ...". comm may contain spaces or
# parentheses, so the fields are split after the LAST ')'.
_PPID_FIELD = 1

# A runaway or cyclic parent chain must not spin the watcher.
_MAX_DEPTH = 64


def argv(pid: int) -> tuple[str, ...]:
    """Return *pid*'s argv, or ``()`` if it cannot be read."""
    try:
        raw = (_PROC / str(pid) / "cmdline").read_bytes()
    except OSError:
        return ()
    return tuple(p for p in raw.decode("utf-8", errors="replace").split("\x00") if p)


def comm(pid: int) -> str:
    """Return *pid*'s kernel command name, or ``""``."""
    try:
        return (_PROC / str(pid) / "comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def exe(pid: int) -> str:
    """Return the resolved path of *pid*'s executable, or ``""``."""
    try:
        return str((_PROC / str(pid) / "exe").readlink())
    except OSError:
        return ""


def cwd(pid: int) -> str:
    """Return *pid*'s working directory, or ``""``."""
    try:
        return str((_PROC / str(pid) / "cwd").readlink())
    except OSError:
        return ""


def ppid(pid: int) -> int:
    """Return *pid*'s parent pid, or ``0`` if unknown."""
    try:
        stat = (_PROC / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return 0
    fields = stat.rpartition(")")[2].split()
    try:
        return int(fields[_PPID_FIELD])
    except IndexError, ValueError:
        return 0


def ancestry(pid: int) -> tuple[int, ...]:
    """Return *pid* followed by its ancestors, nearest first, up to init."""
    chain: list[int] = []
    current = pid
    while current > 1 and current not in chain and len(chain) < _MAX_DEPTH:
        chain.append(current)
        current = ppid(current)
    return tuple(chain)


def pids_named(name: str) -> tuple[int, ...]:
    """Return every pid whose ``comm`` is exactly *name*."""
    try:
        entries = list(_PROC.iterdir())
    except OSError:
        return ()
    found = [
        int(e.name) for e in entries if e.name.isdigit() and comm(int(e.name)) == name
    ]
    return tuple(sorted(found))
