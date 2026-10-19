# leisure-watch

Shared spec + cross-repo contracts: `TODO-leisure-rollout.md` (decisions are
final; do not re-ask). This repo owns contract C3 (`now.json`).

- Package `leisure_watch/` is **stdlib-only** (root imports it). Tests in
  `tests/`, 100% branch coverage. `kuhytrack/` is a subtree import with its
  own gates: root gates exclude it; do not restructure it.
- `leisure_watch.procscan` must stay importable 1:1 by
  steam-backlog-enforcer (same public names as its originals).
- Every action < 60 s: use `scripts/test_changed.sh` for the inner loop.
- Never touch the live desktop beyond reading X properties; never restart a
  browser. Root steps (Helium wrapper) go through vmbox first.

## Commands

Dev tools are exact-pinned in `pyproject.toml` `[dev]`; `python -m venv .venv && .venv/bin/pip install -e '.[dev]'`.


- run: `python3 -m leisure_watch run` (deployed: `systemctl --user status leisure-watch`; one-shot: `python3 -m leisure_watch status --json`)
- test: `python3 -m pytest -q`
- test-changed: `scripts/test_changed.sh`
- lint: `python -m ruff check . && python -m ruff format --check . && python -m mypy leisure_watch tests`
- coverage: `python -m pytest -q --cov=leisure_watch --cov-branch --cov-report=xml --cov-fail-under=100`
- coverage-gaps: `coverage-gaps coverage.xml`
