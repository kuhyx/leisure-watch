"""Classify one snapshot of the desktop into leisure / free / paused (C3).

Pure apart from reading /proc for the Godot and wsg-grabber rules: the
watcher gathers a :class:`Snapshot`, this turns it into a :class:`Now`.
Overlapping reasons are listed once each; billing is wall-clock, so the
enforcer charges one tick however many reasons there are.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

from leisure_watch import _proctree, _rules
from leisure_watch.allowlist import host_key
from leisure_watch.facts import Focus, Now, Reason

if TYPE_CHECKING:
    from leisure_watch._sensors import SinkInput, Window
    from leisure_watch.allowlist import Allowlist

# Browsers our extension runs in; everything else in BROWSERS counts in full.
EXTENSION_BROWSERS: Final = ("helium", "librewolf")
OTHER_BROWSERS: Final = frozenset(
    {
        "chromium",
        "google-chrome",
        "brave-browser",
        "vivaldi-stable",
        "vivaldi",
        "firefox",
        "firefox-esr",
        "opera",
        "microsoft-edge",
        "thorium-browser",
        "floorp",
        "waterfox",
        "zen",
        "mullvad-browser",
        "tor browser",
    }
)


@dataclass(frozen=True)
class ExtReport:
    """The latest report one browser's extension sent."""

    browser: str
    url: str
    title: str
    focused: bool
    audible: tuple[str, ...]
    received: float


@dataclass(frozen=True)
class Snapshot:
    """Everything the classifier needs about one moment."""

    ts: float
    display_ok: bool
    window: Window | None
    idle: float | None
    sinks: tuple[SinkInput, ...]
    games: dict[int, str]
    paused_by: str | None
    reports: dict[str, ExtReport]


@dataclass(frozen=True)
class Settings:
    """Classifier policy."""

    allow: Allowlist
    idle_threshold: float = 180.0
    ext_max_age: float = 15.0
    src_root: Path = field(default_factory=lambda: Path.home() / "src")


def _fresh(snap: Snapshot, settings: Settings, browser: str) -> ExtReport | None:
    report = snap.reports.get(browser)
    if report is None or snap.ts - report.received > settings.ext_max_age:
        return None
    return report


def _browser_of(name: str) -> str | None:
    lowered = name.lower()
    if lowered in EXTENSION_BROWSERS or lowered in OTHER_BROWSERS:
        return lowered
    return None


# A focus rule either decides (True, reason-or-None-for-free) or passes.
_Verdict = tuple[bool, Reason | None]
_PASS: Final[_Verdict] = (False, None)
_FREE: Final[_Verdict] = (True, None)


def _godot_rule(_snap: Snapshot, settings: Settings, win: Window) -> _Verdict:
    if not _rules.is_godot(win.pid, win.instance, win.cls):
        return _PASS
    if _rules.godot_free(win.pid, settings.src_root):
        return _FREE
    name = Path(_proctree.exe(win.pid)).name.lower() or win.instance.lower()
    return True, Reason("focus", f"app:{name}", win.pid, win.title or name)


def _class_rule(_snap: Snapshot, settings: Settings, win: Window) -> _Verdict:
    return _FREE if settings.allow.class_allowed(win.instance, win.cls) else _PASS


def _browser_rule(snap: Snapshot, settings: Settings, win: Window) -> _Verdict:
    browser = _browser_of(win.cls) or _browser_of(win.instance)
    if browser is None:
        return _PASS
    if browser not in EXTENSION_BROWSERS:
        return True, Reason("failclosed", f"browser:{browser}", win.pid, win.title)
    report = _fresh(snap, settings, browser)
    if report is None:
        label = f"{win.cls}: extension silent > {settings.ext_max_age:g} s"
        return True, Reason("failclosed", f"failclosed:{browser}", win.pid, label)
    if settings.allow.url_allowed(report.url):
        return _FREE
    key = f"domain:{host_key(report.url)}"
    return True, Reason("focus", key, win.pid, report.title)


