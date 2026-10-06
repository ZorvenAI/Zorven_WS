#!/bin/sh
# PostToolUse hook (Edit|Write) — format an edited .py file with the black
# version that file's own tree pins.
#
# Why this is not just "run black": this monorepo declares FOUR exact black
# pins plus a floor, across 27 services and the Django app --
#
#   ai-brand-automator               black==23.12.1   (CI gates on it)
#   13 *-svc dirs                    black==24.10.0 / 25.1.0 / 26.1.0
#   the rest                         black>=24.0.0
#
# -- and the versions disagree about real files. Measured 2026-10-05: black
# 26.5.1 reformats 82 of 526 files under ai-brand-automator/ that 23.12.1
# calls clean, and 23.12.1 reformats 4 OIA files that 26.5.1 calls clean. So
# formatting with whichever black is on PATH rewrites code into a state the
# tree's own CI rejects. The pin is read from the tree's requirements file
# rather than hardcoded here, because a table in a comment goes stale and
# silently resumes mis-formatting.
#
# Fails open and silent: a formatter must never block an edit. The one thing
# it reports is being unable to find a black matching the pin, because the
# alternative is an invisible no-op -- the defect this hook replaced.

set -u

# --- payload ----------------------------------------------------------------
# Hooks can run with a minimal PATH, so resolve tools rather than assuming.
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

jq_bin=$(resolve jq) || {
    printf '%s' '{"systemMessage":"Python auto-format is off: jq is not installed, so the hook cannot read the edited file path."}'
    exit 0
}

file=$("$jq_bin" -r '.tool_input.file_path // .tool_input.notebook_path // empty') || exit 0
[ -n "$file" ] || exit 0

case "$file" in
*.py) ;;
*) exit 0 ;;
esac

# Vendored and installed trees are not ours to format.
case "$file" in
*/vendor/* | */.venv/* | */node_modules/* | */site-packages/*) exit 0 ;;
esac

# --- locate the checkout that owns the file ---------------------------------
# Deliberately NOT $CLAUDE_PROJECT_DIR: git worktrees live under
# .claude/worktrees/<name>/ and contain their own full copy of the monorepo
# (505 Django .py files in the one open today). Anchoring on the session's
# project dir sent every one of those files down the wrong branch. Asking git
# which checkout owns the file is correct for a worktree, a second clone, and
# the /private symlink form of a macOS temp path alike.
git_bin=$(resolve git) || exit 0
dir=$(dirname "$file")
[ -d "$dir" ] || exit 0
root=$("$git_bin" -C "$dir" rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -n "$root" ] || exit 0

# Is this that monorepo at all? A .py in some unrelated checkout, in ~/.claude,
# or in the session scratchpad is none of our business.
[ -d "$root/ai-brand-automator" ] || exit 0

rel=${file#"$root"/}
tree=${rel%%/*}
# A file at the repo root belongs to no tree, so no pin applies.
[ "$tree" != "$rel" ] || exit 0

# --- the pin that tree declares ---------------------------------------------
pin=""
for req in "$root/$tree/requirements-dev.txt" "$root/$tree/requirements.txt"; do
    [ -f "$req" ] || continue
    # -E, not BRE: BSD sed (macOS) has no \| alternation, so the basic-regex
    # form matched nothing here and every tree silently fell through to "no
    # pin" -- i.e. no formatting at all.
    pin=$(sed -E -n 's/^black[[:space:]]*(==|>=)[[:space:]]*([0-9][0-9.]*).*/\1 \2/p' "$req" | head -1)
    [ -n "$pin" ] && break
done
# A tree that does not use black is left alone.
[ -n "$pin" ] || exit 0

op=${pin%% *}
want=${pin##* }

version_of() {
    "$1" --version 2>/dev/null | sed -n 's/^black,*[[:space:]]*\([0-9][0-9.]*\).*/\1/p' | head -1
}

satisfies() {
    _v=$(version_of "$1")
    [ -n "$_v" ] || return 1
    case "$op" in
    "==") [ "$_v" = "$want" ] ;;
    # Floor pins: anything at or above it. sort -V puts the lower first.
    ">=") [ "$(printf '%s\n%s\n' "$want" "$_v" | sort -V | head -1)" = "$want" ] ;;
    *) return 1 ;;
    esac
}

black=""
for candidate in \
    "$HOME/.claude/tools/black-$want/bin/black" \
    "$root/.venv/bin/black" \
    "$(resolve black || true)"; do
    [ -n "$candidate" ] || continue
    [ -x "$candidate" ] || continue
    if satisfies "$candidate"; then
        black="$candidate"
        break
    fi
done

if [ -z "$black" ]; then
    if [ "$op" = "==" ]; then
        hint="python3 -m venv ~/.claude/tools/black-$want && ~/.claude/tools/black-$want/bin/pip install black==$want"
    else
        hint="pip install 'black>=$want' into $root/.venv"
    fi
    "$jq_bin" -n --arg tree "$tree" --arg req "black$op$want" --arg hint "$hint" \
        '{systemMessage: "Python auto-format skipped for \($tree)/: no black matching \($req) was found, and formatting with a different version would rewrite code its CI rejects. Install it with: \($hint)"}'
    exit 0
fi

# Silent on black's own failure: the usual cause is a file that is not valid
# Python yet mid-edit, and the next tool call surfaces that anyway.
"$black" --quiet "$file" >/dev/null 2>&1 || true
exit 0
