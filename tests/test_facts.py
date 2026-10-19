"""Tests for the signed now.json contract (C3)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import hmac
import json
import os
import stat
from typing import TYPE_CHECKING

import pytest

from leisure_watch import _safeio, facts
from leisure_watch.facts import Focus, Now, Reason, read_now, write_now
from tests._safe_helpers import call_within

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

KEY = b"0123456789abcdef0123456789abcdef"
TS = 1_760_000_000.0


def _now() -> Now:
    return Now(
        ts=TS,
        seq=42,
        state="leisure",
        paused_by=None,
        reasons=(Reason("media", "app:mpv", 1234, "YouTube — mpv"),),
        focus=Focus("Helium", "t", "youtube.com", idle=False),
        extensions={"helium": TS, "librewolf": None},
    )


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY + b"\n")
    return path


def test_round_trip(tmp_path: Path, key_file: Path) -> None:
    path = tmp_path / "lw" / "now.json"
    write_now(path, _now(), key_file)
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert read_now(path, TS + 3, key_file=key_file) == _now()


def test_signature_is_over_the_canonical_json(tmp_path: Path, key_file: Path) -> None:
    path = tmp_path / "now.json"
    write_now(path, _now(), key_file)
    doc = json.loads(path.read_text(encoding="utf-8"))
    sig = doc.pop("sig")
    body = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    assert sig == hmac.new(KEY, body, hashlib.sha256).hexdigest()
    assert doc["v"] == 1
    assert doc["reasons"] == [
        {"source": "media", "key": "app:mpv", "pid": 1234, "label": "YouTube — mpv"}
    ]
    assert doc["focus"] == {
        "app": "Helium",
        "title": "t",
        "domain": "youtube.com",
        "idle": False,
    }


@pytest.mark.parametrize("when", [TS + 15.1, TS - 2.1])
def test_stale_or_future_is_none(tmp_path: Path, key_file: Path, when: float) -> None:
    path = tmp_path / "now.json"
    write_now(path, _now(), key_file)
    assert read_now(path, when, key_file=key_file) is None


def test_max_age_is_a_parameter(tmp_path: Path, key_file: Path) -> None:
    path = tmp_path / "now.json"
    write_now(path, _now(), key_file)
    assert read_now(path, TS + 30, max_age=60, key_file=key_file) is not None


def test_tampered_is_none(tmp_path: Path, key_file: Path) -> None:
    path = tmp_path / "now.json"
    write_now(path, _now(), key_file)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["state"] = "free"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert read_now(path, TS, key_file=key_file) is None


def test_missing_file_and_key(tmp_path: Path, key_file: Path) -> None:
    assert read_now(tmp_path / "nope.json", TS, key_file=key_file) is None
    path = tmp_path / "now.json"
    write_now(path, _now(), key_file)
    assert read_now(path, TS, key_file=tmp_path / "nokey") is None


def test_unreadable_key_writes_an_empty_signature(tmp_path: Path) -> None:
    """The enforcer then rejects it -- fail closed, never unsigned-but-trusted."""
    path = tmp_path / "now.json"
    write_now(path, _now(), tmp_path / "nokey")
    assert json.loads(path.read_text(encoding="utf-8"))["sig"] == ""


def test_empty_key_is_unreadable(tmp_path: Path) -> None:
    empty = tmp_path / "k"
    empty.write_bytes(b"\n")
    assert facts.read_key(empty) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(v=2),
        lambda d: d.update(state="bogus"),
        lambda d: d.update(ts="x"),
        lambda d: d.update(seq=True),
        lambda d: d.update(paused_by=3),
        lambda d: d.update(reasons="x"),
        lambda d: d.update(reasons=["x"]),
        lambda d: d.update(reasons=[{"source": "focus"}]),
        lambda d: d.update(focus=[]),
        lambda d: d.update(focus={"app": 1}),
        lambda d: d.update(extensions=[]),
        lambda d: d.update(extensions={"helium": "x"}),
    ],
)
def test_malformed_documents_are_none(
    mutate: Callable[[dict[str, object]], None],
) -> None:
    doc = facts.to_doc(_now())
    mutate(doc)
    assert facts.parse_doc(doc) is None


def test_non_object_json(tmp_path: Path, key_file: Path) -> None:
    path = tmp_path / "now.json"
    path.write_text("[1]", encoding="utf-8")
    assert read_now(path, TS, key_file=key_file) is None
    path.write_text("{bad", encoding="utf-8")
    assert read_now(path, TS, key_file=key_file) is None


def test_default_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1234")
    monkeypatch.setattr("os.getuid", lambda: 1234)
    assert str(facts.default_now_path()) == "/run/user/1234/leisure-watch/now.json"
    monkeypatch.setattr("os.getuid", lambda: 0)
    assert str(facts.default_now_path()) == "/run/user/1000/leisure-watch/now.json"
    monkeypatch.setattr("os.getuid", lambda: 1234)
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert str(facts.default_now_path()) == "/run/user/1234/leisure-watch/now.json"


def test_failed_write_leaves_no_temp_file(
    tmp_path: Path, key_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_self: object, _target: object) -> None:
        raise OSError(5, "boom")

    monkeypatch.setattr("leisure_watch.facts.Path.replace", boom)
    with pytest.raises(OSError, match="boom"):
        write_now(tmp_path / "now.json", _now(), key_file)
    assert list(tmp_path.glob(".now.*")) == []


@pytest.mark.parametrize(
    "raw",
    [
        {"source": "focus", "key": "k", "pid": "1", "label": "l"},
        {"source": "focus", "key": "k", "pid": None, "label": 3},
    ],
)
def test_bad_reason_fields(raw: dict[str, object]) -> None:
    doc = facts.to_doc(_now())
    doc["reasons"] = [raw]
    assert facts.parse_doc(doc) is None


def test_bad_focus_fields() -> None:
    doc = facts.to_doc(_now())
    doc["focus"] = {"app": "a", "title": "t", "domain": 3, "idle": False}
    assert facts.parse_doc(doc) is None
    doc["focus"] = {"app": "a", "title": "t", "domain": None, "idle": "no"}
    assert facts.parse_doc(doc) is None


class TestHostileFiles:
    """Root reads now.json from a user-writable dir: nothing there may hang or raise."""

    @pytest.mark.parametrize(
        "data", [b"[" * 100_000 + b"]" * 100_000, b'{"v": 1, "sig": "\xff"}']
    )
    def test_undecodable(self, tmp_path: Path, key_file: Path, data: bytes) -> None:
        path = tmp_path / "now.json"
        path.write_bytes(data)
        assert read_now(path, TS, key_file=key_file) is None

    def test_fifo_does_not_block(self, tmp_path: Path, key_file: Path) -> None:
        path = tmp_path / "now.json"
        os.mkfifo(path)
        assert call_within(lambda: read_now(path, TS, key_file=key_file)) is None

    def test_symlink_is_not_followed(self, tmp_path: Path, key_file: Path) -> None:
        real = tmp_path / "real.json"
        write_now(real, _now(), key_file)
        link = tmp_path / "now.json"
        link.symlink_to(real)
        assert read_now(link, TS, key_file=key_file) is None

    def test_oversize(self, tmp_path: Path, key_file: Path) -> None:
        label = "x" * (_safeio.MAX_BYTES + 1)
        big = replace(_now(), reasons=(Reason("focus", "app:x", None, label),))
        path = tmp_path / "now.json"
        write_now(path, big, key_file)
        assert read_now(path, TS, key_file=key_file) is None

    def test_recursion_while_verifying(
        self, tmp_path: Path, key_file: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "now.json"
        write_now(path, _now(), key_file)

        def deep(*_a: object) -> str:
            raise RecursionError

        monkeypatch.setattr("leisure_watch.facts.signature", deep)
        assert read_now(path, TS, key_file=key_file) is None
