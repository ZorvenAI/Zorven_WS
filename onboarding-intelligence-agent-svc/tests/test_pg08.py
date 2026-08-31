"""H-03 / M-01 · PG-08 sensitive media guardrail tests."""

from __future__ import annotations

from app.logic.guardrails import Action, Verdict
from app.logic.pg08 import pg08_sensitive_media


class TestPG08SensitiveMedia:
    def test_identity_unredacted_drops_and_excludes(self):
        payload = {
            "sensitivity_class": "IDENTITY",
            "redaction_applied": False,
        }
        result = pg08_sensitive_media(payload, None)
        assert result.action is Action.DROP
        assert result.payload["rag_excluded"] is True

    def test_financial_unredacted_drops_and_excludes(self):
        payload = {
            "sensitivity_class": "FINANCIAL",
            "redaction_applied": False,
        }
        result = pg08_sensitive_media(payload, None)
        assert result.action is Action.DROP
        assert result.payload["rag_excluded"] is True

    def test_identity_redacted_passes(self):
        payload = {
            "sensitivity_class": "IDENTITY",
            "redaction_applied": True,
        }
        result = pg08_sensitive_media(payload, None)
        assert result.action is Action.PASS
        assert "rag_excluded" not in result.payload

    def test_general_passes(self):
        payload = {
            "sensitivity_class": "GENERAL",
            "redaction_applied": False,
        }
        result = pg08_sensitive_media(payload, None)
        assert result.action is Action.PASS
        assert "rag_excluded" not in result.payload

    def test_missing_sensitivity_defaults_general(self):
        payload = {"redaction_applied": False}
        result = pg08_sensitive_media(payload, None)
        assert result.action is Action.PASS
        assert "rag_excluded" not in result.payload

    def test_non_dict_payload_passes(self):
        result = pg08_sensitive_media("not-a-dict", None)
        assert result.action is Action.PASS
        assert result.rule_id == "PG-08"
