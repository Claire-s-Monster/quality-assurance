"""
Tests for keeping a pixi task's own arguments and for picking an environment
that actually provides the tool when run_quality_task runs a full-command task
body directly.
"""

from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter

MANIFEST = """
[workspace]
name = "demo"
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
python = "*"

[feature.quality.dependencies]
ruff = "*"

[feature.quality.pypi-dependencies]
mypy = "*"

[feature.quality-extended.dependencies]
bandit = "*"

[environments]
quality = ["quality"]
quality-extended = ["quality", "quality-extended"]
quality-full = ["quality", "quality-extended"]
dev = ["quality", "quality-extended"]
"""

MANIFEST_NO_BANDIT = MANIFEST.replace('bandit = "*"', 'vulture = "*"')

TOOL_ARGS = {
    "ruff": "pixi run -e quality ruff check src/ tests/ --select=F,E9",
    "mypy": "pixi run -e quality mypy src/",
    "bandit": "bandit -r src/ --severity-level high --exclude tests/",
}
TASK_FOR = {"ruff": "lint", "mypy": "typecheck", "bandit": "security-scan"}


def _project(tmp_path, manifest=MANIFEST, tasks=None):
    tasks = tasks if tasks is not None else {}
    body = "\n[tasks]\n" + "".join(f"{k} = {v!r}\n" for k, v in tasks.items())
    (tmp_path / "pixi.toml").write_text(manifest + body)
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))
    env_info = Mock()
    env_info.available_tools = {"ruff", "mypy", "bandit"}
    env_info.tool_versions = {}
    env_info.environment_health = "optimal"
    env_info.performance_indicators = {}
    env_info.recommendations = []
    env_info.missing_tools = set()
    adapter.detect_quality_environment = Mock(return_value=env_info)
    return adapter


def _run(adapter, tool, body, **kwargs):
    proc = Mock(returncode=1, stdout="", stderr="")
    kwargs.setdefault("quality_config", {"output_format": "json"})
    with patch(
        "adapters.direct_pixi_execution.subprocess.run", return_value=proc
    ) as mock_run:
        result = adapter.run_quality_task(
            task_name=TASK_FOR[tool], quality_tool=tool, target_paths=["src/"], **kwargs
        )
    return result, mock_run


def _adapter_for(tmp_path, tool, body, manifest=MANIFEST):
    return _project(tmp_path, manifest, {TASK_FOR[tool]: body})


class TestTaskArgsKept:
    def test_ruff_keeps_paths_and_select(self, tmp_path):
        body = TOOL_ARGS["ruff"]
        result, mock_run = _run(_adapter_for(tmp_path, "ruff", body), "ruff", body)
        assert mock_run.call_args[0][0][1:] == [
            "run",
            "--environment",
            "quality",
            "ruff",
            "check",
            "src/",
            "tests/",
            "--select=F,E9",
            "--output-format",
            "json",
        ]
        assert result["task_args_mode"] == "task_args"

    def test_mypy_keeps_src_once(self, tmp_path):
        body = TOOL_ARGS["mypy"]
        _, mock_run = _run(_adapter_for(tmp_path, "mypy", body), "mypy", body)
        argv = mock_run.call_args[0][0]
        assert argv[1:] == [
            "run",
            "--environment",
            "quality",
            "mypy",
            "src/",
            "--output",
            "json",
        ]
        assert argv.count("src/") == 1

    def test_bandit_keeps_flags_and_picks_env_with_bandit(self, tmp_path):
        body = TOOL_ARGS["bandit"]
        result, mock_run = _run(_adapter_for(tmp_path, "bandit", body), "bandit", body)
        assert mock_run.call_args[0][0][1:] == [
            "run",
            "--environment",
            "quality-extended",
            "bandit",
            "-r",
            "src/",
            "--severity-level",
            "high",
            "--exclude",
            "tests/",
            "-f",
            "json",
        ]
        assert result["task_args_mode"] == "task_args"

    def test_existing_output_flags_are_replaced(self, tmp_path):
        body = "ruff check src/ --output-format=concise --select=F"
        _, mock_run = _run(
            _adapter_for(tmp_path, "ruff", body), "ruff", body, environment="quality"
        )
        assert mock_run.call_args[0][0][5:] == [
            "check",
            "src/",
            "--select=F",
            "--output-format",
            "json",
        ]

    def test_plain_ruff_without_check_is_kept(self, tmp_path):
        body = "ruff --select=F src/"
        _, mock_run = _run(
            _adapter_for(tmp_path, "ruff", body), "ruff", body, environment="quality"
        )
        assert mock_run.call_args[0][0][4:] == [
            "ruff",
            "--select=F",
            "src/",
            "--output-format",
            "json",
        ]

    def test_bandit_existing_format_replaced(self, tmp_path):
        body = "bandit -r src/ -f txt"
        _, mock_run = _run(
            _adapter_for(tmp_path, "bandit", body),
            "bandit",
            body,
            environment="quality-extended",
        )
        assert mock_run.call_args[0][0][5:] == ["-r", "src/", "-f", "json"]

    def test_no_json_flag_without_json_config(self, tmp_path):
        body = TOOL_ARGS["mypy"]
        _, mock_run = _run(
            _adapter_for(tmp_path, "mypy", body), "mypy", body, quality_config={}
        )
        assert mock_run.call_args[0][0][-1] == "src/"


