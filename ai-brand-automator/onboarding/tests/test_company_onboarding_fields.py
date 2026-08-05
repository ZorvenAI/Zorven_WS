"""B-03 · the thirteen approved Company fields (AC-1, AC-2).

Lives in ``onboarding/tests/`` rather than the card's
``apps/companies/tests/`` because there is no ``apps/companies`` app —
``Company`` is a model of the ``onboarding`` app, and the tests sit beside
the code they cover.

Every serializer is exercised, not just one. ``CompanyViewSet`` routes create
to ``CompanyCreateSerializer``, update and partial_update to
``CompanyUpdateSerializer``, and everything else to ``CompanySerializer``, so
a test that only covered the read serializer would pass while PATCH — the
path FR-PROC-03 says J-02 writes through — silently dropped the fields.
"""

from __future__ import annotations

import pytest

from onboarding.models import Company
from onboarding.serializers import (
    ONBOARDING_FIELDS,
    CompanyCreateSerializer,
    CompanySerializer,
    CompanyUpdateSerializer,
)

pytestmark = [pytest.mark.django_db, pytest.mark.unit]

ALL_SERIALIZERS = [CompanySerializer, CompanyCreateSerializer, CompanyUpdateSerializer]

#: One valid value per field, in the declared shapes.
SAMPLE = {
    "competitors": [{"name": "Blue Tokai", "url": "https://example.com"}],
    "products_services": [{"name": "Single-origin beans", "price_range": "500-900"}],
    "marketing_budget_range": {
        "currency": "INR",
        "min": "50000.00",
        "max": "200000.00",
        "period": "monthly",
    },
    "digital_presence": {"instagram": "@kalyaniroasters", "website": "example.com"},
    "business_goals": "Open two more cafes in Pune within a year.",
    "founder_story": "Started on a single roaster in a garage in 2016.",
    "brand_asset_status": "Logo only, no guidelines",
    "legal_name": "Kalyani Coffee Roasters Pvt Ltd",
    "trademark_status": "Pending",
    "customer_proof": [{"type": "testimonial", "text": "Best filter coffee in town."}],
    "sales_channels": [{"channel": "retail", "notes": "Two outlets"}],
    "audience_languages": ["en-IN", "mr-IN"],
    "decision_maker": "Asha Kalyani, founder",
}


def make_company(**kwargs) -> Company:
    defaults = {"name": "Kalyani Roasters", "industry": "Food & Beverage"}
    defaults.update(kwargs)
    return Company.objects.create(**defaults)


# ── AC-1 · all thirteen exist and are optional ───────────────────────


def test_all_thirteen_fields_exist_on_the_model():
    company = make_company()
    for field in ONBOARDING_FIELDS:
        assert hasattr(company, field), field
    assert len(ONBOARDING_FIELDS) == 13


def test_every_field_is_nullable_and_defaults_empty():
    """A company created the old way must be unaffected (NFR-COMPAT)."""
    company = make_company()
    company.refresh_from_db()
    for field in ONBOARDING_FIELDS:
        assert getattr(company, field) is None, field


@pytest.mark.parametrize("serializer_class", ALL_SERIALIZERS)
def test_every_field_is_optional_at_the_serializer_layer(serializer_class):
    fields = serializer_class().fields
    for name in ONBOARDING_FIELDS:
        assert name in fields, f"{serializer_class.__name__} is missing {name}"
        assert not fields[name].required, f"{name} is required — AC-1 says optional"


# ── AC-2 · the serializers round-trip the new fields ─────────────────


def test_new_fields_roundtrip():
    """The card's named case, across create, update and read."""
    create = CompanyCreateSerializer(data={"name": "Kalyani Roasters", **SAMPLE})
    assert create.is_valid(), create.errors
    company = create.save()

    for field, value in SAMPLE.items():
        assert getattr(company, field) is not None, field

    read = CompanySerializer(company).data
    assert read["legal_name"] == SAMPLE["legal_name"]
    assert read["audience_languages"] == ["en-IN", "mr-IN"]
    assert read["marketing_budget_range"]["currency"] == "INR"

    update = CompanyUpdateSerializer(
        company,
        data={"decision_maker": "Ravi Kalyani, co-founder"},
        partial=True,
    )
    assert update.is_valid(), update.errors
    updated = update.save()
    assert updated.decision_maker == "Ravi Kalyani, co-founder"
    # A partial update must not clear the others.
    assert updated.legal_name == SAMPLE["legal_name"]


