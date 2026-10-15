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
    with patch(
        "adapters.direct_pixi_execution.subprocess.run", return_value=proc
    ) as mock_run:
        result = adapter.run_quality_task(
            task_name=task_name, quality_tool=tool, target_paths=["src/"], **kwargs
        )
    return result, mock_run


FULL_COMMAND_CASES = [
    (
        "lint",
        "ruff",
        "pixi run -e quality ruff check src/ tests/ --select=F,E9",
        ["ruff", "check", "src/", "tests/", "--select=F,E9", "--output-format", "json"],
    ),
    (
        "typecheck",
        "mypy",
        "pixi run -e quality mypy src/",
        ["mypy", "src/", "--output", "json"],
    ),
    (
        "security-scan",
        "bandit",
        "bandit -r src/ --severity-level high --exclude tests/",
        [
            "bandit",
            "-r",
            "src/",
            "--severity-level",
            "high",
            "--exclude",
            "tests/",
            "-f",
            "json",
        ],
    ),
]


class TestFullCommandBodyRunsToolDirectly:
    @pytest.mark.parametrize("task,tool,body,expected_tail", FULL_COMMAND_CASES)
    def test_explicit_environment_used(self, task, tool, body, expected_tail):
        adapter = _make_adapter({task: body})
        result, mock_run = _run(
            adapter,
            task,
            tool,
            environment="quality",
            quality_config={"output_format": "json"},
        )
        argv = mock_run.call_args[0][0]
        assert argv[1:] == ["run", "--environment", "quality"] + expected_tail
        assert task not in argv
        assert result["task_body_mode"] == "direct_tool"

    def test_environment_selected_when_not_given(self):
        task, tool, body, expected_tail = FULL_COMMAND_CASES[0]
        body = body.replace("pixi run -e quality ", "")  # no -e in the body
        adapter = _make_adapter({task: body}, declared_envs="quality")
        _, mock_run = _run(
            adapter, task, tool, quality_config={"output_format": "json"}
        )
        argv = mock_run.call_args[0][0]
        assert argv[1:] == ["run", "--environment", "quality"] + expected_tail
        adapter.select_quality_environment.assert_called_once()

    def test_no_environment_available_omits_flag(self):
        task, tool, body, expected_tail = FULL_COMMAND_CASES[1]
        body = body.replace("pixi run -e quality ", "")  # no -e in the body
        adapter = _make_adapter({task: body}, declared_envs=None)
        _, mock_run = _run(
            adapter, task, tool, quality_config={"output_format": "json"}
        )
        assert mock_run.call_args[0][0][1:] == ["run"] + expected_tail

    def test_cmd_list_body(self):
        # _get_available_tasks yields a list for a table body with `cmd = [...]`.
        adapter = _make_adapter({"lint": ["ruff", "check", "src/"]})
        _, mock_run = _run(adapter, "lint", "ruff", environment="quality")
        assert mock_run.call_args[0][0][1:5] == [
            "run",
            "--environment",
            "quality",
            "ruff",
        ]


class TestBareToolBodyKeepsTaskInvocation:
    @pytest.mark.parametrize(
        "task,tool",
        [("lint", "ruff"), ("typecheck", "mypy"), ("security-scan", "bandit")],
    )
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


RUFF_JSON = (
    '[{"code": "F401", "filename": "src/a.py"}, {"code": "E9", "filename": "src/b.py"}]'
)
MYPY_TEXT = "src/a.py:3: error: bad type  [assignment]\nsrc/a.py:9: error: other  [arg-type]\nFound 2 errors\n"
BANDIT_JSON = (
    '{"results": [{"test_id": "B105"}, {"test_id": "B101"}, {"test_id": "B602"}]}'
)


def _run_with_exit(tool, code, stdout, stderr=""):
    adapter = _make_adapter({"t": f"pixi run -e quality {tool} src/"})
    proc = Mock(returncode=code, stdout=stdout, stderr=stderr)
    with patch("adapters.direct_pixi_execution.subprocess.run", return_value=proc):
        return adapter.run_quality_task(
            task_name="t",
            quality_tool=tool,
            target_paths=["src/"],
            quality_config={"output_format": "json"},
            environment="quality",
        )


class TestFindingsVersusToolCrash:
    """Exit 1 with parseable output is "ran and found issues": counts are kept
    but the run still fails. Any other non-zero exit is a crash: no counts."""

    @pytest.mark.parametrize(
        "tool,stdout,key,count",
        [
            ("ruff", RUFF_JSON, "violation_count", 2),
            ("mypy", MYPY_TEXT, "error_count", 2),
            ("bandit", BANDIT_JSON, "issue_count", 3),
        ],
    )
    def test_findings_keep_counts_and_still_fail(self, tool, stdout, key, count):
        result = _run_with_exit(tool, 1, stdout)
        assert result["success"] is False
        assert result["exit_code"] == 1
        assert result["findings_detected"] is True
        assert result["parsed_output"][key] == count

    @pytest.mark.parametrize(
        "tool,stdout",
        [
            ("ruff", ""),
            ("mypy", "usage: mypy ...\nmypy: error: unrecognized arguments\n"),
            ("bandit", "bandit: error: bad option"),
        ],
    )
    def test_crash_exit_2_has_no_counts(self, tool, stdout):
        result = _run_with_exit(tool, 2, stdout, stderr="boom")
        assert result["success"] is False
        assert "parsed_output" not in result
        assert "findings_detected" not in result

    @pytest.mark.parametrize("tool", ["ruff", "bandit"])
    def test_exit_1_with_unparseable_output_is_not_findings(self, tool):
        result = _run_with_exit(tool, 1, "Traceback: something broke")
        assert "parsed_output" not in result
        assert "findings_detected" not in result

    def test_command_not_found_has_no_counts(self):
        result = _run_with_exit("bandit", 127, "", stderr="bandit: command not found")
        assert "parsed_output" not in result


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
        args = self._adapter()._generate_bandit_args(
            ["src/"], {"output_format": "json"}
        )
        assert args == ["-r", "-f", "json", "src/"]
