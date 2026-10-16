"""
Error-path regression tests for QualityToolExecutionAdapter.

When no pixi task resolves, the not-found diagnostic itself can fail (for
example listing tasks raises). The generic except handler then reports the
failure with pixi_task_used=None. "No task resolved" is a legitimate state, so
the result model must accept it instead of raising a validation error out of
the error path.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from adapters.quality_tool_execution import QualityToolExecutionAdapter  # noqa: E402
from core.models import ExecutionStatus, QualityTool  # noqa: E402


class _UnresolvableExecutor:
    """Resolves no task and cannot list tasks, so the diagnostic raises."""

    def resolve_task_name(self, tool_or_candidates, working_dir=None, environment=None):
        return None

    def list_tasks(self, working_dir=None):
        raise RuntimeError("cannot list tasks")


@pytest.mark.parametrize(
    ("method", "tool"),
    [
        ("execute_lint_assessment", QualityTool.RUFF),
        ("execute_typecheck_assessment", QualityTool.MYPY),
        ("execute_security_scan", QualityTool.BANDIT),
        ("execute_complexity_analysis", QualityTool.RADON),
    ],
)
def test_error_result_allows_unresolved_pixi_task(method, tool):
    adapter = QualityToolExecutionAdapter(direct_pixi_executor=_UnresolvableExecutor())

    result = getattr(adapter, method)(tool=tool, project_path="/tmp/project")

    assert result.status == ExecutionStatus.ERROR
    assert result.pixi_task_used is None
    assert "cannot list tasks" in result.raw_output
