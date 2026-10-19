# leisure-watch

Publishes signed facts about whether the desktop is being used for
**leisure** (games, video, browsing, messaging), is **free** (productive), or
is **paused** (a locker holds its grab, or i3lock runs). Phase 1 of the
leisure-budget rollout (`TODO-leisure-rollout.md`): it only *measures*; the
root steam-backlog-enforcer stays the only accountant.

## What it watches (every 5 s)

- **Focus** (X11 `_NET_ACTIVE_WINDOW` → `_NET_WM_PID`, `WM_CLASS`, title),
  ignored while idle (`xprintidle` ≥ 180 s).
- **Media** — uncorked pipewire sink inputs (`pactl -f json list sink-inputs`)
  and audible browser tabs, counted whether focused or not.
- **Games** — Steam (`SteamAppId`), launchers and counted processes, via
  `leisure_watch.procscan` (moved from the enforcer).
- **Pause** — gatelock claims whose grab is held, or a running i3lock.
- **Browsers** — Helium and LibreWolf report the active tab and audible tabs
  through our WebExtension (`extension/`) to `http://127.0.0.1:8775/report`.
  A focused browser whose report is older than 15 s, or any other browser,
  counts as leisure (fail closed).

Allowlists: `leisure_watch/default_allowlist.toml`, extended by
`~/.config/leisure-watch/allowlist.toml` (same tables; reloaded on change).

## Output

- `$XDG_RUNTIME_DIR/leisure-watch/now.json` — contract C3, HMAC-SHA256 signed
  with `/etc/workout-locker/hmac.key`.
- `~/.local/share/leisure-watch/<YYYY-MM-DD>.jsonl` — seconds per
  `(state, source, key)` for the allowlist review (06:00 day boundary).

## Use

```sh
./install.sh                                  # package, extension, user unit
python3 -m leisure_watch status --json        # the live computed state
python3 -m leisure_watch report [--day D]     # top leisure keys of a day
```

Library API for the root enforcer (stdlib only): `leisure_watch.procscan`,
`leisure_watch.lockstate.paused_by()`,
`leisure_watch.facts.read_now(path, now, max_age=15)`.

`kuhytrack/` is the kuhytrack history store, imported with its history via
git subtree; it keeps its own gates and layout.
