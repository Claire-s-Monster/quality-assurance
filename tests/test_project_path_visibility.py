#!/usr/bin/env python3
"""
Regression tests for project_path default-visibility (server.py).

Covers the fix where omitting project_path on the assessment tools silently
analyzed the server's own working directory and returned a confident
"success" with no indication that the caller's intended project was never
touched. project_path stays optional (backward compatible), but the
resolved directory and whether it was supplied are now always surfaced in
the response, with a warning prepended to recommendations when defaulted.

Also covers the quality_execute_pixi_aware_assessment project_path/environment
guard added alongside the QualityTaskTemplate.get() AttributeError fix.

Run with: pixi run python -m pytest tests/test_project_path_visibility.py -v
"""

import sys
from pathlib import Path

import pytest

# Add source paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import ExecutionStatus, QualityTool  # noqa: E402


class _FakeMetrics:
    def dict(self):
        return {}


class _FakeLintResult:
    """Minimal stand-in for QualityAssessmentResult, enough for the lint
    tool's success-path response construction."""

    def __init__(self):
        self.tool = QualityTool.RUFF
        self.status = ExecutionStatus.SUCCESS
        self.execution_time_ms = 5
        self.pixi_task_used = "lint"
        self.target_path = "src/"
        self.files_analyzed = 0
        self.violations = []
        self.parsed_metrics = _FakeMetrics()
        self.auto_fix_available = False
        self.recommendations = []


class _FakePixiExecutor:
    def __init__(self, working_dir):
        self.working_dir = working_dir


class _FakeQualityExecutor:
    def __init__(self, working_dir):
        self.pixi_executor = _FakePixiExecutor(working_dir)


class _FakeOrchestrationService:
    """Stands in for the real QualityOrchestrationService so tests don't
    need a real pixi project / subprocess execution to exercise the
    project_path visibility fields."""

    def __init__(self, working_dir):
        self.quality_executor = _FakeQualityExecutor(working_dir)

    def execute_lint_assessment(self, **kwargs):
        return _FakeLintResult()


@pytest.fixture
def main_server_module():
    from quality_assurance import server as main_server

    return main_server


class TestLintAssessmentProjectPathVisibility:
    def test_supplied_project_path_is_marked_supplied_with_no_warning(
        self, main_server_module, monkeypatch, tmp_path
    ):
        fake = _FakeOrchestrationService(working_dir="/fake/server/cwd")
        monkeypatch.setattr(main_server_module, "orchestration_service", fake)

        result = main_server_module.quality_execute_lint_assessment.fn(
            project_path=str(tmp_path)
        )

        assert result["project_path_supplied"] is True
        assert result["project_path_resolved"] == str(tmp_path)
        assert not any(
            rec.startswith("⚠️ project_path was not supplied")
            for rec in result["recommendations"]
        )

    def test_omitted_project_path_resolves_server_dir_and_prepends_warning(
        self, main_server_module, monkeypatch
    ):
        fake = _FakeOrchestrationService(working_dir="/fake/server/cwd")
        monkeypatch.setattr(main_server_module, "orchestration_service", fake)

        result = main_server_module.quality_execute_lint_assessment.fn()

        assert result["project_path_supplied"] is False
        assert result["project_path_resolved"] == "/fake/server/cwd"
        assert result["recommendations"], "expected a non-empty recommendations list"
        warning = result["recommendations"][0]
        assert warning.startswith("⚠️ project_path was not supplied")
        assert "/fake/server/cwd" in warning


class TestPixiAwareAssessmentGuard:
    def test_rejects_relative_project_path(self, main_server_module):
        result = main_server_module.quality_execute_pixi_aware_assessment.fn(
            project_path="relative/path"
        )

        assert result["status"] == "error"
        assert "Relative path" in result["error"]
        assert "not supported" in result["error"]

    def test_rejects_nonexistent_project_path(self, main_server_module, tmp_path):
        missing = str(tmp_path / "does-not-exist")

        result = main_server_module.quality_execute_pixi_aware_assessment.fn(
            project_path=missing
        )

        assert result["status"] == "error"
        assert missing in result["error"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
