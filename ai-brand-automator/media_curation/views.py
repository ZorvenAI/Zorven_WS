"""
DRF Views for Media Curation API.

REST API endpoints for curation operations.
"""

import logging
from datetime import datetime
from uuid import uuid4

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from media_curation.serializers import (
    CurationRequestSerializer,
    BatchCurationRequestSerializer,
    CurationResponseSerializer,
    BatchCurationResponseSerializer,
    CurationStatusSerializer,
    HealthCheckSerializer,
    TenantConfigSerializer,
    SyncCurationRequestSerializer,
    SyncCurationResponseSerializer,
)


logger = logging.getLogger(__name__)


class CurationViewSet(viewsets.ViewSet):
    """
    ViewSet for curation operations.

    Endpoints:
    - POST /api/v1/curation/ - Submit single curation request
    - POST /api/v1/curation/batch/ - Submit batch curation request
    - GET /api/v1/curation/status/{trace_id}/ - Get curation status
    """

    permission_classes = [IsAuthenticated]

    def create(self, request: Request) -> Response:
        """
        Submit content for curation (async).

        Returns immediately with trace_id for status tracking.
        """
        serializer = CurationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Generate IDs
        event_id = uuid4()
        trace_id = uuid4()

        # Get tenant_id from request data
        tenant_id = serializer.validated_data.get("tenant_id")

        logger.info(
            "Curation request received",
            extra={
                "event_id": str(event_id),
                "trace_id": str(trace_id),
                "tenant_id": tenant_id,
                "source_path": serializer.validated_data.get("source_path"),
            },
        )

        # Submit to Celery task
        from media_curation.tasks import process_curation_event

        process_curation_event.delay(
            event_id=str(event_id),
            trace_id=str(trace_id),
            tenant_id=tenant_id,
            source_path=serializer.validated_data.get("source_path"),
            file_type=serializer.validated_data.get("file_type"),
            brand_id=serializer.validated_data.get("brand_id"),
            file_size_bytes=serializer.validated_data.get("file_size_bytes", 0),
            metadata=serializer.validated_data.get("metadata", {}),
        )

        response_data = {
            "event_id": event_id,
            "trace_id": trace_id,
            "status": "accepted",
            "message": "Curation request queued for processing",
        }

        return Response(
            CurationResponseSerializer(response_data).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["post"], url_path="batch")
    def batch(self, request: Request) -> Response:
        """
        Submit batch curation request (async).

        Returns immediately with trace_ids for each event.
        """
        serializer = BatchCurationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        accepted = 0
        rejected = 0

        for event_data in serializer.validated_data["events"]:
            try:
                event_id = uuid4()
                trace_id = uuid4()

                # Submit to Celery task
                from media_curation.tasks import process_curation_event

                process_curation_event.delay(
                    event_id=str(event_id),
                    trace_id=str(trace_id),
                    tenant_id=event_data.get("tenant_id"),
                    source_path=event_data.get("source_path"),
                    file_type=event_data.get("file_type"),
                    brand_id=event_data.get("brand_id"),
                    file_size_bytes=event_data.get("file_size_bytes", 0),
                    metadata=event_data.get("metadata", {}),
                )

                results.append(
                    {
                        "event_id": event_id,
                        "trace_id": trace_id,
                        "status": "accepted",
                        "message": "Queued for processing",
                    }
                )
                accepted += 1

            except Exception as e:
                logger.exception("Failed to queue curation event")
                results.append(
                    {
                        "event_id": None,
                        "trace_id": None,
                        "status": "rejected",
                        "message": str(e),
                    }
                )
                rejected += 1

        response_data = {
            "accepted": accepted,
            "rejected": rejected,
            "results": results,
        }

        return Response(
            BatchCurationResponseSerializer(response_data).data,
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=False, methods=["get"], url_path="status/(?P<trace_id>[^/.]+)")
    def get_status(self, request: Request, trace_id: str) -> Response:
        """
        Get curation status by trace_id.
        """
        import asyncio
        from media_curation.factory import create_cache_adapter

        logger.info(f"Status check for trace_id: {trace_id}")

        # Get status from Redis cache
        cache = create_cache_adapter()
        tenant = getattr(request, "tenant", None)
        tenant_id = str(tenant.id) if tenant else None

        try:
            # Run async cache lookup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                status_record = loop.run_until_complete(
                    cache.get_status(trace_id, tenant_id=tenant_id)
                )
            finally:
                loop.close()

            if status_record:
                response_data = {
                    "trace_id": status_record.trace_id,
                    "event_id": status_record.event_id,
                    "status": status_record.status.value,
                    "content_type": None,
                    "started_at": status_record.updated_at,
                    "completed_at": (
                        status_record.updated_at
                        if status_record.status.value in ["CURATED", "FAILED"]
                        else None
                    ),
                    "processing_duration_ms": 0,
                    "error_message": (
                        status_record.message
                        if status_record.status.value == "FAILED"
                        else None
                    ),
                    "retry_count": 0,
                    "destination_path": status_record.output_gcs_uri,
                }
            else:
                # Not found - return pending status
                response_data = {
                    "trace_id": trace_id,
                    "event_id": trace_id,
                    "status": "NOT_FOUND",
                    "content_type": None,
                    "started_at": datetime.utcnow(),
                    "completed_at": None,
                    "processing_duration_ms": 0,
                    "error_message": None,
                    "retry_count": 0,
                    "destination_path": None,
                }
        except Exception as e:
            logger.error(f"Error fetching status: {e}")
            response_data = {
                "trace_id": trace_id,
                "event_id": trace_id,
                "status": "ERROR",
                "content_type": None,
                "started_at": datetime.utcnow(),
                "completed_at": None,
                "processing_duration_ms": 0,
                "error_message": str(e),
                "retry_count": 0,
                "destination_path": None,
            }

        return Response(
            CurationStatusSerializer(response_data).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="sync")
    def sync(self, request: Request) -> Response:
        """
        Submit content for synchronous curation (testing/debugging).

        Processes the content immediately and returns the result.
        This endpoint is intended for testing and debugging purposes.
        For production use, prefer the async /curation/ endpoint.
        """
        import time

        from media_curation.domain.services import CurationService
        from media_curation.domain.models import CurationEvent, ContentType

        serializer = SyncCurationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Generate IDs
        event_id = uuid4()
        trace_id = uuid4()
        file_id = uuid4()

        tenant_id = serializer.validated_data.get("tenant_id")
        timeout_seconds = serializer.validated_data.get("timeout_seconds", 60)
        source_path = serializer.validated_data.get("source_path")
        mime_type = serializer.validated_data.get("file_type")

        # Determine content type from mime type
        content_type = ContentType.UNKNOWN
        if mime_type.startswith("video/"):
            content_type = ContentType.VIDEO
        elif mime_type.startswith("audio/"):
            content_type = ContentType.AUDIO
        elif mime_type.startswith("image/"):
            content_type = ContentType.IMAGE
        elif mime_type in ("application/pdf", "application/msword"):
            content_type = ContentType.DOCUMENT
        elif mime_type.startswith("text/"):
            content_type = ContentType.TEXT

        logger.info(
            "Sync curation request received",
            extra={
                "event_id": str(event_id),
                "trace_id": str(trace_id),
                "tenant_id": tenant_id,
                "source_path": source_path,
                "timeout_seconds": timeout_seconds,
            },
        )

        start_time = time.time()

        try:
            # Create curation event with correct field names
            event = CurationEvent(
                event_id=event_id,
                trace_id=trace_id,
                tenant_id=tenant_id if tenant_id else str(uuid4()),
                file_id=file_id,
                raw_gcs_uri=source_path,
                mime_type=mime_type,
                content_type=content_type,
                metadata=serializer.validated_data.get("metadata", {}),
            )

            # Create service and process
            service = CurationService()

            # Run async processing synchronously
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                document = loop.run_until_complete(
                    asyncio.wait_for(service.process(event), timeout=timeout_seconds)
                )
            finally:
                loop.close()

            processing_duration_ms = int((time.time() - start_time) * 1000)

            response_data = {
                "event_id": event_id,
                "trace_id": trace_id,
                "status": "completed",
                "document": {
                    "document_id": document.document_id,
                    "event_id": document.event_id,
                    "trace_id": document.trace_id,
                    "tenant_id": document.tenant_id,
                    "brand_id": str(document.brand_id) if document.brand_id else None,
                    "source_path": document.source_gcs_uri,
                    "destination_path": document.curated_gcs_uri,
                    "file_type": document.content_type,
                    "content_type": document.content_type,
                    "title": document.title,
                    "content": document.extracted_text,
                    "summary": document.summary,
                    "entities": document.entities,
                    "keywords": document.keywords,
                    "language": document.detected_language,
                    "status": (
                        document.status.value
                        if hasattr(document.status, "value")
                        else str(document.status)
                    ),
                    "confidence_score": document.confidence_score,
                    "pii_redacted": document.pii_redacted,
                    "pii_findings_count": document.pii_findings_count,
                    "created_at": document.created_at,
                    "processing_duration_ms": document.processing_duration_ms,
                    "metadata": document.metadata,
                },
                "processing_duration_ms": processing_duration_ms,
                "error": None,
            }

            return Response(
                SyncCurationResponseSerializer(response_data).data,
                status=status.HTTP_200_OK,
            )

        except asyncio.TimeoutError:
            processing_duration_ms = int((time.time() - start_time) * 1000)
            return Response(
                {
                    "event_id": str(event_id),
                    "trace_id": str(trace_id),
                    "status": "timeout",
                    "document": None,
                    "processing_duration_ms": processing_duration_ms,
                    "error": f"Processing timed out after {timeout_seconds} seconds",
                },
                status=status.HTTP_408_REQUEST_TIMEOUT,
            )

        except Exception as e:
            processing_duration_ms = int((time.time() - start_time) * 1000)
            logger.exception("Sync curation failed")
            return Response(
                {
                    "event_id": str(event_id),
                    "trace_id": str(trace_id),
                    "status": "failed",
                    "document": None,
                    "processing_duration_ms": processing_duration_ms,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CurationHealthView(APIView):
    """
    Health check endpoint for the curation service.

    Returns component-level health status including consumer instances.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """
        Check health of all curation service components.
        """
        import asyncio
        from media_curation.factory import (
            create_cache_adapter,
            create_storage_adapter,
            create_kafka_producer,
            get_media_curation_config,
        )
        from media_curation.consumer_health import (
            ConsumerHealthTracker,
            get_consumer_health_summary,
        )

        config = get_media_curation_config()
        components = {}
        overall_status = "healthy"

        # Helper to run async health checks
        def run_async_check(coro):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        # Check Redis
        redis_client = None
        try:
            cache = create_cache_adapter()
            is_healthy = run_async_check(cache.is_healthy())
            components["redis"] = {"status": "healthy" if is_healthy else "unhealthy"}
            if not is_healthy:
                overall_status = "degraded"
            # Get redis client for consumer check
            if hasattr(cache, "_redis") and cache._redis:
                redis_client = cache._redis
        except Exception as e:
            components["redis"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Check Kafka consumer instances (if Redis is available)
        if redis_client:
            try:
                consumers = run_async_check(
                    ConsumerHealthTracker.get_all_consumers_async(redis_client)
                )
                consumer_summary = get_consumer_health_summary(consumers)
                components["consumers"] = consumer_summary

                # Affect overall status based on consumer health
                if consumer_summary["status"] == "unhealthy":
                    overall_status = "degraded"
            except Exception as e:
                components["consumers"] = {
                    "status": "unknown",
                    "error": str(e),
                }
        else:
            components["consumers"] = {
                "status": "unknown",
                "message": "Redis not available for consumer health check",
            }

        # Check Kafka
        try:
            producer = create_kafka_producer()
            # For producer, check if it's initialized
            if hasattr(producer, "_kafka_available") and producer._kafka_available:
                components["kafka"] = {"status": "healthy"}
            else:
                components["kafka"] = {
                    "status": "mock_mode",
                    "message": "Kafka not available, using mock",
                }
        except Exception as e:
            components["kafka"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Check GCS
        try:
            storage = create_storage_adapter()
            is_healthy = run_async_check(storage.is_healthy())
            if is_healthy:
                components["gcs"] = {"status": "healthy"}
            elif (
                hasattr(storage, "_storage_available")
                and not storage._storage_available
            ):
                components["gcs"] = {
                    "status": "mock_mode",
                    "message": "GCS not available, using mock",
                }
            else:
                components["gcs"] = {"status": "unhealthy"}
                overall_status = "degraded"
        except Exception as e:
            components["gcs"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Check AI/Vertex
        try:
            # Check if google-generativeai is available
            import importlib.util

            if importlib.util.find_spec("google.generativeai"):
                components["ai_model"] = {
                    "status": "healthy",
                    "model": config.get("AI_MODEL", {}).get(
                        "MODEL", "gemini-3.5-flash"
                    ),
                }
            else:
                components["ai_model"] = {
                    "status": "mock_mode",
                    "message": "google-generativeai not installed",
                }
        except Exception as e:
            components["ai_model"] = {"status": "unhealthy", "error": str(e)}
            overall_status = "degraded"

        # Check configuration
        components["config"] = {"status": "healthy"}

        response_data = {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "components": components,
        }

        http_status = (
            status.HTTP_200_OK
            if overall_status in ["healthy", "degraded"]
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )

        return Response(
            HealthCheckSerializer(response_data).data,
            status=http_status,
        )


class TenantConfigViewSet(viewsets.ViewSet):
    """
    ViewSet for tenant curation configuration CRUD.

    Endpoints:
    - GET /api/v1/curation/config/ - List all tenant configs
    - POST /api/v1/curation/config/ - Create tenant config
    - GET /api/v1/curation/config/{tenant_id}/ - Get tenant config
    - PUT /api/v1/curation/config/{tenant_id}/ - Update tenant config
    - DELETE /api/v1/curation/config/{tenant_id}/ - Delete tenant config
    """

    permission_classes = [IsAuthenticated]

    # In-memory store for demo (in production, use database)
    _configs = {}

    def list(self, request: Request) -> Response:
        """List all tenant configurations."""
        # Filter by tenant if multi-tenancy
        tenant = getattr(request, "tenant", None)

        configs = list(self._configs.values())

        logger.debug(f"List configs: total={len(configs)}, tenant={tenant}")

        # Optionally filter by tenant access (only in multi-tenant context)
        # In test/development mode without proper tenant context, return all configs
        if tenant and hasattr(tenant, "schema_name") and tenant.schema_name != "public":
            # In multi-tenant context, filter to tenant's own config
            tenant_id_str = (
                str(tenant.id) if hasattr(tenant, "id") else tenant.schema_name
            )
            configs = [c for c in configs if c.get("tenant_id") == tenant_id_str]
            logger.debug(f"Filtered to tenant {tenant_id_str}: {len(configs)} configs")

        return Response(configs, status=status.HTTP_200_OK)

    def create(self, request: Request) -> Response:
        """Create a new tenant configuration."""
        serializer = TenantConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_id = serializer.validated_data["tenant_id"]

        if tenant_id in self._configs:
            return Response(
                {"error": f"Configuration for tenant {tenant_id} already exists"},
                status=status.HTTP_409_CONFLICT,
            )

        config = {
            **serializer.validated_data,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._configs[tenant_id] = config

        logger.info(f"Created tenant config for {tenant_id}")

        return Response(config, status=status.HTTP_201_CREATED)

    def retrieve(self, request: Request, pk: str = None) -> Response:
        """Get a tenant configuration by tenant_id."""
        if pk not in self._configs:
            return Response(
                {"error": f"Configuration for tenant {pk} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(self._configs[pk], status=status.HTTP_200_OK)

    def update(self, request: Request, pk: str = None) -> Response:
        """Update a tenant configuration."""
        if pk not in self._configs:
            return Response(
                {"error": f"Configuration for tenant {pk} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TenantConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data["tenant_id"] != pk:
            return Response(
                {"error": "tenant_id in body must match URL"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        config = {
            **serializer.validated_data,
            "created_at": self._configs[pk].get(
                "created_at", datetime.utcnow().isoformat()
            ),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self._configs[pk] = config

        logger.info(f"Updated tenant config for {pk}")

        return Response(config, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, pk: str = None) -> Response:
        """Partially update a tenant configuration."""
        if pk not in self._configs:
            return Response(
                {"error": f"Configuration for tenant {pk} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        existing = self._configs[pk].copy()
        existing.update(request.data)
        existing["updated_at"] = datetime.utcnow().isoformat()

        # Validate the merged data
        serializer = TenantConfigSerializer(data=existing)
        serializer.is_valid(raise_exception=True)

        self._configs[pk] = existing

        logger.info(f"Partially updated tenant config for {pk}")

        return Response(existing, status=status.HTTP_200_OK)

    def destroy(self, request: Request, pk: str = None) -> Response:
        """Delete a tenant configuration."""
        if pk not in self._configs:
            return Response(
                {"error": f"Configuration for tenant {pk} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        del self._configs[pk]
        logger.info(f"Deleted tenant config for {pk}")

        return Response(status=status.HTTP_204_NO_CONTENT)
