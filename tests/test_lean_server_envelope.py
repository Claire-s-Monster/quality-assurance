#!/usr/bin/env python3
"""
Regression tests for the lean server's execute_tool envelope construction.

Covers the fix in src/quality_assurance/lean_server.py execute_tool (~lines 930-944)
that ensures a tool returning an error payload (a dict, not a raised exception)
produces a FAILED envelope (status == "error") instead of a false "success".

Run with: pixi run python -m pytest tests/test_lean_server_envelope.py -v
"""

import asyncio
import sys
from pathlib import Path

import pytest

# Add source paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import ExecutionStatus  # noqa: E402

_NON_PASSING_EXECUTION_STATUSES = [
    status.value
    for status in ExecutionStatus
    if status.value not in {"success", "warning"}
]


class TestLeanServerExecuteToolEnvelope:
    """Test that execute_tool wraps dispatched tool results in a correct envelope."""

    @pytest.fixture
    def lean_mcp(self):
        """Get a fresh QualityAssuranceLeanMCP instance."""
        from quality_assurance.lean_server import QualityAssuranceLeanMCP

        return QualityAssuranceLeanMCP(working_dir=".")

    @pytest.fixture
    def execute_tool_fn(self, lean_mcp):
        """Get the callable .fn behind the execute_tool meta-tool."""
        tool = asyncio.run(lean_mcp.app.get_tool("execute_tool"))
        return tool.fn

    @pytest.fixture
    def main_server_module(self):
        """Get the main server module whose functions execute_tool dispatches to."""
        from quality_assurance import server as main_server

        return main_server

    def test_error_status_with_error_message_produces_failed_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """A dict with status='error' and an error message must fail the envelope."""

        def stub_tool(**kwargs):
            return {"status": "error", "error": "boom"}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "error"
        assert envelope["error"] == "boom"
        assert envelope["result"] == {"status": "error", "error": "boom"}

    def test_error_key_without_status_produces_failed_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """A truthy 'error' key alone (no status key) must fail the envelope."""

        def stub_tool(**kwargs):
            return {"error": "boom"}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "error"

    def test_error_status_without_error_key_produces_failed_envelope_with_message(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """status='error' with no 'error' key must still fail, with a synthesized message."""

        def stub_tool(**kwargs):
            return {"status": "error"}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "error"
        assert isinstance(envelope["error"], str) and envelope["error"]
        assert "quality_execute_lint_assessment" in envelope["error"]

    def test_normal_success_payload_produces_success_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """A normal successful payload must produce a success envelope."""

        def stub_tool(**kwargs):
            return {
                "assessment_type": "lint",
                "status": "success",
                "files_analyzed": 12,
            }

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "success"
        assert envelope["result"]["files_analyzed"] == 12

    def test_falsy_error_and_plural_errors_key_do_not_trigger_failure(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """Regression guard: a falsy 'error' value and a plural 'errors' key must not
        be mistaken for a failure. The implementation must check result.get("error")
        (truthiness) rather than "error" in result.
        """

        def stub_tool(**kwargs):
            return {"error": None, "errors": ["a", "b"]}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "success"

    def test_unknown_tool_name_returns_not_found_with_available_tools(
        self, execute_tool_fn
    ):
        """An unknown tool name must return the not-found error with available_tools."""
        envelope = execute_tool_fn("definitely_not_a_real_tool", {})

        assert envelope["error"] == "Tool 'definitely_not_a_real_tool' not found"
        assert isinstance(envelope["available_tools"], list)
        assert len(envelope["available_tools"]) > 0

    def test_failure_status_produces_failed_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """ExecutionStatus.FAILURE must not be wrapped in a success envelope."""

        def stub_tool(**kwargs):
            return {"status": "failure", "files_analyzed": 3}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "error"

    def test_timeout_status_produces_failed_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """ExecutionStatus.TIMEOUT must not be wrapped in a success envelope."""

        def stub_tool(**kwargs):
            return {"status": "timeout"}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "error"

    def test_warning_status_produces_success_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """ExecutionStatus.WARNING is a finding, not a failure, and must succeed."""

        def stub_tool(**kwargs):
            return {"status": "warning", "files_analyzed": 3}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "success"

    def test_healthy_status_outside_execution_status_produces_success_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch
    ):
        """Ad-hoc vocabularies like 'healthy' (used by health/capability tools) are
        not ExecutionStatus members and must not be reclassified as failures.
        """

        def stub_tool(**kwargs):
            return {"status": "healthy"}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "success"

    @pytest.mark.parametrize(
        ("verdict", "envelope_status"),
        [("passed", "success"), ("findings", "success"), ("error", "error")],
    )
    def test_gate_verdict_error_fails_the_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch, verdict, envelope_status
    ):
        """A pixi-aware result whose gate_verdict is 'error' (a tool errored or
        could not run) must not be wrapped in a success envelope."""

        def stub_tool(**kwargs):
            return {
                "assessment_type": "pixi_aware_comprehensive",
                "gate_verdict": verdict,
            }

        monkeypatch.setattr(
            main_server_module, "quality_execute_pixi_aware_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_pixi_aware_assessment", {})

        assert envelope["status"] == envelope_status

    @pytest.mark.parametrize("status_value", _NON_PASSING_EXECUTION_STATUSES)
    def test_every_non_passing_execution_status_fails_the_envelope(
        self, execute_tool_fn, main_server_module, monkeypatch, status_value
    ):
        """Every ExecutionStatus member not explicitly declared passing must fail
        the envelope. A newly added enum member fails this test until it is
        classified as passing or left to the default failing behavior.
        """

        def stub_tool(**kwargs):
            return {"status": status_value}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = execute_tool_fn("quality_execute_lint_assessment", {})

        assert envelope["status"] == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
