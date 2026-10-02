"""Which mic was open when a given moment of audio was captured (O-09).

O-03 gave every mic its own STT stream, which made attribution trivial: the
stream *was* the speaker. O-09's energy gate makes that model untenable — a
gated-off channel sends nothing, and ``GoogleSTTAdapter`` drives its rollover
from incoming chunks, so a starved stream sails past Google's ~300 s cap
without rolling over and is dead when its speaker finally talks.

So the gate feeds one stream, and attribution moves here. The browser already
prefixes every audio frame with its stream index, so the server can record when
the open channel changed and later ask which channel was open at the moment a
transcript covers.

Resolution is by the transcript's own ``t_start`` rather than by whatever
channel is open when the result arrives. STT finals lag their audio by around a
second, so "current speaker at emit time" would attribute the tail of every
handover to whoever spoke next.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field


@dataclass
class SpeakerTimeline:
    """Append-only record of which stream index was open, over audio time.

    Times are seconds on the STT stream's own clock, so they are directly
    comparable with the ``t_start`` an ``STTResult`` carries.
    """

    #: Transition times, ascending. Kept parallel to ``_indices`` rather than as
    #: tuples so ``bisect`` can search it without a key function.
    _times: list[float] = field(default_factory=list)
    _indices: list[int] = field(default_factory=list)

    def record(self, at: float, index: int) -> None:
        """Note that ``index`` became the open channel at ``at``.

        A repeat of the current channel is dropped: the gate re-evaluates every
        analysis window, so without this the timeline would grow by ~10 entries
        a second and say nothing new.

        An out-of-order time is also dropped. Audio arrives in order, so a
        backwards timestamp means a clock that moved, and inserting it would
        make ``resolve`` return an answer for a moment that never existed.
        """
        if self._indices and self._indices[-1] == index:
            return
        if self._times and at < self._times[-1]:
            return
        self._times.append(at)
        self._indices.append(index)

    def resolve(self, at: float) -> int | None:
        """The channel open at ``at``, or ``None`` if nothing was recorded yet.

        Audio captured before the first transition is unattributed rather than
        assigned to the first channel to speak — a legal transcript should not
        guess, and a single-mic recording records no transitions at all.
        """
        if not self._times:
            return None
        position = bisect_right(self._times, at)
        if position == 0:
            # The moment predates every transition we know about.
            return None
        return self._indices[position - 1]

    def __len__(self) -> int:
        return len(self._times)
