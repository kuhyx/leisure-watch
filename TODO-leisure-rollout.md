# TODO — leisure budget rollout (gaming → all non-productive time)

> REMOVE ME AFTER FINISH — delete this file once Phase 2 has landed.

Agreed with kuhy 2026-10-19 (grilling Q1–Q23, plan confirmed). This file is the
shared spec + cross-repo contracts for every subagent/session working on it.

## Goal

The daily "gaming" budget becomes a **leisure** budget covering every
non-productive activity on the PC (games, browsing, video, wsg-grabber,
messaging). Fully earned day = **10 h** (base 5 h → 7 h, cap 8 h → 10 h; earner
pay and shutdown ladder untouched). Phase 1 = **shadow week**: everything is
measured and shown loudly, only games stay enforced exactly as today.

## Decisions (do not re-ask)

- Q1 base +2 h & cap 10 h behind dated `LEISURE_FROM` (parked 2027-01-01 until
  Phase 2 sets it to the day after kuhy confirms the shadow week).
- Q2 UI labels become "Leisure" (🛋) in Phase 2; internal `gaming_*`
  identifiers and JSON keys stay.
- Q3 new repo `~/src/leisure-watch` (public `kuhyx/leisure-watch`); kuhytrack
  moved in with history under `kuhytrack/` (android + doomscroll kept). The
  root steam-backlog-enforcer stays the ONLY accountant; the watcher only
  publishes signed facts. Steam/launcher/counted-proc /proc scan moves into
  `leisure_watch` (library) and the enforcer imports it.
- Q4/Q23 own WebExtension (MV3) for Helium AND LibreWolf, reports active tab
  URL + audible tabs to localhost. Any other browser counts in full.
- Q5/Q16/Q18/Q20/Q21 **allowlists** for both domains and apps; anything not
  allowlisted counts as leisure while focused (and, Phase 2, is blocked/killed
  at 0).
- Q6 focus counts only when not idle (xprintidle ≥ 180 s = idle). Media counts
  regardless of focus/idle while playing (uncorked pipewire sink-input of a
  non-allowlisted app, or audible tab on a non-allowlisted domain). Games count
  whenever their process runs (as today). Overlaps bill once (wall clock).
- Q7 a locker whose X grab is ACTUALLY held (gatelock) or i3lock pauses ALL
  shadow billing, games included. Leetcode study mode releases the grab → not
  paused. wsg-grabber: reviewer UI (`/wsg/` Tk window, its mpv child) counts;
  headless `wsg-grabber scrape` never counts.
- Q8 fail closed: focused browser whose extension heartbeat is > 15 s old →
  leisure; watcher `now.json` stale (> 15 s) / missing / bad signature →
  enforcer bills shadow time unless paused.
- Q9 (Phase 2) at 0: Steam as today; extension redirects every non-allowlisted
  domain to a "leisure spent" page; root enforcer kills any focused/playing
  non-allowlisted app's process; no screen lock; warnings 60/30/10/5 min.
- Q10/Q19 shadow visibility: i3bar block `🛋 SHADOW 3h12 left · 1h48 used`,
  yellow < 30 min, red `WOULD BLOCK` at 0, **never blinking**; critical dunst
  notification at would-be 60/30/10/5 min; at would-be 0 a large centred splash
  window (no grab, no focus steal, click to dismiss) listing exactly what would
  be killed/blocked now; re-shown every 15 min while over.
- Q13 `kuhytrack-budget.timer` keeps running until Phase 2, then removed.
- Q14 kuhytrack server/dashboard stays the history store.
- Q22 own Godot prototypes free when run from the Godot editor or from a repo
  under ~/src; exported/itch builds count.

## Allowlists (defaults shipped in `leisure_watch/default_allowlist.toml`)

