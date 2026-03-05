"""HR domain tools — 11 tools for human resources operations."""

from typing import Any, Optional

from app.tools.base import BaseTool


class CreateEmployee(BaseTool):
    name = "hr_create_employee"
    description = "Create a new employee record in the HR system"
    domain = "hr"
    required_model = "hr.employee"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Employee full name",
            },
            "job_title": {
                "type": "string",
                "description": "Job title",
            },
            "job_id": {
                "type": "integer",
                "description": "Job position ID (hr.job)",
            },
            "department_id": {
                "type": "integer",
                "description": "Department ID (hr.department)",
            },
            "parent_id": {
                "type": "integer",
                "description": "Manager (hr.employee) ID",
            },
            "work_email": {
                "type": "string",
                "description": "Work email address",
            },
            "work_phone": {
                "type": "string",
                "description": "Work phone number",
            },
            "company_id": {
                "type": "integer",
                "description": "Company ID (res.company)",
            },
        },
        "required": ["name"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {"name": arguments["name"]}
        optional_fields = [
            "job_title",
            "job_id",
            "department_id",
            "parent_id",
            "work_email",
            "work_phone",
            "company_id",
        ]
        for field in optional_fields:
            if arguments.get(field) is not None:
                vals[field] = arguments[field]

        employee_id = await rpc_client.create("hr.employee", vals)
        return {"employee_id": employee_id, "success": True}


class UpdateEmployee(BaseTool):
    name = "hr_update_employee"
    description = "Update fields on an existing employee record"
    domain = "hr"
    required_model = "hr.employee"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "integer",
                "description": "ID of the employee to update",
            },
            "values": {
                "type": "object",
                "description": "Dictionary of field names and new values to set",
            },
        },
        "required": ["employee_id", "values"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        employee_id = arguments["employee_id"]
        values = arguments["values"]
        success = await rpc_client.write("hr.employee", [employee_id], values)
        return {
            "employee_id": employee_id,
            "updated": success,
        }


class SearchEmployees(BaseTool):
    name = "hr_search_employees"
    description = "Search and read employee records with flexible filters"
    domain = "hr"
    required_model = "hr.employee"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": "Odoo domain filter",
                "default": [],
            },
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Fields to return",
                "default": [],
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
            "order": {"type": "string", "default": ""},
        },
        "required": [],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain = arguments.get("domain", [])
        fields = arguments.get("fields", [])
        if not fields:
            fields = [
                "name",
                "job_title",
                "job_id",
                "department_id",
                "parent_id",
                "work_email",
                "work_phone",
                "active",
            ]
        records = await rpc_client.search_read(
            "hr.employee",
            domain,
            fields=fields,
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
            order=arguments.get("order", ""),
        )
        return {"records": records, "count": len(records)}


class RequestLeave(BaseTool):
    name = "hr_request_leave"
    description = "Create a leave request (time off) for an employee"
    domain = "hr"
    required_model = "hr.leave"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "integer",
                "description": "Employee ID requesting leave",
            },
            "holiday_status_id": {
                "type": "integer",
                "description": (
                    "Leave type ID (hr.leave.type), e.g. sick leave, vacation"
                ),
            },
            "date_from": {
                "type": "string",
                "description": "Leave start date (YYYY-MM-DD HH:MM:SS)",
            },
            "date_to": {
                "type": "string",
                "description": "Leave end date (YYYY-MM-DD HH:MM:SS)",
            },
            "name": {
                "type": "string",
                "description": "Reason / description for the leave",
            },
        },
        "required": [
            "employee_id",
            "holiday_status_id",
            "date_from",
            "date_to",
        ],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {
            "employee_id": arguments["employee_id"],
            "holiday_status_id": arguments["holiday_status_id"],
            "date_from": arguments["date_from"],
            "date_to": arguments["date_to"],
        }
        if arguments.get("name"):
            vals["name"] = arguments["name"]

        leave_id = await rpc_client.create("hr.leave", vals)
        return {"leave_id": leave_id, "success": True}


