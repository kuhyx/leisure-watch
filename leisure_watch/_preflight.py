"""go-live preflight: is every Phase-2 moving part demonstrably alive?

Checks (each one line in the report, ``--force`` overrides any failure):

- watcher: ``leisure-watch.service`` active AND ``now.json`` fresh + signed;
- extension helium / librewolf: a report received in the last 24 h (the
  watcher persists last-seen per browser, :mod:`leisure_watch.heartbeats`);
- enforcer: ``steam-backlog-enforcer.service`` active AND today's
  ``playtime_state.json`` carries every shadow field, ticked in the last
  minute;
- gatelock: every LIVE claim carries ``grab_held`` (contract C2).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from leisure_watch import facts, heartbeats, lockstate, phase2
from leisure_watch._browser import EXTENSION_BROWSERS
from leisure_watch.daylog import gaming_day

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    Capture = Callable[[Sequence[str]], str | None]

WATCHER_UNIT: Final = "leisure-watch.service"
ENFORCER_UNIT: Final = "steam-backlog-enforcer.service"
HEARTBEAT_MAX_AGE: Final = 24 * 3600.0
TICK_MAX_AGE: Final = 60.0
NOW_MAX_AGE: Final = 15.0


@dataclass(frozen=True)
class Check:
    """One preflight line."""

    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Sources:
    """Where the checks look."""

    now_path: Path
    key_file: Path
    heartbeat_file: Path
    playtime_state: Path
    claims_dir: Path | None


def default_sources() -> Sources:
    """The deployed locations."""
    return Sources(
        now_path=facts.default_now_path(),
        key_file=facts.HMAC_KEY_FILE,
        heartbeat_file=heartbeats.default_file(),
        playtime_state=phase2.default_state(),
        claims_dir=None,
    )


def _unit_state(capture: Capture, unit: str, *, user: bool) -> str:
    argv = ["systemctl", *(["--user"] if user else []), "is-active", unit]
    out = capture(argv)
    return out.strip() if out else "not active"


def _watcher(capture: Capture, src: Sources, ts: float) -> Check:
    state = _unit_state(capture, WATCHER_UNIT, user=True)
    fresh = facts.read_now(src.now_path, ts, NOW_MAX_AGE, src.key_file) is not None
    detail = f"{WATCHER_UNIT} {state}; now.json " + (
        "fresh" if fresh else "missing, stale or badly signed"
    )
    return Check("watcher", state == "active" and fresh, detail)


def _extensions(src: Sources, ts: float) -> list[Check]:
    seen = heartbeats.load(src.heartbeat_file)
    checks = []
    for browser in EXTENSION_BROWSERS:
        last = seen.get(browser)
        if last is None:
            checks.append(Check(f"extension {browser}", ok=False, detail="never seen"))
            continue
        age = ts - last
        detail = f"last report {age / 3600:.1f} h ago"
        checks.append(Check(f"extension {browser}", age <= HEARTBEAT_MAX_AGE, detail))
    return checks


def _enforcer_problem(doc: dict[str, object] | None, ts: float) -> str | None:
    if doc is None:
        return "playtime_state.json unreadable"
    missing = [k for k in phase2.SHADOW_KEYS if k not in doc]
    if missing:
        return "no " + ", ".join(missing)
    if doc.get("day_key") != gaming_day(ts).isoformat():
        return f"day_key {doc.get('day_key')!r} is not today"
    tick = phase2.number(doc.get("last_tick_at"))
    if tick is None or ts - tick > TICK_MAX_AGE:
        return "last tick over a minute ago"
    return None


def _enforcer(capture: Capture, src: Sources, ts: float) -> Check:
    state = _unit_state(capture, ENFORCER_UNIT, user=False)
    problem = _enforcer_problem(phase2.read_state(src.playtime_state), ts)
    detail = f"{ENFORCER_UNIT} {state}; " + (problem or "shadow fields fresh")
    return Check("enforcer", state == "active" and problem is None, detail)


def _gatelock(src: Sources) -> Check:
    old = lockstate.claims_without_grab_held(src.claims_dir)
    if old:
        return Check("gatelock", ok=False, detail="no grab_held: " + ", ".join(old))
    return Check("gatelock", ok=True, detail="every live claim carries grab_held")


def preflight(capture: Capture, src: Sources, ts: float) -> list[Check]:
    """Run every check once."""
    return [
        _watcher(capture, src, ts),
        *_extensions(src, ts),
        _enforcer(capture, src, ts),
        _gatelock(src),
    ]


def render(checks: list[Check]) -> list[str]:
    """One report line per check."""
    return [f"  [{'ok' if c.ok else 'FAIL'}] {c.name}: {c.detail}" for c in checks]
