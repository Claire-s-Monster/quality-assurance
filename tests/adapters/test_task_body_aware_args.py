"""
Tests for body-aware argument handling in run_quality_task.

Appending a tool's own args (`check --output-format json src/`) to a pixi task
is only valid when the task body is the bare tool. When the body is a full
command, the tool must be run directly in the right environment instead.
"""

from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter


def _make_adapter(tasks, declared_envs=None) -> DirectPixiExecutionAdapter:
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
    adapter._is_pixi_project = Mock(return_value=True)
    adapter._get_available_tasks = Mock(return_value=tasks)
    adapter.select_quality_environment = Mock(return_value=(declared_envs, "test"))
    env_info = Mock()
    env_info.available_tools = {"ruff", "mypy", "bandit"}
    env_info.tool_versions = {}
    env_info.environment_health = "optimal"
    env_info.performance_indicators = {}
    env_info.recommendations = []
    env_info.missing_tools = set()
    adapter.detect_quality_environment = Mock(return_value=env_info)
    return adapter


def _run(adapter, task_name, tool, **kwargs):
    proc = Mock(returncode=1, stdout="", stderr="")
    with patch("adapters.direct_pixi_execution.subprocess.run", return_value=proc) as mock_run:
        result = adapter.run_quality_task(
            task_name=task_name, quality_tool=tool, target_paths=["src/"], **kwargs
        )
    return result, mock_run


FULL_COMMAND_CASES = [
    ("lint", "ruff", "pixi run -e quality ruff check src/ tests/ --select=F,E9",
     ["ruff", "check", "--output-format", "json", "src/"]),
    ("typecheck", "mypy", "pixi run -e quality mypy src/",
     ["mypy", "--output", "json", "src/"]),
    ("security-scan", "bandit", "bandit -r src/ --severity-level high --exclude tests/",
     ["bandit", "-r", "-f", "json", "src/"]),
]


class TestFullCommandBodyRunsToolDirectly:
    @pytest.mark.parametrize("task,tool,body,expected_tail", FULL_COMMAND_CASES)
    def test_explicit_environment_used(self, task, tool, body, expected_tail):
        adapter = _make_adapter({task: body})
        result, mock_run = _run(
            adapter, task, tool, environment="quality",
            quality_config={"output_format": "json"},
        )
        argv = mock_run.call_args[0][0]
        assert argv[1:] == ["run", "--environment", "quality"] + expected_tail
        assert task not in argv
        assert result["task_body_mode"] == "direct_tool"

    def test_environment_selected_when_not_given(self):
        task, tool, body, expected_tail = FULL_COMMAND_CASES[0]
        adapter = _make_adapter({task: body}, declared_envs="quality")
        _, mock_run = _run(adapter, task, tool, quality_config={"output_format": "json"})
        argv = mock_run.call_args[0][0]
        assert argv[1:] == ["run", "--environment", "quality"] + expected_tail
        adapter.select_quality_environment.assert_called_once()

    def test_no_environment_available_omits_flag(self):
        task, tool, body, expected_tail = FULL_COMMAND_CASES[1]
        adapter = _make_adapter({task: body}, declared_envs=None)
        _, mock_run = _run(adapter, task, tool, quality_config={"output_format": "json"})
        assert mock_run.call_args[0][0][1:] == ["run"] + expected_tail

    def test_cmd_list_body(self):
        # _get_available_tasks yields a list for a table body with `cmd = [...]`.
        adapter = _make_adapter({"lint": ["ruff", "check", "src/"]})
        _, mock_run = _run(adapter, "lint", "ruff", environment="quality")
        assert mock_run.call_args[0][0][1:5] == ["run", "--environment", "quality", "ruff"]


class TestBareToolBodyKeepsTaskInvocation:
    @pytest.mark.parametrize("task,tool", [("lint", "ruff"), ("typecheck", "mypy"), ("security-scan", "bandit")])
    def test_string_body(self, task, tool):
        adapter = _make_adapter({task: tool})
        result, mock_run = _run(adapter, task, tool, environment="quality")
        argv = mock_run.call_args[0][0]
        assert argv[1:4] == ["run", "--environment", "quality"]
        assert argv[4] == task
        assert result["task_body_mode"] == "task"

    def test_list_body(self):
        adapter = _make_adapter({"lint": ["ruff"]})
        _, mock_run = _run(adapter, "lint", "ruff", environment="quality")
        assert mock_run.call_args[0][0][4] == "lint"


class TestUnreadableBody:
    def test_reports_failure_without_running_anything(self):
        adapter = _make_adapter({"lint": 42})
        result, mock_run = _run(adapter, "lint", "ruff", environment="quality")
        mock_run.assert_not_called()
        assert result["success"] is False
        assert "body" in result["stderr"]


class TestArgBuilders:
    def _adapter(self):
        return DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")

    def test_mypy_default(self):
        assert self._adapter()._generate_mypy_args(["src/"], {}) == ["src/"]

    def test_mypy_strict_and_json(self):
        args = self._adapter()._generate_mypy_args(
            ["src/", "lib/"], {"strict_mode": True, "output_format": "json"}
        )
        assert args == ["--strict", "--output", "json", "src/", "lib/"]

    def test_bandit_default(self):
        assert self._adapter()._generate_bandit_args(["src/"], {}) == ["-r", "src/"]

    def test_bandit_json(self):
        args = self._adapter()._generate_bandit_args(["src/"], {"output_format": "json"})
        assert args == ["-r", "-f", "json", "src/"]
