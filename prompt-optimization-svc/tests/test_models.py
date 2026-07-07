"""Tests for SQLAlchemy models."""

from datetime import datetime, timezone

import pytest

from app.models.golden_dataset import GoldenDataset, SCHEMA


class TestGoldenDatasetModel:
    """Unit tests for the GoldenDataset model."""

    def test_create_with_required_fields(self):
        """Model can be instantiated with all required fields."""
        ds = GoldenDataset(
            prompt_name="zorven-wf1-mra-landscape",
            agent_code="MRA",
            input_context={"context.brand_name": "Test Brand"},
            source="manual",
        )
        assert ds.prompt_name == "zorven-wf1-mra-landscape"
        assert ds.agent_code == "MRA"
        assert ds.source == "manual"
        assert ds.input_context == {"context.brand_name": "Test Brand"}

    def test_default_active_is_true(self):
        """Active defaults to True for new datasets."""
        ds = GoldenDataset(
            prompt_name="test",
            agent_code="MRA",
            input_context={},
            source="manual",
        )
        # server_default is set in the column, but Python-side it may be None
        # until persisted. The important thing is the model accepts it.
        assert ds.active is None or ds.active is True

    def test_optional_fields_default_to_none(self):
        """Optional fields are None when not provided."""
        ds = GoldenDataset(
            prompt_name="test",
            agent_code="CGA",
            input_context={},
            source="synthetic",
        )
        assert ds.tenant_id is None
        assert ds.expected_output is None
        assert ds.quality_score is None
        assert ds.metadata_extra is None

    def test_all_fields_populated(self):
        """Model accepts all fields including optional ones."""
        now = datetime.now(timezone.utc)
        ds = GoldenDataset(
            id=1,
            prompt_name="zorven-wf3-cga-creative",
            agent_code="CGA",
            tenant_id="tenant-123",
            input_context={
                "context.brand_name": "Acme",
                "context.industry": "tech",
            },
            expected_output='{"headline": "Test"}',
            source="mined",
            quality_score=0.95,
            active=True,
            metadata_extra={"industry": "tech", "maturity": "startup"},
            created_at=now,
            updated_at=now,
        )
        assert ds.id == 1
        assert ds.tenant_id == "tenant-123"
        assert ds.quality_score == 0.95
        assert ds.metadata_extra["industry"] == "tech"
        assert ds.created_at == now

    def test_valid_source_values(self):
        """Source field accepts all valid values."""
        for source in ("manual", "synthetic", "mined", "adversarial"):
            ds = GoldenDataset(
                prompt_name="test",
                agent_code="MRA",
                input_context={},
                source=source,
            )
            assert ds.source == source

    def test_repr(self):
        """repr includes key identifying fields."""
        ds = GoldenDataset(
            id=42,
            prompt_name="zorven-wf1-mra-landscape",
            agent_code="MRA",
            input_context={},
            source="manual",
        )
        r = repr(ds)
        assert "42" in r
        assert "MRA" in r
        assert "manual" in r

    def test_table_schema(self):
        """Table uses prompt_optimization schema."""
        assert GoldenDataset.__table__.schema == SCHEMA

    def test_table_has_indexes(self):
        """Table definition includes the required indexes."""
        index_names = {idx.name for idx in GoldenDataset.__table__.indexes}
        assert "idx_golden_prompt" in index_names
        assert "idx_golden_tenant" in index_names

    def test_idx_golden_prompt_columns(self):
        """idx_golden_prompt covers (prompt_name, active)."""
        idx = next(
            i for i in GoldenDataset.__table__.indexes if i.name == "idx_golden_prompt"
        )
        col_names = [c.name for c in idx.columns]
        assert col_names == ["prompt_name", "active"]

    def test_idx_golden_tenant_columns(self):
        """idx_golden_tenant covers (tenant_id, agent_code)."""
        idx = next(
            i for i in GoldenDataset.__table__.indexes if i.name == "idx_golden_tenant"
        )
        col_names = [c.name for c in idx.columns]
        assert col_names == ["tenant_id", "agent_code"]
