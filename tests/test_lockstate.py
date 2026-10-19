"""Tests for the lock pause: held gatelock grabs and i3lock (Q7, C2)."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from typing import IO, TYPE_CHECKING

import pytest

from leisure_watch import lockstate
from tests._safe_helpers import call_within

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _claim(claims: Path, name: str, **fields: object) -> Path:
    claims.mkdir(parents=True, exist_ok=True)
    body = {"app": "leetcode_guard", "rank": 150, "pid": 1, "grab": "global"}
    body.update(fields)
    path = claims / f"{name}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


@contextmanager
def _held(path: Path) -> Iterator[IO[str]]:
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield handle


class TestHeldGrabs:
    def test_live_claim_without_grab_held_counts_when_grabbing(
        self, tmp_path: Path
    ) -> None:
        """Old writers: missing grab_held means grab != "none"."""
        path = _claim(tmp_path, "a")
        with _held(path):
            assert lockstate.held_grab_apps(tmp_path) == ("leetcode_guard",)

    def test_released_grab_does_not_pause(self, tmp_path: Path) -> None:
        """Leetcode study mode releases the grab -> not paused."""
        path = _claim(tmp_path, "a", grab_held=False)
        with _held(path):
            assert lockstate.held_grab_apps(tmp_path) == ()

    def test_grab_none_does_not_pause(self, tmp_path: Path) -> None:
        path = _claim(tmp_path, "a", grab="none", grab_held=True)
        with _held(path):
            assert lockstate.held_grab_apps(tmp_path) == ()

    def test_dead_owner_is_ignored_and_not_reaped(self, tmp_path: Path) -> None:
        path = _claim(tmp_path, "a", grab_held=True)
        assert lockstate.held_grab_apps(tmp_path) == ()
        assert path.exists()

    def test_highest_rank_first(self, tmp_path: Path) -> None:
        low = _claim(tmp_path, "low", app="meal_gate", rank=10)
        high = _claim(tmp_path, "high", app="workout_locker", rank=300)
        with _held(low), _held(high):
            assert lockstate.held_grab_apps(tmp_path) == (
                "workout_locker",
                "meal_gate",
            )

    @pytest.mark.parametrize(
        "text", ["", "{bad", "[1]", '{"app": 1, "grab": "global"}', '{"rank": "x"}']
    )
    def test_unusable_files_are_skipped(self, tmp_path: Path, text: str) -> None:
        tmp_path.joinpath("x.json").write_text(text, encoding="utf-8")
        with _held(tmp_path / "x.json"):
            assert lockstate.held_grab_apps(tmp_path) == ()

    def test_missing_dir(self, tmp_path: Path) -> None:
        assert lockstate.held_grab_apps(tmp_path / "nope") == ()

    def test_unopenable_claim(self, tmp_path: Path) -> None:
        (tmp_path / "d.json").mkdir()
        assert lockstate.held_grab_apps(tmp_path) == ()

    def test_flock_error_other_than_contention(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _claim(tmp_path, "a")

        def boom(_fd: int, _op: int) -> None:
            raise OSError(9, "bad fd")

        monkeypatch.setattr("leisure_watch.lockstate.fcntl.flock", boom)
        assert lockstate.held_grab_apps(tmp_path) == ()


class TestPausedBy:
    def test_gatelock_wins(self, tmp_path: Path, fake_proc: Path) -> None:
        path = _claim(tmp_path, "a")
        (fake_proc / "77").mkdir()
        (fake_proc / "77" / "comm").write_text("i3lock\n", encoding="utf-8")
        with _held(path):
            assert lockstate.paused_by(tmp_path) == "gatelock:leetcode_guard"

    def test_i3lock(self, tmp_path: Path, fake_proc: Path) -> None:
        (fake_proc / "77").mkdir()
        (fake_proc / "77" / "comm").write_text("i3lock\n", encoding="utf-8")
        assert lockstate.paused_by(tmp_path) == "i3lock"

    def test_nothing(self, tmp_path: Path) -> None:
        assert lockstate.paused_by(tmp_path) is None


class TestClaimsDir:
    def test_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GATELOCK_RUNTIME_DIR", "/x")
        assert str(lockstate.default_claims_dir()) == "/x/claims"

    def test_root_reads_the_desktop_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GATELOCK_RUNTIME_DIR", raising=False)
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/0")
        monkeypatch.setattr("os.getuid", lambda: 0)
        assert str(lockstate.default_claims_dir()) == "/run/user/1000/gatelock/claims"

    def test_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GATELOCK_RUNTIME_DIR", raising=False)
        monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
        monkeypatch.setattr("os.getuid", lambda: 1001)
        assert str(lockstate.default_claims_dir()) == "/run/user/1001/gatelock/claims"
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/rt")
        assert str(lockstate.default_claims_dir()) == "/run/rt/gatelock/claims"

    def test_default_dir_used(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path))
        path = _claim(tmp_path / "claims", "a")
        with _held(path):
            assert lockstate.paused_by() == "gatelock:leetcode_guard"


def test_claim_vanishing_before_the_open(tmp_path: Path) -> None:
    assert lockstate._live_grab(tmp_path / "gone.json") is None


def test_concurrent_reader_does_not_fake_a_live_owner(tmp_path: Path) -> None:
    """Root enforcer and user watcher probe the same dead claim at once."""
    path = _claim(tmp_path, "a", grab_held=True)
    with path.open("r", encoding="utf-8") as other_reader:
        fcntl.flock(other_reader.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        assert lockstate.held_grab_apps(tmp_path) == ()


def test_probe_never_modifies_the_claims_dir(tmp_path: Path) -> None:
    path = _claim(tmp_path, "a", grab_held=True)
    before = (sorted(p.name for p in tmp_path.iterdir()), path.stat().st_mtime_ns)
    lockstate.held_grab_apps(tmp_path)
    after = (sorted(p.name for p in tmp_path.iterdir()), path.stat().st_mtime_ns)
    assert before == after


class TestHostileClaims:
    """The claims dir is user-writable and root reads it: skip, never hang/raise."""

    def test_fifo_is_skipped(self, tmp_path: Path) -> None:
        live = _claim(tmp_path, "live")
        os.mkfifo(tmp_path / "fifo.json")
        with _held(live):
            found = call_within(lambda: lockstate.held_grab_apps(tmp_path))
        assert found == ("leetcode_guard",)

    def test_symlink_is_skipped(self, tmp_path: Path) -> None:
        target = _claim(tmp_path / "elsewhere", "a")
        claims = tmp_path / "claims"
        claims.mkdir()
        (claims / "a.json").symlink_to(target)
        with _held(target):
            assert lockstate.held_grab_apps(claims) == ()

    @pytest.mark.parametrize(
        "data", [b"[" * 100_000 + b"]" * 100_000, b'{"app": "\xff", "grab": "x"}']
    )
    def test_undecodable_is_skipped(self, tmp_path: Path, data: bytes) -> None:
        path = tmp_path / "x.json"
        path.write_bytes(data)
        with _held(path):
            assert lockstate.held_grab_apps(tmp_path) == ()

    def test_oversize_is_skipped(self, tmp_path: Path) -> None:
        path = _claim(tmp_path, "a", pad="x" * 70_000)
        with _held(path):
            assert lockstate.held_grab_apps(tmp_path) == ()


class TestWithoutGrabHeld:
    """go-live preflight: every LIVE claim must carry ``grab_held`` (C2)."""

    def test_live_old_writer_claim_is_reported(self, tmp_path: Path) -> None:
        path = _claim(tmp_path, "a", app="meal_gate")
        with _held(path):
            assert lockstate.claims_without_grab_held(tmp_path) == ("meal_gate",)

    def test_claims_with_grab_held_pass(self, tmp_path: Path) -> None:
        a = _claim(tmp_path, "a", grab_held=False)
        b = _claim(tmp_path, "b", grab="none", grab_held=True)
        with _held(a), _held(b):
            assert lockstate.claims_without_grab_held(tmp_path) == ()

    def test_dead_claims_are_ignored(self, tmp_path: Path) -> None:
        _claim(tmp_path, "a")
        assert lockstate.claims_without_grab_held(tmp_path) == ()

    def test_unnamed_app(self, tmp_path: Path) -> None:
        path = _claim(tmp_path, "a", app=7)
        with _held(path):
            assert lockstate.claims_without_grab_held(tmp_path) == ("?",)

    @pytest.mark.parametrize("text", ["", "{bad", "[1]"])
    def test_undecodable_is_never_locked(self, tmp_path: Path, text: str) -> None:
        tmp_path.joinpath("x.json").write_text(text, encoding="utf-8")
        assert lockstate.claims_without_grab_held(tmp_path) == ()

    def test_fifo_is_skipped(self, tmp_path: Path) -> None:
        os.mkfifo(tmp_path / "f.json")
        assert lockstate.claims_without_grab_held(tmp_path) == ()

    def test_missing_dir_and_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert lockstate.claims_without_grab_held(tmp_path / "nope") == ()
        monkeypatch.setenv("GATELOCK_RUNTIME_DIR", str(tmp_path / "gl"))
        assert lockstate.claims_without_grab_held() == ()
