"""Tests for the X11 focus, xprintidle and pipewire sensors."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from leisure_watch import _sensors
from leisure_watch._sensors import Window, focused_window, idle_seconds, sink_inputs

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

PROPS = """_NET_WM_PID(CARDINAL) = 10987
WM_CLASS(STRING) = "helium", "Helium"
_NET_WM_NAME(UTF8_STRING) = "Plus \\"One\\" - LeetCode - Helium"
WM_NAME(UTF8_STRING) = "ignored"
"""


def _runner(outputs: dict[str, str | None]) -> Callable[[Sequence[str]], str | None]:
    def run(argv: Sequence[str]) -> str | None:
        return outputs.get(" ".join(argv))

    return run


ROOT = "xprop -root _NET_ACTIVE_WINDOW"
PROPQ = "xprop -id 0x1800003 _NET_WM_PID WM_CLASS _NET_WM_NAME WM_NAME"


class TestFocus:
    def test_reads_pid_class_and_title(self) -> None:
        run = _runner(
            {ROOT: "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x1800003", PROPQ: PROPS}
        )
        assert focused_window(run) == (
            True,
            Window(10987, "helium", "Helium", 'Plus "One" - LeetCode - Helium'),
        )

    def test_falls_back_to_wm_name(self) -> None:
        props = 'WM_CLASS(STRING) = "xterm", "XTerm"\nWM_NAME(STRING) = "bash"\n'
        run = _runner({ROOT: "window id # 0x1800003", PROPQ: props})
        assert focused_window(run) == (True, Window(0, "xterm", "XTerm", "bash"))

    def test_no_window_is_desktop(self) -> None:
        run = _runner({ROOT: "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x0"})
        assert focused_window(run) == (True, None)

    def test_property_not_set_is_unreadable(self) -> None:
        """i3 always sets _NET_ACTIVE_WINDOW (0 = none); absent means unknown."""
        run = _runner({ROOT: "_NET_ACTIVE_WINDOW:  not found."})
        assert focused_window(run) == (True, _sensors.UNREADABLE)

    def test_vanished_window_is_unreadable(self) -> None:
        run = _runner({ROOT: "window id # 0x1800003", PROPQ: None})
        assert focused_window(run) == (True, _sensors.UNREADABLE)

    def test_window_without_any_props_is_unreadable(self) -> None:
        props = "_NET_WM_PID:  not found.\nWM_CLASS:  not found.\n"
        run = _runner({ROOT: "window id # 0x1800003", PROPQ: props})
        assert focused_window(run) == (True, _sensors.UNREADABLE)
        assert not _sensors.UNREADABLE.readable

    def test_title_alone_is_readable(self) -> None:
        props = 'WM_NAME(STRING) = "bash"\n'
        run = _runner({ROOT: "window id # 0x1800003", PROPQ: props})
        assert focused_window(run) == (True, Window(0, "", "", "bash"))

    def test_unreachable_display(self) -> None:
        assert focused_window(_runner({})) == (False, None)


class TestIdle:
    def test_milliseconds_to_seconds(self) -> None:
        assert idle_seconds(_runner({"xprintidle": "181500\n"})) == 181.5

    @pytest.mark.parametrize("out", [None, "", "abc"])
    def test_unknown(self, out: str | None) -> None:
        assert idle_seconds(_runner({"xprintidle": out})) is None


def _sink(
    corked: bool, pid: str | None = "42", binary: str = "mpv"
) -> dict[str, object]:
    props: dict[str, str] = {
        "application.process.binary": binary,
        "application.name": "mpv Media Player",
        "media.name": "video.mkv",
    }
    if pid is not None:
        props["application.process.id"] = pid
    return {"corked": corked, "properties": props}


PACTL = "pactl -f json list sink-inputs"


class TestSinkInputs:
    def test_only_uncorked(self) -> None:
        doc = [_sink(corked=False), _sink(corked=True, binary="blender")]
        sinks = sink_inputs(_runner({PACTL: json.dumps(doc)}))
        assert [(s.pid, s.binary, s.label) for s in sinks] == [
            (42, "mpv", "video.mkv — mpv Media Player")
        ]

    def test_missing_or_bad_pid(self) -> None:
        doc = [_sink(corked=False, pid=None), _sink(corked=False, pid="x")]
        assert [s.pid for s in sink_inputs(_runner({PACTL: json.dumps(doc)}))] == [0, 0]

    @pytest.mark.parametrize(
        "out",
        [
            None,
            "{bad",
            '{"a": 1}',
            '[1, {"corked": false, "properties": 3}]',
            "[" * 100_000 + "]" * 100_000,
        ],
    )
    def test_garbage(self, out: str | None) -> None:
        assert sink_inputs(_runner({PACTL: out})) == ()


class TestRun:
    def test_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DISPLAY", ":7")
        seen: dict[str, object] = {}

        def fake(argv: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
            seen.update(kw)
            return subprocess.CompletedProcess(argv, 0, "out\n", "")

        monkeypatch.setattr("leisure_watch._sensors.subprocess.run", fake)
        assert _sensors.run(["true"]) == "out\n"
        env = seen["env"]
        assert isinstance(env, dict)
        assert env["DISPLAY"] == ":7"

    def test_default_display(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DISPLAY", raising=False)
        assert _sensors.desktop_env()["DISPLAY"] == ":0"

    @pytest.mark.parametrize(
        "exc", [FileNotFoundError(), subprocess.TimeoutExpired("x", 1), OSError()]
    )
    def test_errors(self, monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
        def fake(*_a: object, **_k: object) -> None:
            raise exc

        monkeypatch.setattr("leisure_watch._sensors.subprocess.run", fake)
        assert _sensors.run(["x"]) is None

    def test_nonzero_exit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake(argv: list[str], **_k: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 1, "", "err")

        monkeypatch.setattr("leisure_watch._sensors.subprocess.run", fake)
        assert _sensors.run(["x"]) is None

    def test_non_utf8_output_is_none(self) -> None:
        """Real decode path: undecodable tool output is a failure, not a crash."""
        assert _sensors.run(["printf", "\\377"]) is None
        assert _sensors.run(["printf", "ok"]) == "ok"
