"""Fallback prompts for ADPUB — CRITICAL agent (touches ad spend).

AC-2: Fallback triggers HIGH-severity warning.
"""

CRITICAL_AGENT = True  # AC-2: HIGH-severity warning on fallback

FALLBACK_SYSTEM = (
    "You are a Meta Ads publishing specialist. Manage campaign publishing, "
    "human approval gates, and spend guardrails. Ensure all ads meet "
    "compliance before going live."
)
FALLBACK_PUBLISHING = (
    "Prepare Meta Ads campaign for publishing. Translate to Meta Marketing "
    "API format and validate targeting specs. Respond with valid JSON."
)
FALLBACK_APPROVAL = (
    "Generate human approval summary highlighting key decisions requiring "
    "approval. Respond with valid JSON."
)
FALLBACK_MAP = {
    "zorven-wf3-adpub-system": FALLBACK_SYSTEM,
    "zorven-wf3-adpub-publishing": FALLBACK_PUBLISHING,
    "zorven-wf3-adpub-approval": FALLBACK_APPROVAL,
}
