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

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 0
guard="$here/block-env-access.py"

payload=$(cat)
[ -n "$payload" ] || exit 0

python_bin=$(resolve python3) || python_bin=""

if [ -n "$python_bin" ] && [ -f "$guard" ]; then
    printf '%s' "$payload" | "$python_bin" "$guard"
    exit $?
fi

# Degraded: no python3, or the policy file is missing.
case "$payload" in
*.env* | *.envrc*)
    printf '%s\n' "Cannot evaluate the .env guard (python3 or the policy file is missing) and this call mentions a .env path, so it is blocked rather than allowed by default. Run it yourself if it is safe." >&2
    exit 2
    ;;
esac

exit 0