Domains (entry matches host == entry or host endswith "." + entry):
mail.google.com, calendar.google.com, mail.proton.me, calendar.proton.me,
account.proton.me, leetcode.com, claude.ai, platform.claude.com,
docs.anthropic.com, github.com, githubusercontent.com, gitlab.com,
stackoverflow.com, stackexchange.com, developer.mozilla.org, docs.python.org,
pypi.org, pub.dev, flutter.dev, developer.android.com, docs.godotengine.org,
archlinux.org, figma.com, docs.google.com, drive.google.com, pw.edu.pl,
localhost + 127.0.0.1 (any port EXCEPT wsg-grabber's dashboard port),
100.109.64.41:5600 (kuhytrack dashboard), browser-internal pages (new tab,
chrome://, about:, chrome-extension://, moz-extension://).
NOT allowed: work domains (aiclearing*) — kuhy said no.

Apps (WM_CLASS instance/class, case-insensitive; Tk windows by title):
Terminator, Pcmanfm, KeePassXC, pavucontrol-qt, Soffice / libreoffice-*,
Gcr-prompter, Xdg-desktop-portal-gtk, Xfce4-notifyd, screengrab,
SimpleScreenRecorder, todo, tutor, Daily-limits, issue-dashboard,
steam-backlog-enforcer, book-guard, diet-guard / diet-guard-app, every locker
window (Workout Locker, LeetCode Status, MealGate, …), Krita, Godot, Blender,
kdenlive, code / VSCodium, Xephyr, "no window focused" (empty workspace /
`desktop`). Browsers (Helium, LibreWolf) → domain rules instead.
Everything else counts (steam_app_*, steam, mpv, vlc, totem, FreeTube,
discord/vesktop, signal, beeper, qBittorrent, endless_sky, osu, `/wsg/` …).

## Cross-repo contracts

### C1 earned_time 0.14.0 (`~/src/utils/earned_time`)
- `LEISURE_FROM = date(2027, 1, 1)` (parked).
- `gaming_base_minutes_for(day) -> int` = 7 h if day >= LEISURE_FROM else 5 h;
  `gaming_ceiling_minutes_for(day) -> int` = 10 h / 8 h. `base_for`/`resolve`
  use them. Enforced output for every day < LEISURE_FROM byte-identical.
- `resolve(..., leisure: bool = False)` — `leisure=True` prices the day as if
  LEISURE_FROM had already passed (shadow budget). Same return type.
- Tag `earned-time-v0.14.0`, push tag.

### C2 gatelock (`~/src/utils/gatelock`) + leetcode-guard
- `Claim` gains `grab_held: bool`, serialised always. Missing in JSON (old
  writer) → `grab != "none"`. It reflects the ACTUAL grab: true only after the
  X grab succeeded, false while released (leetcode study mode), rewritten in
  place in the flock-held claim file.
- Public helper `held_grabs(claims_dir=None) -> tuple[Claim, ...]` (live
  claims with `grab_held` and grab != "none"); readable by root (enforcer runs
  as root, claims dir `/run/user/1000/gatelock/claims`).
- leetcode-guard study release/resume updates it. New gatelock tag; re-pin
  every consumer that pins gatelock.

### C3 leisure-watch `now.json` (`$XDG_RUNTIME_DIR/leisure-watch/now.json`)
Written atomically by the user watcher every 5 s (and on change), mode 0644:
```json
{"v": 1, "ts": 1760000000.0, "seq": 42,
 "state": "leisure|free|paused",
 "paused_by": "gatelock:leetcode_guard|i3lock|null",
 "reasons": [{"source": "focus|media|game|failclosed",
              "key": "app:mpv|domain:youtube.com|steam:1091500|...",
              "pid": 1234, "label": "YouTube — mpv",
              "start": 98765432}],
 "focus": {"app": "Helium", "title": "...", "domain": "youtube.com",
           "idle": false},
 "extensions": {"helium": 1760000000.0, "librewolf": null},
 "sig": "<hex hmac-sha256>"}
```
`start` (additive, 0.2.1): `/proc/<pid>/stat` field 22 (raw clock ticks
after boot) of `pid` when it was seen; only on entries with a pid, absent
when unreadable. Readers must accept it missing; a killer compares it with
the live value and spares a pid whose start differs (PID reuse).
`sig` = HMAC-SHA256 with key `/etc/workout-locker/hmac.key` over
`json.dumps(obj_without_sig, sort_keys=True, separators=(",", ":"))`.
Library API used by the enforcer (stdlib only, importable as root):
`leisure_watch.procscan` (moved Steam/launcher/counted scan),
`leisure_watch.lockstate.paused_by() -> str | None`,
`leisure_watch.facts.read_now(path, now, max_age=15) -> Now | None`
(None = missing/stale/bad sig).
Extension endpoint: `http://127.0.0.1:<port>/report` (pick a free port; 8770–
8772 taken). Tag `leisure-watch-v0.1.0`.

### C4 steam-backlog-enforcer shadow fields (`playtime_state.json`)
`shadow_seconds`, `shadow_budget_seconds` (earned_time `resolve(leisure=True)`
× 60, held high-water like `budget_seconds`), `shadow_per_source`
(key → seconds), `shadow_paused_seconds`. Same 06:00 gaming day. Enforced
fields/behaviour unchanged.

### C5 daily-limits cache
Adds `"leisure_shadow": {"day", "budget_minutes", "used_minutes",
"left_minutes", "would_block": bool, "sources": [{"key","label","minutes"}]}`.
i3blocks `leisure_shadow.sh` renders it (in testsAndMisc linux_configuration,
symlinked into ~/.config/i3blocks).

## Phase 1 done

1. `python -m leisure_watch status --json` gives the right state live for:
   Helium on youtube → leisure; Helium on github → free; Terminator → free;
   unfocused mpv playing → leisure; gatelock grab held → paused; extension
   disabled + Helium focused → leisure (failclosed).
2. Enforced `resolve_budget` before/after identical on real ledgers.
3. i3bar shows the shadow block; would-be-0 splash + notifications fire
   (verified with a forced low shadow budget, not by waiting).
4. Root unit changes passed in vmbox first ("passed in vmbox, not verified on
   host" until the host run).

## Status (2026-10-19)

Phase 1 live on host: earned_time 0.14.0, gatelock 0.11.0, leisure-watch
0.1.2 (watcher unit + extension in Helium wrapper and LibreWolf profile),
enforcer shadow billing (restarted, enforced fields unchanged), daily-limits
`leisure_shadow` + i3blocks block + alerts + splash. Shadow week runs
2026-10-20 → 2026-10-27 (10-19 is contaminated: old-code locker claims paused billing, Helium failclosed until the extension loaded); review with `python -m leisure_watch report --day D`.
Known limits: private windows count until kuhy grants "Allow in Incognito"
(Helium) / "Run in Private Windows" (LibreWolf); HMAC key is user-readable
(0644 by design) so a determined forger can sign a "free" now.json; extension
endpoint trusts any local process sending an extension Origin; root imports
leisure_watch from the user site-packages (existing pattern).

## Phase 2 — built dormant now, enabled by ONE command (decided 2026-10-19)

Enabling = `leisure-watch go-live` (no code edits, tags or re-pins). Undo =
`leisure-watch go-live --undo`. Until then every Phase-2 path is dormant and
the shadow week keeps exercising it ("would kill/block" lists).

### C6 switch file (earned_time 0.15.0 owns the reader)
- `/etc/leisure-watch/leisure_from`: one line `YYYY-MM-DD`, root:root 0644.
- `earned_time.leisure_from() -> date`: parsed file date if the file is a
  regular, small, parseable file; else the parked `LEISURE_FROM`
  (2027-01-01). Never raises. Path is a module constant + optional `path=`
  parameter for tests.
- `earned_time.leisure_active(day) -> bool` = `day >= leisure_from()`.
  `gaming_base_minutes_for` / `gaming_ceiling_minutes_for` use
  `leisure_from()` instead of the constant.
- Every consumer decides "Phase 2 on today?" ONLY via `leisure_active(day)`
  (gaming day, 06:00 boundary). No consumer re-reads the file itself.

### `leisure-watch go-live` (runs as kuhy; sudo only for the one write)
- Preflight, refuses unless `--force`: watcher unit active + now.json fresh;
  extension heartbeat seen in the last 24 h from BOTH helium and librewolf
  (persist last-seen per browser in ~/.local/state/leisure-watch/);
  steam-backlog-enforcer active and writing shadow fields; every live gatelock
  claim carries `grab_held`.
- Preflight also requires both extensions to report a version >= the one
  this package ships (0.2.1+ reports carry `version`).
- Writes TOMORROW's date (never today; refuses an argument date <= today or
  more than 14 days ahead) via `sudo install -D -m 0644 -o root -g root`;
  prints what activates when. Already live = exit 0. It does NOT touch
  `kuhytrack-budget.timer`: the watcher disables it
  (`systemctl --user disable --now`) on the first tick where
  `leisure_active(gaming_day)` is true (Q13). `--undo` removes the file
  (sudo) and re-enables the timer.

### Behaviour on and after the go-live gaming day
- Budget: earned_time gives 7 h base / 10 h cap automatically.
- Enforcer: ENFORCED `seconds` are billed by the leisure rule (today's shadow
  logic: lock pause, fail-closed, once per wall clock); `budget_seconds` from
  plain `resolve()`; the 60/30/10/5 warnings + notifications use it. At 0:
  Steam path as today; kill (SIGTERM, SIGKILL after 30 s, every 3 s tick)
  every pid that now.json lists as focus/media leisure, EXCEPT browsers; a
  focused browser that is not reporting (other browsers, unreported private
  window → now.json `failclosed:<browser>*`) IS killed; now.json stale →
  kill all known browsers, media players (mpv, vlc, totem, FreeTube) and
  wsg-grabber until it is fresh again. Shadow fields keep updating (= mirror).
- Watcher: `GET /status` on the extension port returns
  `{"active": bool, "spent": bool, "allow": [domains...]}` (spent = enforcer
  `seconds >= budget_seconds` for today, read from playtime_state.json).
- Extension: when active && spent, redirect every top-level navigation /
  active tab on a non-allowlisted domain to a bundled "leisure spent" page
  (shows used/budget, no bypass button); re-check on every tab update.
  Non-web tabs the classifier counts (file:, view-source:, blob:, data:,
  ftp:) are redirected too; browser-internal schemes never. The last
  /status is persisted: daemon unreachable + last known active = spent.
  `/status` itself is spent when the enforcer's `last_tick_at` is > 60 s old.
- daily-limits + i3blocks: the 🎮 block becomes `🛋 Leisure …` (same colours
  logic), the SHADOW block hides itself, shadow alerts + splash stop.
- Labels: "Leisure" in daily-limits text/GUI and enforcer notifications; JSON
  keys / identifiers stay `gaming_*`.

### Q7 done separately: archive GitHub kuhyx/kuhytrack with a README pointer.

## Phase 2 status (2026-10-19)

Built dormant: earned_time 0.16.0, leisure-watch 0.2.1, enforcer d2c4ea7, daily-limits ed274f2, i3blocks 66321e55. Enable with `leisure-watch go-live` (preflight needs Helium + LibreWolf started once on extension >= 0.2.1); undo with `leisure-watch go-live --undo`. Two finish-line reviews ran; all fixes landed.
