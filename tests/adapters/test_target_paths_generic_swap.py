"""
Generic target_paths swap, alias-resolved dead-code task, and the missing
default-target warning of the comprehensive suite.

Run with: pixi run python -m pytest tests/adapters/test_target_paths_generic_swap.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter  # noqa: E402
from adapters.quality_tool_execution import QualityToolExecutionAdapter  # noqa: E402
from core.models import QualityTool  # noqa: E402


class Executor:
    _split_task_body = staticmethod(DirectPixiExecutionAdapter._split_task_body)
    _parse_task_body_args = DirectPixiExecutionAdapter._parse_task_body_args

    def __init__(self, root, tasks):
        self.working_dir = str(root)
        self.tasks = tasks
        self.calls = []

    def resolve_task_name(self, tool, working_dir=None, environment=None):
        from adapters.direct_pixi_execution import TOOL_TASK_ALIASES

        for candidate in TOOL_TASK_ALIASES.get(tool, (tool,)):
            if candidate in self.tasks:
                return candidate
        return None

    def select_quality_environment(self, task, working_dir=None, candidates=None):
        return None, ""

    def task_exists(self, task, *args, **kwargs):
        return {"exists": task in self.tasks}

    def list_tasks(self, working_dir=None):
        return {"tasks": dict(self.tasks)}

    def _get_available_tasks(self, path, environment=None):
        return dict(self.tasks)

    def run_task(self, task_name, args=None, **kwargs):
        self.calls.append((task_name, list(args or []), kwargs))
        return {"success": True, "stdout": "", "stderr": "", "exit_code": 0}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "pkg").mkdir()
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "pyproject.toml").write_text("")
    return tmp_path


def _lint(root, body, paths):
    ex = Executor(root, {"lint": body})
    QualityToolExecutionAdapter(ex).execute_lint_assessment(
        tool=QualityTool.RUFF, target_paths=paths, project_path=str(root)
    )
    return ex.calls[0][1]


def test_non_src_directory_is_swapped(root):
    args = _lint(root, "ruff check lib/ --select=F", ["pkg/"])

    assert "lib/" not in args
    assert "pkg/" in args
    assert "--select=F" in args


def test_file_positional_is_kept_in_place(root):
    ex = Executor(root, {"dead-code": "vulture src/ app.py --min-confidence 80"})
    QualityToolExecutionAdapter(ex).execute_dead_code_detection(
        project_path=str(root), target_paths=["lib/"]
    )
    args = ex.calls[0][1]

    assert args[:2] == ["lib/", "app.py"]
    assert "src/" not in args


def test_file_only_positional_falls_back_to_appended(root):
    ex = Executor(root, {"lint": "ruff check app.py"})
    result = QualityToolExecutionAdapter(ex).execute_lint_assessment(
        tool=QualityTool.RUFF, target_paths=["pkg/"], project_path=str(root)
    )

    assert result.target_paths_mode == "appended"
    assert result.target_paths_fallback_reason


def test_option_value_that_exists_is_left_intact(root):
    args = _lint(root, "ruff check --config pyproject.toml lib/", ["pkg/"])

    assert args[args.index("--config") + 1] == "pyproject.toml"
    assert "lib/" not in args
    assert "pkg/" in args


def test_option_value_directory_is_left_intact(root):
    args = _lint(root, "ruff check --exclude lib/ pkg/", ["app.py"])

    assert args[args.index("--exclude") + 1] == "lib/"
    assert "pkg/" not in args
    assert "app.py" in args


def test_mypy_option_value_is_left_intact(root):
    ex = Executor(root, {"typecheck": "mypy --config-file pyproject.toml lib/"})
    QualityToolExecutionAdapter(ex).execute_typecheck_assessment(
        tool=QualityTool.MYPY, target_paths=["pkg/"], project_path=str(root)
    )
    args = ex.calls[0][1]

    assert args[args.index("--config-file") + 1] == "pyproject.toml"
    assert "lib/" not in args
    assert "pkg/" in args


def test_bandit_r_followed_by_non_src_path_is_swapped(root):
    ex = Executor(root, {"security-scan": "bandit -r lib -c pyproject.toml"})
    QualityToolExecutionAdapter(ex).execute_security_scan(
        tool=QualityTool.BANDIT, target_paths=["pkg/"], project_path=str(root)
    )
    args = ex.calls[0][1]

    assert args[:2] == ["-r", "pkg/"]
    assert "lib" not in args
    assert args[args.index("-c") + 1] == "pyproject.toml"


def test_no_path_like_positional_falls_back_to_appended(root):
    ex = Executor(root, {"lint": "ruff check --select=F"})
    result = QualityToolExecutionAdapter(ex).execute_lint_assessment(
        tool=QualityTool.RUFF, target_paths=["pkg/"], project_path=str(root)
    )

    assert result.target_paths_mode == "appended"
    assert result.target_paths_fallback_reason


def test_nonexistent_positional_is_not_swapped(root):
    ex = Executor(root, {"lint": "ruff check nowhere/ lib/ --select=F"})
    QualityToolExecutionAdapter(ex).execute_lint_assessment(
        tool=QualityTool.RUFF, target_paths=["pkg/"], project_path=str(root)
    )
    args = ex.calls[0][1]

    assert "nowhere/" in args
    assert "lib/" not in args


# --- dead-code task alias -------------------------------------------------------


@pytest.mark.parametrize("name", ["dead-code-check", "deadcode", "vulture"])
def test_dead_code_task_resolved_through_aliases(root, name):
    ex = Executor(root, {name: "vulture lib/ --min-confidence 80"})
    result = QualityToolExecutionAdapter(ex).execute_dead_code_detection(
        project_path=str(root), target_paths=["pkg/"]
    )

    assert result.pixi_task_used == name
    assert result.target_paths_mode == "replaced"
    assert "pkg/" in ex.calls[0][1] and "lib/" not in ex.calls[0][1]


def test_dead_code_default_run_uses_resolved_task(root):
    ex = Executor(root, {"deadcode": "vulture src/"})
    QualityToolExecutionAdapter(ex).execute_dead_code_detection(project_path=str(root))

    assert ex.calls[0][0] == "deadcode"


def test_dead_code_without_any_task_errors(root):
    ex = Executor(root, {"lint": "ruff check"})
    result = QualityToolExecutionAdapter(ex).execute_dead_code_detection(
        project_path=str(root)
    )

    assert result.status.value == "error"
    assert not ex.calls


# --- missing default target warning ---------------------------------------------


@pytest.fixture
def server():
    from quality_assurance import server as server_module

    return server_module


def _stub_suite(server, monkeypatch):
    result = MagicMock()
    result.individual_results = []
    monkeypatch.setattr(
        server,
        "orchestration_service",
        MagicMock(execute_comprehensive_suite=MagicMock(return_value=result)),
    )


def test_missing_default_src_adds_warning(server, monkeypatch, root):
    _stub_suite(server, monkeypatch)
    out = server.quality_execute_comprehensive_suite.fn(project_path=str(root))

    assert any("src" in w and "default" in w for w in out["warnings"])


def test_existing_default_src_has_no_warning(server, monkeypatch, root):
    (root / "src").mkdir()
    _stub_suite(server, monkeypatch)
    out = server.quality_execute_comprehensive_suite.fn(project_path=str(root))

    assert out["warnings"] == []


def test_explicit_target_paths_skip_default_warning(server, monkeypatch, root):
    _stub_suite(server, monkeypatch)
    out = server.quality_execute_comprehensive_suite.fn(
        project_path=str(root), target_paths=["lib"]
    )

    assert out["warnings"] == []
