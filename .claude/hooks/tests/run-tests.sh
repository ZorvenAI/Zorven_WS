#!/bin/sh
# Regression suite for block-env-access.sh.
#
#   sh .claude/hooks/tests/run-tests.sh                 # test the current guard
#   sh .claude/hooks/tests/run-tests.sh <other-script>  # e.g. a previous version
#
# Why this exists: this hook family shipped broken twice. Once reading an
# environment variable that hooks never receive, so it matched nothing; once
# blocking every Edit in the repo when jq was absent. Both would have been
# caught by feeding it the payload it actually receives.
#
# Every payload is checked for JSON validity before use. An invalid payload
# gets answered by the guard's fail-closed parse-deny rather than by the rule
# under test, which looks like a pass and proves nothing.

set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
guard=${1:-$here/../block-env-access.sh}
cases="$here/payloads.tsv"

[ -f "$guard" ] || {
    echo "no such guard: $guard" >&2
    exit 2
}
[ -f "$cases" ] || {
    echo "no payloads at $cases" >&2
    exit 2
}

if command -v jq >/dev/null 2>&1; then
    invalid=0
    while IFS="$(printf '\t')" read -r _want label payload; do
        case "${_want:-}" in '' | '#'*) continue ;; esac
        [ -n "${payload:-}" ] || continue
        printf '%s' "$payload" | jq -e . >/dev/null 2>&1 || {
            printf 'INVALID JSON in case: %s\n' "$label" >&2
            invalid=$((invalid + 1))
        }
    done <"$cases"
    [ "$invalid" -eq 0 ] || {
        printf '%s payload(s) are not valid JSON; fix them before trusting a pass\n' "$invalid" >&2
        exit 2
    }
fi

passed=0
failed=0
while IFS="$(printf '\t')" read -r want label payload; do
    case "${want:-}" in '' | '#'*) continue ;; esac
    [ -n "${payload:-}" ] || continue

    # Classify the way Claude Code does, not by "did anything come out".
    # A block is permissionDecision "deny" on stdout, or exit code 2. Output
    # on stderr with exit 0 does NOT block -- grading that as a deny would
    # score a crashing hook as a working one.
    out=$(printf '%s' "$payload" | sh "$guard" 2>/dev/null)
    rc=$?
    case "$out" in
    *'"permissionDecision"'*'"deny"'*) got=DENY ;;
    *) if [ "$rc" -eq 2 ]; then got=DENY; else got=allow; fi ;;
    esac

    if [ "$got" = "$want" ]; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
        printf 'FAIL  %-26s want=%-5s got=%s\n' "$label" "$want" "$got"
    fi
done <"$cases"

# ── the degraded path, which payloads.tsv cannot reach ──────────────────────
#
# With no python3 the wrapper falls back to a substring check. Review of #671
# found two fail-open holes in that fallback, so its invariants are asserted
# here rather than left to inspection:
#
#   * a plain dotenv path still blocks
#   * an escaped one (.) blocks too, because this path cannot decode it
#   * an ordinary file is still allowed -- the fallback must not lock the repo
#
# Reached through a documented test-only seam, since the suite cannot
# uninstall python3.
degraded() { # $1 = payload -> prints DENY or allow
    _out=$(printf '%s' "$1" | CLAUDE_ENV_GUARD_FORCE_DEGRADED=1 sh "$guard" 2>/dev/null)
    _rc=$?
    case "$_out" in
    *'"permissionDecision"'*'"deny"'*)
        printf 'DENY'
        return
        ;;
    esac
    if [ "$_rc" -eq 2 ]; then printf 'DENY'; else printf 'allow'; fi
}

check_degraded() { # $1 = label  $2 = want  $3 = payload
    _got=$(degraded "$3")
    if [ "$_got" = "$2" ]; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
        printf 'FAIL  %-26s want=%-5s got=%s (degraded)\n' "$1" "$2" "$_got"
    fi
}

check_degraded 'degraded: plain' DENY \
    '{"tool_name":"Write","tool_input":{"file_path":"/r/.env"}}'
check_degraded 'degraded: escaped dot' DENY \
    '{"tool_name":"Write","tool_input":{"file_path":"/r/.env"}}'
check_degraded 'degraded: ordinary file' allow \
    '{"tool_name":"Edit","tool_input":{"file_path":"/r/app/config.py"}}'
check_degraded 'degraded: no dotenv at all' allow \
    '{"tool_name":"Bash","tool_input":{"command":"pytest -q"}}'

printf '%s passed, %s failed (%s)\n' "$passed" "$failed" "$guard"
[ "$failed" -eq 0 ]
