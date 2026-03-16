"""
Serializers for the workspace app.

WorkflowListSerializer — lightweight list view.
WorkflowDetailSerializer — full detail with manifest + layout.
WorkflowCreateSerializer — create with manifest validation.
WorkflowUpdateSerializer — update manifest + layout.
WorkflowExecuteSerializer — execute with prompt.
WorkflowCloneSerializer — clone with new name.
WorkflowExportSerializer — sanitized export.
WorkflowImportSerializer — validated import.
SnapshotListSerializer — snapshot list with KPIs.
ChatLinkSerializer — link chat job to workspace.
AgentCatalogSerializer — agent metadata + health.
"""

import ipaddress
from urllib.parse import urlparse

from rest_framework import serializers

from brand_automator.validators import sanitize_text_input
from orchestration.serializers import PipelineManifestSerializer

from .models import ChatWorkspaceLink, UserWorkflow, WorkflowSnapshot

# Maximum number of agents per workflow (IG-08)
MAX_AGENT_COUNT = 20


class WorkflowListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (excludes layout_data, manifest)."""

    last_job_status = serializers.SerializerMethodField()

    class Meta:
        model = UserWorkflow
        fields = [
            "id",
            "workflow_id",
            "name",
            "description",
            "source",
            "is_favorite",
            "execution_count",
            "last_executed_at",
            "last_job_status",
            "created_at",
            "updated_at",
        ]

    def get_last_job_status(self, obj):
        """Get status of the most recent job for this workflow."""
        snapshot = obj.snapshots.select_related("job").first()
        if snapshot and snapshot.job:
            return snapshot.job.status
        return None


class WorkflowDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer with manifest_data and layout."""

    last_job_status = serializers.SerializerMethodField()
    last_job_id = serializers.SerializerMethodField()
    manifest_data = serializers.SerializerMethodField()
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)

    class Meta:
        model = UserWorkflow
        fields = [
            "id",
            "workflow_id",
            "name",
            "description",
            "manifest",
            "manifest_data",
            "layout_data",
            "source",
            "is_favorite",
            "execution_count",
            "last_executed_at",
            "last_job_status",
            "last_job_id",
            "created_by_email",
            "created_at",
            "updated_at",
        ]

    def get_last_job_status(self, obj):
        snapshot = obj.snapshots.select_related("job").first()
        if snapshot and snapshot.job:
            return snapshot.job.status
        return None

    def get_last_job_id(self, obj):
        """Return the job_id (UUID) of the most recent execution."""
        snapshot = obj.snapshots.select_related("job").first()
        if snapshot and snapshot.job:
            return str(snapshot.job.job_id)
        return None

    def get_manifest_data(self, obj):
        if obj.manifest:
            return obj.manifest.manifest_data
        return None


class WorkflowCreateSerializer(serializers.Serializer):
    """Serializer for creating a new workflow."""

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    manifest_data = serializers.JSONField()
    layout_data = serializers.JSONField(required=False, default=dict)

    def validate_name(self, value):
        """Sanitize workflow name (IG-07)."""
        return sanitize_text_input(value, max_length=200)

    def validate_manifest_data(self, value):
        """Reuse PipelineManifest validation for manifest_data."""
        validator = PipelineManifestSerializer()
        return validator.validate_manifest_data(value)

    def validate(self, attrs):
        """Check agent count cap (IG-08) and duplicate edges (IG-09)."""
        manifest_data = attrs.get("manifest_data", {})
        nodes = manifest_data.get("nodes", [])
        edges = manifest_data.get("edges", [])

        # IG-08: Agent count cap
        if len(nodes) > MAX_AGENT_COUNT:
            raise serializers.ValidationError(
                {
                    "manifest_data": (
                        f"Workflow cannot have more than " f"{MAX_AGENT_COUNT} agents."
                    )
                }
            )

        # IG-09: Duplicate edge prevention
        edge_set = set()
        for edge in edges:
            edge_tuple = tuple(edge)
            if edge_tuple in edge_set:
                raise serializers.ValidationError(
                    {"manifest_data": (f"Duplicate edge: {edge[0]} -> {edge[1]}")}
                )
            edge_set.add(edge_tuple)

        return attrs