class TestBuilderFallback:
    @pytest.mark.parametrize(
        "body",
        [
            "ruff check src/ && ruff format --check src/",
            "ruff check src/ | tee out.txt",
            "ruff check src/; echo done",
            "ruff check src/ > out.txt",
            "pixi run --frozen ruff check src/",
            "pixi run -e quality black src/",
            "ruff format src/",
            "echo 'unterminated",
        ],
    )
    def test_falls_back_with_reason(self, tmp_path, body):
        result, mock_run = _run(
            _adapter_for(tmp_path, "ruff", body), "ruff", body, environment="quality"
        )
        argv = mock_run.call_args[0][0]
        assert argv[1:] == [
            "run",
            "--environment",
            "quality",
            "ruff",
            "check",
            "--output-format",
            "json",
            "src/",
        ]
        assert result["task_args_mode"] == "builder_fallback"
        assert result["task_args_fallback_reason"]


PYPROJECT = """
[project]
name = "demo"
version = "0.1.0"
dependencies = ["requests>=2"]

[project.optional-dependencies]
docs = ["Sphinx_Rtd.Theme>=1"]

[tool.pixi.workspace]
name = "demo"
channels = ["conda-forge"]
platforms = ["linux-64"]

[tool.pixi.dependencies]
python = "*"

[tool.pixi.feature.quality.dependencies]
ruff = "*"
mypy = "*"

[tool.pixi.feature.quality-extended.dependencies]
{extended}

[tool.pixi.environments]
quality = ["quality"]
quality-extended = ["quality", "quality-extended"]
quality-full = ["quality", "quality-extended"]
dev = ["quality", "quality-extended"]

[tool.pixi.tasks]
security-scan = "bandit -r src/ --severity-level high --exclude tests/"
"""


def _pyproject_adapter(tmp_path, extended='bandit = "*"', extra=""):
    (tmp_path / "pyproject.toml").write_text(
        PYPROJECT.format(extended=extended) + extra
    )
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))
    env_info = Mock()
    env_info.available_tools = {"ruff", "mypy", "bandit"}
    env_info.tool_versions = {}
    env_info.environment_health = "optimal"
    env_info.performance_indicators = {}
    env_info.recommendations = []
    env_info.missing_tools = set()
    adapter.detect_quality_environment = Mock(return_value=env_info)
    return adapter


class TestPyprojectOnlyManifest:
    BODY = TOOL_ARGS["bandit"]

    def test_bandit_only_in_extended_feature_picks_quality_extended(self, tmp_path):
        result, mock_run = _run(_pyproject_adapter(tmp_path), "bandit", self.BODY)
        assert mock_run.call_args[0][0][1:] == [
            "run",
            "--environment",
            "quality-extended",
            "bandit",
            "-r",
            "src/",
            "--severity-level",
            "high",
            "--exclude",
            "tests/",
            "-f",
            "json",
        ]
        assert result["tool_environment_source"] == "tool_dependency"

    def test_no_environment_has_bandit_is_a_clear_error(self, tmp_path):
        adapter = _pyproject_adapter(tmp_path, extended='vulture = "*"')
        result, mock_run = _run(adapter, "bandit", self.BODY)
        mock_run.assert_not_called()
        assert "bandit is not installed in any pixi environment" in result["error"]

    def test_project_dependencies_count_for_default_feature(self, tmp_path):
        adapter = _pyproject_adapter(tmp_path, extended='vulture = "*"', extra="")
        text = (
            (tmp_path / "pyproject.toml")
            .read_text()
            .replace(
                'dependencies = ["requests>=2"]',
                'dependencies = ["requests>=2", "Bandit[toml]>=1.7 ; python_version>\'3\'"]',
            )
        )
        (tmp_path / "pyproject.toml").write_text(text)
        assert adapter.environments_providing_tool("bandit") == [
            "default",
            "quality",
            "quality-extended",
            "quality-full",
            "dev",
        ]

    def test_optional_dependencies_count_and_names_normalize(self, tmp_path):
        adapter = _pyproject_adapter(tmp_path, extended='vulture = "*"')
        assert "quality" in adapter.environments_providing_tool("sphinx-rtd-theme")

    def test_no_manifest_at_all_is_undeterminable(self, tmp_path):
        adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))
        assert adapter.environments_providing_tool("bandit") is None


