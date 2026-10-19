"""Build the Chromium and Firefox variants of the extension from shared JS.

``extension/manifest.base.json`` + ``extension/allow.js`` (prepended to)
``extension/background.js`` + the ``spent.html`` page become:

- ``<out>/chromium/`` -- unpacked MV3 with a service worker (Helium
  ``--load-extension``);
- ``<out>/firefox/`` and ``<out>/leisure-watch@kuhy.dev.xpi`` -- MV3 with
  ``background.scripts`` and a fixed gecko id (LibreWolf profile install).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
import zipfile

if TYPE_CHECKING:
    from pathlib import Path

GECKO_ID = "leisure-watch@kuhy.dev"
_FLAVOURS = {"chromium": "helium", "firefox": "librewolf"}
_PAGES = ("spent.html", "spent.js")  # copied verbatim


def _manifest(base: dict[str, object], flavour: str, port: int) -> dict[str, object]:
    manifest = dict(base)
    manifest["host_permissions"] = [f"http://127.0.0.1:{port}/*"]
    if flavour == "chromium":
        manifest["background"] = {"service_worker": "background.js"}
    else:
        manifest["background"] = {"scripts": ["background.js"]}
        manifest["browser_specific_settings"] = {
            "gecko": {
                "id": GECKO_ID,
                "strict_min_version": "128.0",
                "data_collection_permissions": {"required": ["none"]},
            }
        }
    return manifest


def build(src: Path, out: Path, port: int) -> dict[str, Path]:
    """Write both variants under *out*; return their paths."""
    base = json.loads((src / "manifest.base.json").read_text(encoding="utf-8"))
    script = (src / "allow.js").read_text(encoding="utf-8") + (
        src / "background.js"
    ).read_text(encoding="utf-8")
    built: dict[str, Path] = {}
    for flavour, browser in _FLAVOURS.items():
        target = out / flavour
        target.mkdir(parents=True, exist_ok=True)
        manifest = json.dumps(_manifest(base, flavour, port), indent=2) + "\n"
        (target / "manifest.json").write_text(manifest, encoding="utf-8")
        js = script.replace("__BROWSER__", browser).replace("__PORT__", str(port))
        (target / "background.js").write_text(js, encoding="utf-8")
        for page in _PAGES:
            (target / page).write_bytes((src / page).read_bytes())
        built[flavour] = target
    xpi = out / f"{GECKO_ID}.xpi"
    with zipfile.ZipFile(xpi, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest.json", "background.js", *_PAGES):
            archive.write(built["firefox"] / name, name)
    built["xpi"] = xpi
    return built
