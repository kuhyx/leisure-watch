"""Tests for the publish loop."""

from __future__ import annotations

from dataclasses import replace
import json
import threading
import time
from typing import TYPE_CHECKING

from leisure_watch import heartbeats, watcher
from leisure_watch._browser import ExtReport
from leisure_watch._sensors import SinkInput
from leisure_watch.classify import Snapshot
from leisure_watch.extserver import ReportStore
from leisure_watch.facts import read_now
from leisure_watch.watcher import Config, Watcher, gather, launcher_switch

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

KEY = b"k" * 32


def _cfg(tmp_path: Path, interval: float = 0.05) -> Config:
    (tmp_path / "key").write_bytes(KEY)
    return Config(
        port=0,
        interval=interval,
        now_path=tmp_path / "rt" / "now.json",
        key_file=tmp_path / "key",
        log_dir=tmp_path / "log",
        allowlist_file=tmp_path / "allow.toml",
        counted_config=tmp_path / "sbe.json",
        claims_dir=tmp_path / "claims",
        heartbeat_file=tmp_path / "state" / "ext.json",
        playtime_state=tmp_path / "pt.json",
        switch_path=tmp_path / "leisure_from",
    )


def _snap(*sinks: SinkInput) -> Snapshot:
    return Snapshot(
        ts=time.time(),
        display_ok=True,
        window=None,
        idle=0.0,
        sinks=sinks,
        games={},
        paused_by=None,
        reports={},
    )


def test_launcher_switch(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    assert launcher_switch(path).count_launchers
    path.write_text('{"count_launcher_processes": false}', encoding="utf-8")
    assert not launcher_switch(path).count_launchers
    path.write_text("[1]", encoding="utf-8")
    assert launcher_switch(path).count_launchers


def test_gather_reads_every_sensor(tmp_path: Path) -> None:
    outputs = {
        "xprop -root _NET_ACTIVE_WINDOW": "window id # 0x0",
        "xprintidle": "2000",
        "pactl -f json list sink-inputs": "[]",
    }
    snap = gather(
        _cfg(tmp_path), ReportStore(), lambda argv: outputs.get(" ".join(argv))
    )
    assert (snap.display_ok, snap.window, snap.idle, snap.sinks) == (
        True,
        None,
        2.0,
        (),
    )
    dead = gather(_cfg(tmp_path), ReportStore(), lambda _argv: None)
    assert (dead.display_ok, dead.idle) == (False, None)


def test_gather_survives_corrupt_sensor_data(tmp_path: Path) -> None:
    """A corrupt claim or undecodable tool output never kills the tick."""
    cfg = _cfg(tmp_path)
    assert cfg.claims_dir is not None
    cfg.claims_dir.mkdir()
    (cfg.claims_dir / "bad.json").write_bytes(b'{"app": "\xff", "grab": "x"}')
    (cfg.claims_dir / "deep.json").write_bytes(b"[" * 100_000 + b"]" * 100_000)
    snap = gather(cfg, ReportStore(), lambda _argv: None)
    assert snap.paused_by is None


def test_tick_publishes_signed_and_logs(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    w = Watcher(cfg, gather_fn=lambda _c, _s: _snap(SinkInput(9, "mpv", "x")))
    first = w.tick()
    second = w.tick()
    assert (first.seq, second.seq) == (1, 2)
    read = read_now(cfg.now_path, time.time(), key_file=cfg.key_file)
    assert read is not None
    assert read.state == "leisure"
    assert list(cfg.log_dir.glob("*.jsonl"))
    assert w.status_doc()["seq"] == 2


def test_allowlist_reload(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    w = Watcher(cfg, gather_fn=lambda _c, _s: _snap(SinkInput(9, "mpv", "x")))
    assert w.tick().state == "leisure"
    (tmp_path / "allow.toml").write_text(
        '[apps]\nclasses = ["mpv"]\n', encoding="utf-8"
    )
    assert w.tick().state == "free"
    no_file = Watcher(
        replace(cfg, allowlist_file=None), gather_fn=lambda _c, _s: _snap()
    )
    assert no_file.tick().state == "free"


def test_run_serves_and_wakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg(tmp_path, interval=10.0)
    calls: list[int] = []

    def fake_gather(_c: Config, _s: ReportStore) -> Snapshot:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError
        return _snap()

    w = Watcher(cfg, gather_fn=fake_gather)
    monkeypatch.setattr(watcher, "_MIN_GAP", 0.0)
    stop = threading.Event()
    thread = threading.Thread(target=w.run, args=(stop,))
    thread.start()
    for _ in range(3):
        deadline = time.time() + 2
        before = len(calls)
        w.wake()
        while len(calls) == before and time.time() < deadline:
            time.sleep(0.01)
    stop.set()
    w.wake()
    thread.join(5)
    assert not thread.is_alive()
    assert len(calls) >= 3
    assert json.loads(cfg.now_path.read_text(encoding="utf-8"))["state"] == "free"


def test_tick_persists_extension_heartbeats(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    store = ReportStore()
    store.update(ExtReport("librewolf", "about:blank", "", False, (), 1234.0))
    w = Watcher(cfg, store=store, gather_fn=lambda _c, _s: _snap())
    w.tick()
    assert heartbeats.load(cfg.heartbeat_file) == {"librewolf": 1234.0}


def test_block_status(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    w = Watcher(cfg, gather_fn=lambda _c, _s: _snap())
    doc = w.block_status()
    assert (doc["active"], doc["spent"]) == (False, False)
    cfg.switch_path.write_text("2026-01-01\n", encoding="ascii")
    doc = w.block_status()
    assert (doc["active"], doc["spent"]) == (True, True)  # no state: fail closed
    allow = doc["allow"]
    assert isinstance(allow, list)
    assert "github.com" in allow


def test_default_config_paths_follow_the_patched_modules(
    fake_switch: Path, fake_state: Path
) -> None:
    cfg = Config()
    assert (cfg.switch_path, cfg.playtime_state) == (fake_switch, fake_state)
    assert cfg.heartbeat_file == heartbeats.default_file()
