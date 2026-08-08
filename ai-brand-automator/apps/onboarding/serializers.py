"""Serializers for the session API (Design §10.2).

``status`` is accepted on PATCH but never assigned here — the viewset routes
it through ``services.session_state.transition`` so §9.4 is enforced in one
place. Letting the serializer write it would put a second, unvalidated path
to the same field, which is the shape of bug B-02's review caught on
``onboarding_session``.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.onboarding.models import FieldProvenance, OnboardingSession


class OnboardingSessionSerializer(serializers.ModelSerializer):
    """Read and write shape for a session.

    ``prompt_versions`` is read-only: the card is explicit that it is written
    server-side by L-03 only. It pins the POI resolution for the session
    (§17.2), so a client able to set it could change which prompt versions a
    meeting runs under — the exact thing that pinning exists to prevent.
    """

    legal_next_states = serializers.SerializerMethodField(
        help_text="Statuses reachable from the current one (§9.4)",
    )

    class Meta:
        model = OnboardingSession
        fields = [
            "id",
            "tenant",
            "company",
            "status",
            "escalated_from",
            "questionnaire",
            "created_by",
            "prompt_versions",
            "evidence_manifest_hash",
            "legal_next_states",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "created_by",
            "created_at",
            "updated_at",
            # Written server-side on escalation and cleared on resolution; a
            # client-supplied value would defeat the round trip §9.4 requires.
            "escalated_from",
            # L-03's, not a client's (§17.2).
            "prompt_versions",
            "legal_next_states",
        ]

    def get_legal_next_states(self, obj) -> list[str]:
        """Advertised so a caller does not have to hold §9.4 in its head.

        The Onboarding Interface drives this API without being trusted to
        know the rules; handing it the legal set turns "which button do I
        render" from a guess into a read.
        """
        from apps.onboarding import state

        return sorted(state.legal_targets(obj.status, obj.escalated_from))


class FieldProvenanceSerializer(serializers.ModelSerializer):
    """Read shape for the review page (§10.2).

    ``extracted_value`` is read-only here and everywhere else. The B-06 card
    calls preserving it "the single most important line in the endpoint":
    L-02's golden-dataset candidates compare what a reviewer decided against
    what the agent proposed, so an edit that overwrote the proposal would
    leave the flywheel with no signal at all.
    """

    wizard_page = serializers.SerializerMethodField()
    wizard_page_label = serializers.SerializerMethodField()

    class Meta:
        model = FieldProvenance
        fields = [
            "id",
            "session",
            "model_name",
            "field_name",
            "extracted_value",
            "final_value",
            "classification",
            "confidence",
            "source_recording",
            "source_span",
            "source_media",
            "status",
            "reviewed_by",
            "reviewed_at",
            "wizard_page",
            "wizard_page_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields  # the whole row; writes go through the actions

    def get_wizard_page(self, obj) -> int | None:
        from apps.onboarding.field_map import page_for

        return page_for(obj.field_name)

    def get_wizard_page_label(self, obj) -> str:
        from apps.onboarding.field_map import label_for, page_for

        return label_for(page_for(obj.field_name))


class ProvenanceEditSerializer(serializers.Serializer):
    """The body of ``POST /provenance/{id}/edit/``.

    Only ``final_value``: the reviewer says what the value should be, and the
    server decides everything else — status, reviewer, timestamp and the edit
    distance. Accepting ``extracted_value`` would hand a client the one field
    that must not move.
    """

    final_value = serializers.JSONField()
