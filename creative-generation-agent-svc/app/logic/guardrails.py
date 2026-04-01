"""Creative Generation Guardrails.

Input guardrails (IG):
- IG-08: Verify CAA blueprint exists with creative briefs.
- IG-09: Verify Company model exists with color_palette_desc.

Plan guardrails (PG):
- PG-08: Copy length validation (hooks <= 125, short <= 125, medium <= 250).
- PG-10: A/B variant count matches blueprint specification.

Output guardrails (OG):
- OG-04: Flag compliance violations in final output.
- OG-07: Verify minimum creative package (>= 1 image + 1 copy + 1 CTA
  per audience x funnel).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class InputGuardrails:
    """Validate inputs before creative generation begins."""

    def check(
        self,
        caa_context: dict[str, Any] | None,
        company_context: dict[str, Any] | None,
    ) -> list[str]:
        """Run input guardrail checks.

        IG-08: Verify CAA blueprint exists with ad sets / creative briefs.
        IG-09: Verify Company model exists with color_palette_desc.

        Args:
            caa_context: Campaign Architecture blueprint dict.
            company_context: Company model dict.

        Returns:
            List of issue strings (empty if all checks pass).
        """
        issues: list[str] = []

        # IG-08: CAA blueprint
        if not caa_context:
            issues.append(
                "IG-08: CAA blueprint is missing — cannot generate "
                "creative without campaign architecture"
            )
        else:
            # Some callers pass the full CAA result object where the
            # blueprint (and ad_sets) live under the "blueprint" key.
            # Normalize to the blueprint dict for validation.
            blueprint = caa_context.get("blueprint", caa_context)
            if not isinstance(blueprint, dict):
                issues.append(
                    "IG-08: CAA blueprint structure is invalid — expected "
                    "a dict with ad_sets"
                )
            else:
                ad_sets = blueprint.get("ad_sets", [])
                if not ad_sets:
                    issues.append(
                        "IG-08: CAA blueprint has no ad_sets — need at "
                        "least one audience x funnel combination"
                    )

        # IG-09: Company model
        if not company_context:
            issues.append(
                "IG-09: Company model is missing — cannot generate "
                "brand-aligned creative without Company context"
            )
        else:
            color_palette = company_context.get("color_palette_desc", "")
            if not color_palette:
                # Warning level — can proceed but visual quality may suffer
                logger.warning(
                    "IG-09: Company missing color_palette_desc — "
                    "image generation will use generic colors"
                )

        if issues:
            logger.warning(
                "Input guardrails flagged %d issue(s): %s",
                len(issues),
                "; ".join(issues),
            )

        return issues


class PlanGuardrails:
    """Validate the creative plan after Claude call 2 (copy generation)."""

    def check(
        self,
        copy_result: dict[str, Any],
        blueprint: dict[str, Any],
    ) -> list[str]:
        """Run plan guardrail checks on generated copy.

        PG-08: Copy length validation.
        PG-10: A/B variant count matches blueprint.

        Args:
            copy_result: Dict with hooks, primary_copy, ctas from
                Claude call 2.
            blueprint: CAA blueprint dict with ad_sets.

        Returns:
            List of issue strings (empty if all checks pass).
        """
        issues: list[str] = []

        # PG-08: Copy length validation
        issues.extend(self._check_copy_lengths(copy_result))

        # PG-10: A/B variant count
        issues.extend(
            self._check_variant_counts(copy_result, blueprint)
        )

        if issues:
            logger.warning(
                "Plan guardrails flagged %d issue(s): %s",
                len(issues),
                "; ".join(issues),
            )

        return issues

    def _check_copy_lengths(
        self, copy_result: dict[str, Any]
    ) -> list[str]:
        """PG-08: Validate copy lengths against Meta limits."""
        issues: list[str] = []

        # Check hooks (<= 125 chars)
        for hook_set in copy_result.get("hooks", []):
            ad_set = hook_set.get("ad_set_name", "unknown")
            for hook in hook_set.get("hooks", []):
                text = hook.get("hook_text", "")
                if len(text) > 125:
                    issues.append(
                        f"PG-08: Hook in '{ad_set}' exceeds 125 chars "
                        f"({len(text)} chars): '{text[:50]}...'"
                    )

        # Check primary copy lengths
        for copy_set in copy_result.get("primary_copy", []):
            ad_set = copy_set.get("ad_set_name", "unknown")
            for variant in copy_set.get("variants", []):
                vid = variant.get("variant_id", "")

                short_text = variant.get("short", {}).get("text", "")
                if short_text and len(short_text) > 125:
                    issues.append(
                        f"PG-08: Short copy '{vid}' in '{ad_set}' "
                        f"exceeds 125 chars ({len(short_text)} chars)"
                    )

                medium_text = variant.get("medium", {}).get("text", "")
                if medium_text and len(medium_text) > 250:
                    issues.append(
                        f"PG-08: Medium copy '{vid}' in '{ad_set}' "
                        f"exceeds 250 chars ({len(medium_text)} chars)"
                    )

        return issues

    def _check_variant_counts(
        self,
        copy_result: dict[str, Any],
        blueprint: dict[str, Any],
    ) -> list[str]:
        """PG-10: A/B variant count matches blueprint specification."""
        issues: list[str] = []

        # Build expected variant counts from blueprint — unwrap if needed
        bp = blueprint.get("blueprint", blueprint)
        if not isinstance(bp, dict):
            bp = blueprint
        expected: dict[str, int] = {}
        for ad_set in bp.get("ad_sets", []):
            name = ad_set.get("name", "")
            count = ad_set.get("variant_count", 3)
            if name:
                expected[name] = count

        # Check hooks per ad set
        for hook_set in copy_result.get("hooks", []):
            ad_set = hook_set.get("ad_set_name", "")
            actual = len(hook_set.get("hooks", []))
            min_expected = expected.get(ad_set, 3)
            if actual < min_expected and ad_set in expected:
                issues.append(
                    f"PG-10: '{ad_set}' has {actual} hooks, "
                    f"blueprint expects >= {min_expected}"
                )

        return issues


class OutputGuardrails:
    """Validate the final creative package output."""

    def check(self, result: dict[str, Any]) -> list[str]:
        """Run output guardrail checks on the final package.

        OG-04: Flag compliance violations.
        OG-07: Verify minimum creative package per audience x funnel.

        Args:
            result: Complete CampaignCreativePackage dict.

        Returns:
            List of issue strings (empty if all checks pass).
        """
        issues: list[str] = []

        # OG-04: Compliance violations
        issues.extend(self._check_compliance(result))

        # OG-07: Minimum creative package
        issues.extend(self._check_minimum_package(result))

        if issues:
            logger.warning(
                "Output guardrails flagged %d issue(s): %s",
                len(issues),
                "; ".join(issues),
            )

        return issues

    def _check_compliance(
        self, result: dict[str, Any]
    ) -> list[str]:
        """OG-04: Flag any compliance violations in the package."""
        issues: list[str] = []

        for pkg in result.get("ad_set_packages", []):
            ad_set = pkg.get("ad_set_name", "unknown")
            compliance = pkg.get("compliance_results", [])

            violations = [
                c
                for c in compliance
                if c.get("status") == "fail"
            ]
            if violations:
                for v in violations:
                    violation_rules = [
                        viol.get("rule", "unknown")
                        for viol in v.get("violations", [])
                    ]
                    issues.append(
                        f"OG-04: Compliance violation in '{ad_set}' "
                        f"variant '{v.get('variant_id', '')}': "
                        f"{', '.join(violation_rules)}"
                    )

        return issues

    def _check_minimum_package(
        self, result: dict[str, Any]
    ) -> list[str]:
        """OG-07: Verify minimum creative package per ad set.

        Each audience x funnel must have >= 1 image, >= 1 copy variant,
        and >= 1 CTA.
        """
        issues: list[str] = []

        packages = result.get("ad_set_packages", [])
        if not packages:
            issues.append(
                "OG-07: No ad set packages in creative output"
            )
            return issues

        for pkg in packages:
            ad_set = pkg.get("ad_set_name", "unknown")

            images = pkg.get("images", [])
            if len(images) < 1:
                issues.append(
                    f"OG-07: '{ad_set}' has no images — minimum 1 required"
                )

            copy_variants = pkg.get("primary_copy", [])
            total_copy = sum(
                len(c.get("variants", []))
                for c in copy_variants
            ) if isinstance(copy_variants, list) else 0
            # Handle case where primary_copy is a flat list of variants
            if isinstance(copy_variants, list) and copy_variants:
                if isinstance(copy_variants[0], dict) and "variants" not in copy_variants[0]:
                    total_copy = len(copy_variants)
            if total_copy < 1:
                issues.append(
                    f"OG-07: '{ad_set}' has no copy variants — "
                    f"minimum 1 required"
                )

            ctas = pkg.get("ctas", [])
            total_ctas = sum(
                len(c.get("cta_variants", []))
                for c in ctas
            ) if isinstance(ctas, list) else 0
            if isinstance(ctas, list) and ctas:
                if isinstance(ctas[0], dict) and "cta_variants" not in ctas[0]:
                    total_ctas = len(ctas)
            if total_ctas < 1:
                issues.append(
                    f"OG-07: '{ad_set}' has no CTA variants — "
                    f"minimum 1 required"
                )

        return issues
