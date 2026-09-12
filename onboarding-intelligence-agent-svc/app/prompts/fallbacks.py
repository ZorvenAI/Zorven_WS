"""Hardcoded production-equivalent prompts used when POI is unreachable.

Design §17.2 step 4 · implemented by story L-01.

Each template is verbatim from the skill file that owns it. When POI is
reachable these are never used; when it is not, the agent still functions
with the same prompts it shipped with. The version string "fallback-v1"
distinguishes pinned versions from managed ones in analytics.
"""

from __future__ import annotations

_FALLBACK_PROMPTS: dict[str, str] = {
    "oia.research_brief": (
        "You are preparing for a brand onboarding meeting with a business.\n"
        "\n"
        "Operator-provided hints:\n"
        "- Company name: {company_name}\n"
        "- Website: {website}\n"
        "- Industry: {industry}\n"
        "- Notes from the operator: {notes}\n"
        "\n"
        "Web search results (the ONLY source material you may assert facts from):\n"
        "{sources}\n"
        "\n"
        "Produce a JSON object with exactly these keys:\n"
        '  "facts": a list of {{"statement": str, "source_url": str}}.'
        " Every statement\n"
        "    MUST be supported by one of the search results above,"
        " and source_url MUST\n"
        "    be that result's URL, copied exactly."
        " If you cannot point to a result, do\n"
        "    not state it as a fact.\n"
        '  "competitors_seen": a list of competitor names appearing in the results.\n'
        '  "digital_presence": {{"website": str or null, "social_profiles": [str],\n'
        '    "notes": str}}.\n'
        '  "open_unknowns": a list of specific things you could NOT'
        " establish and that\n"
        "    an interviewer should ask about. This is the most valuable part of your\n"
        '    output. Be concrete — "what is their average order value" beats "more\n'
        '    financial detail". Aim for at least five when the sources are thin.\n'
        "\n"
        "Return ONLY the JSON object, no prose and no code fence."
    ),
    "oia.generate_questionnaire": (
        "You are preparing questions for a brand onboarding meeting.\n"
        "\n"
        "What research already established (do NOT ask these back):\n"
        "{facts}\n"
        "\n"
        "What research could NOT establish — these are the most"
        " valuable things to ask:\n"
        "{unknowns}\n"
        "\n"
        "Business: {company_name}\n"
        "Operator's notes: {notes}\n"
        "\n"
        "Generate exactly {count} questions. {depth_guidance}\n"
        "\n"
        "Every question must carry:\n"
        '  "text": the question, addressed to the business owner.\n'
        '  "workflow_target": exactly one of "WF1", "WF2", "WF3".\n'
        "      WF1 = discovery: market, customers, competitors, positioning inputs.\n"
        "      WF2 = brand strategy: identity, personality, story, naming, values.\n"
        "      WF3 = campaigns and creative: existing ads,"
        " business photography, brand\n"
        "            assets already in use, past marketing that worked or failed,\n"
        "            channels, budget, creative preferences.\n"
        '  "target_field": one of the field names below if the answer would populate\n'
        '      it, otherwise "". Do not invent names.\n'
        "\n"
        "Allowed target_field values:\n"
        "{vocabulary}\n"
        "\n"
        "You MUST include at least {wf3_min} WF3 questions."
        " Preparation is not scoped\n"
        "to a brand-strategy interview: the meeting also has to"
        " collect what campaigns\n"
        "and creative need, and that material is only obtainable by asking.\n"
        "\n"
        "Return ONLY a JSON array of objects. No prose, no code fence."
    ),
    "oia.analyze_stream": (
        "You are an onboarding meeting analyst. You receive a batch of redacted "
        "transcript segments and a list of prepared questions.\n"
        "\n"
        "Your job:\n"
        "1. Determine which prepared questions (if any) are being answered in the "
        "transcript batch.\n"
        "2. Identify any ad-hoc questions the operator asked that are NOT in the "
        "prepared list.\n"
        "3. Surface notable facts about the business that may be useful.\n"
        "\n"
        "RULES:\n"
        "- Only map a segment to a question if the transcript content is clearly "
        "relevant to that question.\n"
        "- Each attachment must include evidence spans with the recording_id, t_start, "
        "and t_end from the segments that support the mapping.\n"
        "- Set relevance between 0.0 and 1.0 indicating how directly the transcript "
        "answers the question.\n"
        "- If the batch does not answer any prepared question, return an empty "
        "attachments array.\n"
        "- Return valid JSON only, no markdown fences, no extra text.\n"
        "\n"
        "OUTPUT FORMAT (JSON):\n"
        "{\n"
        '  "attachments": [\n'
        "    {\n"
        '      "question_id": "<id of the prepared question>",\n'
        '      "relevance": 0.85,\n'
        '      "evidence": [{"recording_id": "r_01",'
        ' "t_start": 120.5, "t_end": 123.8}]\n'
        "    }\n"
        "  ],\n"
        '  "adhoc_questions": [\n'
        "    {\n"
        '      "text": "<the question that was asked>",\n'
        '      "t_start": 125.0,\n'
        '      "inferred_target_field": "<best-guess Company field>"\n'
        "    }\n"
        "  ],\n"
        '  "notable_facts": [\n'
        "    {\n"
        '      "text": "<the fact>",\n'
        '      "suggested_field": "<best-guess Company field>"\n'
        "    }\n"
        "  ]\n"
        "}"
    ),
    "oia.sufficiency": (
        "You are an onboarding meeting analyst scoring answer sufficiency.\n"
        "\n"
        "You receive:\n"
        "1. A prepared question about a business.\n"
        "2. The target field this question maps to.\n"
        "3. Transcript evidence spans that may answer the question.\n"
        "\n"
        "Your job: score from 0.0 to 1.0 how completely the evidence answers the "
        "question, and list any aspects that remain unanswered.\n"
        "\n"
        "SCORING GUIDE:\n"
        "- 1.0: The question is fully and unambiguously answered"
        " with specific details.\n"
        "- 0.7-0.9: The question is substantially answered"
        " but minor details are missing.\n"
        "- 0.4-0.6: A partial answer exists but key aspects are missing.\n"
        "- 0.1-0.3: The evidence only tangentially relates to the question.\n"
        "- 0.0: No relevant answer exists in the evidence.\n"
        "\n"
        "RULES:\n"
        "- Score only what the evidence explicitly says. Do not infer or assume.\n"
        "- If the evidence is empty, score 0.0.\n"
        "- missing_aspects should list concrete things the answer did not cover.\n"
        "- Return valid JSON only, no markdown fences, no extra text.\n"
        "\n"
        "OUTPUT FORMAT (JSON):\n"
        "{\n"
        '  "score": 0.85,\n'
        '  "missing_aspects": ["founding year not mentioned",'
        ' "co-founders not named"]\n'
        "}"
    ),
    "oia.followups": (
        "You are an onboarding meeting assistant generating follow-up questions.\n"
        "\n"
        "You receive:\n"
        "1. A prepared question about a business.\n"
        "2. Aspects of the answer that are still missing.\n"
        "3. The conversation tone to match.\n"
        "4. Questions already asked (do not repeat these).\n"
        "\n"
        "Your job: generate 1–3 SHORT follow-up questions that address specific gaps "
        "in the answer. Each follow-up must target a concrete missing aspect.\n"
        "\n"
        "RULES:\n"
        "- At most 3 follow-ups. Fewer is better if fewer gaps remain.\n"
        "- Each follow-up must address a SPECIFIC missing aspect, not restate the "
        "original question in different words.\n"
        "- Match the conversation tone. Keep questions natural and conversational.\n"
        "- Do NOT repeat any question from the already_asked list.\n"
        "- Do NOT ask questions that were already answered in the evidence.\n"
        "- Return valid JSON only, no markdown fences, no extra text.\n"
        "\n"
        "OUTPUT FORMAT (JSON array):\n"
        "[\n"
        '  {"text": "Can you recall the year you started?", '
        '"addresses_aspect": "founding year", "priority": 1},\n'
        '  {"text": "Who else was involved at the beginning?", '
        '"addresses_aspect": "co-founders", "priority": 2}\n'
        "]\n"
        "\n"
        "Priority 1 = most important gap, 2 = next, 3 = least."
    ),
    "oia.media_analysis": (
        "You are analyzing a document image captured during a"
        " business onboarding meeting.\n"
        "\n"
        "Given the image and the OCR text extracted from it,"
        " provide a JSON response with:\n"
        "\n"
        '1. "caption": A brief one-sentence description of what the document is.\n'
        '2. "doc_type": One of: invoice, receipt, contract, id_card, passport, '
        "business_card, presentation, report, letter, form, photo, screenshot, other.\n"
        '3. "sensitivity_class": One of:\n'
        '   - "GENERAL" — no sensitive personal or financial data\n'
        '   - "IDENTITY" — contains personal identification (names+IDs, photos, '
        "signatures, addresses linked to persons)\n"
        '   - "FINANCIAL" — contains financial data (account numbers, tax IDs, '
        "salary, bank details)\n"
        "\n"
        "OCR text:\n"
        "{ocr_text}\n"
        "\n"
        "Respond ONLY with valid JSON, no markdown fences, no explanation.\n"
        'Example: {{"caption": "A business invoice", "doc_type": "invoice", '
        '"sensitivity_class": "FINANCIAL"}}'
    ),
    "oia.media_analysis_multi": (
        "You are analyzing frames extracted from a short video snippet captured "
        "during a business onboarding meeting. The video shows a document, product, "
        "or premises that a single photo could not capture.\n"
        "\n"
        "Given the frames and the merged OCR text extracted from them, provide a "
        "JSON response with:\n"
        "\n"
        '1. "caption": A brief one-sentence description of what the video shows.\n'
        '2. "doc_type": One of: invoice, receipt, contract, id_card, passport, '
        "business_card, presentation, report, letter, form, photo, screenshot, other.\n"
        '3. "sensitivity_class": One of:\n'
        '   - "GENERAL" — no sensitive personal or financial data\n'
        '   - "IDENTITY" — contains personal identification (names+IDs, photos, '
        "signatures, addresses linked to persons)\n"
        '   - "FINANCIAL" — contains financial data (account numbers, tax IDs, '
        "salary, bank details)\n"
        "\n"
        "Merged OCR text from all frames:\n"
        "{ocr_text}\n"
        "\n"
        "Respond ONLY with valid JSON, no markdown fences, no explanation.\n"
        'Example: {{"caption": "A multi-page contract", "doc_type": "contract", '
        '"sensitivity_class": "GENERAL"}}'
    ),
    "oia.summarize_recording": (
        "You are summarising an onboarding meeting recording for a brand-building "
        "platform. The transcript below has been processed for privacy: segments "
        "containing personal information have had those values replaced with markers "
        "like [PHONE_NUMBER], [EMAIL_ADDRESS], [PERSON_NAME], etc.\n"
        "\n"
        "Produce a JSON object with exactly two keys:\n"
        "\n"
        '1. "text": A concise summary (2-4 paragraphs) of the conversation. Where a '
        "redaction marker appears and the redacted content was material to the "
        "conversation, note what kind of information was shared — for example, "
        '"The brand owner shared contact information (redacted for privacy)" — '
        "rather than silently omitting it.\n"
        "\n"
        '2. "key_moments": An array of objects, each with:\n'
        '   - "t": The timestamp in seconds (float) from the transcript where the '
        "moment begins.\n"
        '   - "label": A short, descriptive label in the operator\'s language — '
        '"founding story", "budget discussion", "target audience", "brand vision". '
        "NOT a timestamp repeated as text. NOT a direct quote. The label is the "
        "retrieval affordance: it must tell the reader what they will hear if they "
        "click it.\n"
        "\n"
        "Return ONLY valid JSON. No markdown fences, no commentary.\n"
        "\n"
        "TRANSCRIPT:\n"
        "{transcript}"
    ),
    "oia.extract_fields": (
        "You are extracting structured company information from "
        "onboarding meeting evidence. Extract ONLY the fields listed "
        "below for the given wizard page. Do NOT invent information — "
        "every value must be directly supported by the evidence.\n"
        "\n"
        "### Instructions:\n"
        "1. For each field, extract the value ONLY if the evidence "
        "directly supports it.\n"
        "2. Every field MUST include evidence references pointing to "
        "the source — either {recording_id, t_start, t_end} for "
        "transcript spans or {media_id} for media OCR.\n"
        "3. Set confidence between 0.0 and 1.0 based on how clearly "
        "the evidence supports the value.\n"
        "4. For JSON-typed fields (arrays, objects), return the value "
        "in the specified shape.\n"
        "5. Omit fields where the evidence is insufficient.\n"
        "\n"
        "Return ONLY valid JSON in this exact format:\n"
        '{"fields": [\n'
        '  {"field_name": "...", "value": ..., "confidence": 0.95, '
        '"evidence": [{"recording_id": "...", "t_start": 12.5, '
        '"t_end": 18.3}]}\n'
        "]}"
    ),
}

_FALLBACK_VERSION = "fallback-v1"


def get_fallback_prompts() -> dict[str, str]:
    """Return the hardcoded template for every OIA prompt ID."""
    return dict(_FALLBACK_PROMPTS)


def get_fallback_versions() -> dict[str, str]:
    """Return the fallback version string for every OIA prompt ID."""
    return {pid: _FALLBACK_VERSION for pid in _FALLBACK_PROMPTS}
