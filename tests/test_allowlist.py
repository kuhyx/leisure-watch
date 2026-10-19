"""Tests for the app/domain allowlists."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from leisure_watch.allowlist import Allowlist, host_key, load_allowlist

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def allow(tmp_path: Path) -> Allowlist:
    return load_allowlist(tmp_path / "missing.toml")


class TestDomains:
    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/kuhyx/leisure-watch",
            "https://gist.github.com/x",
            "https://raw.githubusercontent.com/a/b",
            "https://mail.google.com/mail/u/0/",
            "https://leetcode.com/problems/two-sum/",
            "https://www.pw.edu.pl/",
            "http://localhost:3000/",
            "http://127.0.0.1:8778/",
            "http://100.109.64.41:5600/#/home",
            "chrome://newtab/",
            "chrome-search://local-ntp/local-ntp.html",
            "about:blank",
            "chrome-extension://abc/popup.html",
            "moz-extension://uuid/page.html",
            "",
        ],
    )
    def test_allowed(self, allow: Allowlist, url: str) -> None:
        assert allow.url_allowed(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=x",
            "https://notgithub.com/",
            "https://github.com.evil.example/",
            "https://aiclearing.com/",
            "http://127.0.0.1:8765/",
            "http://localhost:8765/review",
            "http://100.109.64.41:8080/",
            "file:///home/kuhy/x.html",
            "https://google.com/",
            "http://[::1",
        ],
    )
    def test_not_allowed(self, allow: Allowlist, url: str) -> None:
        assert not allow.url_allowed(url)

    def test_host_key_strips_www_and_port(self) -> None:
        assert host_key("https://www.YouTube.com:443/watch") == "youtube.com"
        assert host_key("about:blank") == "about:blank"
        assert host_key("http://[::1") == "http://[::1"


class TestApps:
    @pytest.mark.parametrize(
        ("instance", "cls"),
        [
            ("terminator", "Terminator"),
            ("libreoffice", "libreoffice-writer"),
            ("Soffice", "Soffice"),
            ("code", "Code"),
            ("blender", "Blender"),
            ("daily-limits", "Daily-limits"),
        ],
    )
    def test_classes(self, allow: Allowlist, instance: str, cls: str) -> None:
        assert allow.app_allowed(instance, cls, "")

    def test_tk_window_by_title(self, allow: Allowlist) -> None:
        assert allow.app_allowed("__main__", "Tk", "Workout Locker")
        assert allow.app_allowed("x", "Tk", "LeetCode Status - 2 left")

    def test_unknown_app(self, allow: Allowlist) -> None:
        assert not allow.app_allowed("mpv", "mpv", "video.mkv")
        assert not allow.app_allowed("__main__", "Tk", "/wsg/ — kept 3")

    def test_binary_allowed_for_media(self, allow: Allowlist) -> None:
        assert allow.binary_allowed("blender")
        assert not allow.binary_allowed("mpv")


class TestUserOverride:
    def test_user_lists_extend_the_defaults(self, tmp_path: Path) -> None:
        user = tmp_path / "allowlist.toml"
        user.write_text(
            '[domains]\nallow = ["example.org"]\n[apps]\nclasses = ["mpv"]\n',
            encoding="utf-8",
        )
        allow = load_allowlist(user)
        assert allow.url_allowed("https://docs.example.org/")
        assert allow.url_allowed("https://github.com/")
        assert allow.app_allowed("mpv", "mpv", "")

    def test_broken_user_file_falls_back_to_defaults(self, tmp_path: Path) -> None:
        user = tmp_path / "allowlist.toml"
        user.write_text("[domains\n", encoding="utf-8")
        assert load_allowlist(user).url_allowed("https://github.com/")

    def test_wrong_types_are_ignored(self, tmp_path: Path) -> None:
        user = tmp_path / "allowlist.toml"
        user.write_text(
            'domains = 3\n[apps]\nclasses = "mpv"\ntitles = [1, "Mine"]\n',
            encoding="utf-8",
        )
        allow = load_allowlist(user)
        assert not allow.app_allowed("mpv", "mpv", "")
        assert allow.app_allowed("x", "Tk", "Mine")
