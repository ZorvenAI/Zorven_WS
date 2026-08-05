"""B-03 AC-3 — the wizard and the PDF are deliberately *not* changed yet.

K-03 extends the wizard forms and K-05 extends the PDF. This story lands only
the schema, so the decoupling has to be visible rather than assumed: an
absent change is indistinguishable from a forgotten one unless something
asserts it.

Note this contradicts Design §10.1, which says "serializers, the wizard forms
and the onboarding PDF generator are updated in the same story so the fields
are not orphaned." The backlog is newer (v2.1), names the successor stories,
and gives the reason — landing the schema early lets Epic J proceed while
frontend work queues. The backlog wins; §10.1 needs correcting.

The PDF is asserted through ``build_onboarding_pdf``, extracted from the view
in this story precisely so the field list can be checked without GCS. Driving
the upload path instead would fail on absent credentials and prove nothing
about the fields.
"""

from __future__ import annotations

import re
import zlib

import pytest

from onboarding.models import Company
from onboarding.serializers import ONBOARDING_FIELDS
from onboarding.views import build_onboarding_pdf

pytestmark = [pytest.mark.django_db, pytest.mark.unit]

#: The labels the onboarding PDF emitted before B-03, in order. Committed as
#: the snapshot: K-05 will change this list deliberately, and until then any
#: diff means a field leaked into the PDF ahead of its story.
PDF_LABELS_BEFORE_B03 = [
    "Brand Onboarding Summary",
    "Company Information",
    "Company Name",
    "Industry",
    "Description",
    "Core Problem",
    "Website",
    "Physical Address",
    "Target Audience",
    "Primary Audience",
    "Demographics",
    "Psychographics",
    "Pain Points",
    "Desired Outcomes",
    "Brand Details",
    "Brand Voice",
    "Vision Statement",
    "Mission Statement",
    "Core Values",
    "Positioning Statement",
    "Tagline",
    "Value Proposition",
    "Elevator Pitch",
    "Brand Identity",
    "Color Palette",
    "Font Recommendations",
    "Messaging Guide",
]


def make_company() -> Company:
    """A company with every B-03 field populated.

    Populated on purpose: if the PDF had started rendering them, a filled
    company is what would reveal it. An empty one would pass either way.
    """
    return Company.objects.create(
        # Every pre-B-03 field, because the generator skips a label whose
        # value is empty — an under-filled fixture would silently shrink the
        # snapshot and hide a removal.
        name="Kalyani Roasters",
        industry="Food & Beverage",
        description="Specialty coffee roaster",
        core_problem="Hard to find fresh local beans",
        website="https://example.com",
        address="12 FC Road",
        city="Pune",
        state_province="Maharashtra",
        postal_code="411004",
        country="India",
        target_audience="Urban professionals",
        demographics="25-45, urban",
        psychographics="Values provenance",
        pain_points="Stale supermarket coffee",
        desired_outcomes="A reliable daily cup",
        brand_voice="warm",
        vision_statement="Every home brews well",
        mission_statement="Roast fresh, sell close",
        values="Craft, honesty",
        positioning_statement="The roaster next door",
        tagline="Roasted in Pune",
        value_proposition="Fresh beans within days of roast",
        elevator_pitch="We roast to order for Pune homes",
        color_palette_desc="Earth tones",
        font_recommendations="Humanist sans",
        messaging_guide="Warm, never precious",
        legal_name="Kalyani Coffee Roasters Pvt Ltd",
        trademark_status="Pending",
        decision_maker="Asha Kalyani, founder",
        business_goals="Open two more cafes in Pune",
        founder_story="Started on a single roaster in a garage",
        brand_asset_status="Logo only",
        competitors=[{"name": "Blue Tokai"}],
        products_services=[{"name": "Single-origin beans"}],
        marketing_budget_range={"currency": "INR", "min": "50000.00"},
        digital_presence={"instagram": "@kalyaniroasters"},
        customer_proof=[{"type": "testimonial", "text": "Excellent"}],
        sales_channels=[{"channel": "retail"}],
        audience_languages=["en-IN", "mr-IN"],
    )


def pdf_text(company: Company) -> str:
    """Readable text out of the PDF bytes.

    fpdf2 Flate-compresses its content streams, so the text operators have to
    be inflated first. The first version of this helper did not, and returned
    an empty string — which made every "this value must not appear" assertion
    below pass against an empty haystack. Hence the guard at the end: a text
    extraction that finds nothing is a broken test, not a clean result.
    """
    raw = build_onboarding_pdf(company)

    chunks: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        try:
            chunks.append(zlib.decompress(match.group(1)))
        except zlib.error:
            chunks.append(match.group(1))  # an uncompressed stream

    blob = b"\n".join(chunks).decode("latin-1", errors="ignore")
    text = " ".join(re.findall(r"\((.*?)\)\s*Tj", blob))

    assert text.strip(), (
        "no text recovered from the PDF — the extractor is broken, and every "
        "negative assertion in this file would pass vacuously"
    )
    return text


def test_pdf_unchanged_by_b03():
    """The card's named case: the PDF field list has not moved."""
    text = pdf_text(make_company())

    for label in PDF_LABELS_BEFORE_B03:
        assert label in text, f"the PDF lost the label {label!r}"


def test_no_b03_field_value_leaked_into_the_pdf():
    """The stronger half: the *values* must not appear either.

    Checking only labels would miss a field rendered without a heading.
    """
    text = pdf_text(make_company())

    for leaked in (
        "Kalyani Coffee Roasters Pvt Ltd",  # legal_name
        "Asha Kalyani, founder",  # decision_maker
        "Blue Tokai",  # competitors
        "@kalyaniroasters",  # digital_presence
        "Open two more cafes in Pune",  # business_goals
        "single roaster in a garage",  # founder_story
    ):
        assert leaked not in text, f"a B-03 value reached the PDF: {leaked!r}"


def test_no_b03_field_label_leaked_into_the_pdf():
    # Rendered once, not once per field: the PDF does not change between
    # iterations, and thirteen renders cost thirteen times as much.
    text = pdf_text(make_company())
    for field in ONBOARDING_FIELDS:
        label = field.replace("_", " ").title()
        assert label not in text, f"{label!r} reached the PDF"


def test_the_pdf_still_renders_and_is_a_pdf():
    """The extraction in this story must not have broken the generator."""
    data = build_onboarding_pdf(make_company())
    assert data.startswith(b"%PDF"), "not a PDF"
    assert len(data) > 1000, "suspiciously small"


# ── The wizard half of AC-3 ──────────────────────────────────────────


def test_the_wizard_create_payload_is_unchanged():
    """The wizard posts step 1 through CompanyCreateSerializer.

    B-03 widens what that serializer *accepts*; AC-3 is that what the wizard
    *sends* is unchanged and still succeeds. Asserted here rather than in the
    frontend suite because this is the contract the wizard depends on.
    """
    from onboarding.serializers import CompanyCreateSerializer

    wizard_step_1 = {
        "name": "Kalyani Roasters",
        "description": "Specialty coffee roaster",
        "industry": "Food & Beverage",
        "core_problem": "Hard to find fresh local beans",
        "website": "https://example.com",
        "city": "Pune",
        "country": "India",
    }
    serializer = CompanyCreateSerializer(data=wizard_step_1)
    assert serializer.is_valid(), serializer.errors

    company = serializer.save()
    for field in ONBOARDING_FIELDS:
        assert getattr(company, field) is None, f"{field} was set by the wizard"
