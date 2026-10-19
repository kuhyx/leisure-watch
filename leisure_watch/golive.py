"""``leisure-watch go-live``: the one command that switches Phase 2 on (C6).

Runs as the desktop user. ``sudo`` is used for exactly one thing: writing
(or, with ``--undo``, removing) ``/etc/leisure-watch/leisure_from``. The
date written is TOMORROW's gaming day (06:00 boundary), never today, so a
day is never re-priced while it runs. Whether Phase 2 is already on is
asked of ``earned_time.leisure_active`` -- the file is never parsed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import subprocess
import tempfile
import time
from typing import TYPE_CHECKING, Final

import earned_time

from leisure_watch import _preflight, _sensors, phase2
from leisure_watch.daylog import gaming_day

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from leisure_watch._preflight import Capture

    Execute = Callable[[Sequence[str]], int]

TIMER: Final = "kuhytrack-budget.timer"
_INSTALL: Final = ("sudo", "install", "-D", "-m", "0644", "-o", "root", "-g", "root")


def run_command(argv: Sequence[str]) -> int:
    """Run *argv* on the terminal (sudo may prompt); its exit status."""
    try:
        return subprocess.run(list(argv), check=False).returncode
    except OSError:
        return 127


capture: Capture = _sensors.run
execute: Execute = run_command


@dataclass(frozen=True)
class Env:
    """Everything go-live touches, injectable for tests."""

    capture: Capture
    execute: Execute
    sources: _preflight.Sources
    switch: Path
    clock: Callable[[], float]
    out: Callable[[str], None]


def default_env(out: Callable[[str], None]) -> Env:
    """The real runners, paths and clock (module attributes read now)."""
    return Env(
        capture=capture,
        execute=execute,
        sources=_preflight.default_sources(),
        switch=phase2.default_switch(),
        clock=time.time,
        out=out,
    )


def _plan(day: date) -> list[str]:
    return [
        f"Leisure budget goes live on gaming day {day} (from {day} 06:00 local):",
        "  - earned_time: base 7 h, cap 10 h (leisure_active() is true)",
        "  - steam-backlog-enforcer bills ALL leisure against it and, at 0,",
        "    kills non-allowlisted apps (Steam path as today)",
        "  - Helium + LibreWolf extension sends non-allowlisted sites to the",
        '    "leisure spent" page at 0',
        "  - daily-limits/i3bar show Leisure; the SHADOW block + alerts stop",
        f"  - {TIMER}: disabled now",
        "Undo any time: leisure-watch go-live --undo",
    ]


def _write_switch(env: Env, day: date) -> bool:
    with tempfile.TemporaryDirectory(prefix="leisure-go-live-") as tmp:
        staged = Path(tmp) / "leisure_from"
        staged.write_text(f"{day.isoformat()}\n", encoding="ascii")
        staged.chmod(0o644)  # install -m sets it too; never stage a 0600
        return env.execute([*_INSTALL, str(staged), str(env.switch)]) == 0


def go_live(
    env: Env, *, force: bool = False, dry_run: bool = False, day: date | None = None
) -> int:
    """Preflight, write the switch file, disable the kuhytrack timer."""
    ts = env.clock()
    today = gaming_day(ts)
    target = day or today + timedelta(days=1)
    if target <= today:
        env.out(f"refusing: {target} is not after today's gaming day {today}")
        return 2
    if earned_time.leisure_active(today, path=env.switch):
        live = earned_time.leisure_from(path=env.switch)
        env.out(f"already live since {live} (undo: leisure-watch go-live --undo)")
        return 1
    checks = _preflight.preflight(env.capture, env.sources, ts)
    failed = [c for c in checks if not c.ok]
    env.out("preflight:")
    for line in _preflight.render(checks):
        env.out(line)
    refuse = bool(failed) and not force
    if failed and force:
        env.out(f"--force: forced past {len(failed)} failed check(s)")
    if dry_run:
        if refuse:
            env.out("dry run: would refuse (fix the checks above or use --force)")
        env.out(f"dry run: would write {target} to {env.switch} (sudo install)")
        env.out(f"dry run: would run systemctl --user disable --now {TIMER}")
        for line in _plan(target):
            env.out(line)
        return 1 if refuse else 0
    if refuse:
        env.out(f"refusing: {len(failed)} check(s) failed (--force to override)")
        return 1
    return _apply(env, target)


def _apply(env: Env, target: date) -> int:
    if not _write_switch(env, target):
        env.out(f"sudo install failed: {env.switch} not written")
        return 1
    seen = earned_time.leisure_from(path=env.switch)
    if seen != target:
        env.out(f"wrote {env.switch} but earned_time reads {seen}; check it")
        return 1
    env.out(f"wrote {target} to {env.switch}")
    if env.execute(["systemctl", "--user", "disable", "--now", TIMER]) != 0:
        env.out(f"switch written, but disabling {TIMER} failed: do it by hand")
        return 1
    for line in _plan(target):
        env.out(line)
    return 0


def undo(env: Env, *, dry_run: bool = False) -> int:
    """Remove the switch file (sudo) and re-enable the kuhytrack timer."""
    rm = ["sudo", "rm", "-f", str(env.switch)]
    enable = ["systemctl", "--user", "enable", "--now", TIMER]
    if dry_run:
        env.out(f"dry run: would run {' '.join(rm)}")
        env.out(f"dry run: would run {' '.join(enable)}")
        return 0
    if env.execute(rm) != 0:
        env.out(f"sudo rm failed: {env.switch} kept")
        return 1
    if earned_time.leisure_from(path=env.switch) != earned_time.LEISURE_FROM:
        env.out(f"{env.switch} still names a leisure day; check it")
        return 1
    if env.execute(enable) != 0:
        env.out(f"switch removed, but enabling {TIMER} failed: do it by hand")
        return 1
    env.out(
        f"undone: back to the 5 h / 8 h gaming budget "
        f"(parked {earned_time.LEISURE_FROM}); {TIMER} re-enabled"
    )
    return 0
