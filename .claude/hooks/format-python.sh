#!/bin/sh
# PostToolUse hook (Edit|Write) — format an edited .py file with black.
#
# This monorepo needs TWO black versions and picking one breaks the other tree:
#
#   ai-brand-automator/   CI pins black==23.12.1  (requirements-dev.txt)
#   *-svc, OIA            CI installs black>=24.0.0 -> 26.x
#
# Measured 2026-10-05: black 26.5.1 reformats 82 of the 526 Django files that
# 23.12.1 calls clean, and 23.12.1 reformats 4 OIA files that 26.5.1 calls
# clean. So this resolves the binary per path rather than formatting with
# whichever black is first on PATH.
#
# Fails open: a formatter must never block an edit. The one thing it does warn
# about is a missing binary, because the alternative is a silent no-op.

set -u

# Hooks can run with a minimal PATH, so resolve jq rather than assuming it.
jq_bin=$(command -v jq 2>/dev/null) ||
    for candidate in /opt/homebrew/bin/jq /usr/local/bin/jq /usr/bin/jq; do
        [ -x "$candidate" ] && jq_bin="$candidate" && break
    done

if [ -z "${jq_bin:-}" ]; then
    printf '%s' '{"systemMessage":"Python auto-format is off: jq is not installed, so the hook cannot read the edited file path."}'
    exit 0
fi

file=$("$jq_bin" -r '.tool_input.file_path // empty') || exit 0
[ -n "$file" ] || exit 0

case "$file" in
*.py) ;;
*) exit 0 ;;
esac

# Vendored and installed trees are not ours to format.
case "$file" in
*/vendor/* | */.venv/* | */node_modules/* | */site-packages/*) exit 0 ;;
esac

# Prefer the project dir Claude Code exports; fall back to this script's own
# location so the hook still works if it is ever run by hand.
repo_root="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$repo_root" ]; then
    repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd) || exit 0
fi

case "$file" in
"$repo_root"/ai-brand-automator/*)
    black="$HOME/.claude/tools/black-23.12.1/bin/black"
    pin="23.12.1 (pinned by ai-brand-automator/requirements-dev.txt)"
    hint="python3 -m venv ~/.claude/tools/black-23.12.1 && ~/.claude/tools/black-23.12.1/bin/pip install black==23.12.1"
    ;;
*)
    black="$repo_root/.venv/bin/black"
    pin=">=24 (what the microservice CI jobs install)"
    hint="pip install -r <service>/requirements-dev.txt into $repo_root/.venv"
    ;;
esac

if [ ! -x "$black" ]; then
    "$jq_bin" -n \
        --arg path "$black" \
        --arg pin "$pin" \
        --arg hint "$hint" \
        '{systemMessage: "Python auto-format skipped: no black at \($path). This tree needs black \($pin). Install it with: \($hint)"}'
    exit 0
fi

# Silent on black's own failure: the usual cause is a file that is not valid
# Python yet mid-edit, and the next tool call surfaces that anyway.
"$black" --quiet "$file" >/dev/null 2>&1 || true
exit 0
