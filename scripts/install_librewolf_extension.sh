#!/bin/bash

# ============================================================================
# Install the leisure-watch extension into the default LibreWolf profile.
#
# Profile method, so nothing is written outside $HOME (no policies.json, no
# root): the XPI goes to <profile>/extensions/<gecko-id>.xpi and user.js gets
#   xpinstall.signatures.required = false  (our XPI is unsigned)
#   extensions.autoDisableScopes  = 14     (auto-enable PROFILE-scope add-ons)
# Verified headless by scripts/verify_extension.py librewolf with exactly
# these prefs. Takes effect the next time LibreWolf starts -- it never
# restarts a browser.
#
# Usage: install_librewolf_extension.sh <path/to/leisure-watch@kuhy.dev.xpi>
#        [--profile DIR]   (DIR: for testing)
# ============================================================================

set -euo pipefail

readonly GECKO_ID="leisure-watch@kuhy.dev"
readonly ROOT="$HOME/.librewolf"
readonly MARK="// leisure-watch extension (scripts/install_librewolf_extension.sh)"
PROFILE=""
XPI=""

log() { printf 'leisure-watch librewolf: %s\n' "$1" >&2; }

# The profile LibreWolf actually opens: the [Install*] Default= entry, else
# the [Profile*] marked Default=1.
default_profile() {
    local ini="$ROOT/profiles.ini" line section="" path="" install_default=""
    local flagged=""
    [[ -f "$ini" ]] || return 1
    while IFS= read -r line || [[ -n $line ]]; do
        case $line in
            \[*\]) section="$line"; path="" ;;
            Default=*)
                if [[ $section == "[Install"* ]]; then
                    install_default="${line#Default=}"
                elif [[ ${line#Default=} == 1 && -n $path ]]; then
                    flagged="$path"
                fi
                ;;
            Path=*) path="${line#Path=}" ;;
        esac
    done < "$ini"
    local chosen="${install_default:-$flagged}"
    [[ -n "$chosen" ]] || return 1
    if [[ $chosen == /* ]]; then printf '%s' "$chosen"; else printf '%s' "$ROOT/$chosen"; fi
}

ensure_prefs() {
    local userjs="$PROFILE/user.js"
    touch "$userjs"
    if grep -qF -- "$MARK" "$userjs"; then
        log "prefs already in $userjs"
        return 0
    fi
    printf '\n%s\nuser_pref("xpinstall.signatures.required", false);\nuser_pref("extensions.autoDisableScopes", 14);\n' \
        "$MARK" >> "$userjs"
    log "prefs added to $userjs"
}

install_xpi() {
    local target="$PROFILE/extensions/$GECKO_ID.xpi"
    mkdir -p "$PROFILE/extensions"
    if [[ -f "$target" ]] && cmp -s "$XPI" "$target"; then
        log "XPI already current at $target"
        return 0
    fi
    cp "$XPI" "$target.tmp"
    mv "$target.tmp" "$target"
    log "installed $target"
}

main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --profile) PROFILE="$2"; shift 2 ;;
            -*) log "unknown option: $1"; exit 1 ;;
            *) XPI="$1"; shift ;;
        esac
    done
    [[ -f "$XPI" ]] || { log "usage: $(basename "$0") <xpi> [--profile DIR]"; exit 1; }
    if [[ -z "$PROFILE" ]]; then
        PROFILE="$(default_profile)" || { log "no LibreWolf profile; skipping"; return 0; }
    fi
    [[ -d "$PROFILE" ]] || { log "profile $PROFILE missing; skipping"; return 0; }
    install_xpi
    ensure_prefs
    log "takes effect the next time LibreWolf starts"
}

main "$@"
