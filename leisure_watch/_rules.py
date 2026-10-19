"""Process-ancestry rules: own Godot prototypes (Q22) and wsg-grabber (Q7).

Both look at the PROCESS behind a window or an audio stream, never at its
WM_CLASS alone: an exported Godot build can carry the same class as the
editor, and a scraper's audio looks like any other python3's.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from leisure_watch import _proctree

# Flags the editor passes when it launches the project (Play) or itself.
_EDITOR_FLAGS: Final = frozenset(
    {"-e", "--editor", "-p", "--project-manager", "--remote-debug"}
)
_WSG_NAMES: Final = frozenset({"wsg_grabber", "wsg-grabber"})


def _under(path: str, root: Path) -> bool:
    return bool(path) and Path(path).is_relative_to(root)


def is_godot(pid: int, instance: str, cls: str) -> bool:
    """Whether the window (or its process) is a Godot engine binary."""
    names = (instance.lower(), cls.lower(), Path(_proctree.exe(pid)).name.lower())
    return any(n.startswith("godot") for n in names)


def _project_path(argv: tuple[str, ...]) -> str:
    for i, arg in enumerate(argv):
        if arg == "--path" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--path="):
            return arg.split("=", 1)[1]
    return ""


def godot_free(pid: int, src_root: Path) -> bool:
    """Q22: own prototypes are free; exported/itch builds count.

    Free when the binary itself lives under *src_root* (a build inside one of
    kuhy's repos), or when it is the Godot editor binary running the editor,
    the project manager, a project launched from the editor, or a project
    under *src_root*.
    """
    exe = _proctree.exe(pid)
    if _under(exe, src_root):
        return True
    if not Path(exe).name.lower().startswith("godot"):
        return False
    argv = _proctree.argv(pid)
    if _EDITOR_FLAGS.intersection(argv):
        return True
    project = _project_path(argv)
    if project:
        return _under(str(Path(_proctree.cwd(pid), project)), src_root)
    return True


def _mentions_wsg(argv: tuple[str, ...]) -> bool:
    return any(Path(arg).name in _WSG_NAMES for arg in argv)


def wsg_role(pid: int) -> str | None:
    """``"scrape"`` (never counts), ``"reviewer"`` (counts) or ``None``."""
    for ancestor in _proctree.ancestry(pid):
        argv = _proctree.argv(ancestor)
        if _mentions_wsg(argv):
            return "scrape" if "scrape" in argv else "reviewer"
    return None
