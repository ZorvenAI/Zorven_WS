"""SKL-MRA-06: Research Report Generator — Claude synthesis + optional GCS."""

import json
import logging
import time
from typing import Any

from app.skills.base import BaseSkill
from app.skills.models import SkillContext, SkillMeta, SkillResult

logger = logging.getLogger(__name__)

_REPORT_SYSTEM = """\
You are a senior market research analyst. Generate a comprehensive research report \
from the provided findings and analysis.

The report should include:
1. Executive Summary
2. Market Overview
3. Key Findings
4. Competitive Landscape (if data available)
5. Market Sizing (if data available)
6. Trends and Outlook
7. Recommendations

Respond with a JSON object:
- "report_text": string — full report in markdown format
- "summary": string — 2-3 sentence executive summary
- "word_count": int — approximate word count
- "sections": list of {"title": str, "content": str} objects

Only output valid JSON, no other text."""


class ResearchReportGenerator(BaseSkill):
    """Generates comprehensive research reports using Claude."""

    meta = SkillMeta(
        skill_id="SKL-MRA-06",
        name="research_report_generator",
        description="Generate structured research reports from analysis findings",
        allowed_roles=["OWNER", "ADMIN", "EDITOR"],
        timeout_ms=60000,
        circuit_breaker_dependency="llm",
    )

    def __init__(
        self,
        anthropic_client: Any = None,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        self._client = anthropic_client
        self.model = model
        self.max_tokens = max_tokens

    async def execute(self, input_data: dict, context: SkillContext) -> SkillResult:
        """
        Generate a research report.

        input_data keys:
          - findings (list[str]): Key findings
          - analysis (str): Analysis narrative
          - prompt (str): Original query
          - tenant_context (dict): Tenant info
        """
        start = time.monotonic()
        findings = input_data.get("findings", [])
        analysis = input_data.get("analysis", "")
        prompt = input_data.get("prompt", "")

        if not findings and not analysis:
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error="No findings or analysis provided",
                duration_ms=_elapsed(start),
            )

        # Stub mode
        if self._client is None:
            stub_report = (
                f"# Market Research Report\n\n"
                f"## Query: {prompt[:100]}\n\n"
                f"## Findings\n"
                + "\n".join(f"- {f}" for f in findings[:5])
                + f"\n\n## Analysis\n{analysis[:500]}"
            )
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data={
                    "report_text": stub_report,
                    "summary": f"Stub report for: {prompt[:80]}",
                    "word_count": len(stub_report.split()),
                    "sections": [],
                },
                duration_ms=_elapsed(start),
            )

        try:
            user_msg = (
                f"Research query: {prompt}\n\n"
                f"Findings:\n" + "\n".join(f"- {f}" for f in findings) + "\n\n"
                f"Analysis:\n{analysis[:20000]}"
            )

            message = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=0.3,
                system=_REPORT_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )

            tokens_used = getattr(message, "usage", None)
            token_count = 0
            if tokens_used:
                token_count = getattr(tokens_used, "input_tokens", 0) + getattr(
                    tokens_used, "output_tokens", 0
                )

            content = message.content[0].text.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            report_data = json.loads(content)

            return SkillResult(
                skill_id=self.meta.skill_id,
                success=True,
                data=report_data,
                duration_ms=_elapsed(start),
                tokens_used=token_count,
            )
        except Exception as exc:
            logger.warning("ResearchReportGenerator failed: %s", exc)
            return SkillResult(
                skill_id=self.meta.skill_id,
                success=False,
                error=str(exc),
                duration_ms=_elapsed(start),
            )


def _elapsed(start: float) -> float:
    return (time.monotonic() - start) * 1000
