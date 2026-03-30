"""
Serializers for the orchestration app.

PipelineManifestSerializer — full manifest with HLD v6.0 node validation.
PipelineManifestListSerializer — lightweight list view (no manifest_data).
AnalysisJobCreateSerializer — create job with optional manifest.
AnalysisJobSerializer — full job with progress and results.
CallbackSerializer — validates orchestrator callback payloads.
"""

from collections import deque

from rest_framework import serializers

from .models import AnalysisJob, PipelineManifest, TrendNotification


class PipelineManifestSerializer(serializers.ModelSerializer):
    """Full manifest serializer with HLD v6.0 node validation."""

    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = PipelineManifest
        fields = [
            "id",
            "pipeline_id",
            "name",
            "description",
            "manifest_data",
            "version",
            "is_active",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "version",
            "created_by_email",
            "created_at",
            "updated_at",
        ]

    def validate_manifest_data(self, value):
        """Validate manifest structure per HLD v6.0 Pipeline-as-Code format."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("manifest_data must be a JSON object")
        if "nodes" not in value:
            raise serializers.ValidationError("manifest_data must contain 'nodes' key")
        if "edges" not in value:
            raise serializers.ValidationError("manifest_data must contain 'edges' key")

        nodes = value["nodes"]
        if not isinstance(nodes, list):
            raise serializers.ValidationError("'nodes' must be an array")

        edges = value["edges"]
        if not isinstance(edges, list):
            raise serializers.ValidationError("'edges' must be an array")

        node_ids = set()
        for node in nodes:
            if not isinstance(node, dict):
                raise serializers.ValidationError("Each node must be a JSON object")
            if "id" not in node or "type" not in node:
                raise serializers.ValidationError(
                    "Each node must have 'id' and 'type' fields"
                )
            if node["type"] not in ("internal", "external"):
                raise serializers.ValidationError(
                    f"Node '{node['id']}' type must be "
                    f"'internal' or 'external', got '{node['type']}'"
                )
            if node["type"] == "external" and "url" not in node:
                raise serializers.ValidationError(
                    f"External node '{node['id']}' must have a 'url' field"
                )
            if node["type"] == "external" and "url" in node:
                self._validate_external_url(node["id"], node["url"])
            if node["type"] == "internal" and "handler" not in node:
                raise serializers.ValidationError(
                    f"Internal node '{node['id']}' must have a " f"'handler' field"
                )
            if node["id"] in node_ids:
                raise serializers.ValidationError(f"Duplicate node id: '{node['id']}'")
            node_ids.add(node["id"])

        # Validate edges reference existing nodes
        for edge in edges:
            if not isinstance(edge, list) or len(edge) != 2:
                raise serializers.ValidationError(
                    "Each edge must be a [source, target] pair"
                )
            source, target = edge
            if source not in node_ids:
                raise serializers.ValidationError(
                    f"Edge source '{source}' is not a valid node id"
                )
            if target not in node_ids:
                raise serializers.ValidationError(
                    f"Edge target '{target}' is not a valid node id"
                )

        # Validate no circular dependencies
        self._validate_no_cycles(value)
        return value

    ALLOWED_URL_PREFIXES = (
        "http://discovery-agent-svc",
        "http://intelligence-agent-svc",
        "http://content-agent-svc",
        "http://social-agent-svc",
        "http://pipeline-orchestrator-svc",
        "http://competitor-intel-agent-svc",
        "http://market-research-agent-svc",
        "http://audience-persona-agent-svc",
        "http://trend-cultural-agent-svc",
        "http://localhost:",
        "https://discovery-agent-svc",
        "https://intelligence-agent-svc",
        "https://content-agent-svc",
        "https://social-agent-svc",
        "https://pipeline-orchestrator-svc",
        "https://competitor-intel-agent-svc",
        "https://market-research-agent-svc",
        "https://audience-persona-agent-svc",
        "https://trend-cultural-agent-svc",
        "http://voc-agent-svc",
        "https://voc-agent-svc",
        "http://brand-positioning-agent-svc",
        "https://brand-positioning-agent-svc",
        "http://brand-architecture-agent-svc",
        "https://brand-architecture-agent-svc",
        "http://brand-personality-agent-svc",
        "https://brand-personality-agent-svc",
        "http://brand-naming-agent-svc",
        "https://brand-naming-agent-svc",
    )

    def _validate_external_url(self, node_id, url):
        """Reject external node URLs that are not in the allowlist.

        Prevents SSRF by ensuring only known internal service URLs
        are accepted in manifest definitions.
        """
        if not any(url.startswith(prefix) for prefix in self.ALLOWED_URL_PREFIXES):
            raise serializers.ValidationError(
                f"External node '{node_id}' has a URL that is not in the "
                f"allowed service list. Only internal service URLs are permitted."
            )

    def _validate_no_cycles(self, manifest):
        """Topological sort to detect circular dependencies."""
        nodes = {n["id"] for n in manifest["nodes"]}
        adjacency = {n: [] for n in nodes}
        in_degree = {n: 0 for n in nodes}

        for source, target in manifest["edges"]:
            adjacency[source].append(target)
            in_degree[target] += 1

        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        visited = 0

        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited != len(nodes):
            raise serializers.ValidationError(
                "manifest_data contains circular dependencies in edges"
            )


class PipelineManifestListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (excludes manifest_data)."""

    class Meta:
        model = PipelineManifest
        fields = [
            "id",
            "pipeline_id",
            "name",
            "description",
            "version",
            "is_active",
            "updated_at",
        ]


class AnalysisJobCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new analysis job."""

    class Meta:
        model = AnalysisJob
        fields = ["manifest", "input_prompt", "input_context"]

    def validate_manifest(self, value):
        """Ensure manifest is active (if provided)."""
        if value is not None and not value.is_active:
            raise serializers.ValidationError("Cannot use an inactive manifest")
        return value

    def validate_input_prompt(self, value):
        """Ensure prompt is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("input_prompt cannot be empty")
        return value.strip()


class AnalysisJobSerializer(serializers.ModelSerializer):
    """Full job serializer with progress and results."""

    manifest_name = serializers.CharField(
        source="manifest.name", read_only=True, default=None
    )
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = AnalysisJob
        fields = [
            "id",
            "job_id",
            "manifest",
            "manifest_name",
            "input_prompt",
            "input_context",
            "status",
            "progress",
            "result_data",
            "error_message",
            "created_by_email",
            "duration_seconds",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "job_id",
            "status",
            "progress",
            "result_data",
            "error_message",
            "started_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class CallbackSerializer(serializers.Serializer):
    """Validates callback payload from pipeline-orchestrator-svc."""

    # Maximum allowed size for JSON fields (1 MB)
    MAX_JSON_SIZE = 1024 * 1024

    status = serializers.ChoiceField(
        choices=AnalysisJob.Status.choices,
        required=False,
    )
    progress = serializers.JSONField(required=False)
    result_data = serializers.JSONField(required=False)
    error_message = serializers.CharField(
        required=False, allow_blank=True, max_length=10000
    )
    resolved_manifest_id = serializers.SlugField(
        required=False,
        help_text=(
            "Pipeline ID resolved by intent routing "
            "(when job had no explicit manifest)"
        ),
    )

    def _validate_json_size(self, value, field_name):
        """Reject JSON payloads larger than MAX_JSON_SIZE."""
        import json

        serialized = json.dumps(value)
        if len(serialized.encode("utf-8")) > self.MAX_JSON_SIZE:
            raise serializers.ValidationError(
                f"{field_name} exceeds maximum size of 1 MB"
            )
        return value

    def validate_progress(self, value):
        """Validate progress JSON size."""
        return self._validate_json_size(value, "progress")

    def validate_result_data(self, value):
        """Validate result_data JSON size."""
        return self._validate_json_size(value, "result_data")


class TrendNotificationSerializer(serializers.ModelSerializer):
    """Serializer for TCIA push notifications."""

    class Meta:
        model = TrendNotification
        fields = [
            "id",
            "notification_type",
            "title",
            "body",
            "metadata",
            "is_read",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TrendNotificationCreateSerializer(serializers.Serializer):
    """Validates push notification payload from TCIA service."""

    notification_type = serializers.ChoiceField(
        choices=TrendNotification.NotificationType.choices,
        default=TrendNotification.NotificationType.OPPORTUNITY_ALERT,
    )
    title = serializers.CharField(max_length=255)
    body = serializers.CharField()
    metadata = serializers.JSONField(default=dict, required=False)
    tenant_id = serializers.CharField(max_length=100)
