import abc

from analytics.models import MetricSnapshot


class BaseExtractor(abc.ABC):
    """Abstract base class for pipeline-specific metric extractors."""

    @abc.abstractmethod
    def extract(self, job) -> list[MetricSnapshot]:
        """Extract metrics from a completed AnalysisJob.

        Args:
            job: AnalysisJob instance with result_data populated.

        Returns:
            List of unsaved MetricSnapshot instances.
        """

    def _make_metric(
        self,
        job,
        name: str,
        value: float,
        category: str,
        unit: str = "score",
        agent_source: str = "",
        metadata: dict | None = None,
    ) -> MetricSnapshot:
        """Helper to construct an unsaved MetricSnapshot."""
        pipeline_id = self._resolve_pipeline_id(job)
        return MetricSnapshot(
            tenant=job.tenant,
            job=job,
            pipeline_id=pipeline_id,
            metric_name=name,
            metric_value=value,
            metric_unit=unit,
            metric_category=category,
            agent_source=agent_source,
            metadata=metadata or {},
            recorded_at=job.completed_at or job.updated_at,
        )

    def _resolve_pipeline_id(self, job) -> str:
        """Resolve pipeline ID from manifest or input_context."""
        if job.manifest:
            return job.manifest.pipeline_id
        return (job.input_context or {}).get("pipeline_id", "unknown")

    def _safe_get(self, data: dict, *keys, default=0):
        """Safely traverse nested dict keys."""
        current = data
        for key in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(key, default)
        return current if current is not None else default
