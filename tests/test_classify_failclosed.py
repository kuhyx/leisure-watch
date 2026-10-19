"""Fail-closed classification: unknowable focus, private windows, browser audio."""

from __future__ import annotations

from dataclasses import replace

import pytest

from leisure_watch import _sensors
from leisure_watch._browser import ExtReport
from leisure_watch._sensors import SinkInput, Window
from leisure_watch.classify import Snapshot, classify
from tests.test_classify import BASE, HELIUM, SETTINGS, T

LIBREWOLF = Window(3, "Navigator", "librewolf", "GitHub — LibreWolf")


def _keys(snap: Snapshot) -> tuple[str, list[tuple[str, str]]]:
    now = classify(snap, SETTINGS)
    return now.state, [(r.source, r.key) for r in now.reasons]


def _report(
    browser: str = "helium",
    *,
    title: str = "YouTube",
    focused: bool = True,
    audible: tuple[str, ...] = (),
    incognito: bool = False,
) -> dict[str, ExtReport]:
    url = "https://github.com/"
    report = ExtReport(browser, url, title, focused, audible, T - 1, incognito)
    return {browser: report}


class TestUnknowableFocus:
    def test_unreachable_display_fails_closed(self) -> None:
        dead = replace(BASE, display_ok=False, idle=None)
        assert _keys(dead) == ("leisure", [("failclosed", "failclosed:display")])
        assert classify(dead, SETTINGS).focus.app == "unknown"

    def test_unreadable_window_fails_closed(self) -> None:
        snap = replace(BASE, window=_sensors.UNREADABLE)
        assert _keys(snap) == ("leisure", [("failclosed", "failclosed:window")])
        assert classify(snap, SETTINGS).focus.app == "unknown"

    def test_idle_with_unreadable_window_is_free(self) -> None:
        snap = replace(BASE, window=_sensors.UNREADABLE, idle=600.0)
        assert _keys(snap) == ("free", [])

    def test_empty_workspace_is_free(self) -> None:
        assert _keys(BASE) == ("free", [])
        assert classify(BASE, SETTINGS).focus.app == "desktop"


class TestTitleAllowlistIsTkOnly:
    def test_mpv_titled_like_a_locker_counts(self) -> None:
        snap = replace(BASE, window=Window(5, "mpv", "mpv", "Workout Locker.mkv"))
        assert _keys(snap) == ("leisure", [("focus", "app:mpv")])


class TestPrivateAndUnreportedWindows:
    def test_focused_window_the_extension_cannot_see(self) -> None:
        """An incognito window without extension access: report.focused is False."""
        snap = replace(BASE, window=HELIUM, reports=_report(focused=False))
        assert _keys(snap) == (
            "leisure",
            [("failclosed", "failclosed:helium:unreported")],
        )

    def test_private_title_not_reported_as_private(self) -> None:
        win = replace(LIBREWOLF, title="GitHub — LibreWolf Private Browsing")
        reports = _report("librewolf", title="GitHub")
        snap = replace(BASE, window=win, reports=reports)
        key = "failclosed:librewolf:private"
        assert _keys(snap) == ("leisure", [("failclosed", key)])

    def test_reported_private_window_is_classified(self) -> None:
        win = replace(LIBREWOLF, title="GitHub — LibreWolf Private Browsing")
        reports = _report("librewolf", title="GitHub", incognito=True)
        assert _keys(replace(BASE, window=win, reports=reports)) == ("free", [])

    def test_tab_title_must_match_the_window(self) -> None:
        snap = replace(BASE, window=HELIUM, reports=_report(title="GitHub"))
        assert _keys(snap) == ("leisure", [("failclosed", "failclosed:helium:title")])

    @pytest.mark.parametrize(
        ("win_title", "tab_title"),
        [
            ("Hello World - Helium", "Hello  World"),  # Chromium collapses spaces
            ("LibreWolf", "New Tab"),  # bare browser title: nothing to compare
            ("GitHub — LibreWolf", ""),  # blank tab title
        ],
    )
    def test_titles_that_agree(self, win_title: str, tab_title: str) -> None:
        snap = replace(
            BASE,
            window=replace(LIBREWOLF, title=win_title),
            reports=_report("librewolf", title=tab_title),
        )
        assert _keys(snap) == ("free", [])


class TestBrowserAudio:
    def test_playing_sink_without_an_audible_tab_fails_closed(self) -> None:
        snap = replace(BASE, reports=_report(), sinks=(SinkInput(9, "helium", "x"),))
        assert _keys(snap) == ("leisure", [("failclosed", "failclosed:helium:audio")])

    def test_audible_tab_explains_the_sink(self) -> None:
        reports = _report(audible=("https://claude.ai/",))
        snap = replace(BASE, reports=reports, sinks=(SinkInput(9, "helium", "x"),))
        assert _keys(snap) == ("free", [])
