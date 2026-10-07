#!/usr/bin/env python3
"""PreToolUse guard (Edit|Write|Bash): refuse to WRITE files holding secrets.

A dotenv path means ``.env``, ``.env.<anything>`` (.local, .production,
.staging, .docker.local, .test), ``*.env``, ``.envrc`` (direnv, which routinely
holds ``export AWS_SECRET_...``), or anything inside a ``.env/`` directory.
Templates are exempt -- 13 tracked ``.env.example`` files exist and editing
them is routine.

Scope, and the deliberate choice in it
--------------------------------------
Reads are allowed. An earlier version denied any command naming a dotenv path,
reads included, on the grounds that a precise rule would have silent gaps.
That held, but the cost was wrong: the dominant false positive turned out to be
*prose* -- ``ls -la .env*``, ``docker compose --env-file``, and any commit
message mentioning a path -- none of which touches a file. Writes are what
destroy or leak secrets irreversibly, so writes are what this blocks.

This is a MITIGATION, not a boundary. Shell is not statically analysable and
the gaps below are real:

* a target held in a variable -- ``cat > "$ENV_FILE"``
* a target built inside a quoted script -- ``python -c "open('.env','w')"``,
  ``bash -c``, ``eval``
* a writer not in the tables below
* anything reached via ``xargs``, where operands arrive on stdin

``Read`` is also not covered: pulling a dotenv file into context is a real leak
but a separate policy question about inspection, not write safety.

Within its scope it fails CLOSED: an unparseable command that mentions a
dotenv path is denied, and an unparseable payload is denied.
"""

from __future__ import annotations

import json
import os
import shlex
import sys

TEMPLATE_SUFFIXES = (".example", ".sample", ".template")

# Operators whose following token is a file being written.
# ">&" and "<&" are descriptor duplications, not paths, so they are absent.
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}

# Boundaries between simple commands.
SEPARATORS = {"|", "||", "&&", ";", "&", ";;", "(", ")", "{", "}", "\n"}

# Wrappers that take the real command as their first operand.
WRAPPERS = {"sudo", "env", "command", "nohup", "time", "nice", "doas", "exec"}

# Any dotenv operand is a write or a destruction.
ANY_OPERAND_MUTATORS = {
    "rm",
    "shred",
    "unlink",
    "truncate",
    "mv",
    "tee",
    "sponge",
    "dd",
}

# Only the destination (last non-flag operand) is a write; a dotenv path as the
# SOURCE is a read, which this policy allows.
DEST_ONLY_MUTATORS = {"cp", "install", "ln", "rsync"}

# Editors that rewrite in place, but only when asked to.
INPLACE_EDITORS = {"sed", "perl", "ruby", "awk", "gawk", "sd", "ex"}

DENY_EDIT = (
    "This is a .env file and holds live secrets. Edit it by hand, outside "
    "Claude Code."
)


GLOB_CHARS = "*?["


def _literal_is_dotenv(candidate: str) -> bool:
    if not candidate:
        return False
    candidate = candidate.rstrip("/")
    name = os.path.basename(candidate)
    if name.endswith(TEMPLATE_SUFFIXES):
        return False
    # A dotenv path used as a directory: config/.env/overrides and the like.
    if "/.env/" in candidate or candidate.startswith(".env/"):
        return True
    if name in (".env", ".envrc"):
        return True
    if name.startswith((".env.", ".envrc.")):
        return True
    return name.endswith(".env")


def is_dotenv(path: str) -> bool:
    """Does this token name a secrets file? Templates answer no.

    Globs are expanded by the shell, not by us, so `rm .env*` arrives as the
    single token ".env*" and matched nothing under a literal-only check -- a
    hole big enough to delete every secrets file in a directory. Both the
    literal text before the first metacharacter and the text after the last
    are tested, which catches `.env*` by its prefix and `*.env` by its suffix,
    while `.environment*` and `.env.example*` still answer no.
    """
    if not path:
        return False
    if not any(char in path for char in GLOB_CHARS):
        return _literal_is_dotenv(path)

    first = min(path.find(char) for char in GLOB_CHARS if char in path)
    last = max(path.rfind(char) for char in GLOB_CHARS if char in path)
    prefix = path[:first]
    suffix = path[last + 1 :]
    return _literal_is_dotenv(prefix) or _literal_is_dotenv(suffix)


def mentions_dotenv(text: str) -> bool:
    """Blunt check for the fail-closed paths, where parsing is unavailable."""
    return any(is_dotenv(piece) for piece in text.replace("=", " ").split())


def split_segments(tokens: list[str]) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [seg for seg in segments if seg]


def command_name(segment: list[str]) -> tuple[str, list[str]]:
    """The command being run, skipping wrappers and VAR=value prefixes."""
    index = 0
    while index < len(segment):
        token = segment[index]
        name = os.path.basename(token)
        if "=" in token and not token.startswith("-"):
            index += 1  # VAR=value prefix
            continue
        if name in WRAPPERS:
            index += 1
            continue
        return name, segment[index + 1 :]
    return "", []


def written_paths(segment: list[str]) -> list[str]:
    """Every path this simple command would write to."""
    targets: list[str] = []

    # 1. Redirection targets, wherever they appear.
    for index, token in enumerate(segment):
        if token in REDIRECTS and index + 1 < len(segment):
            targets.append(segment[index + 1])

    name, operands = command_name(segment)
    # Drop redirect operators and their targets before reading operands.
    cleaned: list[str] = []
    skip_next = False
    for token in operands:
        if skip_next:
            skip_next = False
            continue
        if token in REDIRECTS:
            skip_next = True
            continue
        cleaned.append(token)

    flags = [token for token in cleaned if token.startswith("-")]
    positional = [token for token in cleaned if not token.startswith("-")]

    if name in ANY_OPERAND_MUTATORS:
        if name == "dd":
            # Only of= writes; if= is the source.
            targets += [
                token.split("=", 1)[1] for token in cleaned if token.startswith("of=")
            ]
        else:
            targets += positional
    elif name in DEST_ONLY_MUTATORS:
        if positional:
            targets.append(positional[-1])
    elif name in INPLACE_EDITORS:
        if any(flag.startswith("-i") or flag == "--in-place" for flag in flags):
            targets += positional

    return targets


def deny(reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        payload = json.loads(raw)
    except ValueError:
        if mentions_dotenv(raw):
            deny(
                "The hook payload could not be parsed and it mentions a .env "
                "path, so this call is blocked rather than guessed at."
            )
        return

    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return

    command = tool_input.get("command")
    if isinstance(command, str) and command:
        try:
            lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            # Unbalanced quotes and the like: fall back to the blunt check, so
            # an unparseable command blocks more rather than less.
            if mentions_dotenv(command):
                deny(
                    "This command could not be parsed and it mentions a .env "
                    "path, so it is blocked rather than guessed at. Run it "
                    "yourself if it is safe."
                )
            return

        for segment in split_segments(tokens):
            for target in written_paths(segment):
                if is_dotenv(target):
                    deny(
                        f"This command writes to {target}, which holds live "
                        "secrets. Reading one is allowed; writing, moving or "
                        "deleting it is not -- do that by hand."
                    )
        return

    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if isinstance(path, str) and path and is_dotenv(path):
        deny(DENY_EDIT)


if __name__ == "__main__":
    main()