class ApproveLeave(BaseTool):
    name = "hr_approve_leave"
    description = "Approve a pending leave request via action_approve"
    domain = "hr"
    required_model = "hr.leave"
    required_operation = "write"
    input_schema = {
        "type": "object",
        "properties": {
            "leave_id": {
                "type": "integer",
                "description": "ID of the hr.leave to approve",
            },
        },
        "required": ["leave_id"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}
        leave_id = arguments["leave_id"]
        result = await rpc_client.execute_kw(
            "hr.leave",
            "action_approve",
            [[leave_id]],
        )
        return {
            "leave_id": leave_id,
            "approved": True,
            "result": result,
        }


class GetLeaveBalance(BaseTool):
    name = "hr_get_leave_balance"
    description = "Get remaining leave balance (allocations) for an employee"
    domain = "hr"
    required_model = "hr.leave.allocation"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "integer",
                "description": "Employee ID to check balance for",
            },
            "holiday_status_id": {
                "type": "integer",
                "description": "Optional leave type ID to filter by",
            },
        },
        "required": ["employee_id"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        employee_id = arguments["employee_id"]
        domain: list = [
            ["employee_id", "=", employee_id],
            ["state", "=", "validate"],
        ]
        if arguments.get("holiday_status_id"):
            domain.append(
                [
                    "holiday_status_id",
                    "=",
                    arguments["holiday_status_id"],
                ]
            )
        records = await rpc_client.search_read(
            "hr.leave.allocation",
            domain,
            fields=[
                "holiday_status_id",
                "number_of_days",
                "leaves_taken",
                "max_leaves",
                "remaining_leaves",
                "state",
            ],
        )
        return {
            "employee_id": employee_id,
            "allocations": records,
            "count": len(records),
        }


class CreateJobPosting(BaseTool):
    name = "hr_create_job_posting"
    description = "Create a job posting / applicant record in the recruitment pipeline"
    domain = "hr"
    required_model = "hr.applicant"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "partner_name": {
                "type": "string",
                "description": "Applicant name",
            },
            "job_id": {
                "type": "integer",
                "description": "Job position ID (hr.job)",
            },
            "department_id": {
                "type": "integer",
                "description": "Department ID",
            },
            "email_from": {
                "type": "string",
                "description": "Applicant email",
            },
            "partner_phone": {
                "type": "string",
                "description": "Applicant phone",
            },
            "description": {
                "type": "string",
                "description": "Application description / cover letter",
            },
            "stage_id": {
                "type": "integer",
                "description": "Recruitment stage ID (hr.recruitment.stage)",
            },
        },
        "required": ["partner_name", "job_id"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {
            "partner_name": arguments["partner_name"],
            "job_id": arguments["job_id"],
        }
        optional_fields = [
            "department_id",
            "email_from",
            "partner_phone",
            "description",
            "stage_id",
        ]
        for field in optional_fields:
            if arguments.get(field) is not None:
                vals[field] = arguments[field]

        applicant_id = await rpc_client.create("hr.applicant", vals)
        return {"applicant_id": applicant_id, "success": True}


class TrackApplicant(BaseTool):
    name = "hr_track_applicant"
    description = "Search and read applicant records in the recruitment pipeline"
    domain = "hr"
    required_model = "hr.applicant"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "domain": {
                "type": "array",
                "description": "Odoo domain filter",
                "default": [],
            },
            "job_id": {
                "type": "integer",
                "description": "Filter by job position ID",
            },
            "stage_id": {
                "type": "integer",
                "description": "Filter by recruitment stage ID",
            },
            "limit": {"type": "integer", "default": 80},
            "offset": {"type": "integer", "default": 0},
        },
        "required": [],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain: list = arguments.get("domain", [])
        if arguments.get("job_id"):
            domain.append(["job_id", "=", arguments["job_id"]])
        if arguments.get("stage_id"):
            domain.append(["stage_id", "=", arguments["stage_id"]])
        records = await rpc_client.search_read(
            "hr.applicant",
            domain,
            fields=[
                "partner_name",
                "job_id",
                "department_id",
                "stage_id",
                "email_from",
                "partner_phone",
                "priority",
                "create_date",
                "active",
            ],
            limit=arguments.get("limit", 80),
            offset=arguments.get("offset", 0),
        )
        return {"records": records, "count": len(records)}


