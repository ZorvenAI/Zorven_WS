"""
Royalty Relief brand valuation engine — ISO 10668 compliant.

Implements the Royalty Relief methodology:
  NPV = Sum[ (Revenue_t x RoyaltyRate x (1 - TaxRate)) / (1 + DiscountRate)^t ]

Uses NumPy for vectorized financial calculations to avoid
floating-point accumulation errors in high-value valuations.
"""

import logging
from typing import Any

import numpy as np

from app.api.schemas import ValuationResult

logger = logging.getLogger(__name__)

# Default royalty rates by sector (ISO 10668 typical ranges: 2%-5%)
SECTOR_ROYALTY_RATES: dict[str, float] = {
    "technology": 0.04,
    "software": 0.045,
    "consumer_goods": 0.035,
    "retail": 0.03,
    "financial_services": 0.025,
    "healthcare": 0.045,
    "pharmaceuticals": 0.05,
    "automotive": 0.03,
    "aerospace": 0.05,
    "defense": 0.05,
    "industrial": 0.035,
    "electric_vehicles": 0.04,
    "energy": 0.04,
    "telecommunications": 0.035,
    "luxury": 0.05,
    "media": 0.04,
    "default": 0.04,
}

# Default growth rate for stub revenue estimation
DEFAULT_GROWTH_RATE = 0.05

# Sector-specific stub base revenues (used when no real data is available).
# Avoids returning identical valuations for all brands.
SECTOR_STUB_REVENUES: dict[str, float] = {
    "technology": 15_000_000.0,
    "software": 12_000_000.0,
    "consumer_goods": 25_000_000.0,
    "retail": 30_000_000.0,
    "financial_services": 50_000_000.0,
    "healthcare": 20_000_000.0,
    "pharmaceuticals": 35_000_000.0,
    "automotive": 80_000_000.0,
    "aerospace": 60_000_000.0,
    "defense": 70_000_000.0,
    "industrial": 40_000_000.0,
    "electric_vehicles": 50_000_000.0,
    "energy": 100_000_000.0,
    "telecommunications": 45_000_000.0,
    "luxury": 18_000_000.0,
    "media": 8_000_000.0,
    "default": 10_000_000.0,
}


