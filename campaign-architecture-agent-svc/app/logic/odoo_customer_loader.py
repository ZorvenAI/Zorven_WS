"""SKL-CAA-04: Odoo Customer Loader.

Extracts customer segments from Odoo CRM data for custom and
lookalike audience definitions. No-op when Odoo is unavailable.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OdooCustomerLoader:
    """Extract customer segments for audience targeting."""

    def process(self, odoo_context: dict[str, Any] | None) -> dict[str, Any]:
        """Process Odoo customer data into audience segments."""
        if not odoo_context:
            return {
                "available": False,
                "segments": [],
                "custom_audiences": [],
                "lookalike_seed_size": 0,
            }

        segments = odoo_context.get("segments", [])
        total = odoo_context.get("total_customers", 0)
        high_value = odoo_context.get("high_value_customers", [])

        custom_audiences = []
        if total >= 100:
            custom_audiences.append(
                {
                    "name": "All Customers",
                    "size": total,
                    "type": "customer_list",
                }
            )
        if len(high_value) >= 50:
            custom_audiences.append(
                {
                    "name": "High-Value Customers",
                    "size": len(high_value),
                    "type": "customer_list",
                }
            )
        for seg in segments:
            seg_name = seg.get("name", "")
            seg_size = seg.get("size", 0)
            if seg_name and seg_size >= 100:
                custom_audiences.append(
                    {
                        "name": seg_name,
                        "size": seg_size,
                        "type": "customer_segment",
                    }
                )

        return {
            "available": True,
            "segments": segments,
            "custom_audiences": custom_audiences,
            "lookalike_seed_size": total,
            "total_customers": total,
        }

    def build_prompt_section(self, customer_data: dict[str, Any]) -> str:
        """Build customer data prompt section for LLM call."""
        if not customer_data.get("available"):
            return (
                "## Customer Data\n\n"
                "No CRM customer data available. "
                "Use interest-based targeting only.\n"
            )

        audiences = customer_data.get("custom_audiences", [])
        section = "## CRM Customer Data (Odoo)\n\n"
        section += f"Total customers: " f"{customer_data.get('total_customers', 0)}\n"
        if audiences:
            section += "Available custom audiences:\n"
            for aud in audiences:
                section += f"- {aud['name']} " f"({aud['size']} users, {aud['type']})\n"
        return section
