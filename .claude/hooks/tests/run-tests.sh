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

    out=$(printf '%s' "$payload" | sh "$guard" 2>&1)
    if [ -n "$out" ]; then got=DENY; else got=allow; fi

    if [ "$got" = "$want" ]; then
        passed=$((passed + 1))
    else
        failed=$((failed + 1))
        printf 'FAIL  %-26s want=%-5s got=%s\n' "$label" "$want" "$got"
    fi
done <"$cases"

printf '%s passed, %s failed (%s)\n' "$passed" "$failed" "$guard"
[ "$failed" -eq 0 ]
