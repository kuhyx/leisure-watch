"""Tests for the hostile-file-safe reader root uses on user-writable paths."""

from __future__ import annotations

from functools import partial
import os
from typing import TYPE_CHECKING

from leisure_watch import _safeio
from tests._safe_helpers import call_within

if TYPE_CHECKING:
    from pathlib import Path


def test_regular_file_within_the_cap(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"x" * _safeio.MAX_BYTES)
    assert _safeio.read_regular(path) == b"x" * _safeio.MAX_BYTES


def test_over_the_cap(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"x" * 11)
    assert _safeio.read_regular(path, limit=10) is None


def test_not_regular_or_symlinked(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "fifo")
    (tmp_path / "dir").mkdir()
    (tmp_path / "real").write_bytes(b"{}")
    (tmp_path / "link").symlink_to(tmp_path / "real")
    for name in ("fifo", "dir", "link", "missing"):
        path = tmp_path / name
        assert call_within(partial(_safeio.read_regular, path)) is None


def test_read_error_is_none() -> None:
    assert _safeio.read_fd(-1) is None


def test_json_object() -> None:
    assert _safeio.json_object(b'{"a": 1}') == {"a": 1}
    for bad in (None, b"[1]", b"{bad", b"\xff", b"[" * 100_000 + b"]" * 100_000):
        assert _safeio.json_object(bad) is None
