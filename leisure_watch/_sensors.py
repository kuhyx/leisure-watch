"""Desktop sensors: X11 focus (xprop), idle (xprintidle), audio (pactl).

Each sensor takes a ``run`` callable (argv -> stdout, or ``None`` on any
failure) so tests feed canned tool output and the watcher never raises out
of a missing tool or a dead display.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    Runner = Callable[[Sequence[str]], str | None]

_TIMEOUT: Final = 3.0
_WID = re.compile(r"window id # (0x[0-9a-fA-F]+)")
_PID = re.compile(r"^_NET_WM_PID\(CARDINAL\) = (\d+)$", re.MULTILINE)
_CLASS = re.compile(
    r'^WM_CLASS\(STRING\) = "((?:[^"\\]|\\.)*)", "((?:[^"\\]|\\.)*)"', re.MULTILINE
)
_NET_NAME = re.compile(r'^_NET_WM_NAME\(UTF8_STRING\) = "(.*)"$', re.MULTILINE)
_WM_NAME = re.compile(r'^WM_NAME\((?:UTF8_)?STRING\) = "(.*)"$', re.MULTILINE)


@dataclass(frozen=True)
class Window:
    """The focused X11 window."""

    pid: int
    instance: str
    cls: str
    title: str


@dataclass(frozen=True)
class SinkInput:
    """One uncorked (playing) pipewire-pulse sink input."""

    pid: int
    binary: str
    label: str


def desktop_env() -> dict[str, str]:
    """The environment for X tools: the user manager may not export DISPLAY."""
    env = dict(os.environ)
    env.setdefault("DISPLAY", ":0")
    env.setdefault("XAUTHORITY", str(Path.home() / ".Xauthority"))
    return env


def run(argv: Sequence[str]) -> str | None:
    """Run a fixed argv; stdout on exit 0, ``None`` on any failure."""
    try:
        done = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
            env=desktop_env(),
            check=False,
        )
    except OSError, subprocess.TimeoutExpired:
        return None
    return done.stdout if done.returncode == 0 else None


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", r"\1", text)


def focused_window(run: Runner) -> tuple[bool, Window | None]:
    """``(display_reachable, window)``; ``window`` is ``None`` for the desktop."""
    root = run(["xprop", "-root", "_NET_ACTIVE_WINDOW"])
    if not root:
        return False, None
    match = _WID.search(root)
    if match is None or int(match.group(1), 16) == 0:
        return True, None
    props = run(
        [
            "xprop",
            "-id",
            match.group(1),
            "_NET_WM_PID",
            "WM_CLASS",
            "_NET_WM_NAME",
            "WM_NAME",
        ]
    )
    if not props:
        return True, None
    pid = _PID.search(props)
    cls = _CLASS.search(props)
    title = _NET_NAME.search(props) or _WM_NAME.search(props)
    return True, Window(
        pid=int(pid.group(1)) if pid else 0,
        instance=_unescape(cls.group(1)) if cls else "",
        cls=_unescape(cls.group(2)) if cls else "",
        title=_unescape(title.group(1)) if title else "",
    )


def idle_seconds(run: Runner) -> float | None:
    """Seconds since the last X input, or ``None`` if xprintidle cannot say."""
    out = (run(["xprintidle"]) or "").strip()
    return int(out) / 1000 if out.isdigit() else None


def _sink(raw: object) -> SinkInput | None:
    if not isinstance(raw, dict) or raw.get("corked") is not False:
        return None
    props = raw.get("properties")
    if not isinstance(props, dict):
        return None
    pid = str(props.get("application.process.id", ""))
    binary = str(props.get("application.process.binary", ""))
    app = str(props.get("application.name", binary))
    media = str(props.get("media.name", ""))
    return SinkInput(
        pid=int(pid) if pid.isdigit() else 0,
        binary=binary,
        label=f"{media} — {app}" if media else app,
    )


def sink_inputs(run: Runner) -> tuple[SinkInput, ...]:
    """Every playing (uncorked) sink input."""
    out = run(["pactl", "-f", "json", "list", "sink-inputs"])
    try:
        doc = json.loads(out) if out else []
    except ValueError:
        return ()
    if not isinstance(doc, list):
        return ()
    return tuple(s for s in (_sink(raw) for raw in doc) if s is not None)
