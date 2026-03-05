"""Tests for HR domain tools."""

from unittest.mock import AsyncMock

from app.tools.hr.tools import (
    ALL_HR_TOOLS,
    ApproveLeave,
    CreateEmployee,
    CreateJobPosting,
    GeneratePayslip,
    GetLeaveBalance,
    GetOrgChart,
    RecordAttendance,
    RequestLeave,
    SearchEmployees,
    TrackApplicant,
    UpdateEmployee,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateEmployee:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 10
        tool = CreateEmployee()
        result = await tool.execute({"name": "Jane Doe"}, ctx)
        assert result["employee_id"] == 10
        assert result["success"] is True

    async def test_create_no_client(self):
        tool = CreateEmployee()
        result = await tool.execute({"name": "Jane Doe"})
        assert "error" in result


class TestUpdateEmployee:
    async def test_update_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = UpdateEmployee()
        result = await tool.execute(
            {"employee_id": 10, "values": {"job_title": "Engineer"}}, ctx
        )
        assert result["updated"] is True
        assert result["employee_id"] == 10


class TestSearchEmployees:
    async def test_search_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {"id": 10, "name": "Jane Doe", "job_title": "Engineer"}
        ]
        tool = SearchEmployees()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestRequestLeave:
    async def test_request_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 50
        tool = RequestLeave()
        result = await tool.execute(
            {
                "employee_id": 10,
                "holiday_status_id": 1,
                "date_from": "2026-04-01 08:00:00",
                "date_to": "2026-04-05 17:00:00",
            },
            ctx,
        )
        assert result["leave_id"] == 50
        assert result["success"] is True


class TestApproveLeave:
    async def test_approve_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = ApproveLeave()
        result = await tool.execute({"leave_id": 50}, ctx)
        assert result["approved"] is True
        assert result["leave_id"] == 50


class TestGetLeaveBalance:
    async def test_balance_returns_allocations(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "holiday_status_id": [1, "Vacation"],
                "number_of_days": 20,
                "remaining_leaves": 15,
            }
        ]
        tool = GetLeaveBalance()
        result = await tool.execute({"employee_id": 10}, ctx)
        assert result["employee_id"] == 10
        assert result["count"] == 1
        assert len(result["allocations"]) == 1


class TestCreateJobPosting:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 70
        tool = CreateJobPosting()
        result = await tool.execute({"partner_name": "John Smith", "job_id": 3}, ctx)
        assert result["applicant_id"] == 70
        assert result["success"] is True


class TestTrackApplicant:
    async def test_track_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 70,
                "partner_name": "John Smith",
                "job_id": [3, "Developer"],
                "stage_id": [1, "New"],
            }
        ]
        tool = TrackApplicant()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestRecordAttendance:
    async def test_record_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 80
        tool = RecordAttendance()
        result = await tool.execute(
            {
                "employee_id": 10,
                "check_in": "2026-03-04 08:00:00",
            },
            ctx,
        )
        assert result["attendance_id"] == 80
        assert result["success"] is True


class TestGeneratePayslip:
    async def test_generate_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 90
        ctx["rpc_client"].execute_kw.return_value = True
        tool = GeneratePayslip()
        result = await tool.execute(
            {
                "employee_id": 10,
                "date_from": "2026-03-01",
                "date_to": "2026-03-31",
            },
            ctx,
        )
        assert result["payslip_id"] == 90
        assert result["computed"] is True
        assert result["success"] is True


class TestGetOrgChart:
    async def test_org_chart_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {
                "id": 1,
                "name": "Engineering",
                "parent_id": False,
                "manager_id": [10, "Jane Doe"],
                "member_count": 15,
            }
        ]
        tool = GetOrgChart()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["records"]) == 1


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_update_employee_no_client(self):
        tool = UpdateEmployee()
        result = await tool.execute({"employee_id": 1, "values": {}})
        assert "error" in result

    async def test_search_employees_no_client(self):
        tool = SearchEmployees()
        result = await tool.execute({})
        assert "error" in result

    async def test_request_leave_no_client(self):
        tool = RequestLeave()
        result = await tool.execute(
            {
                "employee_id": 1,
                "holiday_status_id": 1,
                "date_from": "2026-04-01 08:00:00",
                "date_to": "2026-04-05 17:00:00",
            }
        )
        assert "error" in result

    async def test_approve_leave_no_client(self):
        tool = ApproveLeave()
        result = await tool.execute({"leave_id": 1})
        assert "error" in result

    async def test_get_leave_balance_no_client(self):
        tool = GetLeaveBalance()
        result = await tool.execute({"employee_id": 1})
        assert "error" in result

    async def test_create_job_posting_no_client(self):
        tool = CreateJobPosting()
        result = await tool.execute({"partner_name": "test", "job_id": 1})
        assert "error" in result

    async def test_track_applicant_no_client(self):
        tool = TrackApplicant()
        result = await tool.execute({})
        assert "error" in result

    async def test_record_attendance_no_client(self):
        tool = RecordAttendance()
        result = await tool.execute(
            {"employee_id": 1, "check_in": "2026-03-04 08:00:00"}
        )
        assert "error" in result

    async def test_generate_payslip_no_client(self):
        tool = GeneratePayslip()
        result = await tool.execute(
            {"employee_id": 1, "date_from": "2026-03-01", "date_to": "2026-03-31"}
        )
        assert "error" in result

    async def test_get_org_chart_no_client(self):
        tool = GetOrgChart()
        result = await tool.execute({})
        assert "error" in result


class TestAllHrTools:
    def test_all_tools_count(self):
        assert len(ALL_HR_TOOLS) == 11

    def test_all_tools_have_names(self):
        for tool in ALL_HR_TOOLS:
            assert tool.name != ""
            assert tool.domain == "hr"
