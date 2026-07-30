"""
Tests for the seed_metrics management command.

Regression coverage for a field-name mismatch that broke the command in
production: 10 brand-architecture records used "min_value"/"max_value" while
MetricDefinition defines "value_range_min"/"value_range_max". The 27th of 104
records raised FieldError mid-loop, so the first 26 rows committed and the
remaining 78 never seeded — and the failure was invisible because the Cloud
Run migration job wraps the call in
`|| echo 'seed_metrics failed - non-critical'`.
"""

import pytest

from django.core.management import call_command

from analytics.management.commands.seed_metrics import METRIC_DEFINITIONS
from analytics.models import MetricDefinition


def _model_field_names():
    return {f.name for f in MetricDefinition._meta.get_fields()}


@pytest.mark.unit
def test_every_definition_uses_only_real_model_fields():
    """Guards against the FieldError class of bug for all future records.

    A key that is not a MetricDefinition field makes update_or_create raise,
    so this must hold for every record — not just the ones we fixed.
    """
    valid = _model_field_names()
    offenders = {}

    for defn in METRIC_DEFINITIONS:
        unknown = sorted(k for k in defn if k not in valid)
        if unknown:
            offenders[defn.get("metric_name", "<unnamed>")] = unknown

    assert not offenders, f"definitions reference unknown model fields: {offenders}"


@pytest.mark.unit
def test_legacy_range_key_names_are_gone():
    """The exact keys that caused the production failure."""
    for defn in METRIC_DEFINITIONS:
        assert "min_value" not in defn, defn["metric_name"]
        assert "max_value" not in defn, defn["metric_name"]


@pytest.mark.unit
def test_no_definition_passes_none_to_a_not_null_column():
    """Second bug found by this suite: four optimization metrics set
    "higher_is_better": None to mean "neutral", but the column is NOT NULL,
    so seeding died with IntegrityError even after the field names were fixed.
    """
    not_null = {
        f.name
        for f in MetricDefinition._meta.get_fields()
        if hasattr(f, "null") and not f.null and not f.auto_created
    }
    offenders = {}

    for defn in METRIC_DEFINITIONS:
        nulls = sorted(k for k, v in defn.items() if v is None and k in not_null)
        if nulls:
            offenders[defn["metric_name"]] = nulls

    assert not offenders, f"None passed to NOT NULL columns: {offenders}"


@pytest.mark.unit
def test_definitions_have_unique_metric_names():
    """update_or_create keys on metric_name, so duplicates silently collapse."""
    names = [d["metric_name"] for d in METRIC_DEFINITIONS]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"duplicate metric_name values: {sorted(dupes)}"


@pytest.mark.django_db
def test_seed_metrics_creates_every_definition():
    """End-to-end: the command seeds all records, not a partial prefix."""
    call_command("seed_metrics")

    assert MetricDefinition.objects.count() == len(METRIC_DEFINITIONS)

    # The brand-architecture block is where seeding used to abort.
    architecture = MetricDefinition.objects.filter(category="brand_architecture")
    assert architecture.exists(), "brand_architecture metrics were not seeded"

    model_score = MetricDefinition.objects.get(metric_name="architecture_model_score")
    assert model_score.value_range_min == 0
    assert model_score.value_range_max == 100


@pytest.mark.django_db
def test_seed_metrics_is_idempotent():
    """Seeding twice updates in place rather than duplicating."""
    call_command("seed_metrics")
    first_count = MetricDefinition.objects.count()

    call_command("seed_metrics")

    assert MetricDefinition.objects.count() == first_count
