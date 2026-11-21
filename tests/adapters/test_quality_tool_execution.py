"""
Unit tests for QualityToolExecutionAdapter's pixi task resolution.

Covers the fix where four assessment methods hardcoded a single pixi task
name per tool (e.g. bandit -> "security"), which breaks against any target
project that names its tasks differently (e.g. "security-scan"). Task
resolution now goes through DirectPixiExecutionAdapter.resolve_task_name /
TOOL_TASK_ALIASES so the first alias that actually exists in the target
project is used, with a diagnostic listing every candidate tried when none
resolve.
"""

import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest  # noqa: E402

from adapters.direct_pixi_execution import TOOL_TASK_ALIASES  # noqa: E402
from adapters.quality_tool_execution import QualityToolExecutionAdapter  # noqa: E402
from core.models import ExecutionStatus, QualityTool  # noqa: E402


class _FakePixiExecutor:
    """Minimal stand-in for DirectPixiExecutionAdapter's task-related surface."""

    def __init__(self, available_tasks: dict, run_result: dict | None = None):
        self._available_tasks = available_tasks
        self._run_result = run_result or {
            "success": True,
            "stdout": "{}",
            "stderr": "",
            "exit_code": 0,
        }

    def task_exists(self, task_name, working_dir=None, environment=None):
        return {"exists": task_name in self._available_tasks}

    def resolve_task_name(self, tool_or_candidates, working_dir=None, environment=None):
        if isinstance(tool_or_candidates, str):
            candidates = list(
                TOOL_TASK_ALIASES.get(tool_or_candidates, (tool_or_candidates,))
            )
        else:
            candidates = list(tool_or_candidates)
        for candidate in candidates:
            if candidate in self._available_tasks:
                return candidate
        return None

    def select_quality_environment(self, task_name, working_dir=None):
        return None, "fake executor declares no environments"

    def list_tasks(self, working_dir=None):
        return {"tasks": dict(self._available_tasks)}

    def _get_available_tasks(self, working_dir=None, environment=None):
        return dict(self._available_tasks)

    def run_task(
        self, task_name, args=None, timeout=300, working_dir=None, environment=None
    ):
        self.run_calls = [
            *getattr(self, "run_calls", []),
            (task_name, list(args or [])),
        ]
        return dict(self._run_result)


