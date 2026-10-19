"""The user watcher: gather -> classify -> publish now.json every 5 s.

Also recomputes as soon as an extension report arrives (rate-limited to one
publish per second), keeps the daily classification log, and serves the
live document on ``GET /status``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import logging
import threading
import time
from typing import TYPE_CHECKING, Final

from leisure_watch import _sensors, lockstate, procscan
from leisure_watch.allowlist import USER_ALLOWLIST, load_allowlist
from leisure_watch.classify import Settings, Snapshot, classify
from leisure_watch.daylog import DEFAULT_DIR, DayLog
from leisure_watch.extserver import PORT, ExtensionServer, ReportStore
from leisure_watch.facts import HMAC_KEY_FILE, default_now_path, signed_doc, write_now

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from leisure_watch.facts import Now

logger = logging.getLogger(__name__)

_MIN_GAP: Final = 1.0  # seconds between event-driven publishes


@dataclass(frozen=True)
class Config:
    """Where the watcher reads and writes."""

    port: int = PORT
    interval: float = 5.0
    now_path: Path = field(default_factory=default_now_path)
    key_file: Path = HMAC_KEY_FILE
    log_dir: Path = DEFAULT_DIR
    allowlist_file: Path | None = USER_ALLOWLIST
    counted_config: Path = procscan.DEFAULT_CONFIG_FILE
    claims_dir: Path | None = None


@dataclass(frozen=True)
class _Rules:
    count_launchers: bool


def launcher_switch(config_file: Path) -> _Rules:
    """The enforcer's ``count_launcher_processes`` (default on)."""
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except OSError, ValueError:
        data = {}
    value = (
        data.get("count_launcher_processes", True) if isinstance(data, dict) else True
    )
    return _Rules(count_launchers=value is not False)


def gather(
    cfg: Config, store: ReportStore, run: _sensors.Runner = _sensors.run
) -> Snapshot:
    """Read every sensor once."""
    display_ok, window = _sensors.focused_window(run)
    return Snapshot(
        ts=time.time(),
        display_ok=display_ok,
        window=window,
        idle=_sensors.idle_seconds(run) if display_ok else None,
        sinks=_sensors.sink_inputs(run),
        games=procscan.qualifying_pids(
            launcher_switch(cfg.counted_config), cfg.counted_config
        ),
        paused_by=lockstate.paused_by(cfg.claims_dir),
        reports=store.snapshot(),
    )


class Watcher:
    """Owns the publish loop, the day log and the extension server."""

    def __init__(
        self,
        cfg: Config,
        store: ReportStore | None = None,
        gather_fn: Callable[[Config, ReportStore], Snapshot] = gather,
    ) -> None:
        """Prepare; nothing runs until :meth:`run` or :meth:`tick`."""
        self.cfg = cfg
        self.store = store or ReportStore()
        self._gather = gather_fn
        self._settings = Settings(allow=load_allowlist(cfg.allowlist_file))
        self._allow_mtime = self._mtime()
        self._daylog = DayLog(cfg.log_dir)
        self._wake = threading.Event()
        self._lock = threading.Lock()
        self.seq = 0
        self._last_ts: float | None = None

    def _mtime(self) -> float | None:
        path = self.cfg.allowlist_file
        try:
            return path.stat().st_mtime if path is not None else None
        except OSError:
            return None

    def _reload_allowlist(self) -> None:
        mtime = self._mtime()
        if mtime != self._allow_mtime:
            self._allow_mtime = mtime
            self._settings = Settings(allow=load_allowlist(self.cfg.allowlist_file))
            logger.info("allowlist reloaded")

    def compute(self) -> Now:
        """Classify the desktop right now (not published)."""
        return classify(self._gather(self.cfg, self.store), self._settings)

    def status_doc(self) -> dict[str, object]:
        """The signed current document, same shape as now.json."""
        return signed_doc(replace(self.compute(), seq=self.seq), self.cfg.key_file)

    def tick(self) -> Now:
        """Compute, publish and log one moment."""
        with self._lock:
            self._reload_allowlist()
            self.seq += 1
            now = replace(self.compute(), seq=self.seq)
            write_now(self.cfg.now_path, now, self.cfg.key_file)
            dt = 0.0 if self._last_ts is None else now.ts - self._last_ts
            dt = max(0.0, min(dt, 2 * self.cfg.interval))
            self._last_ts = now.ts
            self._daylog.add(now, dt)
            self._daylog.flush()
            return now

    def wake(self) -> None:
        """Ask the loop to publish early (an extension report arrived)."""
        self._wake.set()

    def run(self, stop: threading.Event) -> None:
        """Serve and publish until *stop* is set."""
        server = ExtensionServer(self.cfg.port, self.store, self.wake, self.status_doc)
        server.start()
        logger.info(
            "leisure-watch on 127.0.0.1:%d -> %s", server.port, self.cfg.now_path
        )
        try:
            while not stop.is_set():
                started = time.monotonic()
                try:
                    self.tick()
                except Exception:
                    logger.exception("tick failed")
                self._wake.wait(self.cfg.interval)
                self._wake.clear()
                stop.wait(max(0.0, _MIN_GAP - (time.monotonic() - started)))
        finally:
            server.stop()
            self._daylog.flush()
