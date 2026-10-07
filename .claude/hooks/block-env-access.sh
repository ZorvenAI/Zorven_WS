#!/bin/sh
# PreToolUse hook (Edit|Write|Bash) — refuse to touch files that hold live
# secrets.
#
# Covers a dotenv path reached three ways:
#   Edit / Write    tool_input.file_path (or notebook_path)
#   Bash            anywhere in tool_input.command
#
# A dotenv path means .env, .env.<anything> (.local, .production, .staging,
# .docker.local, .test), *.env, .envrc (direnv, which routinely holds
# export AWS_SECRET_...), or anything inside a .env/ directory. Templates are
# exempt: 13 tracked .env.example files exist and editing them is routine.
#
# POLICY FOR BASH, and why it is blunt: any command mentioning a non-template
# dotenv path is denied, whether it reads or writes. The precise alternative --
# match only `> .env`, `tee`, `cp` destinations, `sed -i` and friends -- has
# silent gaps: a path held in a variable, a tool nobody listed, a quoting form
# nobody thought of. A secrets guard with a silent gap reads as protection
# while providing none, which is the exact defect this hook family already
# shipped once. Blunt means the misses are false POSITIVES, which are visible
# and which you can work around by running the command yourself.
#
# Known false positives, accepted: `ls -la .env*`, `git check-ignore .env`,
# `docker compose --env-file .env up`. Each is denied with a message saying
# why, and none of them is silent.
#
# The largest class in practice is PROSE, not file access: a command whose text
# merely discusses a dotenv path is denied too -- `echo "copy .env.example to
# .env"`, or a `git commit -m` whose message mentions one. Writing this hook
# tripped exactly that. The workaround is to keep prose out of command lines:
# write the text to a file and pass it by reference (`git commit -F msg.txt`),
# which is better practice anyway. Distinguishing prose from an operand needs
# real shell parsing, and guessing at it is how silent gaps get in.
#
# Known gap, unavoidable at this layer: a target hidden in a shell variable
# (`cat > "$ENV_FILE"`) is invisible to any textual check.
#
# Not covered: Read. Pulling a .env into context is a real leak, but adding a
# Read matcher is a separate decision about how the assistant is allowed to
# inspect config, not a write-safety question.
#
# Fails CLOSED within that scope: if the payload names a target but the target
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

# Is this token a dotenv path? Templates answer no.
is_dotenv() {
    [ -n "${1:-}" ] || return 1
    _name=${1##*/}
    case "$_name" in
    *.example | *.sample | *.template) return 1 ;;
    esac
    # A .env used as a directory: config/.env/overrides and the like.
    case "$1" in
    */.env/*) return 0 ;;
    esac
    case "$_name" in
    .env | .env.* | *.env | .envrc | .envrc.*) return 0 ;;
    esac
    return 1
}

jq_bin=$(resolve jq) || jq_bin=""

payload=$(cat)
# No payload at all is not a tool call this guard is about.
[ -n "$payload" ] || exit 0

# ── Bash ────────────────────────────────────────────────────────────────────

command_text=""
if [ -n "$jq_bin" ]; then
    command_text=$(printf '%s' "$payload" | "$jq_bin" -r '.tool_input.command // empty') ||
        deny "Could not parse the tool input to check for a .env file; blocking rather than guessing."
else
    # Without jq, scan the raw payload. For a Bash call that is the command
    # text plus JSON noise, which over-approximates in the blocking direction.
    case "$payload" in
    *'"command"'*) command_text=$payload ;;
    esac
fi

if [ -n "$command_text" ]; then
    # Split on shell punctuation as well as whitespace, so `>.env`,
    # `of=.env` and `--env-file=.env` all surface as bare tokens.
    if tr_bin=$(resolve tr); then
        # '[ *]' pads set2 with spaces to the length of set1, so the two sets
        # cannot silently drift out of step as characters are added.
        normalised=$(printf '%s' "$command_text" | "$tr_bin" '><|&;()=,"'"'"'`{}[]' '[ *]')
        for token in $normalised; do
            if is_dotenv "$token"; then
                deny "This command references $token, which holds live secrets. Run it yourself if you need to -- this guard covers reads as well as writes, deliberately, because a precise rule would have silent gaps."
            fi
        done
    else
        # No tr: fall back to a substring check. Blunter than the tokenised
        # path, so a missing tool makes this guard block MORE, never less.
        case "$command_text" in
        *.env* | *.envrc*)
            deny "This command appears to reference a .env file, which holds live secrets, and tr is not available to check precisely. Run it yourself if you need to."
            ;;
        esac
    fi
    # A Bash call carries no file path, so nothing below applies.
    exit 0
fi

# ── Edit / Write / NotebookEdit ─────────────────────────────────────────────

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

if is_dotenv "$file"; then
    deny "This is a .env file and holds live secrets. Edit it by hand, outside Claude Code."
fi

exit 0
