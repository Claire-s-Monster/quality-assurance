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
        is_typecheck = "typecheck" in argv
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
    typecheck_runs = [c for c in mock_run.call_args_list if "typecheck" in c[0][0]]
    return result, typecheck_runs


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
        assert pyright_result["task_body_mode"] == "task_as_defined"
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
