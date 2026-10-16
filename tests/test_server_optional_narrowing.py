"""
Tests for the Optional narrowing in server.py / http_server.py.

Covers the _require_* accessors, coalescing of explicit-None tool parameters to
their documented defaults, and the http_server execute_tool tool_name guard.

Run with: pixi run python -m pytest tests/test_server_optional_narrowing.py -v
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def server(monkeypatch):
    from quality_assurance import server as server_module

    return server_module


def test_require_accessors_raise_when_uninitialized(server, monkeypatch):
    monkeypatch.setattr(server, "container", None)
    monkeypatch.setattr(server, "orchestration_service", None)

    with pytest.raises(RuntimeError, match="server not initialized"):
        server._require_container()
    with pytest.raises(RuntimeError, match="server not initialized"):
        server._require_orchestration()


def test_require_accessors_return_initialized_objects(server, monkeypatch):
    fake_container, fake_service = object(), object()
    monkeypatch.setattr(server, "container", fake_container)
    monkeypatch.setattr(server, "orchestration_service", fake_service)

    assert server._require_container() is fake_container
    assert server._require_orchestration() is fake_service


def test_lint_none_params_fall_back_to_documented_defaults(server, monkeypatch):
    captured = {}

    def execute_lint_assessment(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(
        server,
        "orchestration_service",
        SimpleNamespace(execute_lint_assessment=execute_lint_assessment),
    )

    server.quality_execute_lint_assessment.fn(
        target_path=None, fix_mode=None, output_format=None, use_cache=None
    )

    assert captured["target_path"] == "src/"
    assert captured["fix_mode"] is False
    assert captured["output_format"] == "json"
    assert captured["use_cache"] is True


def test_apply_fixes_none_flags_fall_back_to_defaults(server, monkeypatch):
    captured = {}

    def apply_automated_fixes(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop after capture")

    monkeypatch.setattr(
        server,
        "orchestration_service",
        SimpleNamespace(
            automated_fix=object(), apply_automated_fixes=apply_automated_fixes
        ),
    )
    monkeypatch.setattr(server, "container", SimpleNamespace())

    server.quality_apply_automated_fixes.fn(
        fix_types=["imports"], dry_run=None, backup_before_fix=None
    )

    assert captured["dry_run"] is True
    assert captured["backup_before_fix"] is True


def test_http_execute_tool_without_tool_name_returns_error_not_dispatch():
    from quality_assurance.http_server import HTTPQualityAssuranceServer

    http_server = HTTPQualityAssuranceServer(working_dir=None)
    http_server._lean_mcp._dispatch_tool = Mock()

    result = http_server._execute_lean_tool("execute_tool", {"parameters": {}})

    assert "tool_name" in result["error"]
    http_server._lean_mcp._dispatch_tool.assert_not_called()
