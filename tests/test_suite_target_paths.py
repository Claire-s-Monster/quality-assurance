"""
Tests for target_paths support in the comprehensive quality suite.

Covers path validation, threading of target_paths from the server handler
through the orchestration service to each tool invocation, and the unchanged
default behavior.

Run with: pixi run python -m pytest tests/test_suite_target_paths.py -v
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.models import QualitySuiteConfiguration, QualityTool  # noqa: E402
from core.quality_orchestration_service import (  # noqa: E402
    QualityOrchestrationService,
    resolve_target_paths,
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
def project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "lib" / "pkg").mkdir(parents=True)
    (tmp_path / "scripts").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def service():
    return QualityOrchestrationService(
        quality_executor=MagicMock(),
        quality_analyzer=MagicMock(),
        trend_analyzer=MagicMock(),
        logging=MagicMock(),
    )


def _capture_suite_config(server, monkeypatch):
    captured = {}

    def execute_comprehensive_suite(config):
        captured["config"] = config
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(
        server,
        "orchestration_service",
        SimpleNamespace(execute_comprehensive_suite=execute_comprehensive_suite),
    )
    return captured


def _executor_calls(service):
    ex = service.quality_executor
    return {
        QualityTool.RUFF: ex.execute_lint_assessment,
        QualityTool.MYPY: ex.execute_typecheck_assessment,
        QualityTool.BANDIT: ex.execute_security_scan,
        QualityTool.RADON: ex.execute_complexity_analysis,
        QualityTool.VULTURE: ex.execute_dead_code_detection,
    }


# --- resolve_target_paths -------------------------------------------------


def test_resolve_target_paths_relative_to_root(project):
    assert resolve_target_paths(["lib/pkg", "scripts/"], project) == [
        "lib/pkg",
        "scripts",
    ]


def test_resolve_target_paths_rejects_nonexistent(project):
    with pytest.raises(ValueError, match="does not exist"):
        resolve_target_paths(["nope"], project)


def test_resolve_target_paths_rejects_escape(project):
    with pytest.raises(ValueError, match="escapes the project root"):
        resolve_target_paths(["../outside"], project)
    with pytest.raises(ValueError, match="escapes the project root"):
        resolve_target_paths([str(project.parent)], project)


# --- server handler ---------------------------------------------------------


def test_handler_default_leaves_config_paths_unset(server, monkeypatch, project):
    captured = _capture_suite_config(server, monkeypatch)

    result = server.quality_execute_comprehensive_suite.fn()

    assert captured["config"].target_paths is None
    assert "error" in result  # from the forced stop, not path validation
    assert "Invalid target_paths" not in result["error"]


def test_handler_custom_paths_reach_suite_config(server, monkeypatch, project):
    captured = _capture_suite_config(server, monkeypatch)

    server.quality_execute_comprehensive_suite.fn(target_paths=["lib/pkg", "scripts"])

    assert captured["config"].target_paths == ["lib/pkg", "scripts"]


def test_handler_nonexistent_path_returns_error(server, monkeypatch, project):
    captured = _capture_suite_config(server, monkeypatch)

    result = server.quality_execute_comprehensive_suite.fn(target_paths=["missing"])

    assert result["status"] == "error"
    assert "does not exist" in result["error"]
    assert "config" not in captured


def test_handler_escaping_path_returns_error(server, monkeypatch, project):
    captured = _capture_suite_config(server, monkeypatch)

    result = server.quality_execute_comprehensive_suite.fn(target_paths=["../.."])

    assert result["status"] == "error"
    assert "escapes the project root" in result["error"]
    assert "config" not in captured


# --- orchestration service --------------------------------------------------


@pytest.mark.parametrize("parallel", [False, True])
def test_service_default_calls_have_no_target_paths(service, parallel):
    config = QualitySuiteConfiguration(
        included_tools=ALL_TOOLS, parallel_execution=parallel
    )

    run = (
        service._execute_tools_parallel if parallel else service._execute_tools_sequential
    )
    run(config)

    for mock in _executor_calls(service).values():
        mock.assert_called_once()
        assert "target_paths" not in mock.call_args.kwargs


@pytest.mark.parametrize("parallel", [False, True])
def test_service_custom_paths_passed_to_every_tool(service, parallel):
    config = QualitySuiteConfiguration(
        included_tools=ALL_TOOLS,
        parallel_execution=parallel,
        target_paths=["lib/pkg", "scripts"],
    )

    run = (
        service._execute_tools_parallel if parallel else service._execute_tools_sequential
    )
    run(config)

    for mock in _executor_calls(service).values():
        mock.assert_called_once()
        assert mock.call_args.kwargs["target_paths"] == ["lib/pkg", "scripts"]
