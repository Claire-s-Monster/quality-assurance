#!/usr/bin/env python3
"""
Tests for quality_execute_pixi_aware_assessment: execution_summary /
recommendations must agree with gate_verdict, and summary_only must trim the
fixed environment_info / optimization_result / pixi_intelligence blocks.

Run with: pixi run python -m pytest tests/test_pixi_aware_summary_accounting.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class _FakeEnvInfo:
    def __init__(self, available_tools):
        self.available_tools = available_tools
        self.quality_tasks = {"lint": "ruff check"}
        self.environment_health = "optimal"
        self.tool_versions = {"ruff": "0.1"}
        self.performance_indicators = {"speed": "fast"}
        self.recommendations = []


class _FakeTemplate:
    def __init__(self, task_name: str):
        self.task_name = task_name
        self.output_format = "json"


class _FakePixiAdapter:
    def __init__(self, run_results, available_tools):
        self._run_results = run_results
        self.detect_quality_environment = Mock(
            return_value=_FakeEnvInfo(available_tools)
        )
        self.optimize_quality_environment = Mock(
            return_value={"actions": ["a", "b"], "notes": "x" * 300}
        )
        self.generate_quality_task_template = Mock(
            side_effect=lambda tool_name, target_pattern: _FakeTemplate(
                f"{tool_name}-task"
            )
        )
        self.resolve_task_name = Mock(return_value=None)

    def run_quality_task(self, **kwargs):
        return self._run_results[kwargs["quality_tool"]]


class _FakeContainer:
    def __init__(self, pixi_adapter):
        self.pixi_executor = pixi_adapter


@pytest.fixture
def server_module():
    from quality_assurance import server

    return server


_MYPY_FINDINGS = {
    "success": False,
    "exit_code": 1,
    "stdout": "",
    "stderr": "",
    "findings_detected": True,
    "parsed_output": {"issue_count": 4272},
}
_BANDIT_FINDINGS = {
    "success": False,
    "exit_code": 1,
    "stdout": "",
    "stderr": "",
    "findings_detected": True,
    "parsed_output": {"severity_counts": {"HIGH": 1, "MEDIUM": 2, "LOW": 1}},
}
_RUFF_PASS = {"success": True, "exit_code": 0, "stdout": "", "stderr": ""}
_CRASH = {"success": False, "exit_code": 2, "stdout": "", "stderr": "boom"}


def _run(server, monkeypatch, tmp_path, run_results, tools, **kwargs):
    adapter = _FakePixiAdapter(run_results, available_tools=set(run_results))
    monkeypatch.setattr(server, "orchestration_service", object())
    monkeypatch.setattr(server, "container", _FakeContainer(adapter))
    return server.quality_execute_pixi_aware_assessment.fn(
        tools=tools, project_path=str(tmp_path), **kwargs
    )


class TestFindingsAccounting:
    def test_findings_counted_as_executed_not_failed(
        self, server_module, monkeypatch, tmp_path
    ):
        result = _run(
            server_module,
            monkeypatch,
            tmp_path,
            {"mypy": _MYPY_FINDINGS, "bandit": _BANDIT_FINDINGS, "ruff": _RUFF_PASS},
            ["mypy", "bandit", "ruff"],
        )
        summary = result["execution_summary"]
        assert result["gate_verdict"] == "findings"
        assert summary["tools_executed"] == 3
        assert summary["tools_with_findings"] == 2
        assert summary["tools_failed"] == 0
        assert summary["tools_unavailable"] == 0

    def test_no_execution_failed_recommendation_for_findings(
        self, server_module, monkeypatch, tmp_path
    ):
        result = _run(
            server_module,
            monkeypatch,
            tmp_path,
            {"mypy": _MYPY_FINDINGS, "bandit": _BANDIT_FINDINGS},
            ["mypy", "bandit"],
        )
        recs = result["recommendations"]
        assert not any("execution failed" in r for r in recs)
        assert not any("exit_code=1" in r for r in recs)
        findings_lines = [r for r in recs if r.startswith("Findings reported by:")]
        assert len(findings_lines) == 1
        assert "mypy (4272 errors)" in findings_lines[0]
        assert "bandit (HIGH 1, MEDIUM 2, LOW 1)" in findings_lines[0]

    def test_failed_recommendation_lists_only_errored_tools(
        self, server_module, monkeypatch, tmp_path
    ):
        result = _run(
            server_module,
            monkeypatch,
            tmp_path,
            {"mypy": _MYPY_FINDINGS, "ruff": _CRASH},
            ["mypy", "ruff"],
        )
        summary = result["execution_summary"]
        assert summary["tools_failed"] == 1
        assert summary["tools_executed"] == 1
        assert summary["tools_with_findings"] == 1
        failed = [
            r
            for r in result["recommendations"]
            if r.startswith("Quality tool execution failed for:")
        ]
        assert len(failed) == 1
        assert "ruff" in failed[0]
        assert "mypy" not in failed[0]

    def test_clean_run_has_zero_findings_count(
        self, server_module, monkeypatch, tmp_path
    ):
        result = _run(
            server_module, monkeypatch, tmp_path, {"ruff": _RUFF_PASS}, ["ruff"]
        )
        assert result["execution_summary"]["tools_with_findings"] == 0
        assert not any(
            r.startswith("Findings reported by:") for r in result["recommendations"]
        )


class TestSummaryOnlyTrimsFixedBlocks:
    def test_summary_only_omits_fixed_blocks(
        self, server_module, monkeypatch, tmp_path
    ):
        result = _run(
            server_module,
            monkeypatch,
            tmp_path,
            {"mypy": _MYPY_FINDINGS, "bandit": _BANDIT_FINDINGS, "ruff": _RUFF_PASS},
            ["mypy", "bandit", "ruff"],
            summary_only=True,
        )
        for key in ("environment_info", "optimization_result", "pixi_intelligence"):
            assert key not in result

    def test_summary_only_small_response(self, server_module, monkeypatch, tmp_path):
        result = _run(
            server_module,
            monkeypatch,
            tmp_path,
            {"mypy": _MYPY_FINDINGS, "bandit": _BANDIT_FINDINGS, "ruff": _RUFF_PASS},
            ["mypy", "bandit", "ruff"],
            summary_only=True,
        )
        entries = result["assessment_results"]
        assert len(entries) == 3
        required = {"task_name", "exit_code", "findings_detected", "counts"}
        allowed = required | {"error"}
        for entry in entries:
            assert required <= set(entry) <= allowed
        # Measured 972 chars for 3 tools (whole response); 1500 leaves ~50% margin.
        size = len(json.dumps(result))
        assert size < 1500, size

    def test_default_output_keeps_fixed_blocks(
        self, server_module, monkeypatch, tmp_path
    ):
        result = _run(
            server_module, monkeypatch, tmp_path, {"ruff": _RUFF_PASS}, ["ruff"]
        )
        for key in ("environment_info", "optimization_result", "pixi_intelligence"):
            assert isinstance(result[key], dict), key
            assert result[key], key
        assert "available_tools" in result["environment_info"]
        assert "templates_used" in result["pixi_intelligence"]
