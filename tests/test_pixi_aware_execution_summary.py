#!/usr/bin/env python3
"""
Regression tests for quality_execute_pixi_aware_assessment's execution_summary
accounting (server.py).

Covers the fix where a failed tool result (success=False, non-zero exit_code,
no "status" key) fell through the old `r.get("status") not in ["error",
"unavailable"]` check and was silently counted as "executed" -- so a run
that never completed an analysis was reported as an unqualified success,
with tools_failed staying at 0.

Run with: pixi run python -m pytest tests/test_pixi_aware_execution_summary.py -v
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class _FakeEnvInfo:
    def __init__(self, available_tools):
        self.available_tools = available_tools
        self.quality_tasks = {}
        self.environment_health = "optimal"
        self.tool_versions = {}
        self.performance_indicators = {}
        self.recommendations = []


class _FakeTemplate:
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.output_format = "json"


class _FakePixiAdapter:
    """Stands in for the enhanced DirectPixiExecutionAdapter so tests don't
    need a real pixi project / subprocess execution."""

    def __init__(self, run_results: dict, available_tools: set):
        self._run_results = run_results
        self.detect_quality_environment = Mock(return_value=_FakeEnvInfo(available_tools))
        self.optimize_quality_environment = Mock(return_value={})
        self.generate_quality_task_template = Mock(
            side_effect=lambda tool_name, target_pattern: _FakeTemplate(f"{tool_name}-task")
        )
        # Neither the template's own name nor the tool's alias candidates
        # resolve in this fake project -- irrelevant to execution_summary
        # accounting, which is driven entirely by the run_quality_task result.
        self.resolve_task_name = Mock(return_value=None)

    def run_quality_task(self, **kwargs):
        return self._run_results[kwargs["quality_tool"]]


class _FakeContainer:
    def __init__(self, pixi_adapter):
        self.pixi_executor = pixi_adapter


@pytest.fixture
def main_server_module():
    from quality_assurance import server as main_server

    return main_server


class TestPixiAwareExecutionSummaryAccounting:
    def test_failed_tool_counted_as_failed_not_executed(
        self, main_server_module, monkeypatch, tmp_path
    ):
        """A tool whose run_quality_task result has success=False and a
        non-zero exit_code (e.g. 'task not found') must be counted as
        tools_failed=1, tools_executed=0 -- never as executed."""
        run_results = {
            "ruff": {
                "success": False,
                "stdout": "",
                "stderr": "Task 'ruff-check' not found. Available tasks: ['lint']",
                "exit_code": 1,
                "execution_time": 0.01,
                "quality_intelligence": {"tool_name": "ruff"},
            }
        }
        fake_pixi_adapter = _FakePixiAdapter(run_results, available_tools={"ruff"})
        monkeypatch.setattr(main_server_module, "orchestration_service", object())
        monkeypatch.setattr(main_server_module, "container", _FakeContainer(fake_pixi_adapter))

        result = main_server_module.quality_execute_pixi_aware_assessment.fn(
            tools=["ruff"], project_path=str(tmp_path)
        )

        summary = result["execution_summary"]
        assert summary["tools_requested"] == 1
        assert summary["tools_failed"] == 1
        assert summary["tools_executed"] == 0
        assert summary["tools_unavailable"] == 0
        assert (
            summary["tools_failed"] + summary["tools_executed"] + summary["tools_unavailable"]
            == summary["tools_requested"]
        )

    def test_mixed_success_and_failure_invariant_holds(
        self, main_server_module, monkeypatch, tmp_path
    ):
        """One failing and one succeeding tool: counts partition correctly
        and the requested/executed/failed/unavailable invariant holds."""
        run_results = {
            "ruff": {
                "success": False,
                "stdout": "",
                "stderr": "Task 'ruff-check' not found",
                "exit_code": 1,
                "execution_time": 0.01,
                "quality_intelligence": {"tool_name": "ruff"},
            },
            "mypy": {
                "success": True,
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 0.02,
                "quality_intelligence": {"tool_name": "mypy"},
            },
        }
        fake_pixi_adapter = _FakePixiAdapter(run_results, available_tools={"ruff", "mypy"})
        monkeypatch.setattr(main_server_module, "orchestration_service", object())
        monkeypatch.setattr(main_server_module, "container", _FakeContainer(fake_pixi_adapter))

        result = main_server_module.quality_execute_pixi_aware_assessment.fn(
            tools=["ruff", "mypy"], project_path=str(tmp_path)
        )

        summary = result["execution_summary"]
        assert summary["tools_requested"] == 2
        assert summary["tools_failed"] == 1
        assert summary["tools_executed"] == 1
        assert summary["tools_unavailable"] == 0
        assert (
            summary["tools_failed"] + summary["tools_executed"] + summary["tools_unavailable"]
            == summary["tools_requested"]
        )

    def test_failed_tool_produces_naming_recommendation(
        self, main_server_module, monkeypatch, tmp_path
    ):
        """When a tool fails, a recommendation naming it and the failure
        reason must be present -- so a caller reading only `recommendations`
        still sees the failure, instead of an unqualified success."""
        run_results = {
            "ruff": {
                "success": False,
                "stdout": "",
                "stderr": "Task 'ruff-check' not found. Available tasks: ['lint']",
                "exit_code": 1,
                "execution_time": 0.01,
                "quality_intelligence": {"tool_name": "ruff"},
            }
        }
        fake_pixi_adapter = _FakePixiAdapter(run_results, available_tools={"ruff"})
        monkeypatch.setattr(main_server_module, "orchestration_service", object())
        monkeypatch.setattr(main_server_module, "container", _FakeContainer(fake_pixi_adapter))

        result = main_server_module.quality_execute_pixi_aware_assessment.fn(
            tools=["ruff"], project_path=str(tmp_path)
        )

        assert any(
            "ruff" in rec and "not found" in rec for rec in result["recommendations"]
        )

    def test_no_failures_produces_no_failure_recommendation(
        self, main_server_module, monkeypatch, tmp_path
    ):
        """A fully successful run must not fabricate a failure recommendation."""
        run_results = {
            "mypy": {
                "success": True,
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "execution_time": 0.02,
                "quality_intelligence": {"tool_name": "mypy"},
            }
        }
        fake_pixi_adapter = _FakePixiAdapter(run_results, available_tools={"mypy"})
        monkeypatch.setattr(main_server_module, "orchestration_service", object())
        monkeypatch.setattr(main_server_module, "container", _FakeContainer(fake_pixi_adapter))

        result = main_server_module.quality_execute_pixi_aware_assessment.fn(
            tools=["mypy"], project_path=str(tmp_path)
        )

        assert result["execution_summary"]["tools_failed"] == 0
        assert not any(
            rec.startswith("Quality tool execution failed for:")
            for rec in result["recommendations"]
        )
