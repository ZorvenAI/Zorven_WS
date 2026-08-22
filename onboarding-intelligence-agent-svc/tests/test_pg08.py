"""H-03 · PG-08 sensitive media guardrail tests."""

from __future__ import annotations

from app.logic.pg08 import pg08_sensitive_media


class TestPG08SensitiveMedia:
    def test_identity_unredacted_sets_rag_excluded(self):
        payload = {
            "sensitivity_class": "IDENTITY",
            "redaction_applied": False,
        }
        result = pg08_sensitive_media(payload, None)
        assert result["rag_excluded"] is True

    def test_financial_unredacted_sets_rag_excluded(self):
        payload = {
            "sensitivity_class": "FINANCIAL",
            "redaction_applied": False,
        }
        result = pg08_sensitive_media(payload, None)
        assert result["rag_excluded"] is True

    def test_identity_redacted_passes(self):
        payload = {
            "sensitivity_class": "IDENTITY",
            "redaction_applied": True,
        }
        result = pg08_sensitive_media(payload, None)
        assert "rag_excluded" not in result

    def test_general_passes(self):
        payload = {
            "sensitivity_class": "GENERAL",
            "redaction_applied": False,
        }
        result = pg08_sensitive_media(payload, None)
        assert "rag_excluded" not in result

    def test_missing_sensitivity_defaults_general(self):
        payload = {"redaction_applied": False}
        result = pg08_sensitive_media(payload, None)
        assert "rag_excluded" not in result