def test_payload_without_new_fields():
    """The card's other named case: existing clients are unaffected."""
    create = CompanyCreateSerializer(
        data={"name": "Legacy Co", "industry": "Retail", "brand_voice": "friendly"}
    )
    assert create.is_valid(), create.errors
    company = create.save()

    for field in ONBOARDING_FIELDS:
        assert getattr(company, field) is None, field


def test_a_patch_that_touches_nothing_new_leaves_the_new_fields_alone():
    company = make_company(**{k: SAMPLE[k] for k in ("legal_name", "business_goals")})
    serializer = CompanyUpdateSerializer(
        company, data={"tagline": "Roasted in Pune"}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()

    assert updated.tagline == "Roasted in Pune"
    assert updated.legal_name == SAMPLE["legal_name"]
    assert updated.business_goals == SAMPLE["business_goals"]


# ── Declared shapes · "whatever the LLM emitted" is not a contract ───


@pytest.mark.parametrize("serializer_class", ALL_SERIALIZERS)
def test_shapes_are_enforced_by_every_serializer(serializer_class):
    """Validating in only one would let the PATCH path store any shape."""
    serializer = serializer_class(
        data={"name": "Shape Test", "competitors": [{"url": "https://example.com"}]}
    )
    assert not serializer.is_valid()
    assert "competitors" in serializer.errors


@pytest.mark.parametrize(
    "field,bad",
    [
        ("competitors", [{"url": "https://x.com"}]),  # name missing
        ("competitors", {"name": "not a list"}),
        ("products_services", [{"description": "no name"}]),
        ("marketing_budget_range", {"min": 100}),  # currency missing
        ("marketing_budget_range", {"currency": "inr", "min": 1}),  # not upper
        ("marketing_budget_range", {"currency": "USD", "min": 900, "max": 100}),
        ("digital_presence", ["not", "an", "object"]),
        ("customer_proof", [{"type": "rumour", "text": "hearsay"}]),
        ("sales_channels", [{"channel": "carrier_pigeon"}]),
        ("audience_languages", [""]),
        ("audience_languages", "en-IN"),  # not a list
    ],
)
def test_malformed_shapes_are_refused(field, bad):
    serializer = CompanyCreateSerializer(data={"name": "Shape Test", field: bad})
    assert not serializer.is_valid(), f"{field}={bad!r} was accepted"
    assert field in serializer.errors


def test_the_budget_supports_more_than_one_currency():
    """The reason this is a numeric range and not a band enum."""
    for currency, low in (("INR", "50000.00"), ("USD", "600.00"), ("EUR", "550.00")):
        serializer = CompanyCreateSerializer(
            data={
                "name": f"Co {currency}",
                "marketing_budget_range": {"currency": currency, "min": low},
            }
        )
        assert serializer.is_valid(), serializer.errors
        assert serializer.save().marketing_budget_range["currency"] == currency


def test_an_open_ended_top_band_is_allowed():
    """ "Over 100k" has no max; requiring one would force a fake ceiling."""
    serializer = CompanyCreateSerializer(
        data={
            "name": "Big Spender",
            "marketing_budget_range": {"currency": "USD", "min": "100000.00"},
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert "max" not in serializer.save().marketing_budget_range


def test_period_defaults_are_not_invented_on_the_model():
    """The serializer declares a default; the column stores what was sent."""
    serializer = CompanyCreateSerializer(
        data={
            "name": "Quarterly Co",
            "marketing_budget_range": {
                "currency": "GBP",
                "min": "1000.00",
                "period": "quarterly",
            },
        }
    )
    assert serializer.is_valid(), serializer.errors
    assert serializer.save().marketing_budget_range["period"] == "quarterly"


# ── AC-1 · additive at the database level (NFR-COMPAT) ───────────────


@pytest.mark.django_db(transaction=True)
def test_all_thirteen_columns_are_nullable_in_the_database():
    """A column added NOT NULL without a default is the migration that
    passes on an empty test database and fails on a populated one."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_name = 'onboarding_company' AND column_name IN %s",
            [tuple(ONBOARDING_FIELDS)],
        )
        columns = dict(cursor.fetchall())

    assert set(columns) == set(ONBOARDING_FIELDS), sorted(
        set(ONBOARDING_FIELDS) - set(columns)
    )
    for name, nullable in columns.items():
        assert nullable == "YES", f"{name} is NOT NULL — existing rows would fail"


@pytest.mark.django_db(transaction=True)
def test_a_company_written_the_old_way_still_inserts():
    """The pre-B-03 insert, run verbatim against the new schema."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO onboarding_company "
            "(name, description, industry, target_audience, core_problem, "
            " website, address, city, state_province, postal_code, country, "
            " demographics, psychographics, pain_points, desired_outcomes, "
            " brand_voice, vision_statement, mission_statement, values, "
            " positioning_statement, tagline, value_proposition, "
            " elevator_pitch, color_palette_desc, font_recommendations, "
            " messaging_guide, created_at, updated_at) "
            "VALUES ('Legacy Co', '', '', '', '', '', '', '', '', '', '', "
            "'', '', '', '', '', '', '', '', '', '', '', '', '', '', '', "
            "NOW(), NOW()) RETURNING legal_name, competitors, decision_maker",
            [],
        )
        row = cursor.fetchone()

    assert row == (None, None, None), f"new columns not defaulted null: {row}"


# ── PR #542 review ───────────────────────────────────────────────────


def test_an_unknown_currency_code_is_refused():
    """A three-letter regex accepts "AAA", which is not a currency.

    The PR claimed ISO 4217 validation while only checking the shape. A
    garbage code stored by extraction is unrecoverable downstream.
    """
    serializer = CompanyCreateSerializer(
        data={
            "name": "Fake Money Co",
            "marketing_budget_range": {"currency": "AAA", "min": "100.00"},
        }
    )
    assert not serializer.is_valid()
    assert "marketing_budget_range" in serializer.errors


@pytest.mark.parametrize("code", ["INR", "USD", "EUR", "GBP", "JPY", "AED", "ZAR"])
def test_real_currency_codes_are_accepted(code):
    """The list must not reject currencies a customer actually uses."""
    serializer = CompanyCreateSerializer(
        data={
            "name": f"Co {code}",
            "marketing_budget_range": {"currency": code, "min": "100.00"},
        }
    )
    assert serializer.is_valid(), serializer.errors


def test_an_unlisted_platform_is_kept():
    """Unknown platforms pass through, as DigitalPresenceSerializer claims.

    Two things make this work, and both are easy to "clean up" by accident:
    DRF ignores undeclared keys rather than rejecting them, and
    _validate_object returns the caller's dict rather than validated_data.
    Returning validated_data would silently drop the platform — a reviewer
    read the code as doing exactly that, so it is pinned here.
    """
    serializer = CompanyCreateSerializer(
        data={
            "name": "Fediverse Co",
            "digital_presence": {"instagram": "@known", "mastodon": "@unlisted"},
        }
    )
    assert serializer.is_valid(), serializer.errors
    stored = serializer.save().digital_presence

    assert stored["instagram"] == "@known"
    assert stored["mastodon"] == "@unlisted", "an unlisted platform was dropped"


def test_a_declared_platform_is_still_type_checked():
    """Tolerating unknown keys must not disable validation of known ones."""
    serializer = CompanyCreateSerializer(
        data={"name": "Bad Shape Co", "digital_presence": {"instagram": {"a": 1}}}
    )
    assert not serializer.is_valid()
    assert "digital_presence" in serializer.errors
