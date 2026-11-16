#!/bin/bash

# ============================================================================
# Load the leisure-watch extension into Helium on every launch.
#
# Chromium honours only the LAST --load-extension switch; earlier ones are
# dropped silently. Helium's own wrapper puts helium-browser-flags.conf first
# and the caller's arguments after it, and /usr/local/bin/helium-browser is
# browser-preexec-wrapper, whose exec line carries LeechBlock's flag(s). So a
# conf entry alone is overridden by the wrapper and the extension never loads
# -- which is how the nudge sat dead until 2026-10-10.
#
# Two steps, both idempotent:
#   1. the conf entry (the fallback when the wrapper passes no flag at all);
#   2. if the wrapper's exec line passes any --load-extension, collapse every
#      one of them into a single comma-joined flag that also lists extension/.
#      The wrapper is root-owned, so step 2 runs sudo.
# Takes effect the next time Helium starts -- it never restarts a browser.
#
# --remove undoes both steps (stand-down): the extension path leaves the conf
# entry and the wrapper's flag; the other extensions in them stay. The
# wrapper defaults to $LEISURE_WATCH_WRAPPER (tests) or helium-browser's.
#
# Usage: install_helium_extension.sh <unpacked-extension-dir> [--no-wrapper]
#        [--wrapper-only] [--wrapper PATH] [--remove]   (PATH: for testing)
#
# Adapted from leetcode-guard/scripts/install_nudge_extension.sh: the same
# merge, keeping LeechBlock, uBlock and the leetcode nudge in the one flag.
# ============================================================================

set -euo pipefail

EXTENSION=""
DO_CONF=1
DO_WRAPPER=1
readonly FLAGS_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/helium-browser-flags.conf"
readonly FLAG_RE='--load-extension="([^"]*)"'
DO_REMOVE=0
WRAPPER="${LEISURE_WATCH_WRAPPER:-$(readlink -f /usr/local/bin/helium-browser 2>/dev/null || true)}"
TEMP_FILE=""

cleanup() {
    if [[ -n "$TEMP_FILE" && -f "$TEMP_FILE" ]]; then
        rm -f "$TEMP_FILE"
    fi
}

trap cleanup EXIT

log() { printf 'leisure-watch extension: %s\n' "$1" >&2; }

ensure_conf_entry() {
    touch "$FLAGS_FILE"
    if grep -qF -- "$EXTENSION" "$FLAGS_FILE"; then
        log "already in $FLAGS_FILE"
        return 0
    fi
    if grep -q -- '^--load-extension=' "$FLAGS_FILE"; then
        # One switch only: extend its list instead of adding another.
        local line updated=""
        while IFS= read -r line; do
            [[ $line == --load-extension=* ]] && line="$line,$EXTENSION"
            updated+="$line"$'\n'
        done < "$FLAGS_FILE"
        # Written in place rather than mv'd, so a symlinked config stays linked.
        printf '%s' "$updated" > "$FLAGS_FILE"
    else
        printf -- '--load-extension=%s\n' "$EXTENSION" >> "$FLAGS_FILE"
    fi
    log "added to $FLAGS_FILE"
}

# Every path named by any --load-extension="..." on $1, then $EXTENSION,
# de-duplicated and comma-joined.
merged_paths() {
    local rest="$1" joined="" path
    local -a parts
    local -A seen=()
    while [[ $rest =~ $FLAG_RE ]]; do
        IFS=',' read -r -a parts <<< "${BASH_REMATCH[1]}"
        for path in "${parts[@]}" "$EXTENSION"; do
            [[ -z $path || -n ${seen[$path]:-} ]] && continue
            seen[$path]=1
            joined+="${joined:+,}$path"
        done
        rest="${rest#*"${BASH_REMATCH[0]}"}"
    done
    printf '%s' "$joined"
}

# The exec line with all its --load-extension flags replaced by one, placed
# right before "$@" so the caller's arguments still come last.
rewrite_exec_line() {
    local line="$1" stripped
    stripped="$line"
    while [[ $stripped =~ \ ?$FLAG_RE ]]; do
        stripped="${stripped/"${BASH_REMATCH[0]}"/}"
    done
    printf '%s' "${stripped/ \"\$@\"/ --load-extension=\"$(merged_paths "$line")\" \"\$@\"}"
}

