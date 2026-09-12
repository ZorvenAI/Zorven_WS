#!/usr/bin/env python3
"""Fail on test assertions that cannot fail.

Written after a review sweep of the OIA suite found four tests that passed
regardless of behaviour. Each was a different shape of the same mistake, and
each had survived review because a passing test reads as a covered one:

* ``assert result.count == n or result.count < n`` — that is ``<= n``, and it
  accepted every short result while being named "the count is always
  honoured".
* ``assert isinstance(result.count, int)`` — true of every outcome, including
  the code under test returning nothing at all.
* ``assert response.status_code in (403, 405)`` — passes whether the surface
  is read-only or merely denies this user, which are different guarantees.
* a test with no assertion whose name promised behaviour.

This checks the *shape* of an assertion, not its truth. It cannot tell a weak
assertion from a legitimately narrow one, so every rule is suppressible — but
only with a reason, in a comment on the line:

    assert isinstance(skill, BaseSkill)  # weak-assert: ok — the type contract

A suppression with no reason after the dash is itself an error. The point is
not to win an argument with the linter; it is to make someone write down why
the narrow assertion is the right one, where the next reader will see it.

Usage:
    python scripts/check_weak_assertions.py <path> [<path> ...]
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

SUPPRESSION = re.compile(r"#\s*weak-assert:\s*ok\s*[—-]\s*(?P<reason>\S.*)$")
BARE_SUPPRESSION = re.compile(r"#\s*weak-assert:\s*ok\s*[—-]?\s*$")


class Finding:
    def __init__(self, path: str, line: int, test: str, rule: str, detail: str):
        self.path, self.line, self.test = path, line, test
        self.rule, self.detail = rule, detail

    def __str__(self) -> str:
        return (
            f"{self.path}:{self.line}: [{self.rule}] in {self.test}\n"
            f"    {self.detail}"
        )


class Checker(ast.NodeVisitor):
    def __init__(self, path: pathlib.Path) -> None:
        self.path = str(path)
        self.lines = path.read_text().splitlines()
        self.findings: list[Finding] = []
        self.test: str | None = None

    # ── suppression ──────────────────────────────────────────────────

    def _suppressed(self, lineno: int) -> bool:
        """True when the line carries a reasoned suppression.

        Checks the assertion's own line and the one above it, because black
        wraps long assertions and the comment often ends up on the opening
        line.
        """
        for offset in (0, -1):
            index = lineno - 1 + offset
            if 0 <= index < len(self.lines):
                line = self.lines[index]
                if BARE_SUPPRESSION.search(line):
                    self.findings.append(
                        Finding(
                            self.path,
                            lineno,
                            self.test or "?",
                            "unreasoned-suppression",
                            "weak-assert: ok needs a reason after the dash",
                        )
                    )
                    return True
                if SUPPRESSION.search(line):
                    return True
        return False

    def _report(self, node: ast.AST, rule: str, detail: str) -> None:
        lineno = getattr(node, "lineno", 0)
        if self._suppressed(lineno):
            return
        self.findings.append(Finding(self.path, lineno, self.test or "?", rule, detail))

    # ── rules ────────────────────────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        previous, self.test = self.test, node.name
        if node.name.startswith("test_"):
            self._check_has_a_check(node)
        self.generic_visit(node)
        self.test = previous

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def _check_has_a_check(self, node: ast.AST) -> None:
        """A test that asserts nothing and raises nothing checks nothing.

        ``with pytest.raises(...)`` counts: the context manager is the
        assertion. So does a bare call to a helper that raises — but this
        cannot see that, which is what the suppression is for.
        """
        for child in ast.walk(node):
            if isinstance(child, (ast.Assert, ast.With, ast.AsyncWith)):
                return
        self._report(node, "no-assertion", "the test body asserts nothing")

    def visit_Assert(self, node: ast.Assert) -> None:
        source = self.lines[node.lineno - 1].strip() if node.lineno else ""
        test = node.test

        if isinstance(test, ast.Constant) and test.value:
            self._report(node, "constant-true", f"always true: {source[:70]}")

        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
            comparisons = [v for v in test.values if isinstance(v, ast.Compare)]
            if len(comparisons) >= 2:
                subjects = {ast.dump(c.left) for c in comparisons}
                if len(subjects) == 1:
                    self._report(
                        node,
                        "or-of-comparisons",
                        "several comparisons on one value, or'd together — "
                        "check this is not equivalent to a single looser one",
                    )

        if isinstance(test, ast.Call) and getattr(test.func, "id", "") == "isinstance":
            self._report(
                node,
                "isinstance-only",
                "asserts a type, not a value — true of every outcome the "
                "code can produce with that type",
            )

        if isinstance(test, ast.Compare) and any(
            isinstance(op, ast.In) for op in test.ops
        ):
            container = test.comparators[0] if test.comparators else None
            if (
                isinstance(container, (ast.Tuple, ast.List, ast.Set))
                and len(container.elts) >= 2
                and all(isinstance(e, ast.Constant) for e in container.elts)
                and "status" in source
            ):
                self._report(
                    node,
                    "permissive-status-set",
                    "accepts several status codes — say which one is the "
                    "contract, or suppress with why either is correct",
                )

        self.generic_visit(node)


def check(paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for raw in paths:
        root = pathlib.Path(raw)
        files = sorted(root.rglob("test_*.py")) if root.is_dir() else [root]
        for path in files:
            checker = Checker(path)
            checker.visit(ast.parse(path.read_text()))
            findings.extend(checker.findings)
    return findings


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    findings = check(sys.argv[1:])
    if not findings:
        print("no weak assertions found")
        return 0

    for finding in findings:
        print(finding)
    print(
        f"\n{len(findings)} weak assertion(s). Strengthen them, or add\n"
        "    # weak-assert: ok — <why the narrow assertion is right>\n"
        "on the line."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
