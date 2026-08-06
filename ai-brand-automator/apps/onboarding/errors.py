"""Error codes this app returns, mirroring the §18.4 taxonomy.

Only the codes the Django side actually raises are listed. The agent service
holds the full enum in ``app/core/errors.py``; this is not a second source of
truth so much as the subset the API surfaces, and the values must match.

**ERR-18 is provisional**, added by B-04 for the same reason ERR-17 was added
by A-06: the code the card asked for is already spent on something else.

B-04's AC-2 says an illegal transition returns "409 with ERR-11", but §18.4
assigns ERR-11 to a grounding failure — a value dropped under OG-01. Reusing
it would make a state-machine refusal indistinguishable from a fabricated
brand fact being discarded, which are unrelated problems with unrelated fixes.

ERR-05 ("session not found or wrong state") is closer in meaning but is
documented as 404, while §9.4 says plainly that an invalid transition
"returns 409". So there is no existing 409 code for this, and a new one is
the honest answer. Both the design and the backlog need reconciling.
"""

from __future__ import annotations

#: Session id does not exist, or is not visible to this tenant (§18.4, 404).
SESSION_NOT_FOUND = "ERR-05"

#: A non-terminal session already exists for the company (§18.4, 409). Raised
#: by the B-01 partial unique index rather than by an application check.
LIVE_SESSION_ACTIVE = "ERR-06"

#: Provisional (B-04): the requested status is not reachable from the current
#: one (§9.4, 409). See the module docstring.
INVALID_TRANSITION = "ERR-18"
