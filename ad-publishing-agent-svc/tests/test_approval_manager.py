"""Tests for the approval manager."""

import pytest

from app.services.approval_manager import ApprovalManager


class TestApprovalManager:
    def setup_method(self):
        self.mgr = ApprovalManager(redis_manager=None, expiry_seconds=86400)

    async def test_create_approval_request(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1",
            tenant_id="t-1",
            preview_data={"campaign_name": "Test"},
            is_production=False,
        )
        assert req["status"] == "pending"
        assert req["request_id"]
        assert req["job_id"] == "job-1"
        assert req["is_production"] is False

    async def test_approve_all(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="user-1",
            user_role="ADMIN",
        )
        assert result["status"] == "approved"

    async def test_reject_with_feedback(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="reject",
            feedback="Images need improvement",
            approved_by="user-1",
            user_role="ADMIN",
        )
        assert result["status"] == "rejected"
        assert result["feedback"] == "Images need improvement"

    async def test_partial_approval(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_selected",
            approved_ad_sets=["TOFU - Tech"],
            approved_by="user-1",
            user_role="ADMIN",
        )
        assert result["status"] == "partial"
        assert result["approved_ad_sets"] == ["TOFU - Tech"]

    async def test_viewer_cannot_approve(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="viewer-1",
            user_role="VIEWER",
        )
        assert result["status"] == "denied"

    async def test_editor_escalates(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="editor-1",
            user_role="EDITOR",
        )
        assert result["status"] == "escalated"

    async def test_production_requires_confirmation(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=True,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="admin-1",
            user_role="ADMIN",
            production_confirmed=False,
        )
        assert result["status"] == "requires_production_confirm"

    async def test_production_with_confirmation(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=True,
        )
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="admin-1",
            user_role="ADMIN",
            production_confirmed=True,
        )
        assert result["status"] == "approved"

    async def test_double_approval_rejected(self):
        req = await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="admin-1",
            user_role="ADMIN",
        )
        # Second approval attempt
        result = await self.mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="admin-2",
            user_role="ADMIN",
        )
        assert "already" in result.get("error", "").lower()

    async def test_not_found(self):
        result = await self.mgr.process_approval(
            request_id="nonexistent",
            tenant_id="t-1",
            decision="approve_all",
            approved_by="admin-1",
            user_role="ADMIN",
        )
        assert result["status"] == "error"

    async def test_list_pending(self):
        await self.mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        await self.mgr.create_approval_request(
            job_id="job-2", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        pending = await self.mgr.list_pending("t-1")
        assert len(pending) == 2

    async def test_expired_request(self):
        mgr = ApprovalManager(redis_manager=None, expiry_seconds=0)
        req = await mgr.create_approval_request(
            job_id="job-1", tenant_id="t-1",
            preview_data={}, is_production=False,
        )
        # Immediately expired (expiry_seconds=0)
        import asyncio
        await asyncio.sleep(0.01)  # Tiny delay to ensure expiry
        result = await mgr.process_approval(
            request_id=req["request_id"],
            tenant_id="t-1",
            decision="approve_all",
            approved_by="admin-1",
            user_role="ADMIN",
        )
        assert result["status"] == "expired"
