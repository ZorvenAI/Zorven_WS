"""Tests for Accounting domain tools."""

from unittest.mock import AsyncMock

from app.tools.accounting.tools import (
    ALL_ACCOUNTING_TOOLS,
    BankReconcile,
    CreateBill,
    CreateInvoice,
    CreateJournalEntry,
    GenerateReport,
    GetBalance,
    ManageTaxes,
    PostEntry,
    Reconcile,
    RegisterPayment,
)


def _mock_context():
    rpc = AsyncMock()
    return {"rpc_client": rpc, "tenant_id": "test"}


class TestCreateInvoice:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 100
        tool = CreateInvoice()
        result = await tool.execute({"partner_id": 1}, ctx)
        assert result["id"] == 100
        assert result["move_type"] == "out_invoice"
        assert result["partner_id"] == 1

    async def test_create_no_client(self):
        tool = CreateInvoice()
        result = await tool.execute({"partner_id": 1})
        assert "error" in result


class TestCreateBill:
    async def test_create_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 101
        tool = CreateBill()
        result = await tool.execute({"partner_id": 2}, ctx)
        assert result["id"] == 101
        assert result["move_type"] == "in_invoice"
        assert result["partner_id"] == 2


class TestPostEntry:
    async def test_post_returns_status(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = PostEntry()
        result = await tool.execute({"move_id": 100}, ctx)
        assert result["status"] == "posted"
        assert result["id"] == 100


class TestRegisterPayment:
    async def test_register_payment_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.side_effect = [50, {"res_id": 60}]
        tool = RegisterPayment()
        result = await tool.execute({"move_ids": [100], "journal_id": 5}, ctx)
        assert result["move_ids"] == [100]
        assert result["wizard_id"] == 50


class TestReconcile:
    async def test_reconcile_returns_result(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = Reconcile()
        result = await tool.execute({"line_ids": [1, 2]}, ctx)
        assert result["reconciled"] is True
        assert result["line_ids"] == [1, 2]

    async def test_reconcile_too_few_lines(self):
        ctx = _mock_context()
        tool = Reconcile()
        result = await tool.execute({"line_ids": [1]}, ctx)
        assert "error" in result


class TestGetBalance:
    async def test_get_balance_returns_balances(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = [
            {
                "account_id": [1, "1000 Cash"],
                "debit": 5000,
                "credit": 2000,
                "balance": 3000,
                "account_id_count": 10,
            }
        ]
        tool = GetBalance()
        result = await tool.execute({}, ctx)
        assert result["total_accounts"] == 1
        assert len(result["balances"]) == 1
        assert result["balances"][0]["balance"] == 3000


class TestGenerateReport:
    async def test_generate_report_returns_data(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = {
            "lines": [{"name": "Revenue", "amount": 10000}]
        }
        tool = GenerateReport()
        result = await tool.execute({"report_name": "account.report_financial"}, ctx)
        assert result["report_name"] == "account.report_financial"
        assert "data" in result


class TestCreateJournalEntry:
    async def test_create_journal_entry_returns_id(self):
        ctx = _mock_context()
        ctx["rpc_client"].create.return_value = 200
        tool = CreateJournalEntry()
        result = await tool.execute(
            {
                "journal_id": 1,
                "line_ids": [
                    {"account_id": 10, "name": "Debit", "debit": 500},
                    {"account_id": 20, "name": "Credit", "credit": 500},
                ],
            },
            ctx,
        )
        assert result["id"] == 200
        assert result["move_type"] == "entry"
        assert result["journal_id"] == 1


class TestManageTaxes:
    async def test_search_taxes_returns_records(self):
        ctx = _mock_context()
        ctx["rpc_client"].search_read.return_value = [
            {"id": 1, "name": "VAT 15%", "amount": 15}
        ]
        tool = ManageTaxes()
        result = await tool.execute({}, ctx)
        assert result["count"] == 1
        assert len(result["taxes"]) == 1

    async def test_update_taxes_returns_success(self):
        ctx = _mock_context()
        ctx["rpc_client"].write.return_value = True
        tool = ManageTaxes()
        result = await tool.execute({"tax_ids": [1], "values": {"amount": 20}}, ctx)
        assert result["updated"] is True
        assert result["tax_ids"] == [1]


class TestBankReconcile:
    async def test_bank_reconcile_full_statement(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = BankReconcile()
        result = await tool.execute({"statement_id": 5}, ctx)
        assert result["status"] == "validated"
        assert result["statement_id"] == 5

    async def test_bank_reconcile_specific_lines(self):
        ctx = _mock_context()
        ctx["rpc_client"].execute_kw.return_value = True
        tool = BankReconcile()
        result = await tool.execute(
            {"statement_id": 5, "statement_line_ids": [10, 11]}, ctx
        )
        assert result["statement_id"] == 5
        assert result["line_ids"] == [10, 11]


class TestNoClient:
    """Test all tools return error when no RPC client."""

    async def test_create_bill_no_client(self):
        tool = CreateBill()
        result = await tool.execute({"partner_id": 1})
        assert "error" in result

    async def test_post_entry_no_client(self):
        tool = PostEntry()
        result = await tool.execute({"move_id": 1})
        assert "error" in result

    async def test_register_payment_no_client(self):
        tool = RegisterPayment()
        result = await tool.execute({"move_ids": [1], "journal_id": 1})
        assert "error" in result

    async def test_reconcile_no_client(self):
        tool = Reconcile()
        result = await tool.execute({"line_ids": [1, 2]})
        assert "error" in result

    async def test_get_balance_no_client(self):
        tool = GetBalance()
        result = await tool.execute({})
        assert "error" in result

    async def test_generate_report_no_client(self):
        tool = GenerateReport()
        result = await tool.execute({"report_name": "test"})
        assert "error" in result

    async def test_create_journal_entry_no_client(self):
        tool = CreateJournalEntry()
        result = await tool.execute(
            {
                "journal_id": 1,
                "line_ids": [{"account_id": 1, "name": "test", "debit": 100}],
            }
        )
        assert "error" in result

    async def test_manage_taxes_no_client(self):
        tool = ManageTaxes()
        result = await tool.execute({})
        assert "error" in result

    async def test_bank_reconcile_no_client(self):
        tool = BankReconcile()
        result = await tool.execute({"statement_id": 1})
        assert "error" in result


class TestAllAccountingTools:
    def test_all_tools_count(self):
        assert len(ALL_ACCOUNTING_TOOLS) == 10

    def test_all_tools_have_names(self):
        for tool in ALL_ACCOUNTING_TOOLS:
            assert tool.name != ""
            assert tool.domain == "accounting"
