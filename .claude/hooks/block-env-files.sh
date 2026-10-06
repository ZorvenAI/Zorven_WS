#!/bin/sh
# PreToolUse hook (Edit|Write) — refuse to edit a file that holds live secrets.
#
# Blocks .env, .env.<anything> (.local, .production, .staging, .docker.local,
# .test), *.env, .envrc (direnv, which routinely holds export AWS_SECRET_...)
# and anything inside a .env/ directory. Templates are exempt: 13 tracked
# .env.example files exist and editing them is routine.
#
# SCOPE, stated plainly because the wrong reading of it is dangerous: this
# covers the Edit and Write tools only. A Bash heredoc (`cat > .env <<EOF`),
# `printf >> .env`, `sed -i`, or `cp` can still write a .env, and Read can
# still pull one into context. Closing those needs a Bash matcher that parses
# shell commands, which is a separate decision -- so do not read this hook as
# "a .env cannot be touched".
#
# Within that scope it fails CLOSED: if the payload names a file but the path
# cannot be determined, it blocks. The version this replaced read an
# environment variable that hooks never receive, so it matched nothing and
# protected nothing for as long as it existed.

set -u

deny() {
    if [ -n "${jq_bin:-}" ]; then
        "$jq_bin" -n --arg reason "$1" \
            '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $reason}}'
        exit 0
    fi
    # No jq to build JSON with: exit 2 is the documented fallback block.
    printf '%s\n' "$1" >&2
    exit 2
}

resolve() {
    _found=$(command -v "$1" 2>/dev/null) && [ -n "$_found" ] && {
        printf '%s' "$_found"
        return 0
    }
    for _c in "/opt/homebrew/bin/$1" "/usr/local/bin/$1" "/usr/bin/$1" "/bin/$1"; do
        [ -x "$_c" ] && {
            printf '%s' "$_c"
            return 0
        }
    done
    return 1
}

jq_bin=$(resolve jq) || jq_bin=""

payload=$(cat)
# No payload at all is not a file write.
[ -n "$payload" ] || exit 0

if [ -n "$jq_bin" ]; then
    file=$(printf '%s' "$payload" | "$jq_bin" -r '.tool_input.file_path // .tool_input.notebook_path // empty') ||
        deny "Could not parse the tool input to check for a .env file; blocking rather than guessing."
else
    # Without jq, parse the path rather than blocking every edit in the repo:
    # a repo-wide lockout on a box without jq -- plausible on Linux or in a
    # container image, and settings.json is committed -- would stop all work
    # instead of guarding one file class.
    #
    # Builtins only, no sed/grep/head. Forcing this path with those tools
    # removed showed the guard failing OPEN on a .env, because the deny
    # decision hung on an external command that was not there. A guard must
    # not depend on anything it cannot assume.
    #
    # Known limit of the fallback: a path containing a literal double quote
    # truncates here. The jq path above handles it; this one is best-effort
    # parsing in a degraded environment.
    key_seen=0
    rest=""
    case "$payload" in
    *'"file_path"'*)
        key_seen=1
        rest=${payload#*'"file_path"'}
        ;;
    *'"notebook_path"'*)
        key_seen=1
        rest=${payload#*'"notebook_path"'}
        ;;
    esac

    if [ "$key_seen" -eq 1 ]; then
        rest=${rest#*:}
        # Trim leading whitespace without calling out to anything.
        while :; do
            case "$rest" in
            ' '* | '	'*) rest=${rest#?} ;;
            *) break ;;
            esac
        done
        case "$rest" in
        '"'*)
            rest=${rest#\"}
            file=${rest%%\"*}
            ;;
        # null, or any non-string value: no usable path.
        *) file="" ;;
        esac
    else
        file=""
    fi

    # The payload does name a path but we could not read it: that is the
    # fail-closed case the scope comment promises.
    if [ "$key_seen" -eq 1 ] && [ -z "$file" ]; then
        deny "jq is not installed and the file path could not be parsed from the hook payload, so this edit is blocked rather than risk writing to a .env file. Install jq (brew install jq)."
    fi
fi

# A payload carrying no path at all is not a file write this guard is about --
# a tool with neither key cannot be targeting a .env file.
[ -n "$file" ] || exit 0

name=${file##*/}

case "$name" in
*.example | *.sample | *.template) exit 0 ;;
esac

case "$file" in
# A .env used as a directory: config/.env/overrides and the like.
*/.env/*)
    deny "This path is inside a .env directory, which holds live secrets. Edit it by hand, outside Claude Code."
    ;;
esac

case "$name" in
.env | .env.* | *.env | .envrc | .envrc.*)
    deny "This is a .env file and holds live secrets. Edit it by hand, outside Claude Code."
    ;;
esac

exit 0
