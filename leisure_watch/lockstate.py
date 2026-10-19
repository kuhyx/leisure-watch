"""Whether shadow billing is paused right now (Q7, contract C2).

Paused while a gatelock locker ACTUALLY holds its X grab, or while i3lock
runs. Leetcode study mode releases the grab (``grab_held: false``), so it
does not pause. Claims written before C2 have no ``grab_held``; for those it
is ``grab != "none"``.

Strictly read-only (gatelock 0.11's ``held_grabs`` reaps dead claims, so it
is NOT used): the claim's owner holds an exclusive ``flock`` for its whole
life, so failing to take a shared lock is the proof of life. Never creates,
modifies or unlinks anything in the claims dir, and never locks an empty
file (an owner between ``open`` and ``flock`` would otherwise lose its claim
to us). Stdlib only, root-safe with an explicit claims dir.
"""

from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
from typing import Final

from leisure_watch import _proctree, _safeio

DESKTOP_UID: Final = 1000
_CONTENDED: Final = frozenset({errno.EACCES, errno.EAGAIN})


def default_claims_dir() -> Path:
    """The gatelock claims dir; root (uid 0) reads the desktop user's."""
    override = os.environ.get("GATELOCK_RUNTIME_DIR")
    if override:
        return Path(override) / "claims"
    uid = os.getuid()
    if uid == 0:
        return Path(f"/run/user/{DESKTOP_UID}/gatelock/claims")
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    return Path(runtime) / "gatelock" / "claims"


def _grabbing(raw: dict[str, object] | None) -> tuple[str, int] | None:
    """(app, rank) if the decoded claim says its grab is held, else ``None``."""
    if raw is None:
        return None
    app, grab, rank = raw.get("app"), raw.get("grab"), raw.get("rank", 0)
    if not isinstance(app, str) or not isinstance(grab, str) or type(rank) is not int:
        return None
    held = raw.get("grab_held")
    if not isinstance(held, bool):
        held = grab != "none"
    return (app, rank) if held and grab != "none" else None


def _owner_alive(fd: int) -> bool:
    """Whether a live process still holds the claim's exclusive flock.

    Probes with a SHARED non-blocking lock: it conflicts only with the
    owner's exclusive one, so two readers (root enforcer + user watcher)
    probing the same dead claim at once both see it as dead.
    """
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError as exc:
        return exc.errno in _CONTENDED
    fcntl.flock(fd, fcntl.LOCK_UN)
    return False


def _live_grab(path: Path) -> tuple[str, int] | None:
    """(app, rank) of a live claim at *path* holding its grab, else ``None``.

    The dir is user-writable and root reads it, so one fd does it all: opened
    non-blocking without following symlinks (a FIFO or link is skipped, never
    waited on), read with a size cap, then flock-probed -- the file probed is
    the file read. An empty or undecodable claim is never locked.
    """
    fd = _safeio.open_regular(path)
    if fd is None:
        return None
    try:
        claim = _grabbing(_safeio.json_object(_safeio.read_fd(fd)))
        return claim if claim is not None and _owner_alive(fd) else None
    finally:
        os.close(fd)


def held_grab_apps(claims_dir: Path | None = None) -> tuple[str, ...]:
    """Apps whose live claim holds a real grab, highest rank first."""
    directory = default_claims_dir() if claims_dir is None else claims_dir
    if not directory.is_dir():
        return ()
    found: list[tuple[int, str]] = []
    for path in sorted(directory.glob("*.json")):
        claim = _live_grab(path)
        if claim is not None:
            found.append((-claim[1], claim[0]))
    return tuple(app for _, app in sorted(found))


def paused_by(claims_dir: Path | None = None) -> str | None:
    """``"gatelock:<app>"``, ``"i3lock"`` or ``None`` (not paused)."""
    apps = held_grab_apps(claims_dir)
    if apps:
        return f"gatelock:{apps[0]}"
    if _proctree.pids_named("i3lock"):
        return "i3lock"
    return None
