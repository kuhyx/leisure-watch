"""When each browser's extension last reported, persisted for go-live.

``leisure-watch go-live`` refuses unless BOTH Helium and LibreWolf reported
in the last 24 h. The watcher only keeps the latest report in memory, so it
also records the receive time per browser here, atomically and at most
once a minute per browser (a 24 h window needs no 5 s resolution).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Final

from leisure_watch import _safeio
from leisure_watch._browser import EXTENSION_BROWSERS
from leisure_watch.phase2 import number

if TYPE_CHECKING:
    from collections.abc import Mapping

    from leisure_watch._browser import ExtReport

logger = logging.getLogger(__name__)

DEFAULT_FILE: Path = Path.home() / ".local" / "state" / "leisure-watch" / "ext.json"
MIN_GAP: Final = 60.0


def default_file() -> Path:
    """The heartbeat file (patchable)."""
    return DEFAULT_FILE


def load(path: Path) -> dict[str, float]:
    """``{browser: last receive ts}`` for the extension browsers on record."""
    doc = _safeio.json_object(_safeio.read_regular(path)) or {}
    seen = {b: number(doc.get(b)) for b in EXTENSION_BROWSERS}
    return {b: ts for b, ts in seen.items() if ts is not None}


def _save(path: Path, seen: Mapping[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".ext-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(dict(seen), handle, sort_keys=True)
    Path(tmp).replace(path)


class HeartbeatLog:
    """The persisted last-seen times, updated from the watcher's tick."""

    def __init__(self, path: Path) -> None:
        """Start from what is already on disk."""
        self.path = path
        self._saved = load(path)

    @property
    def seen(self) -> dict[str, float]:
        """What is on disk now."""
        return dict(self._saved)

    def update(self, reports: Mapping[str, ExtReport]) -> None:
        """Persist newer receive times (a new browser at once, else per minute)."""
        merged = dict(self._saved)
        due = False
        for browser, report in reports.items():
            old = merged.get(browser)
            if old is None or report.received > old:
                merged[browser] = report.received
                due = due or old is None or report.received - old >= MIN_GAP
        if not due:
            return
        try:
            _save(self.path, merged)
        except OSError:
            logger.warning("could not persist extension heartbeats to %s", self.path)
            return
        self._saved = merged
