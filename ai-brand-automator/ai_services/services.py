"""
AI Services for BrandForge AI
Integration with Google Gemini AI
"""

import os
import time
import logging
from typing import Dict, List, Any, Optional
from django.conf import settings
import google.generativeai as genai
from .models import AIGeneration
from brand_automator.validators import sanitize_ai_prompt

logger = logging.getLogger(__name__)


class GeminiAIService:
    """
    Service for interacting with Google Gemini AI
    """

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY") or settings.GOOGLE_API_KEY
        self.model_name = "gemini-2.0-flash"
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                logger.info(
                    f"Gemini AI service initialized with model: " f"{self.model_name}"
                )
            except Exception as e:
                logger.error(f"Failed to initialize Gemini AI: {str(e)}")
                self.model = None
        else:
            logger.warning(
                "GOOGLE_API_KEY not configured. AI service will use "
                "fallback responses."
            )
            self.model = None

    def generate_brand_strategy(self, company_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate brand strategy content using AI
        """
        prompt = self._build_brand_strategy_prompt(company_data)

        start_time = time.time()

        try:
            if self.model:
                response = self.model.generate_content(prompt)
                ai_response = response.text

                # Parse the AI response (assuming it returns structured text)
                # For simplicity, we'll extract key sections
                vision = self._extract_section(ai_response, "Vision Statement")
                mission = self._extract_section(ai_response, "Mission Statement")
                values = self._extract_list_section(ai_response, "Core Values")
                positioning = self._extract_section(
                    ai_response, "Positioning Statement"
                )

                result = {
                    "vision_statement": vision
                    or (
                        f"Our vision is to revolutionize the "
                        f"{company_data.get('industry', 'industry')} "
                        f"through innovative solutions."
                    ),
                    "mission_statement": mission
                    or (
                        f"To provide exceptional "
                        f"{company_data.get('industry', 'services')} that solve "
                        f"{company_data.get('core_problem', 'key challenges')} "
                        f"for our customers."
                    ),
                    "values": (
                        ", ".join(values)
                        if values
                        else "Innovation, Customer Focus, Excellence, Integrity"
                    ),
                    "positioning_statement": positioning
                    or (
                        f"The leading {company_data.get('industry', 'solution')} "
                        f"for businesses seeking to overcome "
                        f"{company_data.get('core_problem', 'challenges')}."
                    ),
                }
            else:
                # Fallback to mock response if API not configured
                result = {
                    "vision_statement": (
                        f"Our vision is to revolutionize the "
                        f"{company_data.get('industry', 'industry')} through "
                        f"innovative solutions that empower businesses."
                    ),
                    "mission_statement": (
                        f"To provide exceptional "
                        f"{company_data.get('industry', 'services')} that solve "
                        f"{company_data.get('core_problem', 'key challenges')} "
                        f"for our customers."
                    ),
                    "values": (
                        "Innovation, Customer Focus, Excellence, "
                        "Integrity, Collaboration"
                    ),
                    "positioning_statement": (
                        f"The leading {company_data.get('industry', 'solution')} "
                        f"for businesses seeking to overcome "
                        f"{company_data.get('core_problem', 'challenges')}."
                    ),
                }

        except Exception as e:
            # Log error and use fallback
            logger.error(
                f"AI brand strategy generation failed: {str(e)}", exc_info=True
            )
            result = {
                "vision_statement": (
                    f"Our vision is to revolutionize the "
                    f"{company_data.get('industry', 'industry')} through "
                    f"innovative solutions."
                ),
                "mission_statement": (
                    f"To provide exceptional "
                    f"{company_data.get('industry', 'services')} that solve "
                    f"{company_data.get('core_problem', 'key challenges')} "
                    f"for our customers."
                ),
                "values": "Innovation, Customer Focus, Excellence, Integrity",
                "positioning_statement": (
                    f"The leading {company_data.get('industry', 'solution')} "
                    f"for businesses seeking to overcome "
                    f"{company_data.get('core_problem', 'challenges')}."
                ),
            }

        processing_time = time.time() - start_time

        # Log the generation
        try:
            AIGeneration.objects.create(
                tenant=company_data.get("tenant"),
                content_type="brand_strategy",
                prompt=prompt,
                response=str(result),
                tokens_used=len(prompt.split())
                + len(str(result).split()),  # Rough estimate
                processing_time=processing_time,
            )
        except Exception as e:
            logger.error(f"Failed to log AI generation: {str(e)}", exc_info=True)

        return result

    def generate_brand_identity(self, company_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate brand identity elements using AI
        """
        prompt = self._build_brand_identity_prompt(company_data)

        start_time = time.time()

        try:
            if self.model:
                response = self.model.generate_content(prompt)
                ai_response = response.text

                # Parse the AI response
                color_palette = self._extract_section(ai_response, "Color Palette")
                fonts = self._extract_section(
                    ai_response, "Typography"
                ) or self._extract_section(ai_response, "Fonts")
                messaging = self._extract_section(
                    ai_response, "Messaging Guide"
                ) or self._extract_section(ai_response, "Tone")

                result = {
                    "color_palette_desc": color_palette
                    or (
                        "Primary: Deep Blue (#1a365d) for trust and "
                        "professionalism, Secondary: Teal (#319795) for "
                        "innovation, Accent: Orange (#ed8936) for energy"
                    ),
                    "font_recommendations": fonts
                    or (
                        "Primary: Inter (clean, modern sans-serif for body "
                        "text), Secondary: Playfair Display (elegant serif "
                        "for headings)"
                    ),
                    "messaging_guide": messaging
                    or (
                        f"Professional yet approachable tone. Emphasize "
                        f"{company_data.get('brand_voice', 'innovation')} and "
                        f"customer success. Use clear, jargon-free language."
                    ),
                }
            else:
                # Fallback to mock response if API not configured
                result = {
                    "color_palette_desc": (
                        "Primary: Deep Blue (#1a365d) for trust and "
                        "professionalism, Secondary: Teal (#319795) for "
                        "innovation, Accent: Orange (#ed8936) for energy"
                    ),
                    "font_recommendations": (
                        "Primary: Inter (clean, modern sans-serif for body "
                        "text), Secondary: Playfair Display (elegant serif "
                        "for headings)"
                    ),
                    "messaging_guide": (
                        f"Professional yet approachable tone. Emphasize "
                        f"{company_data.get('brand_voice', 'innovation')} and "
                        f"customer success. Use clear, jargon-free language."
                    ),
                }

        except Exception as e:
            # Log error and use fallback
            logger.error(
                f"AI brand identity generation failed: {str(e)}", exc_info=True
            )
            result = {
                "color_palette_desc": (
                    "Primary: Deep Blue (#1a365d) for trust and "
                    "professionalism, Secondary: Teal (#319795) for "
                    "innovation, Accent: Orange (#ed8936) for energy"
                ),
                "font_recommendations": (
                    "Primary: Inter (clean, modern sans-serif for body "
                    "text), Secondary: Playfair Display (elegant serif "
                    "for headings)"
                ),
                "messaging_guide": (
                    f"Professional yet approachable tone. Emphasize "
                    f"{company_data.get('brand_voice', 'innovation')} and "
                    f"customer success. Use clear, jargon-free language."
                ),
            }

        processing_time = time.time() - start_time

        # Log the generation
        try:
            AIGeneration.objects.create(
                tenant=company_data.get("tenant"),
                content_type="brand_identity",
                prompt=prompt,
                response=str(result),
                tokens_used=len(prompt.split()) + len(str(result).split()),
                processing_time=processing_time,
            )
        except Exception as e:
            logger.error(f"Failed to log AI generation: {str(e)}", exc_info=True)

        return result

    # Stop words that should not be treated as company names
    _STOP_WORDS = frozenset(
        {
            "the",
            "a",
            "an",
            "my",
            "our",
            "this",
            "that",
            "for",
            "and",
            "or",
            "of",
            "in",
            "to",
            "is",
            "it",
            "can",
            "you",
            "please",
            "brand",
            "equity",
            "value",
        }
    )

    @staticmethod
    def extract_target_brand(message: str) -> Optional[Dict[str, Any]]:
        """Extract the target brand name and look up real financial data.

        Strategy:
          1. Extract the company name from the message via regex.
          2. Look up real financial data using Gemini AI.
          3. If data cannot be determined, return an error dict so the
             caller can inform the user.

        Returns:
          - Dict with company financial data (on success).
          - Dict with ``{"error": "...", "company_name": "..."}``
            when the company's data is not available.
          - ``None`` when no company name could be extracted
            (conversational message).
        """
        import re

        # --- Identify the company name via regex ---
        company_name: Optional[str] = None
        patterns = [
            r"(?:brand equity|brand valuation|brand value|brand strength)"
            r"(?:\s+(?:for|of|for the))?\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9\s&'.-]+?)(?:\s+brand)?[?.!,]?\s*$",
            r"(?:calculate|analyze|analyse|evaluate|assess)"
            r"(?:\s+(?:the\s+)?brand\s+(?:equity|value|valuation|"
            r"strength)\s+(?:for|of))?\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9\s&'.-]+?)(?:\s+brand)?[?.!,]?\s*$",
            r"(?:for|of)\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9\s&'.-]+?)(?:\s+brand)[?.!,]?\s*$",
            r"([A-Z][A-Za-z0-9&'.-]+?)(?:'s)\s+"
            r"(?:brand\s+)?(?:equity|value|valuation|strength)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip().rstrip(".,!?")
                if len(name) > 1 and name.lower() not in GeminiAIService._STOP_WORDS:
                    company_name = name
                    break

        if company_name is None:
            return None

        # --- Look up real financial data for the company ---
        return GeminiAIService.estimate_company_data(company_name)

    @staticmethod
    def estimate_company_data(company_name: str) -> Dict[str, Any]:
        """Look up real financial data for a company via Gemini AI.

        Returns:
          - Dict with real company financial data (on success).
          - Dict with ``{"error": "...", "company_name": "..."}``
            when data is unavailable.
        """
        result = GeminiAIService._gemini_estimate(company_name)
        if result:
            logger.info(
                "Gemini provided data for %s: sector=%s, revenue=$%s, " "awareness=%s",
                company_name,
                result.get("sector"),
                f"{result.get('base_revenue', 0):,}",
                result.get("brand_awareness"),
            )
            return result

        # Data not available — return error
        if ai_service.model is None:
            reason = (
                f"I couldn't retrieve financial data for "
                f'"{company_name}". The AI service (Gemini) is not '
                f"configured. Please ensure the GOOGLE_API_KEY is set "
                f"so I can look up real company data."
            )
        else:
            reason = (
                f"I couldn't find reliable public financial data for "
                f'"{company_name}". This may be because the company '
                f"is private, too new, or the name wasn't recognized. "
                f"Please verify the company name and try again, or "
                f"try a publicly traded company."
            )

        logger.warning(
            "Could not determine financial data for %s",
            company_name,
        )
        return {"error": reason, "company_name": company_name}

    @staticmethod
    def _gemini_estimate(company_name: str) -> Optional[Dict[str, Any]]:
        """Use Gemini to look up real company financial data."""
        import json as _json

        try:
            if ai_service.model is None:
                return None

            prompt = (
                f"Look up the real, publicly available financial data "
                f'for "{company_name}". Provide the data as a JSON '
                f"object with ONLY these keys:\n"
                f'  "company_name": the official company name (string)\n'
                f'  "sector": one of: technology, software, '
                f"consumer_goods, retail, automotive, "
                f"aerospace, defense, industrial, "
                f"electric_vehicles, "
                f"financial_services, media, healthcare, "
                f"pharmaceuticals, luxury, energy, "
                f"telecommunications (string)\n"
                f'  "base_revenue": most recent annual revenue in USD '
                f"(integer, e.g. 51000000000 for $51B)\n"
                f'  "growth_rate": year-over-year revenue growth rate '
                f"as a decimal (e.g. 0.10 for 10%)\n"
                f'  "brand_awareness": estimated global brand awareness '
                f"score from 0 to 100 (integer)\n"
                f'  "profit_margin": net profit margin as a decimal '
                f"(e.g. 0.15 for 15%)\n"
                f'  "customer_loyalty": estimated customer loyalty/'
                f"retention score from 0 to 100 (integer, based on "
                f"repeat purchase rates, NPS, brand switching costs)\n"
                f'  "market_share": estimated market share in primary '
                f"market as a decimal (e.g. 0.25 for 25%)\n\n"
                f"IMPORTANT: Use real data from public filings and "
                f"reports. If the company is private or you cannot "
                f"determine its financials, respond with exactly: "
                f"NOT_FOUND\n\n"
                f"Respond with ONLY the JSON object (or NOT_FOUND). "
                f"No markdown fences, no explanation."
            )

            response = ai_service.model.generate_content(prompt)
            text = response.text.strip()

            # Check for NOT_FOUND response
            if "NOT_FOUND" in text.upper():
                logger.info(
                    "Gemini: company '%s' not found or private",
                    company_name,
                )
                return None

            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = _json.loads(text)

            # Validate required fields
            required = {
                "company_name",
                "sector",
                "base_revenue",
                "growth_rate",
                "brand_awareness",
                "profit_margin",
            }
            if not required.issubset(data.keys()):
                logger.warning(
                    "Gemini response missing fields for %s: %s",
                    company_name,
                    required - data.keys(),
                )
                return None

            # Coerce and validate types
            data["base_revenue"] = int(float(data["base_revenue"]))
            data["growth_rate"] = float(data["growth_rate"])
            data["brand_awareness"] = int(float(data["brand_awareness"]))
            data["profit_margin"] = float(data["profit_margin"])

            # Optional fields — coerce if present
            if "customer_loyalty" in data and data["customer_loyalty"] is not None:
                data["customer_loyalty"] = int(float(data["customer_loyalty"]))
            if "market_share" in data and data["market_share"] is not None:
                data["market_share"] = float(data["market_share"])

            # Sanity checks — reject obviously bad data
            if data["base_revenue"] <= 0:
                logger.warning(
                    "Gemini returned non-positive revenue for %s",
                    company_name,
                )
                return None

            # Validate that the returned company matches the request
            # (prevents Gemini hallucinating a different company)
            input_clean = company_name.lower().replace(".", "").replace(",", "").strip()
            result_clean = (
                data["company_name"].lower().replace(".", "").replace(",", "").strip()
            )
            result_words = result_clean.split()
            input_words = input_clean.split()

            match_found = (
                # Direct substring match
                input_clean in result_clean
                or result_clean in input_clean
                # Any input word (>2 chars) appears in result
                or any(w in result_clean for w in input_words if len(w) > 2)
                # Any result word (>2 chars) starts with input
                # (e.g., "spacex" → "space" in result)
                or any(
                    rw.startswith(input_clean[:4])
                    for rw in result_words
                    if len(input_clean) >= 4
                )
                # Input prefix matches result prefix (trade name)
                or result_clean.startswith(input_clean[:4])
            )

            if not match_found:
                logger.warning(
                    "Gemini returned mismatched company: asked for "
                    "'%s', got '%s' — rejecting",
                    company_name,
                    data["company_name"],
                )
                return None

            return data

        except Exception as e:
            logger.warning(
                "Gemini estimation failed for %s: %s",
                company_name,
                e,
            )
            return None

    @staticmethod
    def classify_intent(message: str) -> Dict[str, Any]:
        """Classify message as 'pipeline' or 'conversation'.

        Returns: {"intent": "pipeline"|"conversation", "confidence": float}
        """
        msg = message.lower()

        pipeline_keywords = [
            "analyze",
            "analyse",
            "valuation",
            "brand equity",
            "brand valuation",
            "iso 10668",
            "royalty relief",
            "brand strength",
            "bsi",
            "npv",
            "market research",
            "competitor analysis",
            "run pipeline",
            "run analysis",
            "perform analysis",
            "evaluate brand",
            "assess brand",
        ]

        pipeline_phrases = [
            "can you analyze",
            "can you analyse",
            "run a",
            "perform a",
            "evaluate my",
            "assess my",
            "calculate",
            "what is my brand worth",
            "how strong is my brand",
        ]

        score = 0
        for kw in pipeline_keywords:
            if kw in msg:
                score += 1
        for phrase in pipeline_phrases:
            if phrase in msg:
                score += 2

        # Threshold: 2+ points → pipeline intent
        if score >= 2:
            return {"intent": "pipeline", "confidence": min(score / 6, 1.0)}
        return {"intent": "conversation", "confidence": 1.0 - (score / 6)}

    def chat_with_brand_context(self, message: str, context: Dict[str, Any]) -> str:
        """
        Chat with AI using brand context
        """
        # Sanitize user message to prevent prompt injection
        sanitized_message = sanitize_ai_prompt(message)

        prompt = self._build_chat_prompt(sanitized_message, context)

        # TODO: Replace with actual Gemini API call
        start_time = time.time()

        # Simple mock responses based on message content
        if "vision" in message.lower():
            response = (
                "Your vision statement should be aspirational and "
                "forward-looking. Consider what impact you want to have "
                "on your industry in 5-10 years."
            )
        elif "mission" in message.lower():
            response = (
                "Your mission statement should explain how you serve "
                "your customers and solve their problems today."
            )
        elif "values" in message.lower():
            response = (
                "Core values should guide your company's behavior and "
                "decision-making. Choose 3-5 values that truly "
                "represent your brand."
            )
        elif "positioning" in message.lower():
            response = (
                "Positioning is about how you want customers to perceive your "
                "brand relative to competitors. Focus on your unique strengths."
            )
        else:
            response = (
                "I'm here to help you build a strong brand strategy. "
                "What specific aspect would you like to discuss?"
            )

        processing_time = time.time() - start_time

        # Log the generation
        try:
            AIGeneration.objects.create(
                tenant=context.get("tenant"),
                content_type="content",
                prompt=prompt,
                response=response,
                tokens_used=80,
                processing_time=processing_time,
            )
        except Exception as e:
            logger.error(f"Failed to log chat AI generation: {str(e)}", exc_info=True)

        return response

    def analyze_market(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform market analysis using AI
        """
        prompt = self._build_market_analysis_prompt(company_data)

        # TODO: Replace with actual Gemini API call
        start_time = time.time()

        mock_response = {
            "competitor_analysis": (
                f"Key competitors in {company_data.get('industry', 'your industry')} "
                f"include established players focusing on traditional solutions. "
                f"Your unique advantage lies in addressing "
                f"{company_data.get('core_problem', 'specific customer needs')}."
            ),
            "market_opportunities": (
                "Growing demand for digital solutions, underserved "
                "customer segments, emerging technology trends."
            ),
            "recommendations": (
                "Focus on customer education, build thought leadership "
                "content, leverage digital marketing channels."
            ),
        }

        processing_time = time.time() - start_time

        # Log the generation
        AIGeneration.objects.create(
            tenant=company_data.get("tenant"),
            content_type="analysis",
            prompt=prompt,
            response=str(mock_response),
            tokens_used=200,
            processing_time=processing_time,
        )

        return mock_response

    def _build_brand_strategy_prompt(self, company_data: Dict[str, Any]) -> str:
        """Build prompt for brand strategy generation"""
        return f"""
        Generate a comprehensive brand strategy for a company with the
        following details:

        Company Name: {company_data.get('name', 'N/A')}
        Industry: {company_data.get('industry', 'N/A')}
        Target Audience: {company_data.get('target_audience', 'N/A')}
        Core Problem Solved: {company_data.get('core_problem', 'N/A')}
        Brand Voice: {company_data.get('brand_voice', 'N/A')}

        Please provide:
        1. Vision Statement (aspirational, 1-2 sentences)
        2. Mission Statement (how you serve customers, 1-2 sentences)
        3. Core Values (5 key values with brief descriptions)
        4. Positioning Statement (how you differentiate from competitors)

        Make it professional, compelling, and tailored to the company details provided.
        """

    def _build_brand_identity_prompt(self, company_data: Dict[str, Any]) -> str:
        """Build prompt for brand identity generation"""
        return f"""
Generate brand identity elements for a company with these characteristics:

Company Name: {company_data.get('name', 'N/A')}
Industry: {company_data.get('industry', 'N/A')}
Brand Voice: {company_data.get('brand_voice', 'N/A')}
Target Audience: {company_data.get('target_audience', 'N/A')}

Please provide the following in EXACTLY this format:

Color Palette: Primary: #HEXCODE for [usage], Secondary: #HEXCODE for [usage],
Accent: #HEXCODE for [usage]

Typography: Primary: [Font Name] for body text,
Secondary: [Font Name] for headings

Messaging Guide: [2-3 sentences about tone, voice, and communication style]

Use actual hex color codes (like #1a365d, #319795).
Ensure recommendations align with the brand voice and target audience.
"""

    def _build_chat_prompt(self, message: str, context: Dict[str, Any]) -> str:
        """Build prompt for chat interactions"""
        company_info = context.get("company", {})
        return f"""
        You are an AI brand strategist helping a company build their brand.

        Company Context:
        - Name: {company_info.get('name', 'N/A')}
        - Industry: {company_info.get('industry', 'N/A')}
        - Target Audience: {company_info.get('target_audience', 'N/A')}
        - Core Problem: {company_info.get('core_problem', 'N/A')}
        - Brand Voice: {company_info.get('brand_voice', 'N/A')}

        User Message: {message}

        Provide helpful, professional advice about brand strategy and building.
        """

    def _build_market_analysis_prompt(self, company_data: Dict[str, Any]) -> str:
        """Build prompt for market analysis"""
        return f"""
        Perform a market analysis for a company with these details:

        Company Name: {company_data.get('name', 'N/A')}
        Industry: {company_data.get('industry', 'N/A')}
        Target Audience: {company_data.get('target_audience', 'N/A')}
        Core Problem Solved: {company_data.get('core_problem', 'N/A')}

        Please provide:
        1. Competitor Analysis: Key competitors and market positioning
        2. Market Opportunities: Growth areas and trends
        3. Strategic Recommendations: Actionable advice for market success

        Be specific and actionable in your analysis.
        """

    def _extract_section(self, text: str, section_name: str) -> Optional[str]:
        """Extract a section from AI response text"""
        import re

        # Try multiple patterns to handle different AI response formats
        patterns = [
            # Pattern 1: "Section Name:" followed by content (with optional markdown)
            (
                rf"(?:\d+\.\s*)?(?:\*{{0,2}})?{section_name}"
                rf"(?:\*{{0,2}})?[:\s]+(.*?)(?=\n\n|\n\d+\.|\n(?:\*{{0,2}})?[A-Z]|$)"
            ),
            # Pattern 2: Just the section name followed by content
            rf"{section_name}[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                content = match.group(1).strip()
                # Remove leading/trailing markdown and whitespace
                content = re.sub(r"^[\*\s]+|[\*\s]+$", "", content)
                # Ensure we have meaningful content (not just empty or markdown)
                if content and len(content) > 5 and not content.startswith("**"):
                    return content
        return None

    def _extract_list_section(
        self, text: str, section_name: str
    ) -> Optional[List[str]]:
        """Extract a list section from AI response text"""
        import re

        pattern = rf"{section_name}[:\s]*(.*?)(?=\n\n|\n[A-Z]|$)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Split by common list separators
            items = re.split(r"[,;]|\sand\s|\sor\s", content)
            return [item.strip().strip("-•*").strip() for item in items if item.strip()]
        return None


# Global service instance
ai_service = GeminiAIService()