merge_into_wrapper() {
    if [[ -z "$WRAPPER" || ! -f "$WRAPPER" ]] || ! file "$WRAPPER" | grep -q text; then
        log "no script wrapper in front of Helium; the conf entry is enough"
        return 0
    fi
    local line new_line count
    line="$(grep -m1 -E '^exec .*--load-extension=' "$WRAPPER" || true)"
    if [[ -z $line ]]; then
        log "$WRAPPER passes no --load-extension; the conf entry is enough"
        return 0
    fi
    count="$(grep -o -- '--load-extension=' <<< "$line" | wc -l)"
    if ((count == 1)) && [[ $line == *"$EXTENSION"* ]]; then
        log "already in $WRAPPER's single --load-extension"
        return 0
    fi
    [[ $line == *' "$@"'* ]] || {
        log "cannot find \"\$@\" on $WRAPPER's exec line; not touching it"
        return 1
    }
    new_line="$(rewrite_exec_line "$line")"
    swap_wrapper_line "$line" "$new_line"
    log "merged $count --load-extension flag(s) in $WRAPPER into one"
}

# Replace one exact line of the wrapper. cp onto the existing file keeps its
# owner and mode; the wrapper is root-owned, so that cp may need sudo.
swap_wrapper_line() {
    local old="$1" new="$2" current
    TEMP_FILE="$(mktemp)"
    while IFS= read -r current || [[ -n $current ]]; do
        if [[ $current == "$old" ]]; then
            printf '%s\n' "$new"
        else
            printf '%s\n' "$current"
        fi
    done < "$WRAPPER" > "$TEMP_FILE"
    if [[ -w "$WRAPPER" ]]; then
        cp "$TEMP_FILE" "$WRAPPER"
    else
        sudo cp "$TEMP_FILE" "$WRAPPER"
    fi
}

# Drop $EXTENSION from the comma-joined path list $1.
without_extension() {
    local joined="" path
    local -a parts
    IFS=',' read -r -a parts <<< "$1"
    for path in "${parts[@]}"; do
        [[ -z $path || $path == "$EXTENSION" ]] && continue
        joined+="${joined:+,}$path"
    done
    printf '%s' "$joined"
}

remove_from_conf() {
    [[ -f $FLAGS_FILE ]] || return 0
    local line kept out=""
    while IFS= read -r line || [[ -n $line ]]; do
        if [[ $line == --load-extension=* ]]; then
            kept="$(without_extension "${line#--load-extension=}")"
            [[ -z $kept ]] || out+="--load-extension=$kept"$'\n'
        else
            out+="$line"$'\n'
        fi
    done < "$FLAGS_FILE"
    # In place, so a symlinked config stays linked.
    printf '%s' "$out" > "$FLAGS_FILE"
    log "removed from $FLAGS_FILE"
}

remove_from_wrapper() {
    if [[ -z "$WRAPPER" || ! -f "$WRAPPER" ]] || ! file "$WRAPPER" | grep -q text; then
        log "no script wrapper in front of Helium; nothing to remove"
        return 0
    fi
    local line kept flag
    line="$(grep -m1 -E '^exec .*--load-extension=' "$WRAPPER" || true)"
    if [[ $line != *"$EXTENSION"* || ! $line =~ $FLAG_RE ]]; then
        log "not in $WRAPPER"
        return 0
    fi
    flag="${BASH_REMATCH[0]}"
    kept="$(without_extension "${BASH_REMATCH[1]}")"
    if [[ -n $kept ]]; then
        swap_wrapper_line "$line" "${line/"$flag"/--load-extension=\"$kept\"}"
    else
        swap_wrapper_line "$line" "${line/ "$flag"/}"
    fi
    log "removed from $WRAPPER"
}

main() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --wrapper) WRAPPER="$2"; shift 2 ;;
            --no-wrapper) DO_WRAPPER=0; shift ;;
            --wrapper-only) DO_CONF=0; shift ;;
            --remove) DO_REMOVE=1; shift ;;
            -*) log "unknown option: $1"; exit 1 ;;
            *) EXTENSION="$(realpath -m "$1")"; shift ;;
        esac
    done
    # The removal names the path only; the directory may already be gone.
    if [[ -z "$EXTENSION" ]] || { ((! DO_REMOVE)) && [[ ! -f "$EXTENSION/manifest.json" ]]; }; then
        log "usage: $(basename "$0") <unpacked-extension-dir> [--no-wrapper|--wrapper-only|--remove]"
        exit 1
    fi
    readonly EXTENSION
    if ((DO_REMOVE)); then
        if ((DO_CONF)); then remove_from_conf; fi
        if ((DO_WRAPPER)); then remove_from_wrapper; fi
        return 0
    fi
    if ((DO_CONF)); then ensure_conf_entry; fi
    if ((DO_WRAPPER)); then merge_into_wrapper; fi
    log "takes effect the next time Helium starts (never restarted from here)"
}

main "$@"; exit $?
