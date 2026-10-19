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
leisure-watch go-live --dry-run               # Phase 2: preflight, writes nothing
leisure-watch go-live [--force] [--date D]    # Phase 2 on from tomorrow (sudo)
leisure-watch go-live --undo                  # back to the old budget
```

## Phase 2 (dormant until `go-live`)

`go-live` preflights (watcher + fresh `now.json`; both extensions seen in
24 h, persisted in `~/.local/state/leisure-watch/ext.json`; enforcer active
with fresh shadow fields; every live gatelock claim has `grab_held`), then
`sudo install`s tomorrow's gaming day into `/etc/leisure-watch/leisure_from`
and disables `kuhytrack-budget.timer`. Whether it is on is only ever
`earned_time.leisure_active(gaming_day)`.

`GET http://127.0.0.1:8775/status` →
`{"active", "spent", "allow", "local_hosts", "deny_ports", "used_seconds",
"budget_seconds", "day"}`. `spent` = enforcer `seconds >= budget_seconds`
for today's 06:00 day; dormant is never spent; active + unreadable state
fails closed (spent); another `day_key` = nothing used yet. When active and
spent the extension sends every non-allowlisted web tab to its bundled
`spent.html` (same matcher as Python, lists from `/status`). The full
computed document moved to `GET /now`.

Library API for the root enforcer (stdlib only): `leisure_watch.procscan`,
`leisure_watch.lockstate.paused_by()`,
`leisure_watch.facts.read_now(path, now, max_age=15)`,
`leisure_watch.daylog.gaming_day(ts)`.

`kuhytrack/` is the kuhytrack history store, imported with its history via
git subtree; it keeps its own gates and layout.
