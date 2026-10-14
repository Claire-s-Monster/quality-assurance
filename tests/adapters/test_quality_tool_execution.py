"""
Unit tests for QualityToolExecutionAdapter's pixi task resolution.

Covers the fix where four assessment methods hardcoded a single pixi task
name per tool (e.g. bandit -> "security"), which breaks against any target
project that names its tasks differently (e.g. "security-scan"). Task
resolution now goes through DirectPixiExecutionAdapter.resolve_task_name /
TOOL_TASK_ALIASES so the first alias that actually exists in the target
project is used, with a diagnostic listing every candidate tried when none
resolve.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from adapters.direct_pixi_execution import TOOL_TASK_ALIASES  # noqa: E402
from adapters.quality_tool_execution import QualityToolExecutionAdapter  # noqa: E402
from core.models import ExecutionStatus  # noqa: E402


class _FakePixiExecutor:
    """Minimal stand-in for DirectPixiExecutionAdapter's task-related surface."""

    def __init__(self, available_tasks: dict, run_result: dict | None = None):
        self._available_tasks = available_tasks
        self._run_result = run_result or {
            "success": True,
            "stdout": "{}",
            "stderr": "",
            "exit_code": 0,
        }

    def task_exists(self, task_name, working_dir=None, environment=None):
        return {"exists": task_name in self._available_tasks}

    def resolve_task_name(self, tool_or_candidates, working_dir=None, environment=None):
        if isinstance(tool_or_candidates, str):
            candidates = list(TOOL_TASK_ALIASES.get(tool_or_candidates, (tool_or_candidates,)))
        else:
            candidates = list(tool_or_candidates)
        for candidate in candidates:
            if candidate in self._available_tasks:
                return candidate
        return None

    def select_quality_environment(self, task_name, working_dir=None):
        return None, "fake executor declares no environments"

    def list_tasks(self, working_dir=None):
        return {"tasks": dict(self._available_tasks)}

    def run_task(self, task_name, args=None, timeout=300, working_dir=None, environment=None):
        return dict(self._run_result)


class TestSecurityScanTaskResolution:
    """execute_security_scan must resolve bandit's task through aliases,
    not the old hardcoded "security" name."""

    def test_resolves_security_scan_alias_when_only_it_exists(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"security-scan": "bandit -r src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.pixi_task_used == "security-scan"
        assert result.status != ExecutionStatus.ERROR

    def test_resolves_literal_bandit_alias_when_only_it_exists(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"bandit": "bandit -r src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.pixi_task_used == "bandit"

    def test_not_found_message_lists_candidates_and_available_tasks(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"lint": "ruff check src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status == ExecutionStatus.ERROR
        assert "security-scan" in result.raw_output
        assert "security" in result.raw_output
        assert "bandit" in result.raw_output
        assert "lint" in result.raw_output


class TestTypecheckTaskResolution:
    """execute_typecheck_assessment must resolve mypy's task through
    aliases (typecheck / mypy / type-check), not a single hardcoded name."""

    def test_resolves_typecheck_alias(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"typecheck": "mypy src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_typecheck_assessment(project_path="/tmp/project")

        assert result.pixi_task_used == "typecheck"

    def test_not_found_when_no_alias_defined(self):
        pixi_executor = _FakePixiExecutor(available_tasks={})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_typecheck_assessment(project_path="/tmp/project")

        assert result.status == ExecutionStatus.ERROR
        assert "typecheck" in result.raw_output
        assert "type-check" in result.raw_output


class TestSecurityScanHonestFailure:
    """execute_security_scan must not report a clean/scored result when bandit
    never actually ran, and must not treat bandit's exit-1-on-findings as an
    execution failure (same pattern as lint/typecheck, commit 4d9d638d)."""

    def test_real_execution_failure_is_reported_as_error_not_clean_score(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"},
            run_result={
                "success": False,
                "stdout": "",
                "stderr": "bandit: command not found",
                "exit_code": 127,
            },
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status == ExecutionStatus.ERROR
        assert result.parsed_metrics.overall_score == 0.0
        assert "No security vulnerabilities detected." not in result.recommendations

    def test_findings_on_nonzero_exit_are_not_swallowed_as_execution_error(self):
        bandit_json = (
            '{"results": [{"test_id": "B105", "test_name": "hardcoded_password_string", '
            '"issue_text": "Possible hardcoded password", "issue_severity": "HIGH", '
            '"issue_confidence": "HIGH", "filename": "src/app.py", "line_number": 12}]}'
        )
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"},
            run_result={
                "success": False,
                "stdout": bandit_json,
                "stderr": "",
                "exit_code": 1,
            },
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status != ExecutionStatus.ERROR
        assert result.status == ExecutionStatus.WARNING
        assert len(result.security_issues) == 1
        assert result.parsed_metrics.overall_score != 10.0

    def test_clean_scan_with_zero_findings_stays_clean(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"},
            run_result={
                "success": True,
                "stdout": '{"results": []}',
                "stderr": "",
                "exit_code": 0,
            },
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status == ExecutionStatus.SUCCESS
        assert result.parsed_metrics.overall_score == 10.0


class TestComplexityTaskResolution:
    """execute_complexity_analysis must resolve radon's task through
    aliases (complexity-check / complexity / radon)."""

    def test_resolves_complexity_check_alias(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"complexity-check": "radon cc src/"},
            run_result={"success": True, "stdout": "{}", "stderr": "", "exit_code": 0},
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_complexity_analysis(project_path="/tmp/project")

        assert result.pixi_task_used == "complexity-check"
