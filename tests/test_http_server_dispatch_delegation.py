#!/usr/bin/env python3
"""
Regression tests proving the HTTP transport's execute_tool path exercises the
SAME dispatch implementation as the lean MCP server, instead of a copy-pasted
reimplementation.

Background: src/quality_assurance/http_server.py used to reimplement
execute_tool's lookup/import/fn-call/envelope logic independently of
src/quality_assurance/lean_server.py's QualityAssuranceLeanMCP.execute_tool.
The two drifted -- an envelope-honesty fix (a tool returning an error dict
must produce a FAILED envelope) landed in lean_server plus 6 regression
tests in tests/test_lean_server_envelope.py, but .mcp.json routes ALL real
traffic through the HTTP surface, so the fix never protected production.

http_server.py now delegates to QualityAssuranceLeanMCP._dispatch_tool
(the extracted canonical dispatch body). These tests exercise
HTTPQualityAssuranceServer._execute_lean_tool directly -- the actual method
invoked by the JSON-RPC tools/call handler -- so a regression that
reintroduces duplicated/broken dispatch logic in http_server.py is caught
here, not just in lean_server's own tests.

Run with: pixi run python -m pytest tests/test_http_server_dispatch_delegation.py -v
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestHttpServerExecuteToolDelegation:
    """Test that HTTPQualityAssuranceServer.execute_tool delegates to the lean dispatch."""

    @pytest.fixture
    def http_server(self):
        """Get a fresh HTTPQualityAssuranceServer instance (no working_dir chdir, no bind)."""
        from quality_assurance.http_server import HTTPQualityAssuranceServer

        return HTTPQualityAssuranceServer(working_dir=None)

    @pytest.fixture
    def main_server_module(self):
        """Get the main server module whose functions execute_tool dispatches to."""
        from quality_assurance import server as main_server

        return main_server

    def test_execute_tool_delegates_to_lean_mcp_dispatch_tool(self, http_server):
        """The HTTP path must call QualityAssuranceLeanMCP._dispatch_tool directly.

        This is the load-bearing assertion: if http_server ever regresses back to
        reimplementing dispatch inline instead of calling this method, this test
        fails even though every other envelope assertion might still coincidentally
        pass.
        """
        sentinel = {"tool": "quality_execute_lint_assessment", "status": "success"}
        mock_dispatch = Mock(return_value=sentinel)
        http_server._lean_mcp._dispatch_tool = mock_dispatch

        result = http_server._execute_lean_tool(
            "execute_tool",
            {
                "tool_name": "quality_execute_lint_assessment",
                "parameters": {"target_path": "src/"},
            },
        )

        mock_dispatch.assert_called_once_with(
            "quality_execute_lint_assessment", {"target_path": "src/"}
        )
        assert result is sentinel

    def test_execute_tool_error_payload_produces_failed_envelope_over_http(
        self, http_server, main_server_module, monkeypatch
    ):
        """A tool returning an error dict must fail the envelope on the HTTP path.

        This reproduces the exact defect: a real tool function reporting failure
        via a returned dict (not a raised exception), routed through
        HTTPQualityAssuranceServer._execute_lean_tool -- the method production
        traffic actually calls per .mcp.json, not lean_server directly.
        """

        def stub_tool(**kwargs):
            return {"status": "error", "error": "boom"}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = http_server._execute_lean_tool(
            "execute_tool",
            {"tool_name": "quality_execute_lint_assessment", "parameters": {}},
        )

        assert envelope["status"] == "error"
        assert envelope["error"] == "boom"
        assert envelope["result"] == {"status": "error", "error": "boom"}

    def test_execute_tool_success_payload_produces_success_envelope_over_http(
        self, http_server, main_server_module, monkeypatch
    ):
        """A normal successful payload must still succeed on the HTTP path."""

        def stub_tool(**kwargs):
            return {"status": "success", "files_analyzed": 3}

        monkeypatch.setattr(
            main_server_module, "quality_execute_lint_assessment", stub_tool
        )

        envelope = http_server._execute_lean_tool(
            "execute_tool",
            {"tool_name": "quality_execute_lint_assessment", "parameters": {}},
        )

        assert envelope["status"] == "success"
        assert envelope["result"]["files_analyzed"] == 3

    def test_execute_tool_string_parameters_are_coerced_before_dispatch(
        self, http_server
    ):
        """HTTP JSON-RPC callers may send 'parameters' as a JSON string; it must be
        decoded into a dict before reaching dispatch (lean_server's FastMCP-typed
        signature never needs this coercion, so it must stay in http_server).
        """
        mock_dispatch = Mock(return_value={"tool": "x", "status": "success"})
        http_server._lean_mcp._dispatch_tool = mock_dispatch

        http_server._execute_lean_tool(
            "execute_tool",
            {
                "tool_name": "quality_execute_lint_assessment",
                "parameters": '{"target_path": "src/"}',
            },
        )

        mock_dispatch.assert_called_once_with(
            "quality_execute_lint_assessment", {"target_path": "src/"}
        )

    def test_execute_tool_unknown_tool_returns_not_found_over_http(self, http_server):
        """An unknown tool name must return the not-found error with available_tools."""
        envelope = http_server._execute_lean_tool(
            "execute_tool",
            {"tool_name": "definitely_not_a_real_tool", "parameters": {}},
        )

        assert envelope["error"] == "Tool 'definitely_not_a_real_tool' not found"
        assert isinstance(envelope["available_tools"], list)
        assert len(envelope["available_tools"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
