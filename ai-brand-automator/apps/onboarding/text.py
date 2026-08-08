"""Edit distance for EVT-109.

§17.3 uses "a rising mean edit distance" as the signal that a prompt version
has regressed, so the number has to be Levenshtein distance specifically.
``difflib`` is stdlib but computes a *similarity ratio* — a different quantity
with a different meaning — and neither ``Levenshtein`` nor ``rapidfuzz`` is a
dependency of this project.

Fifteen lines of standard dynamic programming is cheaper than a dependency for
one metric, and exact rather than approximate.
"""

from __future__ import annotations


def levenshtein(left: str, right: str) -> int:
    """Single-character insertions, deletions and substitutions between two
    strings.

    Two rows rather than a full matrix: the values are all a review action
    needs, and an operator can paste a long founder story into a field.
    """
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,  # deletion
                    current[j - 1] + 1,  # insertion
                    previous[j - 1] + (left_char != right_char),  # substitution
                )
            )
        previous = current
    return previous[-1]
