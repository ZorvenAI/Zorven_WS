#!/bin/sh
# PreToolUse hook (Edit|Write|Bash) — thin wrapper around block-env-access.py.
#
# The policy and its gaps are documented in that file. This wrapper exists for
# one reason: deciding what happens when python3 is not there.
#
# It does NOT block everything in that case. An earlier version of this guard
# blocked every Edit and Write when jq was missing, which -- since
# settings.json is committed -- would have cost a teammate without that tool
# the ability to edit any file in the repo. A guard may not hold the whole
# repository hostage to its own dependency.
#
# Instead, with no python3, it falls back to a blunt substring check: a payload
# mentioning a dotenv path is blocked, anything else passes. Coarser than the
# parser, and only in the blocking direction.
#
# Two properties this file is careful about, both from review of #671:
#
#   1. The main path reads NOTHING. It execs python3 so the payload flows
#      straight through on stdin. The previous version did `payload=$(cat)`
#      first, which meant a PATH without `cat` -- a stripped container
#      environment, a hook run from a minimal shell -- left the payload empty
#      and the guard waved a .env write through, exit 0. Verified: the old
#      shape ALLOWED a dotenv write with cat unavailable.
#   2. The degraded path reads stdin with shell builtins only, for the same
#      reason, and treats a JSON escape sequence as undecodable-therefore-
#      suspicious: "/r/.env" is a .env path that no substring check can
#      see. The parser decodes it correctly; this path cannot, so it blocks.

set -u

resolve() {
    _found=$(command -v "$1" 2>/dev/null) && [ -n "$_found" ] && {
        printf '%s' "$_found"
        return 0
    }
    for _c in "/usr/bin/$1" "/opt/homebrew/bin/$1" "/usr/local/bin/$1" "/bin/$1"; do
        [ -x "$_c" ] && {
            printf '%s' "$_c"
            return 0
        }
    done
    return 1
}

# Parameter expansion, not dirname: probing finding 1 with a stripped PATH
# showed `dirname` missing too, which sent the main path into the degraded
# fallback. It still blocked, but for the wrong reason. Builtins only here.
case "$0" in
*/*) here=${0%/*} ;;
*) here=. ;;
esac
here=$(CDPATH= cd -- "$here" && pwd) || exit 0
guard="$here/block-env-access.py"

# Test-only seam. The suite has to exercise the degraded path and cannot
# uninstall python3 to do it.
if [ "${CLAUDE_ENV_GUARD_FORCE_DEGRADED:-}" = "1" ]; then
    python_bin=""
else
    python_bin=$(resolve python3) || python_bin=""
fi

if [ -n "$python_bin" ] && [ -f "$guard" ]; then
    # exec, not a pipe: stdin is untouched, so nothing here needs to read it.
    exec "$python_bin" "$guard"
fi

# ── Degraded: no python3, or the policy file is missing ─────────────────────

block() {
    printf '%s\n' "$1" >&2
    exit 2
}

payload=""
while IFS= read -r line || [ -n "$line" ]; do
    payload="$payload$line"
done
[ -n "$payload" ] || exit 0

degraded_reason="Cannot evaluate the .env guard (python3 or the policy file is missing) and this call references a .env path, so it is blocked rather than allowed by default. Run it yourself if it is safe."

case "$payload" in
*.env* | *.envrc*) block "$degraded_reason" ;;
esac

# An escape sequence anywhere plus the letters "env" somewhere: this path
# cannot decode . or \\, so it cannot rule out a disguised dotenv path.
case "$payload" in
*'\u'* | *'\\'*)
    case "$payload" in
    *env*) block "Cannot evaluate the .env guard (python3 is missing) and this payload contains escape sequences around the text \"env\", which may hide a .env path from a plain-text check. Blocking rather than guessing." ;;
    esac
    ;;
esac

exit 0
