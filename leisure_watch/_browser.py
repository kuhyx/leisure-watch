"""Browsers: which ones our extension speaks for, and when it really does (Q4/Q8).

Helium and LibreWolf run the extension; every other browser counts in full.
A fresh report only describes the focused X window when the extension says
it saw that window: focused, private-ness declared, same tab title. To X an
incognito Helium window is indistinguishable from a normal one (same class,
same title format), and without incognito access the extension reports the
last NORMAL window instead -- unfocused. So any disagreement fails closed.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

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

# Window titles are the tab title, a separator, then the browser name (with
# "Private Browsing" appended in LibreWolf private windows). A title with no
# separator is the bare browser name: a blank page, nothing to compare.
_SEPARATORS: Final = (" - ", " — ")
_PRIVATE_SUFFIXES: Final = ("private browsing", "(incognito)")
_SPACE: Final = re.compile(r"\s+")

_MISMATCH: Final = {
    "unreported": "focused window not seen by the extension (private?)",
    "private": "private window the extension did not report",
    "title": "reported tab is not the focused window",
}


@dataclass(frozen=True)
class ExtReport:
    """The latest report one browser's extension sent."""

    browser: str
    url: str
    title: str
    focused: bool
    audible: tuple[str, ...]
    received: float
    incognito: bool = False


def browser_of(name: str) -> str | None:
    """The browser a WM_CLASS / process binary names, or ``None``."""
    lowered = name.lower()
    if lowered in EXTENSION_BROWSERS or lowered in OTHER_BROWSERS:
        return lowered
    return None


def _norm(text: str) -> str:
    # Browsers collapse whitespace runs when they build the window title.
    return _SPACE.sub(" ", text).strip()


def looks_private(window_title: str) -> bool:
    """Whether the X title marks a private/incognito window."""
    return _norm(window_title).lower().endswith(_PRIVATE_SUFFIXES)


def titles_agree(window_title: str, tab_title: str) -> bool:
    """Whether the X window title is the reported tab's (when comparable)."""
    win, tab = _norm(window_title), _norm(tab_title)
    if not tab or not any(sep in win for sep in _SEPARATORS):
        return True
    return win.startswith(tab)


def mismatch(window_title: str, report: ExtReport) -> tuple[str, str] | None:
    """``(why, label)`` if *report* does not describe the focused window."""
    if not report.focused:
        why = "unreported"
    elif looks_private(window_title) and not report.incognito:
        why = "private"
    elif not titles_agree(window_title, report.title):
        why = "title"
    else:
        return None
    return why, _MISMATCH[why]
