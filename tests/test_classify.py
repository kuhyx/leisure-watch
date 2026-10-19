"""Tests for the classifier: snapshot in, state + reasons out (Phase 1 done #1)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from leisure_watch._browser import ExtReport
from leisure_watch._sensors import SinkInput, Window
from leisure_watch.allowlist import load_allowlist
from leisure_watch.classify import Settings, Snapshot, classify
from tests._proc_helpers import fake_pid

T = 1_760_000_000.0
SETTINGS = Settings(allow=load_allowlist(None), src_root=Path("/home/kuhy/src"))
HELIUM = Window(100, "helium", "Helium", "YouTube - Helium")
BASE = Snapshot(
    ts=T,
    display_ok=True,
    window=None,
    idle=1.0,
    sinks=(),
    games={},
    paused_by=None,
    reports={},
)


def _report(
    url: str,
    *,
    age: float = 1.0,
    audible: tuple[str, ...] = (),
    browser: str = "helium",
) -> dict[str, ExtReport]:
    return {browser: ExtReport(browser, url, "YouTube", True, audible, T - age)}


def _keys(snap: Snapshot) -> tuple[str, list[tuple[str, str]]]:
    now = classify(snap, SETTINGS)
    return now.state, [(r.source, r.key) for r in now.reasons]


class TestPhaseOneCases:
    def test_helium_on_youtube_is_leisure(self) -> None:
        snap = replace(
            BASE, window=HELIUM, reports=_report("https://www.youtube.com/w")
        )
        assert _keys(snap) == ("leisure", [("focus", "domain:youtube.com")])
        assert classify(snap, SETTINGS).focus.domain == "youtube.com"

    def test_helium_on_github_is_free(self) -> None:
        snap = replace(BASE, window=HELIUM, reports=_report("https://github.com/x"))
        assert _keys(snap) == ("free", [])

    def test_terminator_is_free(self) -> None:
        snap = replace(BASE, window=Window(5, "terminator", "Terminator", "zsh"))
        assert _keys(snap) == ("free", [])

    def test_unfocused_mpv_playing_is_leisure(self) -> None:
        snap = replace(BASE, sinks=(SinkInput(9, "mpv", "x — mpv"),))
        assert _keys(snap) == ("leisure", [("media", "app:mpv")])

    def test_held_grab_pauses(self) -> None:
        snap = replace(
            BASE, sinks=(SinkInput(9, "mpv", "x"),), paused_by="gatelock:leetcode_guard"
        )
        now = classify(snap, SETTINGS)
        assert (now.state, now.paused_by) == ("paused", "gatelock:leetcode_guard")

    def test_stale_extension_fails_closed(self) -> None:
        snap = replace(
            BASE, window=HELIUM, reports=_report("https://github.com", age=16)
        )
        assert _keys(snap) == ("leisure", [("failclosed", "failclosed:helium")])

    def test_no_extension_report_fails_closed(self) -> None:
        snap = replace(BASE, window=Window(3, "Navigator", "librewolf", "x"))
        assert _keys(snap) == ("leisure", [("failclosed", "failclosed:librewolf")])


class TestFocus:
    def test_idle_focus_does_not_count(self) -> None:
        snap = replace(BASE, idle=180.0, window=Window(5, "mpv", "mpv", "x"))
        assert _keys(snap) == ("free", [])
        assert classify(snap, SETTINGS).focus.idle

    def test_unknown_idle_counts(self) -> None:
        snap = replace(BASE, idle=None, window=Window(5, "mpv", "mpv", "x"))
        assert _keys(snap) == ("leisure", [("focus", "app:mpv")])

    def test_other_browser_counts_in_full(self) -> None:
        snap = replace(BASE, window=Window(5, "chromium", "Chromium", "x"))
        assert _keys(snap) == ("leisure", [("failclosed", "browser:chromium")])

    def test_tk_window_by_title(self) -> None:
        free = replace(BASE, window=Window(5, "__main__", "Tk", "Workout Locker"))
        assert _keys(free) == ("free", [])
        tk = replace(BASE, window=Window(5, "__main__", "Tk", "Some tool"))
        assert _keys(tk) == ("leisure", [("focus", "tk:Some tool")])

    def test_wsg_reviewer_counts(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 20, "python3", "-m", "wsg_grabber", "review")
        snap = replace(BASE, window=Window(20, "__main__", "Tk", "/wsg/ — kept 3"))
        assert _keys(snap) == ("leisure", [("focus", "app:wsg-grabber")])

    def test_godot(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 7, "godot", "-e", exe="/usr/bin/godot")
        fake_pid(fake_proc, 8, exe="/home/kuhy/Games/x/Brotato.x86_64")
        editor = replace(BASE, window=Window(7, "Godot", "Godot", "Editor"))
        assert _keys(editor) == ("free", [])
        export = replace(BASE, window=Window(8, "Godot_Engine", "Godot", "Brotato"))
        assert _keys(export) == ("leisure", [("focus", "app:brotato.x86_64")])

    def test_desktop_and_unreachable_display(self) -> None:
        assert classify(BASE, SETTINGS).focus.app == "desktop"
        dead = replace(BASE, display_ok=False)
        assert classify(dead, SETTINGS).focus.app == "unknown"

    def test_window_without_class(self) -> None:
        snap = replace(BASE, window=Window(5, "", "", ""))
        assert _keys(snap) == ("leisure", [("focus", "app:?")])


class TestMedia:
    def test_allowlisted_app_audio_is_free(self) -> None:
        snap = replace(BASE, sinks=(SinkInput(9, "blender", "x"),))
        assert _keys(snap) == ("free", [])

    def test_scrape_audio_never_counts(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 10, "python3", "-m", "wsg_grabber", "scrape")
        fake_pid(fake_proc, 11, "mpv", ppid=10)
        snap = replace(BASE, sinks=(SinkInput(11, "mpv", "x"),))
        assert _keys(snap) == ("free", [])

    def test_reviewer_mpv_counts_as_wsg(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 20, "wsg-grabber", "review")
        fake_pid(fake_proc, 21, "mpv", ppid=20)
        snap = replace(BASE, sinks=(SinkInput(21, "mpv", "x"),))
        assert _keys(snap) == ("leisure", [("media", "app:wsg-grabber")])

    def test_fresh_extension_uses_audible_tabs(self) -> None:
        reports = _report(
            "https://github.com",
            audible=("https://www.youtube.com/w", "https://claude.ai/"),
        )
        snap = replace(BASE, reports=reports, sinks=(SinkInput(9, "helium", "x"),))
        assert _keys(snap) == ("leisure", [("media", "domain:youtube.com")])

    def test_stale_extension_bills_browser_audio(self) -> None:
        reports = _report(
            "https://github.com", age=30, audible=("https://youtube.com",)
        )
        snap = replace(BASE, reports=reports, sinks=(SinkInput(9, "helium", "x"),))
        assert _keys(snap) == ("leisure", [("media", "app:helium")])

    def test_duplicates_bill_once(self) -> None:
        sinks = (SinkInput(9, "mpv", "a"), SinkInput(9, "mpv", "b"))
        assert _keys(replace(BASE, sinks=sinks)) == ("leisure", [("media", "app:mpv")])


class TestGamesAndExtensions:
    def test_games_count(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 31, "Cyberpunk2077.e")
        snap = replace(BASE, games={31: "app:1091500", 32: "proc:osu-lazer"})
        now = classify(snap, SETTINGS)
        assert [(r.key, r.label) for r in now.reasons] == [
            ("steam:1091500", "Cyberpunk2077.e"),
            ("proc:osu-lazer", "proc:osu-lazer"),
        ]

    def test_extension_timestamps(self) -> None:
        now = classify(replace(BASE, reports=_report("x", age=3)), SETTINGS)
        assert now.extensions == {"helium": T - 3, "librewolf": None}

    @pytest.mark.parametrize("browser", ["helium", "librewolf"])
    def test_report_matches_its_own_browser(self, browser: str) -> None:
        other = "librewolf" if browser == "helium" else "helium"
        win = HELIUM if browser == "helium" else Window(3, "Navigator", "librewolf", "")
        snap = replace(
            BASE, window=win, reports=_report("https://github.com", browser=other)
        )
        assert _keys(snap)[1] == [("failclosed", f"failclosed:{browser}")]
