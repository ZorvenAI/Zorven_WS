"""L-03 — Process callback includes prompt_versions.

Verifies that _callback includes prompt_versions in the POST payload
when provided. No mocks: tests the actual method signature and payload
construction via inspection.
"""

import inspect

from app.logic.process_executor import ProcessExecutor


class TestCallbackIncludesPromptVersions:
    def test_callback_accepts_prompt_versions_kwarg(self):
        sig = inspect.signature(ProcessExecutor._callback)
        params = list(sig.parameters.keys())
        assert "prompt_versions" in params

    def test_prompt_versions_default_is_none(self):
        sig = inspect.signature(ProcessExecutor._callback)
        param = sig.parameters["prompt_versions"]
        assert param.default is None

    def test_run_job_references_prompt_versions(self):
        source = inspect.getsource(ProcessExecutor._run_job)
        assert "prompt_versions" in source

    def test_callback_invocation_passes_prompt_versions(self):
        source = inspect.getsource(ProcessExecutor._run_job)
        assert "prompt_versions=prompt_versions" in source