class RoyaltyReliefEngine:
    """ISO 10668 compliant Royalty Relief brand valuation."""

    def calculate_npv(
        self,
        projected_revenues: list[float],
        royalty_rate: float,
        discount_rate: float,
        tax_rate: float = 0.25,
        terminal_growth_rate: float = 0.025,
    ) -> ValuationResult:
        """
        Calculate the Net Present Value of brand royalty savings.

        Explicit period:
          NPV = Sum[ (Revenue_t x RoyaltyRate x (1 - TaxRate)) / (1 + r)^t ]

        Terminal value (Gordon Growth Model) captures brand value beyond
        the explicit forecast horizon:
          TV = (Final Royalty x (1 + g)) / (r - g)
          PV(TV) = TV / (1 + r)^T

        Args:
            projected_revenues: Revenue forecast for each year.
            royalty_rate: Comparable royalty rate (e.g., 0.045 for 4.5%).
            discount_rate: WACC or risk-adjusted discount rate.
            tax_rate: Corporate tax rate (default 25%).
            terminal_growth_rate: Long-term sustainable growth rate
                for terminal value (default 2.5%).

        Returns:
            ValuationResult with NPV and per-year breakdown.
        """
        if not projected_revenues:
            return ValuationResult(
                brand_value_npv=0.0,
                royalty_rate=royalty_rate,
                discount_rate=discount_rate,
                tax_rate=tax_rate,
                horizon_years=0,
                annual_royalties=[],
                methodology="royalty_relief",
            )

        years = np.arange(1, len(projected_revenues) + 1)
        revenues = np.array(projected_revenues, dtype=np.float64)

        # Post-tax royalty savings per year
        royalties = revenues * royalty_rate * (1 - tax_rate)

        # Discount factors
        discount_factors = (1 + discount_rate) ** years

        # Present values of explicit forecast period
        present_values = royalties / discount_factors

        explicit_npv = float(np.sum(present_values))

        # Terminal value (Gordon Growth Model) — captures ongoing brand
        # value beyond the explicit forecast horizon.
        # Requires discount_rate > terminal_growth_rate.
        terminal_value_pv = 0.0
        if discount_rate <= terminal_growth_rate:
            logger.warning(
                "Skipping terminal value: discount_rate (%.4f) must exceed "
                "terminal_growth_rate (%.4f). Returning explicit NPV only.",
                discount_rate,
                terminal_growth_rate,
            )
        else:
            final_royalty = float(royalties[-1])
            terminal_value = (final_royalty * (1 + terminal_growth_rate)) / (
                discount_rate - terminal_growth_rate
            )
            # Discount terminal value back to present
            terminal_discount = (1 + discount_rate) ** len(projected_revenues)
            terminal_value_pv = terminal_value / terminal_discount

        npv = explicit_npv + terminal_value_pv

        logger.info(
            "Royalty Relief NPV: $%.2f (explicit=$%.2f, terminal=$%.2f, "
            "rate=%.3f, discount=%.3f, years=%d)",
            npv,
            explicit_npv,
            terminal_value_pv,
            royalty_rate,
            discount_rate,
            len(projected_revenues),
        )

        return ValuationResult(
            brand_value_npv=round(npv, 2),
            royalty_rate=royalty_rate,
            discount_rate=discount_rate,
            tax_rate=tax_rate,
            horizon_years=len(projected_revenues),
            annual_royalties=[round(float(r), 2) for r in royalties],
            methodology="royalty_relief",
        )

    def estimate_revenues_from_context(
        self,
        previous_outputs: dict[str, Any],
        input_context: dict[str, Any],
        horizon_years: int = 5,
        sector: str = "default",
    ) -> list[float]:
        """
        Extract or estimate a multi-year revenue forecast.

        Priority:
        1. input_context.projected_revenues — user-provided forecast
        2. input_context.base_revenue + growth — single year extrapolated
        3. previous_outputs discovery findings — attempt extraction
        4. Fallback — sector + brand-seeded stub revenue projection
        """
        # 1. Direct revenue forecast from user
        if "projected_revenues" in input_context:
            revenues = input_context["projected_revenues"]
            if isinstance(revenues, list) and len(revenues) > 0:
                logger.info(
                    "Using user-provided revenue forecast (%d years)", len(revenues)
                )
                return [float(r) for r in revenues]

        # 2. Base revenue + growth rate
        base_revenue = input_context.get("base_revenue") or input_context.get(
            "annual_revenue"
        )
        if base_revenue is not None:
            base = float(base_revenue)
            growth = float(input_context.get("growth_rate", DEFAULT_GROWTH_RATE))
            revenues = [base * (1 + growth) ** t for t in range(horizon_years)]
            logger.info(
                "Extrapolated revenues from base $%.0f at %.1f%% growth",
                base,
                growth * 100,
            )
            return revenues

        # 3. Try to extract from discovery findings (structured fields)
        for node_id, output in previous_outputs.items():
            if isinstance(output, dict):
                rev = output.get("estimated_revenue") or output.get("revenue")
                if rev is not None:
                    base = float(rev)
                    revenues = [
                        base * (1 + DEFAULT_GROWTH_RATE) ** t
                        for t in range(horizon_years)
                    ]
                    logger.info(
                        "Extracted revenue from node '%s': $%.0f", node_id, base
                    )
                    return revenues

        # 4. Try to parse revenue from discovery raw_context or findings text
        extracted = self._extract_revenue_from_text(previous_outputs)
        if extracted is not None:
            revenues = [
                extracted * (1 + DEFAULT_GROWTH_RATE) ** t for t in range(horizon_years)
            ]
            logger.info("Extracted revenue from discovery text: $%.0f", extracted)
            return revenues

        # 5. Stub fallback — use sector-specific base and brand name seed
        #    for variation so different brands produce different valuations
        sector_lower = sector.lower().strip()
        stub_base = SECTOR_STUB_REVENUES.get(
            sector_lower, SECTOR_STUB_REVENUES["default"]
        )

        # Use company name hash to add deterministic per-brand variation
        # (±20% around the sector base), so "Acme" and "Zenith" differ
        company_name = input_context.get("company_name", "")
        if company_name:
            import hashlib

            name_hash = int(hashlib.md5(company_name.encode()).hexdigest()[:8], 16)
            # Map to a multiplier between 0.80 and 1.20
            variation = 0.80 + (name_hash % 4001) / 10000.0
            stub_base *= variation

        growth = float(input_context.get("growth_rate", DEFAULT_GROWTH_RATE))
        revenues = [stub_base * (1 + growth) ** t for t in range(horizon_years)]
        logger.warning(
            "No revenue data found — using stub projection "
            "(sector=%s, base=$%.0fM, company=%s)",
            sector_lower,
            stub_base / 1e6,
            company_name or "unknown",
        )
        return revenues

    @staticmethod
    def select_royalty_rate(
        sector: str, benchmarks: dict[str, float] | None = None
    ) -> float:
        """
        Select the appropriate royalty rate for a sector.

        Args:
            sector: Industry sector (e.g., "technology", "healthcare").
            benchmarks: Optional cached benchmark rates by sector.

        Returns:
            Royalty rate as a float (e.g., 0.045 for 4.5%).
        """
        sector_lower = sector.lower().strip()

        # Check cached benchmarks first
        if benchmarks and sector_lower in benchmarks:
            return benchmarks[sector_lower]

        # Fall back to built-in defaults
        return SECTOR_ROYALTY_RATES.get(sector_lower, SECTOR_ROYALTY_RATES["default"])

    @staticmethod
    def _extract_revenue_from_text(
        previous_outputs: dict[str, Any],
    ) -> float | None:
        """
        Try to extract a revenue figure from discovery text outputs.

        Searches raw_context and findings for patterns like:
          "$51.2 billion", "$51.2B", "revenue of $51.2 billion",
          "$12.5 million", "$12.5M"
        """
        import re

        texts: list[str] = []
        for node_id, output in previous_outputs.items():
            if isinstance(output, dict):
                raw_ctx = output.get("raw_context", "")
                if raw_ctx:
                    texts.append(raw_ctx)
                findings = output.get("findings", [])
                if isinstance(findings, list):
                    texts.extend(str(f) for f in findings)

        if not texts:
            return None

        combined = " ".join(texts)

        # Match patterns: $X.Y billion/million/B/M
        patterns = [
            # "$51.2 billion" or "$51.2billion"
            r"\$\s*([\d,.]+)\s*billion",
            r"\$\s*([\d,.]+)\s*B\b",
            # "$12.5 million" or "$12.5million"
            r"\$\s*([\d,.]+)\s*million",
            r"\$\s*([\d,.]+)\s*M\b",
            # "revenue of $X,XXX,XXX" or "revenue: $X,XXX"
            r"revenue[^$]*\$\s*([\d,.]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, combined, re.IGNORECASE)
            if match:
                try:
                    value_str = match.group(1).replace(",", "")
                    value = float(value_str)
                    # Determine multiplier from pattern context
                    full_match = match.group(0).lower()
                    if "billion" in full_match or full_match.endswith("b"):
                        value *= 1e9
                    elif "million" in full_match or full_match.endswith("m"):
                        value *= 1e6
                    elif value < 1000:
                        # Small number without unit — likely in millions
                        value *= 1e6
                    if value > 0:
                        logger.info(
                            "Parsed revenue from text: $%.0f (pattern: %s)",
                            value,
                            pattern,
                        )
                        return value
                except (ValueError, IndexError):
                    continue

        return None

    @staticmethod
    def build_rationale(
        result: ValuationResult,
        sector: str,
        bsi_score: int | None = None,
    ) -> str:
        """Build a human-readable rationale for the valuation."""
        lines = [
            "Methodology: Royalty Relief (ISO 10668)",
            f"Sector: {sector}",
            f"Royalty Rate: {result.royalty_rate:.1%}",
            f"Discount Rate (WACC): {result.discount_rate:.1%}",
            f"Tax Rate: {result.tax_rate:.1%}",
            f"Forecast Horizon: {result.horizon_years} years",
        ]
        if bsi_score is not None:
            lines.append(f"Brand Strength Index (BSI): {bsi_score}/100")
        lines.append(
            f"Brand Value (NPV): ${result.brand_value_npv:,.2f}",
        )
        lines.append("")
        lines.append("Annual Post-Tax Royalties:")
        for i, royalty in enumerate(result.annual_royalties, 1):
            lines.append(f"  Year {i}: ${royalty:,.2f}")
        return "\n".join(lines)
