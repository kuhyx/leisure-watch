"""``install.sh --uninstall``: the stand-down undoes every writer, in a sandbox.

Real scripts run with a scratch HOME/XDG, a systemctl shim that only logs, a
sudo shim that runs the command unprivileged, and the switch file and browser
wrapper redirected into ``tmp_path`` (LEISURE_WATCH_SWITCH / _WRAPPER).
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess

import pytest

ROOT = Path(__file__).resolve().parent.parent
LEECH = "/home/u/leechblock"
LEETCODE = "/home/u/leetcode-guard/extension"
WRAPPER_TEXT = """#!/bin/bash
set -euo pipefail
exec "$real_bin" --load-extension="{paths}" "$@"
"""


class Box:
    """One scratch desktop: HOME, shims, and the run helper."""

    def __init__(self, tmp: Path) -> None:
        self.home = tmp / "home"
        self.bin = tmp / "bin"
        self.log = tmp / "calls.log"
        self.switch = tmp / "etc" / "leisure-watch" / "leisure_from"
        self.wrapper = tmp / "browser-preexec-wrapper"
        self.unit = self.home / ".config/systemd/user/leisure-watch.service"
        self.flags = self.home / ".config/helium-browser-flags.conf"
        self.ext = self.home / ".local/share/leisure-watch/extension"
        self.ours = str(self.ext / "chromium")
        for path in (self.home, self.bin, self.switch.parent, self.unit.parent):
            path.mkdir(parents=True)
        self._shim("systemctl", f'echo "systemctl $*" >> {self.log}')
        self._shim("sudo", 'if [[ $1 == -n ]]; then shift; fi; exec "$@"')
        self.unit.write_text("[Service]\n", encoding="ascii")
        self.switch.write_text("2026-11-09\n", encoding="ascii")
        (self.ext / "chromium").mkdir(parents=True)
        (self.ext / "chromium" / "manifest.json").write_text("{}", encoding="ascii")
        self.flags.write_text(
            f"--password-store=basic\n--load-extension={LEETCODE},{self.ours}\n",
            encoding="ascii",
        )
        self.set_wrapper(f"{LEECH},{LEETCODE},{self.ours}")

    def _shim(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/bash\n{body}\n", encoding="ascii")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def set_wrapper(self, paths: str) -> None:
        self.wrapper.write_text(WRAPPER_TEXT.format(paths=paths), encoding="ascii")

    def run(self, *argv: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "LEISURE_WATCH_SWITCH": str(self.switch),
            "LEISURE_WATCH_WRAPPER": str(self.wrapper),
        }
        return subprocess.run(
            list(argv), env=env, text=True, capture_output=True, check=False
        )

    def calls(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []


@pytest.fixture
def box(tmp_path: Path) -> Box:
    return Box(tmp_path)


def test_uninstall_undoes_every_writer(box: Box) -> None:
    done = box.run(str(ROOT / "install.sh"), "--uninstall")
    assert done.returncode == 0, done.stderr
    assert box.calls() == [
        "systemctl --user disable --now leisure-watch.service",
        "systemctl --user daemon-reload",
    ]
    assert not box.unit.exists()
    assert not box.ext.exists()
    assert not box.switch.parent.exists()
    # Other extensions survive in both places; ours is gone from both.
    assert box.flags.read_text() == (
        f"--password-store=basic\n--load-extension={LEETCODE}\n"
    )
    assert f'--load-extension="{LEECH},{LEETCODE}"' in box.wrapper.read_text()
    assert box.ours not in box.wrapper.read_text()


def test_uninstall_twice_is_a_no_op(box: Box) -> None:
    assert box.run(str(ROOT / "install.sh"), "--uninstall").returncode == 0
    again = box.run(str(ROOT / "install.sh"), "--uninstall")
    assert again.returncode == 0, again.stderr
    assert len(box.calls()) == 2  # nothing left to disable the second time


def test_the_wrapper_flag_goes_when_ours_was_the_only_path(box: Box) -> None:
    box.set_wrapper(box.ours)
    box.flags.write_text(f"--load-extension={box.ours}\n", encoding="ascii")
    assert box.run(str(ROOT / "install.sh"), "--uninstall").returncode == 0
    assert "--load-extension" not in box.wrapper.read_text()
    assert box.flags.read_text() == ""


def test_librewolf_remove_drops_only_our_xpi(tmp_path: Path) -> None:
    profile = tmp_path / "profile"
    (profile / "extensions").mkdir(parents=True)
    ours = profile / "extensions" / "leisure-watch@kuhy.dev.xpi"
    other = profile / "extensions" / "uBlock0@raymondhill.net.xpi"
    ours.write_text("x", encoding="ascii")
    other.write_text("y", encoding="ascii")
    (profile / "user.js").write_text("user_pref('a', 1);\n", encoding="ascii")
    script = ROOT / "scripts" / "install_librewolf_extension.sh"
    done = subprocess.run(
        [str(script), "--remove", "--profile", str(profile)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert not ours.exists()
    assert other.exists()
    assert (profile / "user.js").read_text() == "user_pref('a', 1);\n"
