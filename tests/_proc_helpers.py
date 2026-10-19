"""Build fake /proc entries for the rule and classifier tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def fake_pid(
    proc: Path, pid: int, *argv: str, exe: str = "", cwd: str = "", ppid: int = 1
) -> None:
    """Create ``proc/<pid>`` with cmdline *argv* (comm = argv[0]), exe, cwd, parent."""
    entry = proc / str(pid)
    entry.mkdir()
    entry.joinpath("cmdline").write_bytes(b"\x00".join(a.encode() for a in argv))
    entry.joinpath("stat").write_text(f"{pid} (x y) S {ppid} 0 0", encoding="utf-8")
    entry.joinpath("comm").write_text(argv[0] if argv else "", encoding="utf-8")
    if exe:
        entry.joinpath("exe").symlink_to(exe)
    if cwd:
        entry.joinpath("cwd").symlink_to(cwd)


def fake_start(proc: Path, pid: int, start: int, ppid: int = 1) -> None:
    """Give ``proc/<pid>`` a full ``stat``: field 22 (starttime) is *start*.

    The comm holds ``) (`` so a reader must split after the LAST ``)``.
    """
    stat = f"{pid} (a) (b) S {ppid} " + "0 " * 17 + f"{start} 4096 0"
    (proc / str(pid) / "stat").write_text(stat, encoding="utf-8")
