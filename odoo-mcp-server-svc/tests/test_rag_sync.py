"""Tests for Odoo-RAG sync — indexes Odoo records into the RAG knowledge store."""

import logging
from unittest.mock import AsyncMock

import pytest

from app.rag.sync import INDEXABLE_MODELS, OdooRAGSync, make_doc_id

# ── Fixtures ──


@pytest.fixture
def mock_rag_client() -> AsyncMock:
    """Mock RAG client with standard upload response."""
    client = AsyncMock()
    client.upload_document.return_value = {"doc_id": "doc-123", "status": "indexed"}
    client.delete_document.return_value = {"status": "completed"}
    return client


@pytest.fixture
def mock_rpc_client() -> AsyncMock:
    """Mock Odoo RPC client with sample records."""
    client = AsyncMock()
    client.search_read.return_value = [
        {
            "id": 42,
            "name": "Acme Corp",
            "email": "info@acme.com",
            "phone": "+1-555-0100",
            "is_company": True,
        }
    ]
    return client


@pytest.fixture
def sync(mock_rag_client: AsyncMock, mock_rpc_client: AsyncMock) -> OdooRAGSync:
    """OdooRAGSync with mocked clients."""
    return OdooRAGSync(rag_client=mock_rag_client, rpc_client=mock_rpc_client)


@pytest.fixture
def sync_no_clients() -> OdooRAGSync:
    """OdooRAGSync without any clients."""
    return OdooRAGSync()


# ── make_doc_id ──


class TestMakeDocId:
    """Test deterministic document ID generation."""

    def test_basic_model(self) -> None:
        assert make_doc_id("sale.order", 42) == "odoo-sale_order-42"

    def test_partner_model(self) -> None:
        assert make_doc_id("res.partner", 1) == "odoo-res_partner-1"

    def test_product_template(self) -> None:
        assert make_doc_id("product.template", 99) == "odoo-product_template-99"


# ── INDEXABLE_MODELS ──


class TestIndexableModels:
    """Test that INDEXABLE_MODELS is correctly populated."""

    def test_contains_expected_models(self) -> None:
        expected = [
            "product.template",
            "product.product",
            "sale.order",
            "purchase.order",
            "account.move",
            "hr.employee",
            "project.project",
            "crm.lead",
            "res.partner",
        ]
        for model in expected:
            assert model in INDEXABLE_MODELS

    def test_has_9_models(self) -> None:
        assert len(INDEXABLE_MODELS) == 9

    def test_no_duplicates(self) -> None:
        assert len(INDEXABLE_MODELS) == len(set(INDEXABLE_MODELS))


# ── Constructor tests ──


class TestOdooRAGSyncInit:
    """Test OdooRAGSync initialization."""

    def test_init_with_both_clients(
        self, mock_rag_client: AsyncMock, mock_rpc_client: AsyncMock
    ) -> None:
        s = OdooRAGSync(rag_client=mock_rag_client, rpc_client=mock_rpc_client)
        assert s.rag_client is mock_rag_client
        assert s.rpc_client is mock_rpc_client

    def test_init_defaults_to_none(self) -> None:
        s = OdooRAGSync()
        assert s.rag_client is None
        assert s.rpc_client is None


# ── sync_record ──