class RecordAttendance(BaseTool):
    name = "hr_record_attendance"
    description = "Log an attendance check-in or check-out for an employee"
    domain = "hr"
    required_model = "hr.attendance"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "integer",
                "description": "Employee ID",
            },
            "check_in": {
                "type": "string",
                "description": "Check-in datetime (YYYY-MM-DD HH:MM:SS)",
            },
            "check_out": {
                "type": "string",
                "description": (
                    "Check-out datetime (YYYY-MM-DD HH:MM:SS), "
                    "optional if still checked in"
                ),
            },
        },
        "required": ["employee_id", "check_in"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {
            "employee_id": arguments["employee_id"],
            "check_in": arguments["check_in"],
        }
        if arguments.get("check_out"):
            vals["check_out"] = arguments["check_out"]

        attendance_id = await rpc_client.create("hr.attendance", vals)
        return {"attendance_id": attendance_id, "success": True}


class GeneratePayslip(BaseTool):
    name = "hr_generate_payslip"
    description = "Create and compute a payslip for an employee for a given period"
    domain = "hr"
    required_model = "hr.payslip"
    required_operation = "create"
    input_schema = {
        "type": "object",
        "properties": {
            "employee_id": {
                "type": "integer",
                "description": "Employee ID",
            },
            "date_from": {
                "type": "string",
                "description": "Period start date (YYYY-MM-DD)",
            },
            "date_to": {
                "type": "string",
                "description": "Period end date (YYYY-MM-DD)",
            },
            "struct_id": {
                "type": "integer",
                "description": "Salary structure ID (hr.payroll.structure)",
            },
            "contract_id": {
                "type": "integer",
                "description": "Employee contract ID (hr.contract)",
            },
            "name": {
                "type": "string",
                "description": "Payslip name / reference",
            },
        },
        "required": ["employee_id", "date_from", "date_to"],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available"}

        vals: dict[str, Any] = {
            "employee_id": arguments["employee_id"],
            "date_from": arguments["date_from"],
            "date_to": arguments["date_to"],
        }
        optional_fields = ["struct_id", "contract_id", "name"]
        for field in optional_fields:
            if arguments.get(field) is not None:
                vals[field] = arguments[field]

        payslip_id = await rpc_client.create("hr.payslip", vals)

        # Compute the payslip to calculate salary lines
        await rpc_client.execute_kw(
            "hr.payslip",
            "compute_sheet",
            [[payslip_id]],
        )

        return {
            "payslip_id": payslip_id,
            "computed": True,
            "success": True,
        }


class GetOrgChart(BaseTool):
    name = "hr_get_org_chart"
    description = (
        "Get the department hierarchy (org chart) showing parent-child relationships"
    )
    domain = "hr"
    required_model = "hr.department"
    required_operation = "read"
    input_schema = {
        "type": "object",
        "properties": {
            "parent_id": {
                "type": "integer",
                "description": (
                    "Filter by parent department ID to get "
                    "sub-departments (optional)"
                ),
            },
            "domain": {
                "type": "array",
                "description": "Additional Odoo domain filters",
                "default": [],
            },
            "limit": {"type": "integer", "default": 200},
        },
        "required": [],
    }

    async def execute(
        self,
        arguments: dict[str, Any],
        context: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        ctx = context or {}
        rpc_client = ctx.get("rpc_client")
        if rpc_client is None:
            return {"error": "No RPC client available", "records": []}
        domain: list = arguments.get("domain", [])
        if arguments.get("parent_id") is not None:
            domain.append(["parent_id", "=", arguments["parent_id"]])
        records = await rpc_client.search_read(
            "hr.department",
            domain,
            fields=[
                "name",
                "complete_name",
                "parent_id",
                "manager_id",
                "child_ids",
                "member_count",
                "active",
                "company_id",
            ],
            limit=arguments.get("limit", 200),
        )
        return {"records": records, "count": len(records)}


ALL_HR_TOOLS = [
    CreateEmployee(),
    UpdateEmployee(),
    SearchEmployees(),
    RequestLeave(),
    ApproveLeave(),
    GetLeaveBalance(),
    CreateJobPosting(),
    TrackApplicant(),
    RecordAttendance(),
    GeneratePayslip(),
    GetOrgChart(),
]
