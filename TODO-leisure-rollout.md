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
              "pid": 1234, "label": "YouTube — mpv"}],
 "focus": {"app": "Helium", "title": "...", "domain": "youtube.com",
           "idle": false},
 "extensions": {"helium": 1760000000.0, "librewolf": null},
 "sig": "<hex hmac-sha256>"}
```
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

## Phase 2 (separate session, after kuhy OKs the shadow week)
Set `LEISURE_FROM` = next day; extension blocking + root kill of
non-allowlisted apps at 0; "Leisure" labels; remove `kuhytrack-budget.timer`;
archive GitHub `kuhyx/kuhytrack` (confirm first).
