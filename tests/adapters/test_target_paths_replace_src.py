"""
target_paths must REPLACE the hard-coded src/ of a pixi task body (not add to it)
for ruff, mypy, bandit and vulture.

Run with: pixi run python -m pytest tests/adapters/test_target_paths_replace_src.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter  # noqa: E402
from adapters.quality_tool_execution import QualityToolExecutionAdapter  # noqa: E402
from core.models import QualityTool  # noqa: E402

BODIES = {
    "lint": "ruff check src/ tests/ --select=F,E9",
    "typecheck": "mypy src/",
    "security-scan": "bandit -r src/ --severity-level high --exclude tests/",
    "dead-code": "vulture src/ --min-confidence 80",
}


class FakeExecutor:
    working_dir = "/proj"
    _split_task_body = staticmethod(DirectPixiExecutionAdapter._split_task_body)
    _parse_task_body_args = DirectPixiExecutionAdapter._parse_task_body_args

    def __init__(self):
        self.calls = []

    def resolve_task_name(self, tool, working_dir=None, environment=None):
        return {"ruff": "lint", "mypy": "typecheck", "bandit": "security-scan"}[tool]

    def select_quality_environment(self, task, working_dir=None, candidates=None):
        return "quality", "test"

    def task_exists(self, task, *args, **kwargs):
        return {"exists": True}

    def _get_available_tasks(self, path, environment=None):
        return dict(BODIES)

    def run_task(self, task_name, args=None, **kwargs):
        self.calls.append((task_name, list(args or []), kwargs))
        return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}


def _run(tool, target_paths):
    executor = FakeExecutor()
    adapter = QualityToolExecutionAdapter(executor)
    if tool == QualityTool.RUFF:
        adapter.execute_lint_assessment(tool=tool, target_paths=target_paths)
    elif tool == QualityTool.MYPY:
        adapter.execute_typecheck_assessment(tool=tool, target_paths=target_paths)
    elif tool == QualityTool.BANDIT:
        adapter.execute_security_scan(tool=tool, target_paths=target_paths)
    else:
        adapter.execute_dead_code_detection(tool=tool, target_paths=target_paths)
    return executor.calls[0]


@pytest.mark.parametrize(
    "tool",
    [QualityTool.RUFF, QualityTool.MYPY, QualityTool.BANDIT, QualityTool.VULTURE],
)
def test_target_paths_replace_src_in_argv(tool):
    name, args, kwargs = _run(tool, ["tests/"])

    assert name == tool.value
    assert kwargs.get("as_command") is True
    assert kwargs["environment"] == "quality"
    assert "src/" not in args
    assert "tests/" in args


def test_ruff_keeps_task_flags_and_swaps_paths():
    _, args, _ = _run(QualityTool.RUFF, ["lib/", "scripts/"])

    assert args[:3] == ["check", "lib/", "scripts/"]
    assert "--select=F,E9" in args
    assert "tests/" not in args


def test_bandit_keeps_recursive_flag_and_exclude():
    _, args, _ = _run(QualityTool.BANDIT, ["lib/"])

    assert args[:2] == ["-r", "lib/"]
    assert "--severity-level" in args
    assert args[args.index("--exclude") + 1] == "tests/"


@pytest.mark.parametrize(
    "tool",
    [QualityTool.RUFF, QualityTool.MYPY, QualityTool.BANDIT, QualityTool.VULTURE],
)
def test_default_runs_the_task_unchanged(tool):
    name, args, kwargs = _run(tool, None)

    assert name in BODIES
    assert "as_command" not in kwargs
