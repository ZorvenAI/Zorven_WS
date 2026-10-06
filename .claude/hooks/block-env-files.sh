#!/bin/sh
# PreToolUse hook (Edit|Write) — refuse to edit a file that holds live secrets.
#
# Blocks .env, .env.<anything> (.local, .production, .staging, .docker.local,
# .test) and *.env. Templates are exempt: 13 tracked .env.example files exist
# and editing them is routine.
#
# Fails CLOSED. A guard that quietly stops guarding is worse than no guard --
# the version this replaced read an environment variable that hooks never
# receive, so it matched nothing and protected nothing for as long as it
# existed. If this script cannot determine the target path, it blocks.

set -u

deny() {
    # Built with jq where available so the reason is escaped correctly;
    # exit 2 is the fallback block, which feeds stderr back to the model.
    if [ -n "${jq_bin:-}" ]; then
        "$jq_bin" -n --arg reason "$1" \
            '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
        exit 0
    fi
    printf '%s\n' "$1" >&2
    exit 2
}

jq_bin=$(command -v jq 2>/dev/null) ||
    for candidate in /opt/homebrew/bin/jq /usr/local/bin/jq /usr/bin/jq; do
        [ -x "$candidate" ] && jq_bin="$candidate" && break
    done

if [ -z "${jq_bin:-}" ]; then
    deny "Cannot check whether this is a .env file: jq is not installed, so the secrets guard is blocking every edit rather than failing open. Install jq (brew install jq) or remove the PreToolUse hook from .claude/settings.json."
fi

file=$("$jq_bin" -r '.tool_input.file_path // empty') ||
    deny "Could not parse the tool input to check for a .env file; blocking rather than guessing."

# No path at all is not a file edit this guard is about.
[ -n "$file" ] || exit 0

name=${file##*/}

case "$name" in
*.example | *.sample | *.template) exit 0 ;;
esac

case "$name" in
.env | .env.* | *.env)
    deny "This is a .env file and holds live secrets. Edit it by hand, outside Claude Code."
    ;;
esac

exit 0
