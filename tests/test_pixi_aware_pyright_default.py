"""
quality_execute_pixi_aware_assessment on a project whose `typecheck` task runs
pyright: the default "mypy" request must run that task as pyright instead of
reporting mypy unavailable (issue #9).
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter  # noqa: E402

PYRIGHT_ERRORS = (
    "/abs/src/a.py:12:5 - error: Message text (reportFooBar)\n"
    "/abs/src/a.py:20:1 - error: Other (reportUndefinedVariable)\n"
    "2 errors, 0 warnings, 0 informations \n"
)
PYRIGHT_CLEAN = "0 errors, 0 warnings, 0 informations \n"


class _Container:
    def __init__(self, pixi_executor):
        self.pixi_executor = pixi_executor


def _adapter(body, available):
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
    adapter._is_pixi_project = Mock(return_value=True)
    adapter._get_available_tasks = Mock(
        return_value={"typecheck": body, "lint": "ruff"}
    )
    adapter.select_quality_environment = Mock(return_value=(None, "test"))
    adapter.optimize_quality_environment = Mock(return_value={})
    env_info = Mock()
    env_info.available_tools = set(available)
    env_info.tool_versions = {}
    env_info.environment_health = "optimal"
    env_info.performance_indicators = {}
    env_info.recommendations = []
    env_info.missing_tools = set()
    adapter.detect_quality_environment = Mock(return_value=env_info)
    return adapter


def _assess(monkeypatch, adapter, tools, code, stdout):
    from quality_assurance import server

    monkeypatch.setattr(server, "orchestration_service", object())
    monkeypatch.setattr(server, "container", _Container(adapter))

    def fake_run(argv, **kwargs):
        is_typecheck = "pyright" in argv or "typecheck" in argv
        return Mock(
            returncode=code if is_typecheck else 0,
            stdout=stdout if is_typecheck else "[]",
            stderr="",
        )

    with patch(
        "adapters.direct_pixi_execution.subprocess.run", side_effect=fake_run
    ) as mock_run:
        result = server.quality_execute_pixi_aware_assessment.fn(
            tools=tools, project_path="/tmp"
        )
    typecheck_runs = [
        c
        for c in mock_run.call_args_list
        if "pyright" in c[0][0] or "typecheck" in c[0][0]
    ]
    return result, typecheck_runs


def _detected_env(tasks):
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
    adapter._is_pixi_project = Mock(return_value=True)
    adapter._get_available_tasks = Mock(return_value=tasks)
    adapter._get_tool_version = Mock(return_value=None)
    adapter.environments_providing_tool = Mock(return_value=[])
    return adapter.detect_quality_environment("/tmp/project")


class TestMypyRecommendationWhenTypeCheckCovered:
    PYRIGHT_TASKS = {"typecheck": "pyright src/", "lint": "ruff check ."}

    def test_pyright_only_project_not_told_to_install_mypy(self):
        env = _detected_env(self.PYRIGHT_TASKS)
        assert not any("mypy" in r for r in env.recommendations)
        assert "mypy" not in env.missing_tools
        assert "mypy" not in env.available_tools
        assert "pyright" in env.available_tools

    def test_body_only_mentioning_pyright_does_not_suppress_mypy(self):
        env = _detected_env(
            {"note": "echo see pyrightconfig.json", "lint": "ruff check ."}
        )
        assert "mypy" in env.missing_tools
        assert any(
            "Install essential tools" in r and "mypy" in r for r in env.recommendations
        )

    def test_basedpyright_body_suppresses_mypy(self):
        env = _detected_env({"typecheck": "basedpyright src/", "lint": "ruff check ."})
        assert "mypy" not in env.missing_tools
        assert not any("mypy" in r for r in env.recommendations)

    def test_mypy_and_pyright_tasks_both_present(self):
        env = _detected_env(
            {"typecheck": "mypy src/", "typecheck-pyright": "pyright src/"}
        )
        assert "mypy" in env.available_tools
        assert "mypy" not in env.missing_tools
        assert not any("mypy" in r for r in env.recommendations)

    @pytest.mark.parametrize(
        "body",
        [
            "pyright --version",
            "pyright --help",
            "basedpyright -h",
            "basedpyright --version",
            "cd src && echo pyright",
            "echo pyright; ls",
            'pyright "src/',
        ],
    )
    def test_non_checking_bodies_do_not_cover_mypy(self, body):
        env = _detected_env({"typecheck": body, "lint": "ruff check ."})
        assert "mypy" in env.missing_tools
        assert any(
            "Install essential tools" in r and "mypy" in r for r in env.recommendations
        )

    @pytest.mark.parametrize(
        "body",
        [
            "cd src && pyright",
            "cd src && pyright src/ | tee out.txt",
            "bash -c 'pyright src/'",
            "sh -c 'cd src && basedpyright'",
            ["cd", "src", "&&", "pyright"],
            "bash -lc 'pyright src/'",
            "echo x & pyright",
        ],
    )
    def test_shell_wrapped_pyright_covers_mypy(self, body):
        env = _detected_env({"typecheck": body, "lint": "ruff check ."})
        assert "mypy" not in env.missing_tools
        assert not any(
            "Install essential tools" in r and "mypy" in r for r in env.recommendations
        )

    @staticmethod
    def _manifest_env(tmp_path, tasks, pyright_feature=None):
        """Real manifest in pyproject [tool.pixi] form; tool_versions stay empty."""
        lines = [
            "[project]",
            'name = "demo"',
            "[tool.pixi.dependencies]",
            'ruff = "*"',
            "[tool.pixi.environments]",
            'quality = ["quality"]',
            "[tool.pixi.feature.quality.dependencies]",
        ]
        if pyright_feature:
            lines.append(f'{pyright_feature} = "*"')
        (tmp_path / "pyproject.toml").write_text("\n".join(lines) + "\n")
        adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))
        adapter._is_pixi_project = Mock(return_value=True)
        adapter._get_available_tasks = Mock(return_value=tasks)
        adapter._get_tool_version = Mock(return_value=None)
        return adapter.detect_quality_environment(str(tmp_path))

    def test_pyright_declared_only_in_non_default_env_gets_no_recommendation(
        self, tmp_path
    ):
        env = self._manifest_env(tmp_path, self.PYRIGHT_TASKS, "pyright")
        assert "pyright" not in env.tool_versions
        assert not any("pixi add" in r for r in env.recommendations)

    def test_pyright_declared_nowhere_gets_actionable_recommendation(self, tmp_path):
        env = self._manifest_env(tmp_path, self.PYRIGHT_TASKS)
        assert any("pixi add pyright" in r for r in env.recommendations)
        assert not any("mypy" in r for r in env.recommendations)

    def test_basedpyright_declared_nowhere_gets_basedpyright_recommendation(
        self, tmp_path
    ):
        tasks = {"typecheck": "basedpyright src/", "lint": "ruff check ."}
        env = self._manifest_env(tmp_path, tasks)
        assert any("pixi add basedpyright" in r for r in env.recommendations)
        assert not any("pixi add pyright" in r for r in env.recommendations)

    def test_basedpyright_declared_in_feature_gets_no_recommendation(self, tmp_path):
        tasks = {"typecheck": "basedpyright src/", "lint": "ruff check ."}
        env = self._manifest_env(tmp_path, tasks, "basedpyright")
        assert not any("pixi add" in r for r in env.recommendations)

    def test_unreadable_manifest_gives_no_install_recommendation(self):
        adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
        adapter._is_pixi_project = Mock(return_value=True)
        adapter._get_available_tasks = Mock(return_value=self.PYRIGHT_TASKS)
        adapter._get_tool_version = Mock(return_value=None)
        adapter.environments_providing_tool = Mock(return_value=None)
        env = adapter.detect_quality_environment("/tmp/project")
        assert not any("pixi add pyright" in r for r in env.recommendations)

    def test_no_type_checker_still_told_to_install_mypy(self):
        env = _detected_env({"lint": "ruff check ."})
        assert any(
            "Install essential tools" in r and "mypy" in r for r in env.recommendations
        )
        assert "mypy" in env.missing_tools

    def test_mypy_project_unchanged(self):
        env = _detected_env({"typecheck": "mypy src/", "lint": "ruff check ."})
        assert "mypy" in env.available_tools
        assert not any("mypy" in r for r in env.recommendations)
        assert any(
            "Install essential tools" in r and "bandit" in r
            for r in env.recommendations
        )


class TestOptimizeEnvironmentMypySuggestion:
    @staticmethod
    def _optimize(monkeypatch, tasks):
        from quality_assurance import server

        adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
        adapter._is_pixi_project = Mock(return_value=True)
        adapter._get_available_tasks = Mock(return_value=tasks)
        adapter._get_tool_version = Mock(return_value=None)
        adapter.environments_providing_tool = Mock(return_value=[])
        adapter._optimize_tool_environment = Mock(return_value=[])
        adapter._apply_global_optimizations = Mock(return_value={})
        monkeypatch.setattr(server, "orchestration_service", object())
        monkeypatch.setattr(server, "container", _Container(adapter))
        return server.quality_optimize_pixi_environment.fn(
            working_dir="/tmp/project",
            target_tools=["ruff", "mypy"],
            generate_tasks=False,
        )

    def test_pyright_only_project_gets_no_mypy_install(self, monkeypatch):
        result = self._optimize(
            monkeypatch, {"typecheck": "pyright src/", "lint": "ruff check ."}
        )
        analysis = result["missing_tools_analysis"]
        assert "mypy" not in analysis["missing_tools"]
        assert not any(a["tool"] == "mypy" for a in analysis["recommended_additions"])
        assert result["optimization_summary"]["tools_missing"] == 0
        assert "mypy" not in str(result["optimization_results"])
        assert not any("mypy" in r for r in result["recommendations"])

    def test_no_type_checker_still_gets_mypy_install(self, monkeypatch):
        result = self._optimize(monkeypatch, {"lint": "ruff check ."})
        analysis = result["missing_tools_analysis"]
        assert "pixi add mypy" in str(result["optimization_results"])
        assert "mypy" in analysis["missing_tools"]
        assert any(
            a["tool"] == "mypy" and a["install_command"] == "pixi add mypy"
            for a in analysis["recommended_additions"]
        )


class TestDefaultMypyOnPyrightProject:
    @pytest.mark.parametrize(
        "code,stdout,verdict,reason",
        [
            (0, PYRIGHT_CLEAN, "passed", "all 2 requested tools ran clean"),
            (
                1,
                PYRIGHT_ERRORS,
                "findings",
                "findings reported by: pyright (2 errors)",
            ),
        ],
    )
    def test_default_typecheck_tool_is_run_as_pyright(
        self, monkeypatch, code, stdout, verdict, reason
    ):
        adapter = _adapter("pyright src/", {"ruff"})
        result, runs = _assess(monkeypatch, adapter, ["ruff", "mypy"], code, stdout)

        assert result["gate_verdict"] == verdict
        assert result["gate_verdict_reason"] == reason
        assert result["execution_summary"]["tools_unavailable"] == 0
        assert len(runs) == 1
        assert "--output" not in runs[0][0][0]
        pyright_result = result["assessment_results"][1]
        assert pyright_result["task_body_mode"] == "direct_tool"
        assert "not applied" in pyright_result["task_args_note"]

    def test_other_tools_are_never_deduplicated(self):
        from quality_assurance.server import _resolve_pyright_typecheck_tools

        adapter = _adapter("pyright src/", {"ruff"})
        tools, _ = _resolve_pyright_typecheck_tools(
            adapter, ["ruff", "ruff", "mypy", "pyright"], None, None
        )
        assert tools == ["ruff", "ruff", "pyright"]

    def test_mypy_and_pyright_requested_together_run_once(self, monkeypatch):
        adapter = _adapter("pyright src/", {"mypy", "pyright"})
        result, runs = _assess(
            monkeypatch, adapter, ["mypy", "pyright"], 0, PYRIGHT_CLEAN
        )

        assert len(runs) == 1
        assert result["execution_summary"]["tools_requested"] == 1
        assert result["gate_verdict"] == "passed"

    def test_mypy_body_still_reports_mypy_unavailable_when_missing(self, monkeypatch):
        adapter = _adapter("mypy src/", {"ruff"})
        result, runs = _assess(monkeypatch, adapter, ["mypy"], 0, "")

        assert runs == []
        assert result["gate_verdict"] == "error"
