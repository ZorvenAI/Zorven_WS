"""Number the agreements in a stored description — without rewording them.

The description is a legal record: once written it is never reworded. So the
numbered Agreements in a meeting record are *found* in the stored text, not
regenerated. This is plain text parsing with no model call, and the split is
lossless: ``before + section + after`` is the original description, character
for character.

The section is the ``## Agreements`` heading and everything up to the next
``## `` heading. Each top-level bullet in it is one agreement; lines that
follow a bullet without starting a new one belong to it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^##\s+agreements\s*:?\s*$", re.IGNORECASE)
_ANY_H2 = re.compile(r"^##\s+\S")
#: A top-level bullet: at most one leading space, then ``-`` or ``*``. A deeper
#: indent is a sub-point of the agreement above it, not a new agreement.
_BULLET = re.compile(r"^ ?[-*]\s+(?P<text>.*\S.*)$")
#: A horizontal rule. Descriptions separate sections with one, and it is
#: layout, not part of the agreement written above it.
_RULE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")


@dataclass(frozen=True)
class Agreement:
    number: str
    text: str


@dataclass(frozen=True)
class AgreementSplit:
    """A description, divided around its Agreements section.

    ``before + section + after`` equals the original description exactly.
    """

    before: str
    section: str
    after: str
    #: Text under the heading that precedes the first bullet, if any.
    preamble: str = ""
    agreements: tuple[Agreement, ...] = field(default_factory=tuple)

    @property
    def remainder(self) -> str:
        """The description without its Agreements section."""
        return self.before + self.after

    @property
    def original(self) -> str:
        return self.before + self.section + self.after


def split_agreements(description: str) -> AgreementSplit:
    """Find and number the agreements in ``description``.

    With no Agreements heading the whole text is ``before`` and there are no
    agreements — the description said none were made, and that is recorded as
    such rather than guessed at.
    """
    text = description or ""
    lines = text.splitlines(keepends=True)

    start = next(
        (i for i, line in enumerate(lines) if _HEADING.match(line.strip())), None
    )
    if start is None:
        return AgreementSplit(before=text, section="", after="")

    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if _ANY_H2.match(lines[i].rstrip("\r\n"))
        ),
        len(lines),
    )

    preamble: list[str] = []
    items: list[list[str]] = []
    for raw in lines[start + 1 : end]:
        line = raw.rstrip("\r\n")
        # Rule before bullet: ``* * *`` would otherwise read as a bullet whose
        # text is ``* *``.
        if not line.strip() or _RULE.match(line):
            continue
        bullet = _BULLET.match(line)
        if bullet:
            items.append([bullet.group("text").rstrip()])
        elif items:
            items[-1].append(line.strip())
        else:
            preamble.append(line.strip())

    return AgreementSplit(
        before="".join(lines[:start]),
        section="".join(lines[start:end]),
        after="".join(lines[end:]),
        preamble="\n".join(preamble),
        agreements=tuple(
            Agreement(number=f"A-{index}", text="\n".join(parts))
            for index, parts in enumerate(items, start=1)
        ),
    )
