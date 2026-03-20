import json
import logging
import re
from urllib.parse import urlparse

from analytics.rag_query import RAGSearchClient

logger = logging.getLogger(__name__)


class BrandAffinityVerifier:
    """Verifies that pipeline results relate to the tenant's own brand.

    Three-tier verification:
    - Tier 1: Input match (fast, checks job input_context.company_name)
    - Tier 2: Result content scan (scans result_data for brand signals)
    - Tier 3: RAG cross-reference (queries tenant's RAG data store)
    """

    def __init__(self, tenant):
        self.tenant = tenant
        self._load_brand_info()
        self._rag_client = RAGSearchClient()

    def _load_brand_info(self):
        """Load brand identity from Company model."""
        try:
            from onboarding.models import Company

            company = Company.objects.get(tenant=self.tenant)
            self.brand_name = (company.name or "").strip()
            self.brand_domain = self._extract_domain(company.website or "")
            self.brand_industry = (company.industry or "").strip().lower()

            # Build keyword set from description, core_problem, target_audience
            text_sources = [
                company.description or "",
                company.core_problem or "",
                company.target_audience or "",
            ]
            combined = " ".join(text_sources).lower()
            # Extract meaningful words (3+ chars, not common stop words)
            words = re.findall(r"\b[a-z]{3,}\b", combined)
            stop_words = {
                "the",
                "and",
                "for",
                "are",
                "but",
                "not",
                "you",
                "all",
                "can",
                "had",
                "her",
                "was",
                "one",
                "our",
                "out",
                "has",
                "have",
                "from",
                "this",
                "that",
                "with",
                "they",
                "been",
                "will",
                "their",
                "would",
                "there",
                "what",
                "about",
                "which",
                "when",
                "make",
                "like",
                "just",
                "over",
                "such",
                "also",
                "into",
                "some",
                "than",
                "them",
            }
            self.brand_keywords = {w for w in words if w not in stop_words}
        except Exception:
            logger.warning("Could not load brand info for tenant %s", self.tenant)
            self.brand_name = ""
            self.brand_domain = ""
            self.brand_industry = ""
            self.brand_keywords = set()

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url if "://" in url else f"https://{url}")
            domain = parsed.netloc or parsed.path
            return domain.lower().replace("www.", "")
        except Exception:
            return ""

    def tier1_input_match(self, job) -> float:
        """Compare job input_context.company_name vs tenant's company name.

        Returns:
            Score 0.0-1.0
        """
        if not self.brand_name:
            return 1.0  # No brand to compare against, pass through

        input_ctx = job.input_context or {}
        job_company = (input_ctx.get("company_name", "") or "").strip()

        if not job_company:
            return 1.0  # No company specified in input, assume own brand

        # Exact match
        if job_company.lower() == self.brand_name.lower():
            return 1.0

        # Containment match
        if (
            self.brand_name.lower() in job_company.lower()
            or job_company.lower() in self.brand_name.lower()
        ):
            return 0.95

        # Jaccard token overlap
        brand_tokens = set(self.brand_name.lower().split())
        job_tokens = set(job_company.lower().split())
        if brand_tokens and job_tokens:
            intersection = brand_tokens & job_tokens
            union = brand_tokens | job_tokens
            jaccard = len(intersection) / len(union) if union else 0
            return jaccard

        return 0.0

    def tier2_result_content_scan(self, job) -> float:
        """Scan result_data JSON for brand signals.

        Returns:
            Score 0.0-1.0 based on weighted signal detection.
        """
        if not job.result_data:
            return 0.0

        try:
            content = json.dumps(job.result_data).lower()
        except (TypeError, ValueError):
            return 0.0

        score = 0.0

        # Brand name presence (0.4 weight)
        if self.brand_name and self.brand_name.lower() in content:
            score += 0.4

        # Domain presence (0.3 weight)
        if self.brand_domain and self.brand_domain in content:
            score += 0.3

        # Industry mention (0.1 weight)
        if self.brand_industry and self.brand_industry in content:
            score += 0.1

        # Keyword hits >= 2 (0.2 weight)
        if self.brand_keywords:
            hits = sum(1 for kw in self.brand_keywords if kw in content)
            if hits >= 2:
                score += 0.2

        return min(score, 1.0)

    def tier3_rag_cross_reference(self, job) -> float:
        """Query tenant's RAG data store for brand identity documents.

        Returns:
            Score 0.0-1.0 based on RAG document relevance.
            Falls back to 0.5 (inconclusive) on failure.
        """
        try:
            data_store_id = self.tenant.get_data_store_id()
        except Exception:
            return 0.5

        if not data_store_id:
            return 0.5

        query_text = f"brand identity {self.brand_name}"
        try:
            results = self._rag_client.query(
                data_store_id=data_store_id,
                query_text=query_text,
                top_k=3,
            )
        except Exception:
            return 0.5

        if not results:
            return 0.5

        # Extract keywords from RAG results
        rag_content = " ".join(r.get("content", "") for r in results).lower()

        # Build a short summary of result_data for comparison
        result_summary = ""
        if job.result_data:
            try:
                result_summary = json.dumps(job.result_data)[:1000].lower()
            except (TypeError, ValueError):
                return 0.5

        # Check overlap between RAG brand docs and result summary
        rag_words = set(re.findall(r"\b[a-z]{3,}\b", rag_content))
        result_words = set(re.findall(r"\b[a-z]{3,}\b", result_summary))

        if not rag_words or not result_words:
            return 0.5

        overlap = len(rag_words & result_words) / len(rag_words)
        return min(overlap, 1.0)

    def verify(self, job) -> tuple[bool, str, dict]:
        """Run tiered brand affinity verification.

        Returns:
            Tuple of (should_extract, reason, scores_dict)
        """
        scores = {}

        # Tier 1: Input match
        t1 = self.tier1_input_match(job)
        scores["t1"] = round(t1, 3)

        # Fast path: strong match
        if t1 >= 0.9:
            return True, "tier1_strong_match", scores

        # Fast path: clear mismatch
        if t1 < 0.3:
            return False, "tier1_brand_mismatch", scores

        # Tier 2: Result content scan
        t2 = self.tier2_result_content_scan(job)
        scores["t2"] = round(t2, 3)

        combined_t1_t2 = (t1 + t2) / 2
        if combined_t1_t2 >= 0.6:
            return True, "tier2_content_confirmed", scores

        # Tier 3: RAG cross-reference
        t3 = self.tier3_rag_cross_reference(job)
        scores["t3"] = round(t3, 3)

        weighted = t1 * 0.3 + t2 * 0.4 + t3 * 0.3
        scores["weighted_final"] = round(weighted, 3)

        if weighted >= 0.5:
            return True, "tier3_rag_confirmed", scores

        return False, "brand_affinity_rejected", scores