class TestSecurityScanTaskResolution:
    """execute_security_scan must resolve bandit's task through aliases,
    not the old hardcoded "security" name."""

    def test_resolves_security_scan_alias_when_only_it_exists(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"}
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.pixi_task_used == "security-scan"
        assert result.status != ExecutionStatus.ERROR

    def test_resolves_literal_bandit_alias_when_only_it_exists(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"bandit": "bandit -r src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.pixi_task_used == "bandit"

    def test_not_found_message_lists_candidates_and_available_tasks(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"lint": "ruff check src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status == ExecutionStatus.ERROR
        assert "security-scan" in result.raw_output
        assert "security" in result.raw_output
        assert "bandit" in result.raw_output
        assert "lint" in result.raw_output


class TestTypecheckTaskResolution:
    """execute_typecheck_assessment must resolve mypy's task through
    aliases (typecheck / mypy / type-check), not a single hardcoded name."""

    def test_resolves_typecheck_alias(self):
        pixi_executor = _FakePixiExecutor(available_tasks={"typecheck": "mypy src/"})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_typecheck_assessment(project_path="/tmp/project")

        assert result.pixi_task_used == "typecheck"

    def test_not_found_when_no_alias_defined(self):
        pixi_executor = _FakePixiExecutor(available_tasks={})
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_typecheck_assessment(project_path="/tmp/project")

        assert result.status == ExecutionStatus.ERROR
        assert "typecheck" in result.raw_output
        assert "type-check" in result.raw_output


PYRIGHT_FINDINGS = """\
/abs/src/a.py
  /abs/src/a.py:12:5 - error: Message text (reportFooBar)
  /abs/src/a.py:20:1 - error: "x" is not defined (reportUndefinedVariable)
/abs/src/b.py
  /abs/src/b.py:3:1 - warning: Import "os" is not accessed (reportUnusedImport)
2 errors, 1 warning, 0 informations
"""
PYRIGHT_CLEAN = "0 errors, 0 warnings, 0 informations \n"
MYPY_ONLY_FLAGS = (
    "--show-error-codes",
    "--show-column-numbers",
    "--strict",
    "--no-incremental",
    "--cache-dir",
)


def _typecheck(body, run_result, **kwargs):
    executor = _FakePixiExecutor({"typecheck": body}, run_result=run_result)
    adapter = QualityToolExecutionAdapter(direct_pixi_executor=executor)
    result = adapter.execute_typecheck_assessment(project_path="/tmp/project", **kwargs)
    return result, executor


def _run(exit_code, stdout="", stderr=""):
    return {
        "success": exit_code == 0,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
    }


class TestPyrightTypecheck:
    """A pyright `typecheck` task must run as defined, be parsed as pyright
    and be reported as pyright (issue #9)."""

    def test_no_mypy_flags_and_tool_is_pyright(self):
        result, executor = _typecheck(
            "pyright src/",
            _run(1, PYRIGHT_FINDINGS),
            strict_mode=True,
            incremental=False,
            cache_dir="/tmp/c",
        )
        args = executor.run_calls[0][1]
        assert not [a for a in args if a in MYPY_ONLY_FLAGS]
        assert result.tool.value == "pyright"

    def test_exit_1_with_diagnostics_is_findings(self):
        result, _ = _typecheck("pyright src/", _run(1, PYRIGHT_FINDINGS))
        assert result.status == ExecutionStatus.WARNING
        assert result.parsed_metrics.type_errors == 2
        assert len(result.violations) == 3
        assert {v.tool.value for v in result.violations} == {"pyright"}
        assert result.violations[0].line_number == 12
        assert result.violations[0].rule_code == "reportFooBar"

    @pytest.mark.parametrize(
        "stdout",
        [
            "0 errors, 0 warnings, 0 informations \n",
            "  /abs/a.py:3:1 - warning: Unused (reportUnusedImport)\n"
            "0 errors, 1 warning, 0 informations \n",
        ],
    )
    def test_exit_1_with_summary_or_warnings_only_is_findings(self, stdout):
        result, _ = _typecheck("pyright --warnings src/", _run(1, stdout))

        assert result.status == ExecutionStatus.WARNING
        assert result.parsed_metrics.type_errors == 0

    def test_exit_1_with_unrecognised_output_is_an_error(self):
        result, _ = _typecheck("pyright src/", _run(1, "Traceback: boom\n"))

        assert result.status == ExecutionStatus.ERROR

    def test_clean_exit_0_passes(self):
        result, _ = _typecheck("pyright src/", _run(0, PYRIGHT_CLEAN))
        assert result.status == ExecutionStatus.SUCCESS
        assert result.parsed_metrics.type_errors == 0

    def test_exit_4_is_an_error(self):
        result, _ = _typecheck(
            "pyright src/", _run(4, "", "Unexpected option --show-error-codes")
        )
        assert result.status == ExecutionStatus.ERROR

    def test_requested_pyright_resolves_typecheck_task(self):
        executor = _FakePixiExecutor(
            {"typecheck": "pyright src/"}, run_result=_run(0, PYRIGHT_CLEAN)
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=executor)
        result = adapter.execute_typecheck_assessment(
            tool=QualityTool("pyright"), project_path="/tmp/project"
        )
        assert result.pixi_task_used == "typecheck"
        assert result.tool.value == "pyright"

    def test_mypy_body_still_gets_mypy_flags_and_tool(self):
        result, executor = _typecheck("mypy src/", _run(0, ""), strict_mode=True)
        args = executor.run_calls[0][1]
        assert "--show-error-codes" in args
        assert "--show-column-numbers" in args
        assert "--strict" in args
        assert result.tool.value == "mypy"


class TestPyrightMultiLineDiagnostic:
    def test_rule_and_full_message_come_from_the_continuation_lines(self):
        from adapters.direct_pixi_execution import parse_pyright_text

        output = (
            "/abs/src/a.py\n"
            "  /abs/src/a.py:12:5 - error: Argument of type X is wrong\n"
            '    "X" is not assignable to "Y" (reportArgumentType)\n'
            "  /abs/src/a.py:20:1 - warning: Unused (reportUnusedImport)\n"
            "1 error, 1 warning, 0 informations \n"
        )
        diagnostics, error_count = parse_pyright_text(output)

        assert error_count == 1
        assert len(diagnostics) == 2
        _, _, _, severity, message, rule = diagnostics[0]
        assert (severity, rule) == ("error", "reportArgumentType")
        assert message == 'Argument of type X is wrong\n"X" is not assignable to "Y"'
        assert diagnostics[1][5] == "reportUnusedImport"


PYRIGHT_JSON = json.dumps(
    {
        "version": "1.1.0",
        "generalDiagnostics": [
            {
                "file": "/abs/a.py",
                "severity": "error",
                "message": "bad",
                "range": {
                    "start": {"line": 11, "character": 4},
                    "end": {"line": 11, "character": 9},
                },
                "rule": "reportFooBar",
            },
            {
                "file": "/abs/b.py",
                "severity": "warning",
                "message": "meh",
                "range": {
                    "start": {"line": 2, "character": 0},
                    "end": {"line": 2, "character": 1},
                },
            },
        ],
        "summary": {"errorCount": 1, "warningCount": 1, "informationCount": 0},
    }
)
PYRIGHT_JSON_SUMMARY_ONLY = json.dumps(
    {
        "generalDiagnostics": [],
        "summary": {"errorCount": 2, "warningCount": 0, "informationCount": 0},
    }
)


class TestPyrightJsonOutput:
    def test_parse_uses_one_based_lines_and_summary(self):
        from adapters.direct_pixi_execution import parse_pyright_text

        diagnostics, error_count = parse_pyright_text(PYRIGHT_JSON)

        assert error_count == 1
        assert diagnostics[0] == ("/abs/a.py", 12, 5, "error", "bad", "reportFooBar")
        assert diagnostics[1][:4] == ("/abs/b.py", 3, 1, "warning")

    def test_json_after_a_log_prefix_containing_braces(self):
        from adapters.direct_pixi_execution import parse_pyright_text

        output = 'starting {cfg} and {"x": 1}\n' + PYRIGHT_JSON

        diagnostics, error_count = parse_pyright_text(output)

        assert error_count == 1
        assert diagnostics[0][:2] == ("/abs/a.py", 12)

    def test_exit_1_with_json_errors_is_findings(self):
        result, _ = _typecheck("pyright --outputjson src/", _run(1, PYRIGHT_JSON))

        assert result.status == ExecutionStatus.WARNING
        assert result.parsed_metrics.type_errors == 1
        assert result.violations[0].line_number == 12

    def test_exit_1_with_summary_only_json_is_findings(self):
        result, _ = _typecheck(
            "pyright --outputjson src/", _run(1, PYRIGHT_JSON_SUMMARY_ONLY)
        )

        assert result.status == ExecutionStatus.WARNING
        assert result.parsed_metrics.type_errors == 2


class TestTypecheckRecommendations:
    def test_pyright_findings_get_pyright_advice(self):
        result, _ = _typecheck("pyright src/", _run(1, PYRIGHT_FINDINGS))
        advice = " ".join(result.recommendations)

        assert "typeCheckingMode" in advice
        assert "mypy --strict" not in advice

    def test_mypy_findings_keep_mypy_advice(self):
        result, _ = _typecheck(
            "mypy src/", _run(1, "src/a.py:3:1: error: bad type  [assignment]\n")
        )

        assert "mypy --strict" in " ".join(result.recommendations)


class TestDetectTypechecker:
    @pytest.mark.parametrize(
        "body,expected",
        [
            ("pyright src/", "pyright"),
            ("basedpyright", "pyright"),
            ("pixi run -e quality pyright src/", "pyright"),
            (["pyright", "src/"], "pyright"),
            ("mypy src/", "mypy"),
            ("python -m mypy src", "mypy"),
            ("uv run mypy src", "mypy"),
            ("env FOO=1 pyright src/", "pyright"),
            ("env -i FOO=1 BAR=2 mypy src", "mypy"),
            ("env -u FOO basedpyright", "pyright"),
            ("FOO=1 BAR=2 pyright src/", "pyright"),
            ("FOO=1 env BAR=2 mypy src", "mypy"),
            ("env FOO=1 flake8 src/", None),
            ("flake8 src/", None),
            ("echo 'a b", None),
            ("", None),
        ],
    )
    def test_classifies_first_real_token(self, body, expected):
        from adapters.direct_pixi_execution import detect_typechecker

        assert detect_typechecker(body) == expected


class TestSecurityScanHonestFailure:
    """execute_security_scan must not report a clean/scored result when bandit
    never actually ran, and must not treat bandit's exit-1-on-findings as an
    execution failure (same pattern as lint/typecheck, commit 4d9d638d)."""

    def test_real_execution_failure_is_reported_as_error_not_clean_score(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"},
            run_result={
                "success": False,
                "stdout": "",
                "stderr": "bandit: command not found",
                "exit_code": 127,
            },
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status == ExecutionStatus.ERROR
        assert result.parsed_metrics.overall_score == 0.0
        assert "No security vulnerabilities detected." not in result.recommendations

    def test_findings_on_nonzero_exit_are_not_swallowed_as_execution_error(self):
        bandit_json = (
            '{"results": [{"test_id": "B105", "test_name": "hardcoded_password_string", '
            '"issue_text": "Possible hardcoded password", "issue_severity": "HIGH", '
            '"issue_confidence": "HIGH", "filename": "src/app.py", "line_number": 12}]}'
        )
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"},
            run_result={
                "success": False,
                "stdout": bandit_json,
                "stderr": "",
                "exit_code": 1,
            },
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status != ExecutionStatus.ERROR
        assert result.status == ExecutionStatus.WARNING
        assert len(result.security_issues) == 1
        assert result.parsed_metrics.overall_score != 10.0

    def test_clean_scan_with_zero_findings_stays_clean(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"security-scan": "bandit -r src/"},
            run_result={
                "success": True,
                "stdout": '{"results": []}',
                "stderr": "",
                "exit_code": 0,
            },
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_security_scan(project_path="/tmp/project")

        assert result.status == ExecutionStatus.SUCCESS
        assert result.parsed_metrics.overall_score == 10.0


class TestComplexityTaskResolution:
    """execute_complexity_analysis must resolve radon's task through
    aliases (complexity-check / complexity / radon)."""

    def test_resolves_complexity_check_alias(self):
        pixi_executor = _FakePixiExecutor(
            available_tasks={"complexity-check": "radon cc src/"},
            run_result={"success": True, "stdout": "{}", "stderr": "", "exit_code": 0},
        )
        adapter = QualityToolExecutionAdapter(direct_pixi_executor=pixi_executor)

        result = adapter.execute_complexity_analysis(project_path="/tmp/project")

        assert result.pixi_task_used == "complexity-check"
