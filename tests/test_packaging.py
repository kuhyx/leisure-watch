"""What a non-editable install ships, checked against the source tree.

Without `py.typed` in the installed package, strict mypy in a consumer
(steam-backlog-enforcer) types every leisure_watch import as Any and
reports no-any-unimported.
"""

from __future__ import annotations

from pathlib import Path
import tomllib

import leisure_watch

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_py_typed_marker_exists_and_is_package_data() -> None:
    assert (ROOT / "leisure_watch" / "py.typed").is_file()
    data = PYPROJECT["tool"]["setuptools"]["package-data"]["leisure_watch"]
    assert "py.typed" in data


def test_the_package_version_matches_pyproject() -> None:
    assert leisure_watch.__version__ == PYPROJECT["project"]["version"]
