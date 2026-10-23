#!/bin/bash

# ============================================================================
# Install leisure-watch for the desktop user (idempotent, never as root).
#
#   1. tool deps (xprintidle, xprop, pactl) via pacman if any is missing;
#   2. the package, NON-editable, into the user site-packages (root's
#      enforcer imports it from there);
#   3. the extension builds under ~/.local/share/leisure-watch/extension;
#   4. Helium: helium-browser-flags.conf entry (user part only -- the
#      root-owned wrapper merge is scripts/install_helium_extension.sh, run
#      by kuhy); LibreWolf: profile install (all inside $HOME);
#   5. the systemd --user unit, enabled and (re)started.
# Never restarts a browser.
# ============================================================================

set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
readonly REPO
readonly DATA="${XDG_DATA_HOME:-$HOME/.local/share}/leisure-watch"
readonly EXT_OUT="$DATA/extension"
readonly UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
readonly UNIT="leisure-watch.service"

log() { printf 'leisure-watch install: %s\n' "$1" >&2; }

ensure_tools() {
    local -A pkg_of=([xprintidle]=xprintidle [xprop]=xorg-xprop [pactl]=libpulse)
    local -a missing=()
    local tool
    for tool in "${!pkg_of[@]}"; do
        command -v "$tool" > /dev/null || missing+=("${pkg_of[$tool]}")
    done
    ((${#missing[@]})) || return 0
    if sudo -n pacman -S --needed --noconfirm "${missing[@]}"; then
        log "installed ${missing[*]}"
        return 0
    fi
    log "needs root: run  ! sudo pacman -S --needed ${missing[*]}  then re-run $0"
    exit 1
}

readonly EARNED_TIME="earned-time @ git+https://github.com/kuhyx/utils@earned-time-v0.17.0#subdirectory=earned_time"

ensure_earned_time() {
    # --no-deps below never pulls earned-time; install the pin only when the
    # C6 API is missing (it is usually already there for the enforcer).
    env -C / python3 -c 'from earned_time import leisure_active' 2> /dev/null && return 0
    python3 -m pip install --user --break-system-packages --quiet "$EARNED_TIME"
    log "installed $EARNED_TIME"
}

install_package() {
    ensure_earned_time
    python3 -m pip install --user --break-system-packages --no-deps --quiet \
        --force-reinstall "$REPO"
    log "package installed: $(env -C / python3 -c 'import leisure_watch; print(leisure_watch.__file__)')"
}

build_extension() {
    # Run from / so the installed package (not the checkout) does the build.
    env -C / python3 -m leisure_watch build-extension "$REPO/extension" "$EXT_OUT" > /dev/null
    log "extension built under $EXT_OUT"
}

install_unit() {
    mkdir -p "$UNIT_DIR"
    install -m 0644 "$REPO/systemd/$UNIT" "$UNIT_DIR/$UNIT"
    systemctl --user daemon-reload
    systemctl --user enable "$UNIT" > /dev/null 2>&1
    # restart, not start: a running watcher must pick up the new package.
    systemctl --user restart "$UNIT"
    log "$UNIT enabled and running"
}

main() {
    [[ $EUID -ne 0 ]] || { log "run as the desktop user, not root"; exit 1; }
    ensure_tools
    install_package
    build_extension
    "$REPO/scripts/install_helium_extension.sh" "$EXT_OUT/chromium" --no-wrapper
    "$REPO/scripts/install_librewolf_extension.sh" "$EXT_OUT/leisure-watch@kuhy.dev.xpi"
    install_unit
    log "on PATH: $(command -v leisure-watch || echo "MISSING: add ~/.local/bin to PATH")"
    log "Helium also needs the root wrapper merge once:"
    log "  ! $REPO/scripts/install_helium_extension.sh $EXT_OUT/chromium --wrapper-only"
}

main "$@"
