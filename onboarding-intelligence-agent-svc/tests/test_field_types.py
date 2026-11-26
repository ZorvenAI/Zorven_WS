"""J-03 — Field type metadata tests."""

from app.logic.field_types import (
    FIELD_TYPE_HINTS,
    KEY_FIELDS,
    WIZARD_PAGES,
    all_mapped_fields,
)


def test_all_mapped_fields_have_type_info():
    """Every field in WIZARD_PAGES has a type description."""
    mapped = all_mapped_fields()
    missing = mapped - set(FIELD_TYPE_HINTS)
    assert not missing, f"Fields without type hints: {missing}"


def test_key_fields_subset_of_mapped():
    """KEY_FIELDS must be a subset of all mapped fields."""
    mapped = all_mapped_fields()
    extra = KEY_FIELDS - mapped
    assert not extra, f"KEY_FIELDS not in WIZARD_PAGES: {extra}"


def test_wizard_pages_match_django():
    """Pages 1-4 exist with expected labels."""
    assert set(WIZARD_PAGES.keys()) == {1, 2, 3, 4}
    assert WIZARD_PAGES[1][0] == "Company Info"
    assert WIZARD_PAGES[2][0] == "Brand Voice"
    assert WIZARD_PAGES[3][0] == "Target Audience"
    assert WIZARD_PAGES[4][0] == "Assets & Market"


def test_field_count():
    """Every extraction target across the 4 pages.

    Django's field_map.py has three more on page 1 — signatory_email,
    billing_contact_email and registration_number. Those are collected in
    writing only and are deliberately not extraction targets here.
    """
    total = sum(len(fields) for _, fields in WIZARD_PAGES.values())
    # 17 + 12 + 7 + 6 = 42 fields
    assert total == 42


def test_written_only_contract_fields_are_not_extraction_targets():
    """A misheard email address must never reach the field links are sent to."""
    written_only = {"signatory_email", "billing_contact_email", "registration_number"}
    assert not written_only & all_mapped_fields()
    assert not written_only & set(FIELD_TYPE_HINTS)


def test_no_field_overlap_between_pages():
    """No field should appear on more than one page."""
    seen: set[str] = set()
    for _label, fields in WIZARD_PAGES.values():
        overlap = seen & fields
        assert not overlap, f"Overlapping fields: {overlap}"
        seen |= fields
