"""Tests for the Godot (Q22) and wsg-grabber (Q7) process rules."""

from __future__ import annotations

from pathlib import Path

import pytest

from leisure_watch import _proctree
from leisure_watch._rules import godot_free, is_godot, wsg_role
from tests._proc_helpers import fake_pid

SRC = Path("/home/kuhy/src")


class TestGodot:
    def test_detects_by_class_or_exe(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 5, exe="/usr/bin/godot")
        assert is_godot(5, "", "")
        assert is_godot(0, "Godot_Engine", "")
        assert not is_godot(0, "mpv", "mpv")

    @pytest.mark.parametrize(
        ("argv", "cwd", "free"),
        [
            (("godot",), "", True),  # project manager
            (("godot", "-e", "--path", "/opt/x"), "", True),  # editor
            (("godot", "--path", "/opt/x", "--remote-debug", "tcp://"), "", True),
            (("godot", "--path", "/home/kuhy/src/legatus"), "", True),
            (("godot", "--path=/home/kuhy/src/legatus"), "", True),
            (("godot", "--path", "legatus"), "/home/kuhy/src", True),
            (("godot", "--path", "/home/kuhy/Downloads/game"), "/", False),
            (("godot", "--path"), "", True),
        ],
    )
    def test_editor_binary(
        self, fake_proc: Path, argv: tuple[str, ...], cwd: str, free: bool
    ) -> None:
        fake_pid(fake_proc, 7, *argv, exe="/usr/bin/godot", cwd=cwd)
        assert godot_free(7, SRC) is free

    def test_export_in_a_repo_is_free(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 8, exe="/home/kuhy/src/legatus/build/legatus.x86_64")
        assert godot_free(8, SRC)

    def test_itch_build_counts(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 9, exe="/home/kuhy/Games/brotato/Brotato.x86_64")
        assert not godot_free(9, SRC)

    def test_gone_process_counts(self) -> None:
        assert not godot_free(4242, SRC)


class TestWsg:
    def test_scrape_never_counts(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 10, "python3", "-m", "wsg_grabber", "scrape")
        fake_pid(fake_proc, 11, "chromium", "--headless", ppid=10)
        assert wsg_role(11) == "scrape"

    def test_reviewer_and_its_mpv(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 20, "/usr/local/bin/wsg-grabber", "review")
        fake_pid(fake_proc, 21, "mpv", "--wid=1", ppid=20)
        assert wsg_role(21) == "reviewer"

    def test_unrelated(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 30, "mpv", "x.mkv")
        assert wsg_role(30) is None


class TestProctree:
    def test_unreadable_entries(self, fake_proc: Path) -> None:
        assert _proctree.argv(1) == ()
        assert _proctree.comm(1) == ""
        assert _proctree.ppid(1) == 0
        (fake_proc / "3").mkdir()
        (fake_proc / "3" / "stat").write_text("3 (x)", encoding="utf-8")
        assert _proctree.ppid(3) == 0

    def test_cycle_and_init_stop_the_walk(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 40, ppid=41)
        fake_pid(fake_proc, 41, ppid=40)
        assert _proctree.ancestry(40) == (40, 41)

    def test_pids_named(self, fake_proc: Path) -> None:
        fake_pid(fake_proc, 50, "i3lock")
        (fake_proc / "self").mkdir()
        assert _proctree.pids_named("i3lock") == (50,)

    def test_pids_named_without_proc(
        self, fake_proc: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(_proctree, "_PROC", fake_proc / "nope")
        assert _proctree.pids_named("i3lock") == ()
