"""
Celery tasks for onboarding pipeline integration.

These tasks handle asynchronous operations for the data pipeline,
including exporting company data for RAG indexing.
"""

import logging
from typing import Any

from celery import shared_task

from .services import get_pipeline_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, ignore_result=True)
def export_company_for_rag(self, company_id: int) -> dict[str, Any]:
    """
    Export company data as a structured document for RAG indexing.

    This task extracts company information (name, description, industry,
    target audience, brand values) and publishes it to the data pipeline
    for embedding and indexing in the RAG system.

    Args:
        company_id: The ID of the Company to export.

    Returns:
        dict with export status and trace_id.

    Raises:
        Company.DoesNotExist: If company not found (won't retry).
        Exception: Other errors will retry up to 3 times.
    """
    # Import here to avoid circular imports
    from .models import Company

    try:
        company = Company.objects.select_related("tenant").get(id=company_id)
    except Company.DoesNotExist:
        logger.error(f"Company {company_id} not found, cannot export for RAG")
        return {"status": "error", "message": f"Company {company_id} not found"}

    # Build structured document for RAG
    company_doc = _build_company_document(company)

    # Publish to data pipeline
    pipeline_service = get_pipeline_service()

    try:
        trace_id = pipeline_service.publish_company_document(company_doc)
        logger.info(
            f"Exported company {company_id} for RAG indexing, trace_id={trace_id}"
        )
        return {
            "status": "success",
            "company_id": company_id,
            "trace_id": str(trace_id),
        }
    except Exception as exc:
        logger.exception(f"Failed to export company {company_id} for RAG")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=2**self.request.retries * 10)


def _build_company_document(company) -> dict[str, Any]:
    """
    Build a structured document from Company for RAG indexing.

    Creates a document with metadata and text content suitable for
    embedding and retrieval.
    """
    tenant_id = company.tenant.id if company.tenant else None

    # Combine text fields for embedding
    text_parts = []
    if company.name:
        text_parts.append(f"Company: {company.name}")
    if company.description:
        text_parts.append(f"Description: {company.description}")
    if company.industry:
        text_parts.append(f"Industry: {company.industry}")
    if company.target_audience:
        text_parts.append(f"Target Audience: {company.target_audience}")
    if company.values:
        text_parts.append(f"Values: {company.values}")
    if company.brand_voice:
        text_parts.append(f"Brand Voice: {company.brand_voice}")

    # Get brand assets summary
    asset_count = company.assets.count()
    if asset_count > 0:
        text_parts.append(f"Brand Assets: {asset_count} files uploaded")

    return {
        "document_type": "company_profile",
        "tenant_id": str(tenant_id) if tenant_id else None,
        "company_id": company.id,
        "metadata": {
            "name": company.name,
            "industry": company.industry,
            "created_at": company.created_at.isoformat()
            if hasattr(company, "created_at")
            else None,
            "updated_at": company.updated_at.isoformat()
            if hasattr(company, "updated_at")
            else None,
        },
        "content": "\n\n".join(text_parts),
        "source": "onboarding_service",
    }


@shared_task(bind=True, max_retries=3, ignore_result=True)
def batch_export_companies_for_rag(
    self, tenant_id: int | None = None
) -> dict[str, Any]:
    """
    Export all companies (optionally filtered by tenant) for RAG indexing.

    This is useful for initial data population or re-indexing.

    Args:
        tenant_id: Optional tenant ID to filter companies.

    Returns:
        dict with count of companies queued for export.
    """
    from .models import Company

    if tenant_id:
        companies = Company.objects.filter(tenant_id=tenant_id)
    else:
        companies = Company.objects.all()

    count = 0
    for company in companies.iterator():
        export_company_for_rag.delay(company.id)
        count += 1

    logger.info(f"Queued {count} companies for RAG export (tenant_id={tenant_id})")
    return {"status": "success", "queued_count": count, "tenant_id": tenant_id}
