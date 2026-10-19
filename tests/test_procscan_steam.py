"""Tests for the SteamAppId / comm scanners (moved from the enforcer)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from leisure_watch.procscan import (
    get_pids_by_process_names,
    get_running_steam_game_pids,
)

if TYPE_CHECKING:
    from pathlib import Path


def _pid(proc: Path, pid: int) -> Path:
    entry = proc / str(pid)
    entry.mkdir()
    return entry


class TestGetRunningPids:
    def test_finds_steam_pid(self, fake_proc: Path) -> None:
        environ = b"HOME=/home/user\x00SteamAppId=440\x00PATH=/usr/bin"
        (_pid(fake_proc, 12345) / "environ").write_bytes(environ)
        assert get_running_steam_game_pids() == {12345: 440}

    def test_skips_non_digit_entries(self, fake_proc: Path) -> None:
        (fake_proc / "self").mkdir()
        (fake_proc / "cpuinfo").touch()
        assert get_running_steam_game_pids() == {}

    def test_handles_unreadable_environ(self, fake_proc: Path) -> None:
        _pid(fake_proc, 99)
        assert get_running_steam_game_pids() == {}

    def test_skips_non_digit_steam_app_id(self, fake_proc: Path) -> None:
        (_pid(fake_proc, 100) / "environ").write_bytes(b"SteamAppId=notanumber\x00")
        assert get_running_steam_game_pids() == {}

    def test_no_steam_env(self, fake_proc: Path) -> None:
        environ = b"HOME=/home/user\x00PATH=/usr/bin\x00"
        (_pid(fake_proc, 200) / "environ").write_bytes(environ)
        assert get_running_steam_game_pids() == {}


class TestGetPidsByProcessNames:
    def test_finds_matching_comm(self, fake_proc: Path) -> None:
        (_pid(fake_proc, 12345) / "comm").write_text("lutris\n", encoding="utf-8")
        assert get_pids_by_process_names(frozenset({"lutris"})) == {12345: "lutris"}

    def test_no_match_returns_empty(self, fake_proc: Path) -> None:
        (_pid(fake_proc, 12345) / "comm").write_text("bash\n", encoding="utf-8")
        assert get_pids_by_process_names(frozenset({"lutris"})) == {}

    def test_skips_non_digit_entries(self, fake_proc: Path) -> None:
        (fake_proc / "self").mkdir()
        assert get_pids_by_process_names(frozenset({"lutris"})) == {}

    def test_handles_missing_comm_file(self, fake_proc: Path) -> None:
        _pid(fake_proc, 42)
        assert get_pids_by_process_names(frozenset({"lutris"})) == {}

    def test_truncates_long_names_to_15_chars(self, fake_proc: Path) -> None:
        """The kernel truncates /proc/[pid]/comm to 15 chars."""
        (_pid(fake_proc, 777) / "comm").write_text(
            "EpicGamesLaunch\n", encoding="utf-8"
        )
        result = get_pids_by_process_names(frozenset({"EpicGamesLauncher"}))
        assert result == {777: "EpicGamesLauncher"}
