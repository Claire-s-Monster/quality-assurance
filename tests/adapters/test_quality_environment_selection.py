"""Tests for automatic pixi environment selection for quality assessments."""

import textwrap
from unittest.mock import MagicMock

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from adapters.quality_tool_execution import QualityToolExecutionAdapter
from core.models import QualityTool


def _executor(tmp_path, manifest: str) -> DirectPixiExecutionAdapter:
    (tmp_path / "pyproject.toml").write_text(textwrap.dedent(manifest))
    return DirectPixiExecutionAdapter(logging=MagicMock(), working_dir=str(tmp_path))


def test_top_level_task_selects_quality_over_dev(tmp_path):
    executor = _executor(
        tmp_path,
        """
        [tool.pixi.tasks]
        lint = "ruff check src/"

        [tool.pixi.environments]
        default = { features = [] }
        quality = ["quality"]
        dev = ["dev"]
        """,
    )
    assert executor.environments_for_task("lint") == ["default", "quality", "dev"]
    env, reason = executor.select_quality_environment("lint")
    assert env == "quality"
    assert reason


def test_feature_defined_task_selects_quality_ci(tmp_path):
    executor = _executor(
        tmp_path,
        """
        [tool.pixi.feature.linting.tasks]
        lint = "ruff check src/"

        [tool.pixi.environments]
        dev = ["linting"]
        ci = ["linting"]
        quality-ci = ["linting"]
        quality-extended = ["linting"]
        """,
    )
    assert executor.environments_for_task("lint") == [
        "dev",
        "ci",
        "quality-ci",
        "quality-extended",
    ]
    env, _ = executor.select_quality_environment("lint")
    assert env == "quality-ci"


def test_no_named_environments_selects_none(tmp_path):
    executor = _executor(
        tmp_path,
        """
        [tool.pixi.tasks]
        lint = "ruff check src/"
        """,
    )
    env, reason = executor.select_quality_environment("lint")
    assert env is None
    assert reason


def test_no_preferred_candidate_is_ambiguous(tmp_path):
    executor = _executor(
        tmp_path,
        """
        [tool.pixi.tasks]
        lint = "ruff check src/"

        [tool.pixi.environments]
        foo = ["foo"]
        bar = ["bar"]
        """,
    )
    assert executor.environments_for_task("lint") == ["default", "foo", "bar"]
    env, reason = executor.select_quality_environment("lint")
    assert env is None
    assert "foo" in reason and "bar" in reason


def test_single_non_default_candidate_is_selected(tmp_path):
    executor = _executor(
        tmp_path,
        """
        [tool.pixi.feature.only.tasks]
        lint = "ruff check src/"

        [tool.pixi.environments]
        custom = ["only"]
        other = []
        """,
    )
    env, _ = executor.select_quality_environment("lint")
    assert env == "custom"


class _RecordingExecutor:
    def __init__(self, selection):
        self.selection = selection
        self.run_environments = []
        self.select_calls = 0

    def resolve_task_name(self, tool_or_candidates, working_dir=None, environment=None):
        return "lint"

    def select_quality_environment(self, task_name, working_dir=None):
        self.select_calls += 1
        return self.selection

    def run_task(
        self, task_name, args=None, timeout=300, working_dir=None, environment=None
    ):
        self.run_environments.append(environment)
        return {"success": True, "stdout": "{}", "stderr": "", "exit_code": 0}


def test_explicit_environment_is_never_overridden():
    executor = _RecordingExecutor(("quality", "preferred"))
    result = QualityToolExecutionAdapter(executor).execute_lint_assessment(
        tool=QualityTool.RUFF, environment="dev"
    )
    assert executor.run_environments == ["dev"]
    assert executor.select_calls == 0
    assert result.environment_used == "dev"
    assert result.environment_auto_selected is False


def test_auto_selected_environment_is_passed_and_surfaced():
    executor = _RecordingExecutor(("quality", "preferred candidate"))
    result = QualityToolExecutionAdapter(executor).execute_lint_assessment(
        tool=QualityTool.RUFF
    )
    assert executor.run_environments == ["quality"]
    assert result.environment_used == "quality"
    assert result.environment_auto_selected is True
    assert any(
        "No environment given; ran 'lint' in pixi environment 'quality'" in r
        for r in result.recommendations
    )


def test_no_selection_keeps_environment_unset():
    executor = _RecordingExecutor((None, "ambiguous"))
    result = QualityToolExecutionAdapter(executor).execute_lint_assessment(
        tool=QualityTool.RUFF
    )
    assert executor.run_environments == [None]
    assert result.environment_used is None
    assert result.environment_auto_selected is False


@pytest.mark.parametrize("method", ["typecheck", "security", "complexity"])
def test_other_assessments_also_auto_select(method):
    executor = _RecordingExecutor(("quality", "preferred candidate"))
    adapter = QualityToolExecutionAdapter(executor)
    result = {
        "typecheck": adapter.execute_typecheck_assessment,
        "security": adapter.execute_security_scan,
        "complexity": adapter.execute_complexity_analysis,
    }[method]()
    assert executor.run_environments[0] == "quality"
    assert result.environment_used == "quality"
    assert result.environment_auto_selected is True
