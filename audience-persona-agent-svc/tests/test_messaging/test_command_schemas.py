"""Tests for Kafka command schemas."""

from app.messaging.command_schemas import ScheduledScanCommand, ScheduledScanPayload


class TestScheduledScanPayload:
    def test_defaults(self):
        payload = ScheduledScanPayload()
        assert payload.brand_description == ""
        assert payload.industry == ""
        assert payload.geography == ""
        assert payload.max_personas == 5
        assert payload.scan_type == "incremental"
        assert payload.refresh_interval_days == 30

    def test_custom_values(self):
        payload = ScheduledScanPayload(
            brand_description="SaaS product",
            industry="Technology",
            geography="North America",
            max_personas=8,
            scan_type="full",
            refresh_interval_days=7,
        )
        assert payload.brand_description == "SaaS product"
        assert payload.scan_type == "full"
        assert payload.max_personas == 8


class TestScheduledScanCommand:
    def test_required_fields(self):
        cmd = ScheduledScanCommand(
            command_id="cmd-123",
            tenant_id="tenant-1",
        )
        assert cmd.command_id == "cmd-123"
        assert cmd.tenant_id == "tenant-1"
        assert cmd.command_type == "scheduled_persona_scan"
        assert cmd.payload.scan_type == "incremental"
        assert cmd.idempotency_key == ""

    def test_full_command(self):
        cmd = ScheduledScanCommand(
            command_id="cmd-456",
            command_type="scheduled_persona_scan",
            tenant_id="tenant-2",
            payload=ScheduledScanPayload(
                brand_description="EV Charging",
                industry="Energy",
                scan_type="full",
            ),
            idempotency_key="schedule:abc:2026-03-13",
        )
        assert cmd.payload.brand_description == "EV Charging"
        assert cmd.idempotency_key == "schedule:abc:2026-03-13"

    def test_from_dict(self):
        data = {
            "command_id": "cmd-789",
            "command_type": "scheduled_persona_scan",
            "tenant_id": "tenant-3",
            "payload": {
                "brand_description": "Test brand",
                "scan_type": "incremental",
            },
            "idempotency_key": "key-1",
        }
        cmd = ScheduledScanCommand(**data)
        assert cmd.command_id == "cmd-789"
        assert cmd.payload.brand_description == "Test brand"
