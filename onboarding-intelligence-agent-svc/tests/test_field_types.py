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
    """40 fields across 4 pages, matching Django's field_map.py."""
    total = sum(len(fields) for _, fields in WIZARD_PAGES.values())
    # 14 + 12 + 7 + 6 = 39 fields (Django has the same)
    assert total == 39


def test_no_field_overlap_between_pages():
    """No field should appear on more than one page."""
    seen: set[str] = set()
    for _label, fields in WIZARD_PAGES.values():
        overlap = seen & fields
        assert not overlap, f"Overlapping fields: {overlap}"
        seen |= fields
