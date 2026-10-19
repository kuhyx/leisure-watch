"""Phase 2 (contract C6): is the leisure budget enforced, and is it spent?

"On today?" is ONLY ``earned_time.leisure_active(gaming day)`` -- this module
never reads the switch file itself; it only tells earned_time which path to
use (``SWITCH_PATH``, looked up at call time so tests can redirect it).

"Spent?" compares the root enforcer's ENFORCED ``seconds`` with
``budget_seconds`` in ``playtime_state.json`` for today's 06:00 gaming day:

- dormant (not active): never spent -- nothing is blocked before go-live;
- active, file unreadable / malformed: spent (fail closed: the browser
  extension blocks rather than let an unknowable budget run free);
- active, ``day_key`` of another day: 0 used yet (the enforcer has not done
  its first tick of the new gaming day; yesterday's total is not today's).

User side only (the watcher and go-live import it, root never does), so it
may import earned_time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import earned_time

from leisure_watch import _safeio
from leisure_watch.daylog import gaming_day

if TYPE_CHECKING:
    from leisure_watch.allowlist import Allowlist

SWITCH_PATH: Path = earned_time.LEISURE_FROM_PATH
PLAYTIME_STATE: Path = (
    Path.home() / ".config" / "steam_backlog_enforcer" / "playtime_state.json"
)
SHADOW_KEYS: Final = (
    "shadow_seconds",
    "shadow_budget_seconds",
    "shadow_per_source",
    "shadow_paused_seconds",
)


def default_switch() -> Path:
    """The switch file path earned_time is asked about (patchable)."""
    return SWITCH_PATH


def default_state() -> Path:
    """The enforcer's ``playtime_state.json`` (patchable)."""
    return PLAYTIME_STATE


@dataclass(frozen=True)
class Budget:
    """Today's enforced leisure: seconds used, seconds allowed, spent?"""

    used: float | None
    budget: float | None
    spent: bool


def active(ts: float, switch: Path | None = None) -> bool:
    """Whether the gaming day of *ts* is on the leisure budget (Phase 2 on)."""
    path = default_switch() if switch is None else switch
    return bool(earned_time.leisure_active(gaming_day(ts), path=path))


def read_state(path: Path | None = None) -> dict[str, object] | None:
    """The enforcer state document, or ``None`` if unreadable/not an object."""
    target = default_state() if path is None else path
    return _safeio.json_object(_safeio.read_regular(target))


def number(value: object) -> float | None:
    """*value* as a float if it is a real number (not a bool), else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def budget_today(
    ts: float, *, is_active: bool, state_path: Path | None = None
) -> Budget:
    """Today's enforced budget; see the module docstring for the edge cases."""
    if not is_active:
        return Budget(None, None, spent=False)
    doc = read_state(state_path)
    closed = Budget(None, None, spent=True)
    if doc is None or not isinstance(doc.get("day_key"), str):
        return closed
    if doc["day_key"] != gaming_day(ts).isoformat():
        return Budget(0.0, None, spent=False)
    used, budget = number(doc.get("seconds")), number(doc.get("budget_seconds"))
    if used is None or budget is None:
        return closed
    return Budget(used, budget, spent=used >= budget)


def block_doc(
    allow: Allowlist,
    ts: float,
    switch: Path | None = None,
    state_path: Path | None = None,
) -> dict[str, object]:
    """The ``GET /status`` document the browser extension enforces."""
    is_active = active(ts, switch)
    budget = budget_today(ts, is_active=is_active, state_path=state_path)
    return {
        "active": is_active,
        "spent": budget.spent,
        "allow": sorted(allow.domains),
        "local_hosts": sorted(allow.local_hosts),
        "deny_ports": sorted(allow.deny_ports),
        "used_seconds": budget.used,
        "budget_seconds": budget.budget,
        "day": gaming_day(ts).isoformat(),
    }
