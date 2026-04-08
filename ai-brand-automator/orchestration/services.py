"""
Service layer for the orchestration app.

OrchestratorDispatcher — dispatches jobs to the external
pipeline-orchestrator-svc via HTTP and handles cancellation.
"""

import logging

import requests
from decouple import config
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class OrchestratorDispatcher:
    """
    Dispatches analysis jobs to the external pipeline-orchestrator-svc.

    The orchestrator is a separate Python/LangGraph microservice that:
    1. Receives a manifest (agent graph) + input prompt
    2. Executes agents in dependency order
    3. Calls back to our /callback/ endpoint with progress and results

    Configuration (via decouple.config):
        ORCHESTRATOR_URL: Base URL of the pipeline-orchestrator-svc
        ORCHESTRATOR_SERVICE_TOKEN: Auth token for dispatch calls
        ORCHESTRATOR_CALLBACK_TOKEN: Shared secret for callback auth
        ORCHESTRATOR_TIMEOUT: HTTP timeout for dispatch call (seconds)
    """

    def __init__(self):
        self.orchestrator_url = config(
            "ORCHESTRATOR_URL", default="http://localhost:8010"
        )
        self.service_token = config(
            "ORCHESTRATOR_SERVICE_TOKEN", default="dev-service-token"
        )
        self.callback_token = config(
            "ORCHESTRATOR_CALLBACK_TOKEN", default="dev-callback-token"
        )
        self.timeout = config("ORCHESTRATOR_TIMEOUT", default=30, cast=int)

    def dispatch(self, job):
        """
        POST the job to the orchestrator service.

        Builds payload per Service Interaction Contract 1 (HLD v6.0).
        Includes tenant_context for secure data isolation.

        Returns True on successful dispatch (202), False on failure.
        Updates job.status to RUNNING on success, FAILED on error.
        """
        from .models import AnalysisJob

        payload = self._build_payload(job)

        try:
            response = requests.post(
                f"{self.orchestrator_url}/v1/jobs/dispatch",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Token": self.service_token,
                },
                timeout=self.timeout,
            )

            if response.status_code == 202:
                job.status = AnalysisJob.Status.RUNNING
                job.started_at = timezone.now()
                job.save(update_fields=["status", "started_at", "updated_at"])
                logger.info("Job %s dispatched successfully", job.job_id)
                return True

            # 4xx = non-retryable (bad request, auth, etc.) → mark failed
            if 400 <= response.status_code < 500:
                logger.error(
                    "Non-retryable dispatch failure for job %s: HTTP %s — %s",
                    job.job_id,
                    response.status_code,
                    response.text[:500],
                )
                job.status = AnalysisJob.Status.FAILED
                job.error_message = f"Dispatch failed: HTTP {response.status_code}"
                job.completed_at = timezone.now()
                job.save(
                    update_fields=[
                        "status",
                        "error_message",
                        "completed_at",
                        "updated_at",
                    ]
                )
                return False

            # 5xx = retryable → leave job in current status for Celery retry
            logger.warning(
                "Retryable dispatch failure for job %s: HTTP %s — %s",
                job.job_id,
                response.status_code,
                response.text[:500],
            )
            return False

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Orchestrator unreachable for job %s at %s",
                job.job_id,
                self.orchestrator_url,
            )
            # Leave job in QUEUED status for retry
            return False

        except requests.exceptions.Timeout:
            logger.error(
                "Dispatch timeout for job %s after %ds",
                job.job_id,
                self.timeout,
            )
            return False

        except requests.exceptions.RequestException as exc:
            logger.error(
                "Dispatch error for job %s: %s",
                job.job_id,
                str(exc),
            )
            return False

    def cancel(self, job):
        """
        POST cancel request to the orchestrator (Contract 3).

        Returns True if orchestrator accepted the cancel, False otherwise.
        """
        try:
            response = requests.post(
                f"{self.orchestrator_url}/v1/jobs/{job.job_id}/cancel",
                headers={"X-Service-Token": self.service_token},
                timeout=self.timeout,
            )
            if response.status_code == 200:
                logger.info("Job %s cancel accepted", job.job_id)
                return True
            logger.warning(
                "Cancel rejected for job %s: HTTP %s",
                job.job_id,
                response.status_code,
            )
            return False

        except requests.exceptions.RequestException as exc:
            logger.error(
                "Cancel request failed for job %s: %s",
                job.job_id,
                str(exc),
            )
            return False

    def _build_payload(self, job):
        """Build dispatch payload per Service Interaction Contract 1.

        Injects an authoritative brand_context (compiled from the tenant's
        Company row + uploaded BrandAssets) into every dispatch as:

          1. ``tenant_context.brand_context`` — structured dict
          2. ``tenant_context.brand_context_preamble`` (full) and
             ``tenant_context.brand_context_preamble_compact`` — so the
             orchestrator-svc ExternalWrapper can re-apply the guardrail
             if a node rewrites input_prompt, and can pick the compact
             variant for token-sensitive nodes via the
             ``brand_context_mode`` node config flag.
          3. The full ``BRAND CONTEXT`` guardrail preamble prepended to
             ``input_prompt`` so every downstream LLM call honors it
             without requiring agent-side code changes.

        This is the single chokepoint that ensures WF1 / WF2 / WF3 agents
        ground themselves in the onboarding data (location, audience,
        voice, positioning, uploaded assets) before executing their task.
        """
        from .models import PipelineManifest

        brand_context, preamble_full, preamble_compact = self._build_brand_context(job)

        input_prompt = job.input_prompt or ""
        input_context = dict(job.input_context or {})
        tenant_context = self._build_tenant_context(job)

        if brand_context is not None:
            tenant_context["brand_context"] = brand_context
            tenant_context["brand_context_preamble"] = preamble_full
            tenant_context["brand_context_preamble_compact"] = preamble_compact

            # Backward-compatible flat mirrors for agents that already
            # look at input_context for geo scope (previous revision).
            loc = brand_context.get("location") or {}
            if loc.get("is_local_single_location"):
                input_context.setdefault("geo_scope", "local")
                input_context.setdefault("brand_location", loc.get("formatted", ""))
                input_context.setdefault("brand_location_parts", loc.get("parts", {}))

            if preamble_full and "BRAND CONTEXT" not in input_prompt:
                input_prompt = preamble_full + input_prompt

        payload = {
            "job_id": str(job.job_id),
            "manifest": (job.manifest.manifest_data if job.manifest else None),
            "input_prompt": input_prompt,
            "input_context": input_context,
            "tenant_context": tenant_context,
            "callback_url": self._build_callback_url(job),
        }

        # When manifest is null (auto-detect mode), include catalog
        # with full manifest_data so orchestrator can execute after routing
        if job.manifest is None:
            payload["available_manifests"] = list(
                PipelineManifest.objects.filter(is_active=True).values(
                    "pipeline_id", "name", "description", "manifest_data"
                )
            )

        return payload

    def _build_brand_context(self, job):
        """
        Compile the authoritative brand-context block and its guardrail
        preambles from the tenant's Company + uploaded BrandAssets.

        Returns ``(structured_dict, preamble_full, preamble_compact)``.
        Returns ``(None, None, None)`` when there is no tenant / no
        Company — in which case _build_payload falls back to the legacy
        payload shape.

        The structured dict is safe to serialize (all primitives).
        ``preamble_full`` is written as a hard input-guardrail
        (authoritative, do-not-override, with a grounding checklist).
        ``preamble_compact`` keeps only the load-bearing fields (brand
        name, industry, location scope directive, primary audience,
        voice, positioning) for token-sensitive nodes that opt in via
        the manifest's ``brand_context_mode: compact`` node config.
        """
        tenant = getattr(job, "tenant", None)
        if not tenant:
            return None, None, None

        try:
            company = getattr(tenant, "company", None)
        except Exception:  # pragma: no cover — defensive
            company = None
        if company is None:
            return None, None, None

        # Uploaded brand assets — include metadata + (LLM-generated)
        # summary when present. Contents live in the tenant RAG data
        # store and agents retrieve them on-demand using
        # tenant_context.rag_data_store_id.
        try:
            assets = [
                {
                    "file_name": a.file_name,
                    "file_type": a.file_type,
                    "status": a.pipeline_status,
                    "summary": a.summary or "",
                }
                for a in company.assets.all().only(
                    "file_name", "file_type", "pipeline_status", "summary"
                )
            ]
        except Exception:  # pragma: no cover — defensive
            assets = []

        has_local = bool(getattr(company, "has_local_scope", False))
        formatted_location = company.formatted_address if has_local else ""

        structured = {
            "name": company.name or "",
            "industry": company.industry or "",
            "description": company.description or "",
            "core_problem": company.core_problem or "",
            "website": company.website or "",
            "location": {
                "formatted": formatted_location,
                "parts": {
                    "address": company.address or "",
                    "city": company.city or "",
                    "state_province": company.state_province or "",
                    "postal_code": company.postal_code or "",
                    "country": company.country or "",
                },
                "is_local_single_location": has_local,
            },
            "target_audience": {
                "summary": company.target_audience or "",
                "demographics": company.demographics or "",
                "psychographics": company.psychographics or "",
                "pain_points": company.pain_points or "",
                "desired_outcomes": company.desired_outcomes or "",
            },
            "brand_voice": company.brand_voice or "",
            "vision_statement": company.vision_statement or "",
            "mission_statement": company.mission_statement or "",
            "values": company.values or "",
            "positioning_statement": company.positioning_statement or "",
            "tagline": company.tagline or "",
            "value_proposition": company.value_proposition or "",
            "elevator_pitch": company.elevator_pitch or "",
            "assets": assets,
        }

        # --- Preamble (hard input guardrail) ---------------------------
        lines = [
            "=" * 70,
            "BRAND CONTEXT — AUTHORITATIVE GROUND TRUTH",
            "=" * 70,
            "The orchestrator has compiled the following brand context from",
            "this tenant's onboarding data. It is the AUTHORITATIVE source",
            "of truth about the brand. You MUST:",
            "  - Read every field below before planning your work.",
            "  - Treat these fields as non-negotiable constraints.",
            "  - NOT override, contradict, or default away from any field.",
            "  - Treat any output that contradicts this context as an error",
            "    and correct it before returning.",
            "",
        ]

        def _add(label, value):
            if value:
                lines.append(f"- {label}: {value}")

        _add("Brand name", company.name)
        _add("Industry", company.industry)
        _add("Description", company.description)
        _add("Core problem solved", company.core_problem)
        _add("Website", company.website)

        if has_local and formatted_location:
            lines.append(f"- Physical location: {formatted_location}")
            lines.append(
                "  >>> SINGLE LOCAL LOCATION. Scope ALL research, market "
                "sizing, competitor analysis, audience personas, trend "
                "monitoring, VoC, brand positioning, campaign architecture, "
                "ad targeting, placements, and creative references "
                "EXCLUSIVELY to the city / neighborhood around this address. "
                "Do NOT expand to national, regional, or global scope. "
                "Meta ad campaigns MUST target this location with a tight "
                "geo radius."
            )

        # Target audience — preserve each field separately so the LLM
        # cannot collapse them into a generic "everyone" default.
        ta_any = False
        if company.target_audience:
            lines.append(f"- Target audience (primary): {company.target_audience}")
            ta_any = True
        if company.demographics:
            lines.append(f"- Target audience — demographics: {company.demographics}")
            ta_any = True
        if company.psychographics:
            lines.append(
                f"- Target audience — psychographics: {company.psychographics}"
            )
            ta_any = True
        if company.pain_points:
            lines.append(f"- Target audience — pain points: {company.pain_points}")
            ta_any = True
        if company.desired_outcomes:
            lines.append(
                f"- Target audience — desired outcomes: {company.desired_outcomes}"
            )
            ta_any = True
        if ta_any:
            lines.append(
                "  >>> Use these audience fields verbatim. Do NOT invent a "
                "different audience, and do NOT broaden to a generic "
                "demographic unless the task explicitly asks you to."
            )

        _add("Brand voice", company.brand_voice)
        _add("Positioning statement", company.positioning_statement)
        _add("Value proposition", company.value_proposition)
        _add("Tagline", company.tagline)
        _add("Vision", company.vision_statement)
        _add("Mission", company.mission_statement)
        _add("Core values", company.values)
        _add("Elevator pitch", company.elevator_pitch)

        if assets:
            lines.append("")
            lines.append("Uploaded brand assets (contents live in the tenant RAG")
            lines.append("data store — retrieve them when their contents are")
            lines.append(
                "relevant to your task, using the rag_data_store_id in "
                "tenant_context):"
            )
            for a in assets:
                header = f"  - {a['file_name']} ({a['file_type']}, {a['status']})"
                lines.append(header)
                if a.get("summary"):
                    lines.append(f"      {a['summary']}")

        lines.extend(
            [
                "",
                "GROUNDING CHECKLIST (perform BEFORE your main task):",
                "  1. Re-read every brand-context field above.",
                "  2. Constrain your analysis to the brand's industry, "
                "physical location, and stated target audience.",
                "  3. Retrieve uploaded assets from the tenant RAG store "
                "when their contents are relevant (e.g. menu.pdf for food "
                "items, brand_guidelines.pdf for visual rules).",
                "  4. Keep your output consistent with the brand voice, "
                "positioning, values, and tagline.",
                "  5. If any part of your output would contradict the "
                "brand context, stop and correct it.",
                "=" * 70,
                "",
                "USER TASK:",
                "",
            ]
        )

        preamble_full = "\n".join(lines)

        # --- Compact variant --------------------------------------------
        # ~10 lines vs ~40. Keeps only the load-bearing fields for
        # token-sensitive nodes. Opt in via node config in the manifest:
        #   { "brand_context_mode": "compact" }
        clines = [
            "BRAND CONTEXT (authoritative — do not override):",
        ]
        if company.name:
            clines.append(f"- Brand: {company.name}")
        if company.industry:
            clines.append(f"- Industry: {company.industry}")
        if has_local and formatted_location:
            clines.append(
                f"- LOCAL SINGLE LOCATION: {formatted_location}. "
                "Scope all research, audience, campaigns, and ad targeting "
                "exclusively to the city / neighborhood around this "
                "address. Do NOT expand to national/regional/global."
            )
        if company.target_audience:
            clines.append(
                f"- Target audience (use verbatim): {company.target_audience}"
            )
        if company.brand_voice:
            clines.append(f"- Voice: {company.brand_voice}")
        if company.positioning_statement:
            clines.append(f"- Positioning: {company.positioning_statement}")
        if company.value_proposition:
            clines.append(f"- Value proposition: {company.value_proposition}")
        if assets:
            summarized = [a for a in assets if a.get("summary")]
            if summarized:
                clines.append(
                    "- Uploaded assets (retrieve from RAG when relevant): "
                    + "; ".join(
                        f"{a['file_name']} — {a['summary']}" for a in summarized[:6]
                    )
                )
            else:
                clines.append(
                    "- Uploaded assets: "
                    + ", ".join(a["file_name"] for a in assets[:6])
                )
        clines.append("")
        clines.append("USER TASK:")
        clines.append("")
        preamble_compact = "\n".join(clines)

        return structured, preamble_full, preamble_compact

    def _build_tenant_context(self, job):
        """
        Build tenant-scoped context for secure data isolation.

        Resolves the tenant's GCS bucket paths and RAG data store ID
        so the orchestrator only accesses the correct tenant's data.
        The authoritative ``brand_context`` is attached by
        ``_build_payload`` on top of this base dict.
        """
        tenant = job.tenant
        if not tenant:
            return {}

        gs_bucket = getattr(settings, "GS_BUCKET_NAME", "brand-automator")
        return {
            "tenant_id": str(tenant.id),
            "gcs_raw_bucket": f"{gs_bucket}/{tenant.id}/",
            "gcs_processed_bucket": f"{gs_bucket}-curated/{tenant.id}/",
            "rag_data_store_id": tenant.get_data_store_id(),
        }

    def _build_callback_url(self, job):
        """Build the callback URL for this job.

        Uses ``CALLBACK_BASE_URL`` which must point to the **web**
        service's private networking URL (e.g.
        ``http://previsionws.railway.internal:8000`` on Railway).

        Note: Do NOT use ``RAILWAY_PRIVATE_DOMAIN`` here — dispatch runs
        inside a Celery worker which is a separate Railway service with
        its own private domain.  The callback must always target the
        web service.
        """
        base_url = config(
            "CALLBACK_BASE_URL",
            default=config("BACKEND_URL", default="http://localhost:8001"),
        ).rstrip("/")
        if "localhost" in base_url or "127.0.0.1" in base_url:
            logger.warning(
                "Callback base URL is '%s' — pipeline callbacks will "
                "fail if the orchestrator runs on a different host. "
                "Set CALLBACK_BASE_URL to the internal service URL "
                "(e.g. http://backend:8001 or "
                "http://<service>.railway.internal:<port>).",
                base_url,
            )
        callback_url = f"{base_url}/api/v1/orchestration/jobs/{job.job_id}/callback/"
        logger.info("Callback URL for job %s: %s", job.job_id, callback_url)
        return callback_url
