"""Serializers for the session API (Design §10.2).

``status`` is accepted on PATCH but never assigned here — the viewset routes
it through ``services.session_state.transition`` so §9.4 is enforced in one
place. Letting the serializer write it would put a second, unvalidated path
to the same field, which is the shape of bug B-02's review caught on
``onboarding_session``.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.onboarding.models import (
    ConsentRecord,
    FieldProvenance,
    MeetingRecording,
    OnboardingSession,
)


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
    consent = serializers.SerializerMethodField(
        help_text="Consent state for this session (AC-2); granted: false when none",
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
            "consent",
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
            "consent",
        ]

    def get_legal_next_states(self, obj) -> list[str]:
        """Advertised so a caller does not have to hold §9.4 in its head.

        The Onboarding Interface drives this API without being trusted to
        know the rules; handing it the legal set turns "which button do I
        render" from a guess into a read.
        """
        from apps.onboarding import state

        return sorted(state.legal_targets(obj.status, obj.escalated_from))

    def get_consent(self, obj) -> dict:
        """Consent state for this session, never inherited (AC-2, AC-4).

        Consent attaches to the specific conversation being recorded, not to
        the customer relationship — the card calls AC-4 "the one people get
        wrong". Because the FK is to *session*, a new session simply has no
        consent row and reports granted: false. There is no inheritance to
        suppress; the absence is structural.
        """
        prefetched = getattr(obj, "active_consents", None)
        if prefetched is not None:
            # The list endpoint attaches this, so N sessions cost one query
            # rather than N. Falling back below keeps the serializer correct
            # when it is used without the prefetch.
            record = prefetched[0] if prefetched else None
        else:
            record = (
                obj.consent_records.filter(revoked_at__isnull=True)
                .order_by("-granted_at")
                .first()
            )

        if record is None:
            return {
                "granted": False,
                "granted_at": None,
                "method": None,
                "scope": None,
            }
        return {
            "granted": True,
            "granted_at": record.granted_at,
            "method": record.method,
            "scope": record.scope,
        }


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


class ConsentScopeSerializer(serializers.Serializer):
    """The v1 shape of ``ConsentRecord.scope``.

    The technical note asks for a declared shape now, because the column is
    JSON precisely so it can grow — audio, transcript, captured media,
    retention period — without a migration. Declaring it here means the growth
    is deliberate rather than whatever a caller happened to send.

    Every key is optional with a default, so an operator who ticks nothing
    still produces a record that says what was consented to.
    """

    audio = serializers.BooleanField(default=True)
    transcript = serializers.BooleanField(default=True)
    captured_media = serializers.BooleanField(default=True)
    retention_days = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=3650,
        help_text="Tenant retention window for this recording; M-03 erases on it",
    )


class ConsentRecordSerializer(serializers.ModelSerializer):
    """Read and write shape for consent (§10.2, IG-08).

    ``granted_at`` and ``granted_by`` are read-only. FR-REC-01 is explicit
    that the timestamp is server-set, and a client-chosen consent time is the
    single field an incident would turn on — so it is not accepted even to be
    ignored politely.
    """

    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = ConsentRecord
        fields = [
            "id",
            "session",
            "subject_name",
            "granted_by",
            "method",
            "scope",
            "granted_at",
            "revoked_at",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "session",
            # Server-set (FR-REC-01). A client-supplied value is discarded.
            "granted_by",
            "granted_at",
            # Set by the revoke action, never by a body.
            "revoked_at",
            "is_active",
        ]

    def validate_scope(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("scope must be an object.")
        nested = ConsentScopeSerializer(data=value)
        nested.is_valid(raise_exception=True)
        # Merged rather than either alone. Returning ``value`` preserved
        # unlisted keys but silently dropped the declared defaults, so a
        # caller who ticked nothing stored ``{}`` — a record that does not say
        # what was consented to, which is the opposite of the point. Returning
        # ``validated_data`` alone would apply the defaults but discard the
        # growth the JSON column exists for.
        #
        # Unlisted keys first, then the validated known keys on top: the
        # latter carry both the defaults and any coercion.
        return {**value, **nested.validated_data}


class SessionConsentStateSerializer(serializers.Serializer):
    """The ``consent`` object on a session read (AC-2).

    A flat ``granted: false`` rather than a null, so the frontend renders a
    state rather than checking for absence — and so "no consent" and "consent
    we failed to load" cannot look alike.
    """

    granted = serializers.BooleanField()
    granted_at = serializers.DateTimeField(allow_null=True)
    method = serializers.CharField(allow_null=True)
    scope = serializers.JSONField(allow_null=True)


class MeetingRecordingSerializer(serializers.ModelSerializer):
    """The library row (AC-3, FR-LIB-01).

    ``has_summary`` rather than the summary blob: AC-3 asks for "summary
    presence", and the library lists rows rather than rendering them. Sending
    the whole summary for every row would make a long meeting's list heavy for
    a boolean's worth of information.
    """

    has_summary = serializers.SerializerMethodField()
    has_transcript = serializers.SerializerMethodField()

    class Meta:
        model = MeetingRecording
        fields = [
            "id",
            "session",
            "modality",
            "status",
            "duration_s",
            "audio_asset",
            # transcript_gcs_path is deliberately absent. It is an internal
            # bucket path, and FR-LIB-01 says media is served "only through
            # short-lived signed URLs minted per request" — handing out the
            # raw path leaks infrastructure detail and routes around the
            # design before it exists. The library only needs to know whether
            # a transcript is there yet, which is the same reasoning that
            # makes summary a presence flag.
            "has_transcript",
            "has_summary",
            "started_at",
            "stopped_at",
        ]
        read_only_fields = fields  # writes go through open and stop

    def get_has_summary(self, obj) -> bool:
        return bool(obj.summary)

    def get_has_transcript(self, obj) -> bool:
        return bool(obj.transcript_gcs_path)


class RecordingStopSerializer(serializers.Serializer):
    """The body of ``POST /recordings/{id}/stop/``.

    ``duration_s`` is optional and comes from the client's MediaRecorder,
    which *is* the audio timeline FR-REC-02 requires — "elapsed time derives
    from the audio timeline, not wall-clock, so a stalled tab does not report
    phantom duration", to under a second over 45 minutes.

    The server deliberately does not compute wall-clock between open and stop.
    A paused upload or a slow network would make that number wrong, and a
    wrong duration shown confidently in the library is worse than none.
    F-03 corrects it from the stored asset once uploads exist.
    """

    duration_s = serializers.IntegerField(required=False, min_value=0, allow_null=True)
