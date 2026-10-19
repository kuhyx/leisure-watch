"""Tests for the extension builder."""

from __future__ import annotations

import json
from pathlib import Path
import zipfile

from leisure_watch._browser import EXTENSION_VERSION
from leisure_watch._extbuild import GECKO_ID, build

SRC = Path(__file__).resolve().parent.parent / "extension"


def test_builds_both_variants(tmp_path: Path) -> None:
    built = build(SRC, tmp_path, 8775)
    chromium = json.loads((built["chromium"] / "manifest.json").read_text())
    firefox = json.loads((built["firefox"] / "manifest.json").read_text())
    assert chromium["background"] == {"service_worker": "background.js"}
    assert firefox["background"] == {"scripts": ["background.js"]}
    assert firefox["browser_specific_settings"]["gecko"]["id"] == GECKO_ID
    assert chromium["host_permissions"] == ["http://127.0.0.1:8775/*"]
    # Report the truly focused window, private ones included where allowed.
    assert chromium["incognito"] == firefox["incognito"] == "spanning"
    js = (built["chromium"] / "background.js").read_text()
    assert 'const BROWSER = "helium"' in js
    assert "127.0.0.1:8775/report" in js
    assert "incognito: Boolean(win.incognito)" in js
    assert 'windowTypes: ["normal"]' not in js
    assert (
        'const BROWSER = "librewolf"'
        in (built["firefox"] / "background.js").read_text()
    )
    with zipfile.ZipFile(built["xpi"]) as archive:
        assert sorted(archive.namelist()) == [
            "background.js",
            "manifest.json",
            "spent.html",
            "spent.js",
        ]


def test_background_carries_the_shared_matcher_and_the_status_poll(
    tmp_path: Path,
) -> None:
    built = build(SRC, tmp_path, 8775)
    js = (built["firefox"] / "background.js").read_text()
    assert "function urlAllowed(" in js
    assert "127.0.0.1:8775/status" in js
    assert "__PORT__" not in js
    assert "__BROWSER__" not in js
    manifest = json.loads((built["chromium"] / "manifest.json").read_text())
    # go-live's preflight requires at least this version from both browsers.
    assert manifest["version"] == EXTENSION_VERSION == "0.2.1"
    assert "storage" in manifest["permissions"]  # the persisted last /status
    assert "Blocks nothing" not in manifest["description"]
    page = (built["chromium"] / "spent.html").read_text()
    assert '<script src="spent.js"></script>' in page
    assert "<script>" not in page  # MV3 CSP: no inline script