def _title_rule(_snap: Snapshot, settings: Settings, win: Window) -> _Verdict:
    return _FREE if settings.allow.title_allowed(win.title) else _PASS


def _fallback(win: Window) -> Reason:
    if win.title.startswith("/wsg/") or _rules.wsg_role(win.pid) == "reviewer":
        return Reason("focus", "app:wsg-grabber", win.pid, win.title)
    if win.cls == "Tk":
        return Reason("focus", f"tk:{win.title[:60]}", win.pid, win.title)
    name = (win.instance or win.cls or "?").lower()
    return Reason("focus", f"app:{name}", win.pid, win.title or name)


_FOCUS_RULES: Final = (_godot_rule, _class_rule, _browser_rule, _title_rule)


def _focus_reason(snap: Snapshot, settings: Settings, win: Window) -> Reason | None:
    for rule in _FOCUS_RULES:
        decided, reason = rule(snap, settings, win)
        if decided:
            return reason
    return _fallback(win)


def _sink_reason(snap: Snapshot, settings: Settings, sink: SinkInput) -> Reason | None:
    role = _rules.wsg_role(sink.pid) if sink.pid else None
    if role == "scrape":
        return None
    if role == "reviewer":
        return Reason("media", "app:wsg-grabber", sink.pid, sink.label)
    browser = _browser_of(sink.binary)
    if browser in EXTENSION_BROWSERS and _fresh(snap, settings, browser):
        return None  # its audible tabs speak for it
    if browser is None and settings.allow.binary_allowed(sink.binary):
        return None
    return Reason(
        "media", f"app:{sink.binary.lower() or '?'}", sink.pid or None, sink.label
    )


def _tab_reasons(snap: Snapshot, settings: Settings) -> list[Reason]:
    reasons: list[Reason] = []
    for browser in EXTENSION_BROWSERS:
        report = _fresh(snap, settings, browser)
        reasons.extend(
            Reason("media", f"domain:{host_key(url)}", None, url)
            for url in (report.audible if report else ())
            if not settings.allow.url_allowed(url)
        )
    return reasons


def _game_reason(pid: int, key: str) -> Reason:
    kind, _, ident = key.partition(":")
    out_key = f"steam:{ident}" if kind == "app" else key
    return Reason("game", out_key, pid, _proctree.comm(pid) or out_key)


def _focus(snap: Snapshot, *, idle: bool) -> Focus:
    if not snap.display_ok:
        return Focus("unknown", "", None, idle=idle)
    if snap.window is None:
        return Focus("desktop", "", None, idle=idle)
    domain = None
    browser = _browser_of(snap.window.cls) or _browser_of(snap.window.instance)
    report = snap.reports.get(browser or "")
    if report is not None and report.url:
        domain = host_key(report.url)
    return Focus(
        snap.window.cls or snap.window.instance, snap.window.title, domain, idle=idle
    )


def classify(snap: Snapshot, settings: Settings) -> Now:
    """Turn *snap* into a :class:`Now` (``seq`` 0; the watcher numbers it)."""
    idle = snap.idle is not None and snap.idle >= settings.idle_threshold
    found: list[Reason | None] = [_game_reason(p, k) for p, k in snap.games.items()]
    if snap.window is not None and not idle:
        found.append(_focus_reason(snap, settings, snap.window))
    found.extend(_sink_reason(snap, settings, s) for s in snap.sinks)
    found.extend(_tab_reasons(snap, settings))
    reasons: dict[tuple[str, str], Reason] = {}
    for reason in found:
        if reason is not None:
            reasons.setdefault((reason.source, reason.key), reason)
    busy = "leisure" if reasons else "free"
    state = "paused" if snap.paused_by else busy
    return Now(
        ts=snap.ts,
        seq=0,
        state=state,
        paused_by=snap.paused_by,
        reasons=tuple(reasons.values()),
        focus=_focus(snap, idle=idle),
        extensions={
            b: (snap.reports[b].received if b in snap.reports else None)
            for b in EXTENSION_BROWSERS
        },
    )
