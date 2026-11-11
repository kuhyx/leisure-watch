#!/bin/bash

# ============================================================================
# Deploy leisure-watch for real (idempotent, desktop user, never root).
#
#   1. fast-forward the live checkout ~/src/leisure-watch (fails on a dirty
#      tree or a diverged branch);
#   2. run that checkout's install.sh (non-editable package, extension build,
#      browser user parts, unit install + restart; never restarts a browser);
#   3. health check, exit non-zero naming the failed check:
#      unit active, restarted by this run, installed package == checkout,
#      watcher serving a fresh now.json on 127.0.0.1.
#
# Usage: scripts/deploy.sh [--check-only]
#   --check-only  skip steps 1-2 (and the "restarted by this run" check).
# The root-owned Helium wrapper merge stays a separate step (install.sh
# prints it); this script does not touch it.
# ============================================================================

set -euo pipefail

# The system interpreter, never a venv that happens to be first on PATH:
# root's enforcer and the unit both use /usr/bin/python3's user site.
export PATH="/usr/bin:$PATH"

readonly LIVE="${LEISURE_WATCH_LIVE:-$HOME/src/leisure-watch}"
readonly UNIT="leisure-watch.service"
readonly FRESH_SEC=30
readonly WAIT_SEC=30

log() { printf 'leisure-watch deploy: %s\n' "$1" >&2; }
fail() { log "FAIL: $1"; exit 1; }

update_checkout() {
    git -C "$LIVE" pull --ff-only --quiet || fail "git pull --ff-only in $LIVE"
    log "checkout at $(git -C "$LIVE" rev-parse --short HEAD)"
}

check_active() {
    systemctl --user is-active --quiet "$UNIT" || fail "$UNIT not active"
}

check_restarted_since() {
    local since="$1" started
    started="$(systemctl --user show "$UNIT" -p ExecMainStartTimestamp --value --timestamp=unix)"
    ((${started#@} >= since)) || fail "$UNIT was not restarted by this deploy"
}

check_installed_matches() {
    local installed
    installed="$(env -C / python3 -c 'import leisure_watch, os; print(os.path.dirname(leisure_watch.__file__))')" \
        || fail "leisure_watch not importable by /usr/bin/python3"
    diff -rq -x __pycache__ "$LIVE/leisure_watch" "$installed" > /dev/null \
        || fail "installed package $installed differs from $LIVE/leisure_watch"
}

# The watcher's HTTP doc (status --json falls back to a standalone compute
# and says so on stderr; that fallback is a failure here).
live_doc_fresh() {
    local doc err
    err="$(mktemp)"
    doc="$(env -C / python3 -m leisure_watch status --json 2> "$err")" || { rm -f "$err"; return 1; }
    if [[ -s "$err" ]]; then rm -f "$err"; return 1; fi
    rm -f "$err"
    jq -e --argjson now "$(date +%s)" --argjson max "$FRESH_SEC" \
        '(.ts | type == "number") and ($now - .ts) < $max and (.sig | type == "string")' \
        <<< "$doc" > /dev/null
}

check_now_json() {
    local deadline=$((SECONDS + WAIT_SEC))
    until live_doc_fresh; do
        ((SECONDS < deadline)) || fail "watcher not serving a fresh now.json within ${WAIT_SEC}s"
        sleep 1
    done
}

main() {
    [[ $EUID -ne 0 ]] || fail "run as the desktop user, not root"
    local check_only=0
    case "${1:-}" in
        "") ;;
        --check-only) check_only=1 ;;
        *) fail "unknown argument: $1 (usage: $0 [--check-only])" ;;
    esac
    if ((!check_only)); then
        local since
        since="$(date +%s)"
        update_checkout
        "$LIVE/install.sh" || fail "install.sh"
        check_active
        check_restarted_since "$since"
    else
        check_active
    fi
    check_installed_matches
    check_now_json
    log "OK $(git -C "$LIVE" rev-parse --short HEAD)"
}

main "$@"