class TestSyncRecord:
    """Test syncing a single Odoo record to the RAG store."""

    async def test_syncs_record_successfully(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Successfully syncs an indexable record."""
        result = await sync.sync_record("res.partner", 42, "tenant-1")

        assert result["synced"] is True
        assert result["model"] == "res.partner"
        assert result["record_id"] == 42
        assert result["doc_id"] == "odoo-res_partner-42"
        mock_rpc_client.search_read.assert_awaited_once_with(
            "res.partner", [["id", "=", 42]], limit=1
        )
        mock_rag_client.upload_document.assert_awaited_once()

    async def test_upload_receives_correct_metadata(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Upload document receives correct metadata dict."""
        await sync.sync_record("res.partner", 42, "tenant-1")

        call_kwargs = mock_rag_client.upload_document.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert metadata["source"] == "odoo"
        assert metadata["model"] == "res.partner"
        assert metadata["record_id"] == 42
        assert metadata["tenant_id"] == "tenant-1"
        assert metadata["name"] == "Acme Corp"

    async def test_upload_receives_deterministic_doc_id(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Upload receives deterministic doc_id."""
        await sync.sync_record("res.partner", 42, "tenant-1")

        call_kwargs = mock_rag_client.upload_document.call_args.kwargs
        assert call_kwargs["doc_id"] == "odoo-res_partner-42"

    async def test_upload_receives_correct_tenant_id(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Upload document passes tenant_id correctly."""
        await sync.sync_record("res.partner", 42, "acme-corp")

        call_kwargs = mock_rag_client.upload_document.call_args.kwargs
        assert call_kwargs["tenant_id"] == "acme-corp"

    async def test_error_when_no_clients(self, sync_no_clients: OdooRAGSync) -> None:
        """Returns error when RAG or RPC client is not available."""
        result = await sync_no_clients.sync_record("res.partner", 42)

        assert "error" in result
        assert "not available" in result["error"]

    async def test_error_for_non_indexable_model(self, sync: OdooRAGSync) -> None:
        """Returns error when model is not in INDEXABLE_MODELS."""
        result = await sync.sync_record("ir.config_parameter", 1)

        assert "error" in result
        assert "not indexable" in result["error"]

    async def test_error_when_record_not_found(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns error when Odoo record does not exist."""
        mock_rpc_client.search_read.return_value = []

        result = await sync.sync_record("res.partner", 9999)

        assert "error" in result
        assert "not found" in result["error"]

    async def test_handles_rpc_exception(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns error dict when RPC call fails."""
        mock_rpc_client.search_read.side_effect = Exception("RPC timeout")

        result = await sync.sync_record("res.partner", 42)

        assert "error" in result
        assert "RPC timeout" in result["error"]

    async def test_handles_rag_upload_exception(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Returns error dict when RAG upload fails."""
        mock_rag_client.upload_document.side_effect = Exception("Upload failed")

        result = await sync.sync_record("res.partner", 42)

        assert "error" in result
        assert "Upload failed" in result["error"]

    async def test_default_tenant_id(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Uses 'default' tenant_id when not specified."""
        await sync.sync_record("res.partner", 42)

        call_kwargs = mock_rag_client.upload_document.call_args.kwargs
        assert call_kwargs["tenant_id"] == "default"

    async def test_logs_error_on_exception(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logs an error message when sync fails."""
        mock_rpc_client.search_read.side_effect = Exception("Connection lost")

        with caplog.at_level(logging.ERROR):
            await sync.sync_record("res.partner", 42)

        assert "Failed to sync res.partner/42" in caplog.text


# ── sync_model ──


class TestSyncModel:
    """Test syncing all records of a model to the RAG store."""

    async def test_syncs_all_records(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Syncs all returned records and reports count."""
        mock_rpc_client.search_read.return_value = [
            {"id": 1, "name": "Record A"},
            {"id": 2, "name": "Record B"},
            {"id": 3, "name": "Record C"},
        ]

        result = await sync.sync_model("res.partner")

        assert result["model"] == "res.partner"
        assert result["synced"] == 3
        assert result["errors"] == 0
        assert mock_rag_client.upload_document.await_count == 3

    async def test_passes_limit(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Passes limit parameter to search_read."""
        mock_rpc_client.search_read.return_value = []

        await sync.sync_model("res.partner", limit=50)

        mock_rpc_client.search_read.assert_awaited_once_with(
            "res.partner", [], limit=50
        )

    async def test_passes_domain_filter(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Passes domain filter to search_read."""
        mock_rpc_client.search_read.return_value = []

        await sync.sync_model(
            "sale.order",
            domain=[["state", "=", "sale"]],
        )

        mock_rpc_client.search_read.assert_awaited_once_with(
            "sale.order", [["state", "=", "sale"]], limit=100
        )

    async def test_counts_individual_upload_errors(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Counts per-record upload errors separately from successes."""
        mock_rpc_client.search_read.return_value = [
            {"id": 1, "name": "Good Record"},
            {"id": 2, "name": "Bad Record"},
            {"id": 3, "name": "Good Record 2"},
        ]
        # Fail on the second upload
        mock_rag_client.upload_document.side_effect = [
            {"doc_id": "d1"},
            Exception("Upload error"),
            {"doc_id": "d3"},
        ]

        result = await sync.sync_model("res.partner")

        assert result["synced"] == 2
        assert result["errors"] == 1

    async def test_error_when_no_clients(self, sync_no_clients: OdooRAGSync) -> None:
        """Returns error when clients are not available."""
        result = await sync_no_clients.sync_model("res.partner")

        assert "error" in result
        assert "not available" in result["error"]

    async def test_handles_search_read_exception(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Returns error dict when search_read itself fails."""
        mock_rpc_client.search_read.side_effect = Exception("Connection refused")

        result = await sync.sync_model("res.partner")

        assert "error" in result

    async def test_default_domain_is_empty_list(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Default domain is an empty list."""
        mock_rpc_client.search_read.return_value = []

        await sync.sync_model("res.partner")

        call_args = mock_rpc_client.search_read.call_args
        assert call_args.args[1] == []

    async def test_logs_warning_on_per_record_error(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
        mock_rag_client: AsyncMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Logs a warning for each individual record that fails to sync."""
        mock_rpc_client.search_read.return_value = [
            {"id": 1, "name": "Failing Record"},
        ]
        mock_rag_client.upload_document.side_effect = Exception("Boom")

        with caplog.at_level(logging.WARNING):
            await sync.sync_model("res.partner")

        assert "Failed to sync res.partner/1" in caplog.text


# ── handle_record_change ──


class TestHandleRecordChange:
    """Test handling Kafka events for Odoo record changes."""

    async def test_update_event_syncs_record(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """An update event for an indexable model triggers sync."""
        event = {
            "model": "res.partner",
            "record_id": 42,
            "tenant_id": "tenant-1",
            "action": "update",
        }

        await sync.handle_record_change(event)

        mock_rag_client.upload_document.assert_awaited_once()

    async def test_create_event_syncs_record(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """A create event for an indexable model triggers sync."""
        event = {
            "model": "sale.order",
            "record_id": 10,
            "tenant_id": "default",
            "action": "create",
        }

        await sync.handle_record_change(event)

        mock_rag_client.upload_document.assert_awaited_once()

    async def test_delete_event_calls_delete_document(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """A delete event triggers RAG document deletion."""
        event = {
            "model": "res.partner",
            "record_id": 42,
            "tenant_id": "default",
            "action": "delete",
        }

        await sync.handle_record_change(event)

        mock_rag_client.delete_document.assert_awaited_once_with(
            "odoo-res_partner-42", tenant_id="default"
        )
        mock_rag_client.upload_document.assert_not_awaited()

    async def test_non_indexable_model_skips_sync(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Events for non-indexable models are ignored."""
        event = {
            "model": "ir.config_parameter",
            "record_id": 1,
            "tenant_id": "default",
            "action": "update",
        }

        await sync.handle_record_change(event)

        mock_rag_client.upload_document.assert_not_awaited()

    async def test_default_action_is_update(
        self,
        sync: OdooRAGSync,
        mock_rag_client: AsyncMock,
    ) -> None:
        """Missing action key defaults to 'update' and triggers sync."""
        event = {
            "model": "res.partner",
            "record_id": 42,
            "tenant_id": "default",
        }

        await sync.handle_record_change(event)

        mock_rag_client.upload_document.assert_awaited_once()

    async def test_default_tenant_id(
        self,
        sync: OdooRAGSync,
        mock_rpc_client: AsyncMock,
    ) -> None:
        """Missing tenant_id defaults to 'default'."""
        event = {
            "model": "res.partner",
            "record_id": 42,
            "action": "update",
        }

        await sync.handle_record_change(event)

        mock_rpc_client.search_read.assert_awaited_once()


# ── _build_document_content ──


class TestBuildDocumentContent:
    """Test the static method that builds structured content from Odoo records."""

    def test_returns_dict_with_required_keys(self) -> None:
        """Returns a dict with document_type, metadata, and extracted_text."""
        record = {"id": 1, "name": "Acme Corp", "email": "info@acme.com"}
        content = OdooRAGSync._build_document_content("res.partner", record)

        assert isinstance(content, dict)
        assert "document_type" in content
        assert "metadata" in content
        assert "extracted_text" in content

    def test_document_type_format(self) -> None:
        """document_type uses odoo_{model_underscore} format."""
        record = {"id": 1, "name": "Order 001"}
        content = OdooRAGSync._build_document_content("sale.order", record)

        assert content["document_type"] == "odoo_sale_order"

    def test_metadata_contains_source_and_model(self) -> None:
        """metadata includes source, model, record_id, and name."""
        record = {"id": 42, "name": "Acme Corp"}
        content = OdooRAGSync._build_document_content("res.partner", record)

        assert content["metadata"]["source"] == "odoo"
        assert content["metadata"]["model"] == "res.partner"
        assert content["metadata"]["record_id"] == 42
        assert content["metadata"]["name"] == "Acme Corp"

    def test_extracted_text_contains_fields(self) -> None:
        """extracted_text contains field key-value pairs."""
        record = {"id": 1, "name": "Acme Corp", "email": "info@acme.com"}
        content = OdooRAGSync._build_document_content("res.partner", record)
        text = content["extracted_text"]

        assert "name: Acme Corp" in text
        assert "email: info@acme.com" in text

    def test_excludes_id_field(self) -> None:
        """id field is excluded from extracted_text."""
        record = {"id": 1, "name": "Test"}
        content = OdooRAGSync._build_document_content("res.partner", record)

        assert "id:" not in content["extracted_text"]

    def test_excludes_false_values(self) -> None:
        """Skips fields with False value (Odoo convention for empty)."""
        record = {"id": 1, "name": "Test", "phone": False}
        content = OdooRAGSync._build_document_content("res.partner", record)

        assert "phone" not in content["extracted_text"]

    def test_excludes_none_values(self) -> None:
        """Skips fields with None value."""
        record = {"id": 1, "name": "Test", "email": None}
        content = OdooRAGSync._build_document_content("res.partner", record)

        assert "email" not in content["extracted_text"]

    def test_many2one_field(self) -> None:
        """Formats Many2one fields using the display name (index 1)."""
        record = {
            "id": 1,
            "name": "Order 001",
            "partner_id": [42, "Acme Corp"],
        }
        content = OdooRAGSync._build_document_content("sale.order", record)

        assert "partner_id: Acme Corp" in content["extracted_text"]

    def test_truncates_long_strings(self) -> None:
        """Truncates string fields longer than 500 characters."""
        long_text = "A" * 600
        record = {"id": 1, "name": "Test", "notes": long_text}
        content = OdooRAGSync._build_document_content("res.partner", record)
        text = content["extracted_text"]

        assert "notes:" in text
        assert "..." in text
        assert "A" * 501 not in text

    def test_regular_values(self) -> None:
        """Non-special values are rendered as-is."""
        record = {"id": 1, "amount_total": 1500.50, "state": "sale"}
        content = OdooRAGSync._build_document_content("sale.order", record)
        text = content["extracted_text"]

        assert "amount_total: 1500.5" in text
        assert "state: sale" in text
