"""Tests for cmdline-based process detection (moved from the enforcer)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from leisure_watch.procscan._cmdline import (
    _match_cmdline,
    get_pids_by_cmdline_names,
    process_name,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestMatchCmdline:
    def _proc(self, fake_proc: Path, pid: int, argv: list[str]) -> Path:
        entry = fake_proc / str(pid)
        entry.mkdir(parents=True, exist_ok=True)
        (entry / "cmdline").write_bytes(
            b"\x00".join(a.encode() for a in argv) + b"\x00"
        )
        return entry

    def test_direct_argv0_match(self, fake_proc: Path) -> None:
        entry = self._proc(fake_proc, 10, ["/usr/bin/lutris", "--foo"])
        assert _match_cmdline(entry, frozenset({"lutris"})) == "lutris"

    def test_interpreter_falls_through_to_argv1(self, fake_proc: Path) -> None:
        """The real case: /usr/bin/lutris is a python3 script."""
        entry = self._proc(fake_proc, 11, ["/usr/bin/python3", "/usr/bin/lutris"])
        assert _match_cmdline(entry, frozenset({"lutris"})) == "lutris"

    def test_interpreter_with_no_argv1(self, fake_proc: Path) -> None:
        entry = self._proc(fake_proc, 12, ["python3"])
        assert _match_cmdline(entry, frozenset({"lutris"})) is None

    def test_interpreter_running_something_else(self, fake_proc: Path) -> None:
        entry = self._proc(fake_proc, 13, ["python3", "/usr/bin/other"])
        assert _match_cmdline(entry, frozenset({"lutris"})) is None

    def test_non_interpreter_no_match(self, fake_proc: Path) -> None:
        entry = self._proc(fake_proc, 14, ["/usr/bin/firefox"])
        assert _match_cmdline(entry, frozenset({"lutris"})) is None

    def test_empty_cmdline(self, fake_proc: Path) -> None:
        entry = fake_proc / "15"
        entry.mkdir(parents=True, exist_ok=True)
        (entry / "cmdline").write_bytes(b"")
        assert _match_cmdline(entry, frozenset({"lutris"})) is None

    def test_unreadable_cmdline(self, fake_proc: Path) -> None:
        entry = fake_proc / "16"
        entry.mkdir(parents=True, exist_ok=True)
        assert _match_cmdline(entry, frozenset({"lutris"})) is None

    def test_undecodable_bytes_do_not_raise(self, fake_proc: Path) -> None:
        entry = fake_proc / "17"
        entry.mkdir(parents=True, exist_ok=True)
        (entry / "cmdline").write_bytes(b"\xff\xfe\x00")
        assert _match_cmdline(entry, frozenset({"lutris"})) is None


class TestGetPidsByCmdlineNames:
    def _proc(self, fake_proc: Path, pid: int, argv: list[str]) -> None:
        entry = fake_proc / str(pid)
        entry.mkdir(parents=True, exist_ok=True)
        (entry / "cmdline").write_bytes(
            b"\x00".join(a.encode() for a in argv) + b"\x00"
        )

    def test_finds_matches(self, fake_proc: Path) -> None:
        self._proc(fake_proc, 100, ["python3", "/usr/bin/lutris"])
        self._proc(fake_proc, 101, ["/usr/bin/firefox"])
        assert get_pids_by_cmdline_names(frozenset({"lutris"})) == {100: "lutris"}

    def test_skips_non_digit_entries(self, fake_proc: Path) -> None:
        (fake_proc / "cpuinfo").touch()
        (fake_proc / "self").mkdir(exist_ok=True)
        self._proc(fake_proc, 102, ["python3", "/usr/bin/lutris"])
        assert get_pids_by_cmdline_names(frozenset({"lutris"})) == {102: "lutris"}

    def test_never_matches_our_own_pid(self, fake_proc: Path) -> None:
        """The daemon is itself python3 - it must not count as a launcher."""
        self._proc(fake_proc, os.getpid(), ["python3", "/usr/bin/lutris"])
        assert get_pids_by_cmdline_names(frozenset({"lutris"})) == {}

    def test_empty_proc(self) -> None:
        assert get_pids_by_cmdline_names(frozenset({"lutris"})) == {}


class TestProcessName:
    """Tests for resolving a PID to its program name."""

    def _comm(self, fake_proc: Path, pid: int, name: str) -> None:
        entry = fake_proc / str(pid)
        entry.mkdir(parents=True, exist_ok=True)
        (entry / "comm").write_text(name, encoding="utf-8")

    def test_reads_comm(self, fake_proc: Path) -> None:
        self._comm(fake_proc, 42, "hollow_knight\n")
        assert process_name(42) == "hollow_knight"

    def test_missing_pid_is_none(self) -> None:
        # A PID recorded earlier may have exited, and the number may since have
        # been recycled — "gone" is the only safe answer.
        assert process_name(999999) is None

    def test_empty_comm_is_none(self, fake_proc: Path) -> None:
        self._comm(fake_proc, 43, "\n")
        assert process_name(43) is None