class WorkflowUpdateSerializer(serializers.Serializer):
    """Serializer for updating a workflow."""

    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    manifest_data = serializers.JSONField(required=False)
    layout_data = serializers.JSONField(required=False)
    is_favorite = serializers.BooleanField(required=False)

    def validate_name(self, value):
        return sanitize_text_input(value, max_length=200)

    def validate_manifest_data(self, value):
        validator = PipelineManifestSerializer()
        return validator.validate_manifest_data(value)

    def validate(self, attrs):
        manifest_data = attrs.get("manifest_data")
        if manifest_data:
            nodes = manifest_data.get("nodes", [])
            edges = manifest_data.get("edges", [])

            if len(nodes) > MAX_AGENT_COUNT:
                raise serializers.ValidationError(
                    {
                        "manifest_data": (
                            f"Workflow cannot have more than "
                            f"{MAX_AGENT_COUNT} agents."
                        )
                    }
                )

            edge_set = set()
            for edge in edges:
                edge_tuple = tuple(edge)
                if edge_tuple in edge_set:
                    raise serializers.ValidationError(
                        {"manifest_data": (f"Duplicate edge: {edge[0]} -> {edge[1]}")}
                    )
                edge_set.add(edge_tuple)

        return attrs


class WorkflowExecuteSerializer(serializers.Serializer):
    """Serializer for executing a workflow."""

    input_prompt = serializers.CharField()
    input_context = serializers.JSONField(required=False, default=dict)

    def validate_input_prompt(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("input_prompt cannot be empty")
        return value.strip()


class WorkflowCloneSerializer(serializers.Serializer):
    """Serializer for cloning a workflow."""

    name = serializers.CharField(max_length=200)

    def validate_name(self, value):
        return sanitize_text_input(value, max_length=200)


class WorkflowExportSerializer(serializers.ModelSerializer):
    """Output-only serializer for workflow export (strips sensitive data)."""

    manifest_data = serializers.SerializerMethodField()

    class Meta:
        model = UserWorkflow
        fields = [
            "name",
            "description",
            "manifest_data",
            "layout_data",
            "source",
        ]

    def get_manifest_data(self, obj):
        """Return manifest_data with internal URLs replaced."""
        if not obj.manifest:
            return None
        data = obj.manifest.manifest_data.copy()
        nodes = data.get("nodes", [])
        sanitized_nodes = []
        for node in nodes:
            node_copy = node.copy()
            if node_copy.get("type") == "external" and "url" in node_copy:
                node_copy["url"] = "{{SERVICE_URL}}"
            sanitized_nodes.append(node_copy)
        data["nodes"] = sanitized_nodes
        return data


class WorkflowImportSerializer(serializers.Serializer):
    """Serializer for importing a workflow from JSON.

    Extends the base manifest validation to allow ``{{SERVICE_URL}}``
    placeholders (resolved in the service layer) while enforcing SSRF
    prevention for any non-placeholder URLs.
    """

    # Placeholder that the export serializer writes for external URLs
    SERVICE_URL_PLACEHOLDER = "{{SERVICE_URL}}"

    name = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    manifest_data = serializers.JSONField()
    layout_data = serializers.JSONField(required=False, default=dict)

    def validate_name(self, value):
        return sanitize_text_input(value, max_length=200)

    def validate_manifest_data(self, value):
        """Validate manifest structure, allowing SERVICE_URL placeholders.

        Temporarily swaps placeholders to a valid internal URL so the
        base PipelineManifestSerializer validation passes, then restores
        them.  Also applies SSRF checks on any real (non-placeholder) URLs.
        """
        import copy

        data = copy.deepcopy(value)

        # Track which nodes use placeholders and check real URLs for SSRF
        placeholder_indices = []
        for i, node in enumerate(data.get("nodes", [])):
            if node.get("type") != "external":
                continue
            url = node.get("url", "")

            if url == self.SERVICE_URL_PLACEHOLDER:
                # Swap with a known-safe URL for base validation
                node["url"] = "http://discovery-agent-svc:8020/v1/execute"
                placeholder_indices.append(i)
            else:
                # SSRF check on the actual URL
                self._validate_no_ssrf(node["id"], url)

        # Run standard manifest validation (structure, cycles, etc.)
        validator = PipelineManifestSerializer()
        validated = validator.validate_manifest_data(data)

        # Restore placeholders
        for idx in placeholder_indices:
            validated["nodes"][idx]["url"] = self.SERVICE_URL_PLACEHOLDER

        return validated

    @staticmethod
    def _validate_no_ssrf(node_id, url):
        """Reject URLs targeting private/internal networks (SSRF prevention)."""
        try:
            parsed = urlparse(url)
        except Exception:
            raise serializers.ValidationError(
                f"External node '{node_id}' has an invalid URL."
            )

        hostname = parsed.hostname or ""

        # Block private hostnames
        blocked_hostnames = {
            "localhost",
            "0.0.0.0",
            "[::]",
            "metadata.google.internal",
        }
        if hostname.lower() in blocked_hostnames:
            raise serializers.ValidationError(
                f"External node '{node_id}': URL targets a blocked hostname."
            )

        # Block private/reserved IP ranges
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise serializers.ValidationError(
                    f"External node '{node_id}': URL targets a private IP range."
                )
        except ValueError:
            # hostname is not an IP — that's fine
            pass

    def validate(self, attrs):
        manifest_data = attrs.get("manifest_data", {})
        nodes = manifest_data.get("nodes", [])
        if len(nodes) > MAX_AGENT_COUNT:
            raise serializers.ValidationError(
                {
                    "manifest_data": (
                        f"Workflow cannot have more than " f"{MAX_AGENT_COUNT} agents."
                    )
                }
            )
        return attrs


class SnapshotListSerializer(serializers.ModelSerializer):
    """Serializer for listing workflow snapshots."""

    job_id = serializers.UUIDField(source="job.job_id", read_only=True)
    job_status = serializers.CharField(source="job.status", read_only=True)
    duration_seconds = serializers.FloatField(
        source="job.duration_seconds", read_only=True
    )
    chat_session_id = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowSnapshot
        fields = [
            "id",
            "snapshot_id",
            "job_id",
            "job_status",
            "summary",
            "dashboard_data",
            "duration_seconds",
            "chat_session_id",
            "created_at",
        ]

    def get_chat_session_id(self, obj):
        """Return chat_session_id from the associated ChatWorkspaceLink, if any."""
        # Use prefetched reverse FK (from view's prefetch_related) to avoid N+1
        links = getattr(obj, "chatworkspacelink_set", None)
        if links is not None:
            # prefetch_related caches as a manager; .all() hits the cache
            cached = links.all()
            if cached:
                return cached[0].chat_session_id
            return None
        # Fallback if not prefetched
        link = ChatWorkspaceLink.objects.filter(snapshot=obj).first()
        return link.chat_session_id if link else None


class ChatLinkSerializer(serializers.Serializer):
    """Serializer for linking a chat job to a workspace workflow."""

    job_id = serializers.UUIDField()
    chat_session_id = serializers.CharField(max_length=100)


class AgentCatalogSerializer(serializers.Serializer):
    """Serializer for agent catalog entries."""

    id = serializers.CharField()
    name = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    type = serializers.ChoiceField(choices=["internal", "external"])
    url = serializers.CharField(required=False, allow_blank=True)
    handler = serializers.CharField(required=False, allow_blank=True)
    health = serializers.ChoiceField(
        choices=["healthy", "unhealthy", "unknown"],
        default="unknown",
    )
    icon = serializers.CharField(required=False, allow_blank=True)
