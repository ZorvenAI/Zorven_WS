"""Fallback prompts for Odoo Worker Agent -- used when MLflow and Redis are both unreachable.

These are verbatim copies of the static instruction portions currently used in
production. They serve as the last-resort fallback when both Redis cache and
MLflow are unavailable. The prompt-optimization-svc (MLflow) is the primary
source of truth; these fallbacks ensure zero-downtime degradation.

Note: Dynamic portions (persona prompt, available tools list, observation
history, skill context) remain code-constructed in llm.py. Only the STATIC
instruction preambles are loaded from prompt-optimization-svc.
"""

# Static Odoo 19 field conventions + plan format instructions
# extracted from GeminiClient._build_plan_prompt()
FALLBACK_PLAN_INSTRUCTIONS = """\
## Odoo 19 Field Conventions
- To find customers: use domain [['customer_rank', '>', 0]] on res.partner
- To find suppliers: use domain [['supplier_rank', '>', 0]] on res.partner
- The 'customer' and 'is_customer' fields do NOT exist in Odoo 19
- For partners with email: add ['email', '!=', false] to domain
- Use odoo_search_read (not odoo_search) for reading records with fields
- When no filter is needed, use an empty domain: []

## Instructions
Analyze the user's request and decide what to do.
You MUST use the available MCP tools to query or modify Odoo data.
NEVER answer from memory or fabricate data — always call tools first.
Only set is_complete=true AFTER tool results have been observed \
(i.e. there are previous observations above).

Respond with a JSON object:
{
  "thought": "Your reasoning about what to do",
  "tool_calls": [{"tool_name": "...", "arguments": {...}}],
  "is_complete": false,
  "final_answer": ""
}

Set is_complete=true and provide final_answer ONLY when previous \
observations show the task is complete. If there are no previous \
observations, you MUST call at least one tool.

IMPORTANT:
- If previous observations show a tool FAILED, do NOT retry it.
- If a model 'doesn't exist', the module is not installed — skip it.
- For email campaigns, use marketing_create_campaign (NOT website_create_page).
- Summarize partial results if some steps fail."""

# Static critical rules for reflection
# extracted from GeminiClient._build_reflect_prompt()
FALLBACK_REFLECT_INSTRUCTIONS = """\
## Instructions
Evaluate the tool results. Respond with JSON:
{
  "reflection": "Your analysis of the results",
  "is_complete": true/false,
  "final_answer": "Summary for the user (if complete)",
  "next_actions": [{"tool_name": "...", "arguments": {...}}]
}

CRITICAL RULES:
- If a tool call FAILED, do NOT retry the same tool. Try a \
different tool or approach instead.
- If an Odoo model 'doesn't exist', the module is not installed. \
Do NOT retry — skip that step and proceed with what you can do.
- Set is_complete=true and summarize partial results if some \
steps succeeded and others cannot be completed.
- For email campaigns use marketing_create_campaign, NOT \
website_create_page.
- Set is_complete=true if the task is done or no further \
actions are needed."""

# Map catalog names -> fallback constants for programmatic lookup
FALLBACK_MAP = {
    "zorven-odoo-worker-plan": FALLBACK_PLAN_INSTRUCTIONS,
    "zorven-odoo-worker-reflect": FALLBACK_REFLECT_INSTRUCTIONS,
}
