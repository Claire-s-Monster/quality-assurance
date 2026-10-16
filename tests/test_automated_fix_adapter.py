"""AutomatedFixAdapter wired as core/container.py wires it.

The adapter gets a real DirectPixiExecutionAdapter; only the subprocess boundary
(the actual `pixi run ...` call) is mocked.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List
from unittest.mock import MagicMock, patch

import pytest

from adapters.automated_fix import AutomatedFixAdapter
from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from core.models import FixType, FixValidationMode

PIXI_TOML = """\
[project]
name = "fixture"
channels = ["conda-forge"]
platforms = ["linux-64"]

[dependencies]
ruff = "*"
mypy = "*"

[tasks]
lint = "ruff check src/"
typecheck = "mypy src/"
"""

UNSORTED = "import sys\nimport os\n\nprint(os, sys)\n"
SORTED = "import os\nimport sys\n\nprint(os, sys)\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pixi.toml").write_text(PIXI_TOML)
    (tmp_path / "pixi.lock").write_text("")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(UNSORTED)
    return tmp_path


def _wire(project: Path) -> AutomatedFixAdapter:
    """Same construction as AssuranceContainer._initialize_adapters."""
    direct_pixi = DirectPixiExecutionAdapter(
        logging=MagicMock(), working_dir=str(project)
    )
    return AutomatedFixAdapter(
        direct_pixi_executor=direct_pixi, working_dir=str(project)
    )


def _fake_run(
    project: Path, returncode: int = 0, rewrite: bool = True
) -> Callable[..., Any]:
    calls: List[List[str]] = []

    def run(command: List[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if returncode == 0 and rewrite:
            (project / "src" / "mod.py").write_text(SORTED)
        return subprocess.CompletedProcess(
            command, returncode, stdout="", stderr="boom" if returncode else ""
        )

    run.calls = calls  # type: ignore[attr-defined]
    return run


def test_apply_fixes_end_to_end_reports_real_success(project: Path) -> None:
    adapter = _wire(project)
    fake = _fake_run(project)
    with patch("adapters.direct_pixi_execution.subprocess.run", fake):
        result = adapter.apply_automated_fixes(
            [FixType.IMPORTS], dry_run=False, backup_before_fix=True
        )

    assert result.failed_fixes == []
    assert len(result.successful_fixes) == 1
    fix = result.successful_fixes[0]
    assert fix.file_path == str(Path("src") / "mod.py")
    assert fix.original_content_hash != fix.modified_content_hash
    assert result.total_files_modified == 1
    assert result.total_changes_applied >= 1
    assert (project / "src" / "mod.py").read_text() == SORTED
    assert result.backup_created and result.rollback_available
    # Nothing was assessed, so nothing may be fabricated.
    assert result.pre_fix_validation is None
    assert result.post_fix_validation is None
    assert result.execution_time_ms >= 0
    # ruff ran as a command (the `lint` task has a fixed --select/target).
    assert any("ruff" in c and "--fix" in c and "--select=I" in c for c in fake.calls)


def test_failed_fix_is_reported_as_failure_not_success(project: Path) -> None:
    adapter = _wire(project)
    fake = _fake_run(project, returncode=2)
    with patch("adapters.direct_pixi_execution.subprocess.run", fake):
        result = adapter.apply_automated_fixes(
            [FixType.IMPORTS], dry_run=False, backup_before_fix=False
        )

    assert result.successful_fixes == []
    assert len(result.failed_fixes) == 1
    assert result.failed_fixes[0]["fix_type"] == FixType.IMPORTS.value
    assert "boom" in result.failed_fixes[0]["error"]
    assert result.total_changes_applied == 0
    assert (project / "src" / "mod.py").read_text() == UNSORTED


def test_ruff_findings_exit_code_one_is_not_a_failed_fix(project: Path) -> None:
    adapter = _wire(project)
    fake = _fake_run(project, returncode=1, rewrite=False)
    with patch("adapters.direct_pixi_execution.subprocess.run", fake):
        result = adapter.apply_automated_fixes(
            [FixType.IMPORTS], dry_run=False, backup_before_fix=False
        )

    assert result.failed_fixes == []
    assert len(result.successful_fixes) == 1
    assert result.successful_fixes[0].lines_changed == 0


def test_dry_run_runs_nothing_and_modifies_nothing(project: Path) -> None:
    adapter = _wire(project)
    fake = _fake_run(project)
    with patch("adapters.direct_pixi_execution.subprocess.run", fake):
        result = adapter.apply_automated_fixes([FixType.IMPORTS], dry_run=True)

    assert fake.calls == []
    assert result.failed_fixes == []
    assert (project / "src" / "mod.py").read_text() == UNSORTED


def test_missing_tool_blocks_fixes_with_failure(project: Path) -> None:
    (project / "pixi.toml").write_text(PIXI_TOML.replace('ruff = "*"\n', ""))
    adapter = _wire(project)
    fake = _fake_run(project)
    with patch("adapters.direct_pixi_execution.subprocess.run", fake):
        result = adapter.apply_automated_fixes([FixType.IMPORTS], dry_run=False)

    assert fake.calls == []
    assert result.successful_fixes == []
    assert result.failed_fixes
    assert result.failed_fixes[0]["error"] == "Pre-fix safety validation failed"


def _assert_op_metadata(op: Any, operation_type: str) -> None:
    assert op.operation_type == operation_type
    assert op.execution_time_ms >= 0.0
    parsed = datetime.fromisoformat(op.timestamp)
    assert parsed.tzinfo is not None


def test_validate_fix_safety_result_has_timing_and_timestamp(project: Path) -> None:
    op = _wire(project).validate_fix_safety([FixType.IMPORTS], ["src/mod.py"])
    assert op.success, op.message
    _assert_op_metadata(op, "validate_fix_safety")


def test_rollback_results_have_timing_and_timestamp(project: Path) -> None:
    adapter = _wire(project)
    missing = adapter.rollback_fixes(str(project / "nope"))
    assert not missing.success
    _assert_op_metadata(missing, "rollback_fixes")

    backup = adapter.create_fix_backup(["src/mod.py"])
    (project / "src" / "mod.py").write_text("changed\n")
    restored = adapter.rollback_fixes(backup)
    assert restored.success, restored.message
    _assert_op_metadata(restored, "rollback_fixes")
    assert (project / "src" / "mod.py").read_text() == UNSORTED


def test_validation_mode_permissive_skips_syntax_check(project: Path) -> None:
    adapter = _wire(project)
    fake = _fake_run(project)
    with patch("adapters.direct_pixi_execution.subprocess.run", fake):
        result = adapter.apply_automated_fixes(
            [FixType.FORMATTING],
            dry_run=False,
            backup_before_fix=False,
            validation_mode=FixValidationMode.PERMISSIVE,
        )
    assert result.failed_fixes == []
    assert any(c[-3:-1] == ["ruff", "format"] or "format" in c for c in fake.calls)