class TestMypyJsonCounts:
    LINES = (
        '{"file": "src/a.py", "line": 3, "column": 4, "message": "bad type", '
        '"hint": null, "code": "assignment", "severity": "error"}\n'
        '{"file": "src/a.py", "line": 3, "column": 4, "message": "see docs", '
        '"hint": null, "code": "assignment", "severity": "note"}\n'
        '{"file": "src/b.py", "line": 9, "column": 1, "message": "other", '
        '"hint": null, "code": "arg-type", "severity": "error"}\n'
    )

    def test_exit_1_json_lines_keep_counts(self, tmp_path):
        body = TOOL_ARGS["mypy"]
        adapter = _adapter_for(tmp_path, "mypy", body)
        proc = Mock(returncode=1, stdout=self.LINES, stderr="")
        with patch("adapters.direct_pixi_execution.subprocess.run", return_value=proc):
            result = adapter.run_quality_task(
                task_name="typecheck",
                quality_tool="mypy",
                target_paths=["src/"],
                quality_config={"output_format": "json"},
            )
        assert result["success"] is False
        assert result["findings_detected"] is True
        assert result["parsed_output"]["error_count"] == 2

    def test_text_output_still_counted(self, tmp_path):
        adapter = _project(tmp_path)
        parsed = adapter._parse_mypy_output("src/a.py:3: error: bad\nFound 1 error\n")
        assert parsed["error_count"] == 1


class TestEnvironmentChoice:
    def test_caller_environment_overrides_body(self, tmp_path):
        body = TOOL_ARGS["ruff"]
        _, mock_run = _run(
            _adapter_for(tmp_path, "ruff", body), "ruff", body, environment="dev"
        )
        argv = mock_run.call_args[0][0]
        assert argv[2:4] == ["--environment", "dev"]
        assert "quality" not in argv

    def test_body_environment_beats_manifest_search(self, tmp_path):
        body = TOOL_ARGS["ruff"]
        result, mock_run = _run(_adapter_for(tmp_path, "ruff", body), "ruff", body)
        assert mock_run.call_args[0][0][2:4] == ["--environment", "quality"]
        assert result["tool_environment_source"] == "task_body"

    def test_pypi_dependency_counts(self, tmp_path):
        body = "mypy src/"
        result, mock_run = _run(_adapter_for(tmp_path, "mypy", body), "mypy", body)
        assert mock_run.call_args[0][0][2:4] == ["--environment", "quality"]
        assert result["tool_environment_source"] == "tool_dependency"

    def test_tool_in_no_environment_is_a_clear_error(self, tmp_path):
        body = TOOL_ARGS["bandit"]
        adapter = _adapter_for(tmp_path, "bandit", body, MANIFEST_NO_BANDIT)
        result, mock_run = _run(adapter, "bandit", body)
        mock_run.assert_not_called()
        assert result["success"] is False
        assert "bandit is not installed in any pixi environment" in result["error"]
        assert result["exit_code"] != 127
        assert "parsed_output" not in result
        assert "findings_detected" not in result

    def test_explicit_environment_trusted_even_if_tool_undeclared(self, tmp_path):
        body = TOOL_ARGS["bandit"]
        adapter = _adapter_for(tmp_path, "bandit", body, MANIFEST_NO_BANDIT)
        _, mock_run = _run(adapter, "bandit", body, environment="quality")
        mock_run.assert_called_once()
