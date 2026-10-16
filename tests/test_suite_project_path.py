"""
Tests for the optional project_path of the comprehensive quality suite.

Run with: pixi run python -m pytest tests/test_suite_project_path.py -v
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from adapters.quality_tool_execution import QualityToolExecutionAdapter  # noqa: E402
from core.models import QualitySuiteConfiguration, QualityTool  # noqa: E402
from core.quality_orchestration_service import (  # noqa: E402
    QualityOrchestrationService,
)

ALL_TOOLS = [
    QualityTool.RUFF,
    QualityTool.MYPY,
    QualityTool.BANDIT,
    QualityTool.RADON,
    QualityTool.VULTURE,
]


@pytest.fixture
def server():
    from quality_assurance import server as server_module

    return server_module


@pytest.fixture
def other(tmp_path):
    root = tmp_path / "other"
    (root / "lib" / "pkg").mkdir(parents=True)
    return root


@pytest.fixture
def cwd_project(tmp_path, monkeypatch):
    cwd = tmp_path / "cwd"
    (cwd / "src").mkdir(parents=True)
    monkeypatch.chdir(cwd)
    return cwd


@pytest.fixture
def service():
    return QualityOrchestrationService(
        quality_executor=MagicMock(),
        quality_analyzer=MagicMock(),
        trend_analyzer=MagicMock(),
        logging=MagicMock(),
    )


def _capture(server, monkeypatch):
    captured = {}

    def run(config):
        captured["config"] = config
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(
        server,
        "orchestration_service",
        SimpleNamespace(execute_comprehensive_suite=run),
    )
    return captured


def _calls(service):
    ex = service.quality_executor
    return [
        ex.execute_lint_assessment,
        ex.execute_typecheck_assessment,
        ex.execute_security_scan,
        ex.execute_complexity_analysis,
        ex.execute_dead_code_detection,
    ]


# --- handler -----------------------------------------------------------------


def test_handler_default_project_path_unset(server, monkeypatch, cwd_project):
    captured = _capture(server, monkeypatch)
    server.quality_execute_comprehensive_suite.fn()
    assert captured["config"].project_path is None


def test_handler_project_path_reaches_config_resolved(server, monkeypatch, other):
    captured = _capture(server, monkeypatch)
    server.quality_execute_comprehensive_suite.fn(project_path=str(other))
    assert captured["config"].project_path == str(other.resolve())


def test_handler_nonexistent_project_path_errors(server, monkeypatch, tmp_path):
    captured = _capture(server, monkeypatch)
    result = server.quality_execute_comprehensive_suite.fn(
        project_path=str(tmp_path / "missing")
    )
    assert result["status"] == "error"
    assert "project_path" in result["error"]
    assert "config" not in captured


def test_handler_file_project_path_errors(server, monkeypatch, tmp_path):
    captured = _capture(server, monkeypatch)
    f = tmp_path / "f.txt"
    f.write_text("x")
    result = server.quality_execute_comprehensive_suite.fn(project_path=str(f))
    assert result["status"] == "error"
    assert "config" not in captured


def test_handler_target_paths_relative_to_project_path(
    server, monkeypatch, cwd_project, other
):
    captured = _capture(server, monkeypatch)
    # lib/pkg exists only under project_path, not under cwd
    server.quality_execute_comprehensive_suite.fn(
        project_path=str(other), target_paths=["lib/pkg"]
    )
    assert captured["config"].target_paths == ["lib/pkg"]


def test_handler_target_paths_escaping_project_path_errors(
    server, monkeypatch, cwd_project, other
):
    captured = _capture(server, monkeypatch)
    result = server.quality_execute_comprehensive_suite.fn(
        project_path=str(other), target_paths=["../.."]
    )
    assert result["status"] == "error"
    assert "escapes the project root" in result["error"]
    assert "config" not in captured


def test_handler_does_not_chdir(server, monkeypatch, cwd_project, other):
    _capture(server, monkeypatch)
    before = os.getcwd()
    server.quality_execute_comprehensive_suite.fn(project_path=str(other))
    assert os.getcwd() == before


# --- orchestration -------------------------------------------------------------


@pytest.mark.parametrize("parallel", [False, True])
def test_service_default_has_no_project_path_kwarg(service, parallel):
    config = QualitySuiteConfiguration(
        included_tools=ALL_TOOLS, parallel_execution=parallel
    )
    run = (
        service._execute_tools_parallel if parallel else service._execute_tools_sequential
    )
    run(config)
    for mock in _calls(service):
        assert "project_path" not in mock.call_args.kwargs


@pytest.mark.parametrize("parallel", [False, True])
def test_service_passes_project_path_to_every_tool(service, parallel):
    config = QualitySuiteConfiguration(
        included_tools=ALL_TOOLS, parallel_execution=parallel, project_path="/p"
    )
    run = (
        service._execute_tools_parallel if parallel else service._execute_tools_sequential
    )
    run(config)
    for mock in _calls(service):
        assert mock.call_args.kwargs["project_path"] == "/p"


# --- adapter: dead-code must honor project_path -------------------------------


class _Executor:
    working_dir = "/server-cwd"

    def __init__(self):
        self.task_exists_dirs = []
        self.runs = []

    def task_exists(self, task, working_dir=None, environment=None):
        self.task_exists_dirs.append(working_dir)
        return {"exists": True}

    def select_quality_environment(self, task, working_dir=None, candidates=None):
        self.env_dir = working_dir
        return None, ""

    def _get_available_tasks(self, path, environment=None):
        return {}

    def run_task(self, task_name, args=None, **kwargs):
        self.runs.append(kwargs)
        return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}


@pytest.mark.parametrize("target_paths", [None, ["lib"]])
def test_dead_code_runs_in_project_path(target_paths):
    ex = _Executor()
    QualityToolExecutionAdapter(ex).execute_dead_code_detection(
        project_path="/p", target_paths=target_paths
    )
    assert ex.task_exists_dirs == ["/p"]
    assert ex.env_dir == "/p"
    assert ex.runs and all(r.get("working_dir") == "/p" for r in ex.runs)
