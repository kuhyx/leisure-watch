"""Contract C3, additive in 0.2.1: ``reasons[].start`` (PID-reuse defence)."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from leisure_watch import facts
from leisure_watch.facts import Reason, read_now, write_now
from tests.test_facts import TS, _now

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"0123456789abcdef0123456789abcdef"


@pytest.fixture
def key_file(tmp_path: Path) -> Path:
    path = tmp_path / "hmac.key"
    path.write_bytes(KEY + b"\n")
    return path


def test_start_is_optional_and_round_trips(tmp_path: Path, key_file: Path) -> None:
    started = Reason("game", "steam:1", 31, "x", start=123456)
    now = replace(_now(), reasons=(started, *_now().reasons))
    doc = facts.to_doc(now)
    assert doc["reasons"] == [
        {"source": "game", "key": "steam:1", "pid": 31, "label": "x", "start": 123456},
        {"source": "media", "key": "app:mpv", "pid": 1234, "label": "YouTube — mpv"},
    ]
    path = tmp_path / "now.json"
    write_now(path, now, key_file)
    assert read_now(path, TS, key_file=key_file) == now
    # A 0.2.0 document (no "start" anywhere) still parses: start is additive.
    assert facts.parse_doc(facts.to_doc(_now())) == _now()


@pytest.mark.parametrize("start", ["1", True, 1.5, []])
def test_bad_start_is_malformed(start: object) -> None:
    doc = facts.to_doc(_now())
    doc["reasons"] = [
        {"source": "game", "key": "k", "pid": 1, "label": "l", "start": start}
    ]
    assert facts.parse_doc(doc) is None


def test_null_start_reads_as_unknown() -> None:
    doc = facts.to_doc(_now())
    doc["reasons"] = [
        {"source": "game", "key": "k", "pid": 1, "label": "l", "start": None}
    ]
    parsed = facts.parse_doc(doc)
    assert parsed is not None
    assert parsed.reasons[0].start is None
