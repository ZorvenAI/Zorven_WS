"""Edit distance for EVT-109.

§17.3 uses "a rising mean edit distance" as the signal that a prompt version
has regressed, so the number has to be Levenshtein distance specifically.
``difflib`` is stdlib but computes a *similarity ratio* — a different quantity
with a different meaning — and neither ``Levenshtein`` nor ``rapidfuzz`` is a
dependency of this project.

Fifteen lines of standard dynamic programming is cheaper than a dependency for
one metric, and exact rather than approximate.

Also holds :func:`normalise_company_name`, which must stay identical to the
agent service's copy — see its docstring.
"""

from __future__ import annotations

import re


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


#: Legal-form suffixes carry no identity and vary by how the operator typed
#: them. Kept as a module constant so the test corpus and the function cannot
#: drift apart silently.
_LEGAL_SUFFIXES = r"\b(pvt|private|ltd|limited|llp|inc|incorporated|co|corp|llc)\b"


def normalise_company_name(name: str) -> str:
    """Reduce a business name to a stable lookup key.

    **This must stay identical to** ``normalise_company_name`` in
    ``onboarding-intelligence-agent-svc/app/skills/research_business.py``.
    The agent stores briefs under this key and the Onboarding Interface looks
    them up by it, so a divergence means the Interface silently finds nothing
    and the operator is told there is no research when there is.

    Duplicated rather than shared because the two live in separate deployables
    with no common package. ``tests/test_name_normalisation.py`` on each side
    runs the same corpus, so a change to one fails the other.

    The failure mode is bounded — a miss returns no brief rather than the
    wrong one — but "your research vanished" is still the wrong answer.
    """
    lowered = name.strip().lower()
    lowered = re.sub(r"[.,]", "", lowered)
    lowered = re.sub(_LEGAL_SUFFIXES, " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()
