"""Whether shadow billing is paused right now (Q7, contract C2).

Paused while a gatelock locker ACTUALLY holds its X grab, or while i3lock
runs. Leetcode study mode releases the grab (``grab_held: false``), so it
does not pause. Claims written before C2 have no ``grab_held``; for those it
is ``grab != "none"``.

Reads claims the way gatelock's ``read_claim_if_held`` does -- the claim's
owner holds an exclusive ``flock`` for its whole life, so failing to take the
lock is the proof of life -- but never reaps a dead claim (that is
gatelock's job) and never locks an empty file (an owner between ``open`` and
``flock`` would otherwise lose its claim to us). Stdlib only, root-safe.
"""

from __future__ import annotations

import errno
import fcntl
import json
import os
from pathlib import Path
from typing import Final

from leisure_watch import _proctree

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


def _grabbing(text: str) -> tuple[str, int] | None:
    """(app, rank) if the claim text says its grab is held, else ``None``."""
    try:
        raw = json.loads(text)
    except ValueError:
        return None
    if not isinstance(raw, dict):
        return None
    app, grab, rank = raw.get("app"), raw.get("grab"), raw.get("rank", 0)
    if not isinstance(app, str) or not isinstance(grab, str) or type(rank) is not int:
        return None
    held = raw.get("grab_held")
    if not isinstance(held, bool):
        held = grab != "none"
    return (app, rank) if held and grab != "none" else None


def _owner_alive(path: Path) -> bool:
    """Whether a live process still holds *path*'s flock."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                return exc.errno in _CONTENDED
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return False
    except OSError:
        return False


def held_grab_apps(claims_dir: Path | None = None) -> tuple[str, ...]:
    """Apps whose live claim holds a real grab, highest rank first."""
    directory = default_claims_dir() if claims_dir is None else claims_dir
    if not directory.is_dir():
        return ()
    found: list[tuple[int, str]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        claim = _grabbing(text) if text.strip() else None
        if claim is not None and _owner_alive(path):
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
