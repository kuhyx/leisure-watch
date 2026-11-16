#!/bin/bash

# ============================================================================
# Stand leisure-watch down (idempotent, desktop user, never as root).
#
# The gaming/leisure budget is gone (earned_time 0.22.0), so nothing consumes
# the watcher's facts. This undoes what install.sh put in place:
#   1. the systemd --user unit: disabled, stopped, file and enablement gone;
#   2. Helium: the extension path leaves helium-browser-flags.conf and the
#      root-owned browser wrapper's --load-extension (sudo -n; other
#      extensions in both stay);
#   3. LibreWolf: the XPI leaves the default profile;
#   4. the built extension under ~/.local/share/leisure-watch/extension;
#   5. the root switch file /etc/leisure-watch/leisure_from (sudo -n).
# Kept on purpose: the pip package (the root enforcer imports
# leisure_watch.procscan from it), the day logs, the allowlist and the
# LibreWolf prefs (see install_librewolf_extension.sh). No browser restarts:
# the extension drops out the next time each browser starts.
#
# Usage: install.sh --uninstall   (or this script directly)
# Test seams: LEISURE_WATCH_SWITCH, LEISURE_WATCH_WRAPPER (see the scripts).
# ============================================================================

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
readonly REPO
readonly DATA="${XDG_DATA_HOME:-$HOME/.local/share}/leisure-watch"
readonly EXT_OUT="$DATA/extension"
readonly UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly UNIT="leisure-watch.service"
readonly SWITCH="${LEISURE_WATCH_SWITCH:-/etc/leisure-watch/leisure_from}"

log() { printf 'leisure-watch uninstall: %s\n' "$1" >&2; }

stop_unit() {
    if [[ -f "$UNIT_DIR/$UNIT" ]]; then
        systemctl --user disable --now "$UNIT"
        rm -f "$UNIT_DIR/$UNIT"
        systemctl --user daemon-reload
        log "$UNIT disabled, stopped, removed"
    else
        log "$UNIT not installed"
    fi
}

remove_browser_parts() {
    "$REPO/scripts/install_helium_extension.sh" "$EXT_OUT/chromium" --remove
    "$REPO/scripts/install_librewolf_extension.sh" --remove
    rm -rf "$EXT_OUT"
    log "extension build removed"
}

remove_switch() {
    sudo -n rm -f "$SWITCH"
    local dir
    dir="$(dirname "$SWITCH")"
    if [[ -d $dir ]]; then
        sudo -n rmdir --ignore-fail-on-non-empty "$dir"
    fi
    log "switch file $SWITCH removed"
}

main() {
    [[ $EUID -ne 0 ]] || { log "run as the desktop user, not root"; exit 1; }
    stop_unit
    remove_browser_parts
    remove_switch
}

main "$@"
