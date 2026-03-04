"""Tests for app/core/logging_config.py — setup_logging coverage."""

import logging

from app.core.logging_config import setup_logging


class TestSetupLogging:
    def test_sets_root_level(self):
        setup_logging()
        root = logging.getLogger()
        assert root.level <= logging.INFO

    def test_suppresses_uvicorn_access(self):
        setup_logging()
        assert logging.getLogger("uvicorn.access").level == logging.WARNING

    def test_suppresses_httpx(self):
        setup_logging()
        assert logging.getLogger("httpx").level == logging.WARNING

    def test_suppresses_xmlrpc_client(self):
        setup_logging()
        assert logging.getLogger("xmlrpc.client").level == logging.WARNING

    def test_suppresses_httpcore(self):
        setup_logging()
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_idempotent(self):
        """Calling setup_logging twice does not raise."""
        setup_logging()
        setup_logging()
        root = logging.getLogger()
        assert root.level <= logging.INFO
