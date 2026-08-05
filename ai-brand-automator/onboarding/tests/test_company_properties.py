"""B-03 property tests — AC-2 generalised past the two named examples.

The example tests check the payloads we thought of: all thirteen fields, and
none of them. AC-2's actual claim is about *any* payload, and the interesting
failures live in between — one field set, a field set to null, the same field
patched twice.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from onboarding.models import Company
from onboarding.serializers import (
    ONBOARDING_FIELDS,
    CompanyCreateSerializer,
    CompanyUpdateSerializer,
)

pytestmark = [pytest.mark.django_db, pytest.mark.property]

#: Fields that take plain text, so a subset can be generated freely. The
#: JSON-typed ones have declared shapes and are covered by example tests.
TEXT_FIELDS = [
    "business_goals",
    "founder_story",
    "brand_asset_status",
    "legal_name",
    "trademark_status",
    "decision_maker",
]

db_settings = settings(
    max_examples=20,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


@given(chosen=st.lists(st.sampled_from(TEXT_FIELDS), unique=True))
@db_settings
def test_any_subset_of_fields_round_trips(chosen):
    """Any subset, including the empty one, creates and reads back."""
    payload = {"name": "Subset Co"}
    payload.update({field: f"value for {field}" for field in chosen})

    serializer = CompanyCreateSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
    company = serializer.save()

    for field in TEXT_FIELDS:
        expected = f"value for {field}" if field in chosen else None
        assert getattr(company, field) == expected, field


@given(chosen=st.lists(st.sampled_from(TEXT_FIELDS), unique=True, min_size=1))
@db_settings
def test_a_partial_patch_never_disturbs_a_field_it_omits(chosen):
    """The invariant J-02 depends on: additive PATCH semantics (FR-PROC-03).

    Extraction writes page by page, so a later page must not silently clear
    what an earlier one established.
    """
    company = Company.objects.create(
        name="Patch Co", **{field: f"original {field}" for field in TEXT_FIELDS}
    )

    serializer = CompanyUpdateSerializer(
        company,
        data={field: f"updated {field}" for field in chosen},
        partial=True,
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()

    for field in TEXT_FIELDS:
        prefix = "updated" if field in chosen else "original"
        assert getattr(updated, field) == f"{prefix} {field}", field


@given(field=st.sampled_from(ONBOARDING_FIELDS))
@db_settings
def test_every_field_accepts_an_explicit_null(field):
    """Extraction that finds nothing must be able to say so.

    Refusing null would force it to invent a value or omit the key, and the
    two mean different things to a reviewer.
    """
    company = Company.objects.create(name="Null Co")

    serializer = CompanyUpdateSerializer(company, data={field: None}, partial=True)
    assert serializer.is_valid(), (field, serializer.errors)
    assert getattr(serializer.save(), field) is None
