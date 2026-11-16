"""
Bandit "found issues" must never be reported as "bandit errored", and the
payload of quality_execute_pixi_aware_assessment must stay bounded.

Covers: JSON captured through a temp file (-f json -o <tmp>), tolerant parsing,
the findings / error / passed classification, stdout/stderr truncation and the
summary_only mode.
"""

import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from quality_assurance import server as main_server

SEVERITIES = ["HIGH", "MEDIUM", "MEDIUM", "LOW"]


def bandit_doc(n_results=4, errors=None):
    results = [
        {
            "filename": f"pkg/f{i}.py",
            "line_number": i + 1,
            "test_id": f"B10{i}",
            "test_name": "x",
            "issue_severity": SEVERITIES[i % 4],
            "issue_confidence": "HIGH",
            "issue_text": "something risky",
            "code": "SECRET_SNIPPET = 1\n",
            "line_range": [i + 1],
            "more_info": "https://example.invalid",
        }
        for i in range(n_results)
    ]
    return json.dumps(
        {
            "errors": errors or [],
            "generated_at": "now",
            "metrics": {"_totals": {"loc": 10}},
            "results": results,
        }
    )


def make_adapter(body="bandit -c pyproject.toml -r hummingbot/"):
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
    adapter._is_pixi_project = Mock(return_value=True)
    adapter._get_available_tasks = Mock(return_value={"security-scan": body})
    adapter.select_quality_environment = Mock(return_value=("quality", "test"))
    env_info = Mock()
    env_info.available_tools = {"bandit"}
    env_info.tool_versions = {}
    env_info.environment_health = "optimal"
    env_info.performance_indicators = {}
    env_info.recommendations = []
    env_info.missing_tools = set()
    adapter.detect_quality_environment = Mock(return_value=env_info)
    return adapter


def run_bandit(exit_code, file_json=None, stdout="", stderr="", body=None, **cfg):
    """Run bandit through the adapter with subprocess mocked; the fake writes
    file_json to whatever path follows -o."""
    adapter = make_adapter(body) if body else make_adapter()
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        if "-o" in argv:
            seen["path"] = argv[argv.index("-o") + 1]
            seen["existed_during_run"] = os.path.exists(seen["path"])
            if file_json is not None:
                Path(seen["path"]).write_text(file_json)
        return Mock(returncode=exit_code, stdout=stdout, stderr=stderr)

    with patch("adapters.direct_pixi_execution.subprocess.run", side_effect=fake_run):
        result = adapter.run_quality_task(
            task_name="security-scan",
            quality_tool="bandit",
            target_paths=["src/"],
            quality_config={"output_format": "json"},
            environment="quality",
            **cfg,
        )
    return result, seen


class FakeEnv:
    available_tools = {"bandit"}
    quality_tasks = {}
    environment_health = "optimal"
    tool_versions = {}
    performance_indicators = {}
    recommendations = []


class AdapterBackedFake:
    """Server-facing adapter whose run_quality_task is the real one."""

    def __init__(self, result):
        self._result = result
        self.detect_quality_environment = Mock(return_value=FakeEnv())
        self.optimize_quality_environment = Mock(return_value={})
        self.generate_quality_task_template = Mock(
            return_value=Mock(task_name="security-scan", output_format="json")
        )
        self.resolve_task_name = Mock(return_value="security-scan")

    def run_quality_task(self, **kwargs):
        return self._result


def assess(monkeypatch, tmp_path, result, **kwargs):
    monkeypatch.setattr(main_server, "orchestration_service", object())
    monkeypatch.setattr(
        main_server, "container", Mock(pixi_executor=AdapterBackedFake(result))
    )
    return main_server.quality_execute_pixi_aware_assessment.fn(
        tools=["bandit"], project_path=str(tmp_path), **kwargs
    )


class TestFileCapture:
    def test_tempfile_added_and_caller_flags_replaced_task_body(self):
        body = "bandit -c pyproject.toml -f txt -o old.txt -r hummingbot/"
        _, seen = run_bandit(1, file_json=bandit_doc(), body=body)
        argv = seen["argv"]
        assert "old.txt" not in argv and "txt" not in argv
        assert argv.count("-f") == 1 and argv[argv.index("-f") + 1] == "json"
        assert argv.count("-o") == 1
        assert "-c" in argv and "hummingbot/" in argv
        assert not seen["path"].startswith("/tmp/project")

    @pytest.mark.parametrize(
        "body",
        [
            "bandit -r src/ --format=csv --output=o.csv",
            "bandit -r src/ -fcsv -oo.csv",
        ],
    )
    def test_attached_forms_are_stripped(self, body):
        _, seen = run_bandit(1, file_json=bandit_doc(), body=body)
        argv = seen["argv"]
        assert not any(a.startswith(("--format", "--output", "-fcsv")) for a in argv)
        assert "o.csv" not in argv and "-oo.csv" not in argv
        assert argv[-4:-2] == ["-f", "json"] and argv[-2] == "-o"

    def test_generated_args_path_uses_tempfile(self):
        _, seen = run_bandit(1, file_json=bandit_doc(), body="bandit")
        argv = seen["argv"]
        assert argv.count("-f") == 1 and argv.count("-o") == 1

    def test_file_is_read_and_removed(self):
        result, seen = run_bandit(1, file_json=bandit_doc(), stdout="")
        assert result["findings_detected"] is True
        assert result["parsed_output"]["issue_count"] == 4
        assert not os.path.exists(seen["path"])
        assert "structured_output" not in result

    def test_file_removed_when_run_raises(self):
        adapter = make_adapter()
        seen = {}

        def boom(argv, **kwargs):
            seen["path"] = argv[argv.index("-o") + 1]
            raise OSError("no pixi")

        with patch("adapters.direct_pixi_execution.subprocess.run", side_effect=boom):
            adapter.run_quality_task(
                task_name="security-scan",
                quality_tool="bandit",
                target_paths=["src/"],
                environment="quality",
            )
        assert not os.path.exists(seen["path"])

    def test_falls_back_to_stdout_when_file_empty(self):
        result, _ = run_bandit(1, file_json=None, stdout=bandit_doc(2))
        assert result["parsed_output"]["issue_count"] == 2
        assert result["findings_detected"] is True


class TestParse:
    def parse(self, text):
        return make_adapter()._parse_bandit_output(text)

    def test_noise_around_json(self):
        parsed = self.parse("[main] INFO profile\n" + bandit_doc() + "\ntrailer")
        assert parsed["issue_count"] == 4

    def test_shape_and_no_metrics_or_code(self):
        parsed = self.parse(bandit_doc())
        assert parsed["severity_counts"] == {"HIGH": 1, "MEDIUM": 2, "LOW": 1}
        assert parsed["confidence_counts"] == {"HIGH": 4, "MEDIUM": 0, "LOW": 0}
        assert parsed["error_count"] == 0 and parsed["errors"] == []
        assert parsed["security_issues_truncated"] is False
        assert set(parsed["security_issues"][0]) == {
            "filename",
            "line_number",
            "test_id",
            "issue_severity",
            "issue_confidence",
            "issue_text",
        }
        assert "metrics" not in parsed and "metrics" not in json.dumps(parsed)
        assert "SECRET_SNIPPET" not in json.dumps(parsed)

    def test_caps(self):
        errs = [{"filename": f"e{i}.py", "reason": "syntax"} for i in range(30)]
        parsed = self.parse(bandit_doc(120, errors=errs))
        assert parsed["issue_count"] == 120
        assert len(parsed["security_issues"]) == 50
        assert parsed["security_issues_truncated"] is True
        assert parsed["error_count"] == 30 and len(parsed["errors"]) == 20


class TestVerdict:
    def test_findings_with_severity_counts(self, monkeypatch, tmp_path):
        result, _ = run_bandit(1, file_json=bandit_doc())
        out = assess(monkeypatch, tmp_path, result)
        assert out["gate_verdict"] == "findings"
        assert "bandit (HIGH 1, MEDIUM 2, LOW 1)" in out["gate_verdict_reason"]

    def test_banner_noise_before_json_still_findings(self, monkeypatch, tmp_path):
        result, _ = run_bandit(1, stdout="[main] INFO banner\n" + bandit_doc())
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "findings"

    def test_errors_array_is_error(self, monkeypatch, tmp_path):
        doc = bandit_doc(4, errors=[{"filename": "x.py", "reason": "syntax error"}])
        result, _ = run_bandit(1, file_json=doc)
        out = assess(monkeypatch, tmp_path, result)
        assert out["gate_verdict"] == "error"
        assert "1" in out["gate_verdict_reason"]
        assert "bandit" in out["gate_verdict_reason"]
        assert not result.get("findings_detected")

    @pytest.mark.parametrize("code,stdout", [(2, "usage: bandit"), (1, "Traceback")])
    def test_crash_or_no_json_is_error(self, monkeypatch, tmp_path, code, stdout):
        result, _ = run_bandit(code, stdout=stdout, stderr="boom")
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "error"

    def test_not_found_is_error(self, monkeypatch, tmp_path):
        result, _ = run_bandit(127, stderr="bandit: command not found")
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "error"

    def test_exit_1_zero_results_is_error(self, monkeypatch, tmp_path):
        result, _ = run_bandit(1, file_json=bandit_doc(0))
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "error"

    def test_clean_exit_0_passed(self, monkeypatch, tmp_path):
        result, _ = run_bandit(0, file_json=bandit_doc(0))
        out = assess(monkeypatch, tmp_path, result)
        assert out["gate_verdict"] == "passed"


class TestBoundedPayload:
    def test_stdout_stderr_truncated_with_flags(self, monkeypatch, tmp_path):
        result = {
            "success": False,
            "exit_code": 2,
            "stdout": "x" * 5000,
            "stderr": "y" * 2500,
        }
        entry = assess(monkeypatch, tmp_path, result)["assessment_results"][0]
        assert len(entry["stdout"]) == 2000 and entry["stdout_truncated"] is True
        assert len(entry["stderr"]) == 2000 and entry["stderr_truncated"] is True
        assert entry["stdout_length"] == 5000 and entry["stderr_length"] == 2500

    def test_short_output_not_flagged(self, monkeypatch, tmp_path):
        result = {"success": False, "exit_code": 2, "stdout": "ab", "stderr": ""}
        entry = assess(monkeypatch, tmp_path, result)["assessment_results"][0]
        assert entry["stdout"] == "ab" and entry["stdout_truncated"] is False

    def test_stdout_dropped_when_parsed(self, monkeypatch, tmp_path):
        result, _ = run_bandit(1, stdout=bandit_doc())
        out = assess(monkeypatch, tmp_path, result)
        entry = out["assessment_results"][0]
        assert entry["stdout"] == "" and entry["stdout_note"]
        assert entry["parsed_output"]["issue_count"] == 4
        assert "metrics" not in json.dumps(out["assessment_results"])

    def test_summary_only_shape(self, monkeypatch, tmp_path):
        result, _ = run_bandit(1, file_json=bandit_doc())
        out = assess(monkeypatch, tmp_path, result, summary_only=True)
        entry = out["assessment_results"][0]
        assert set(entry) == {
            "task_name",
            "exit_code",
            "findings_detected",
            "counts",
        }
        assert entry["exit_code"] == 1 and entry["findings_detected"] is True
        assert entry["counts"]["issue_count"] == 4
        assert entry["counts"]["severity_counts"] == {
            "HIGH": 1,
            "MEDIUM": 2,
            "LOW": 1,
        }
        assert out["gate_verdict"] == "findings"

    def test_summary_only_includes_error(self, monkeypatch, tmp_path):
        doc = bandit_doc(1, errors=[{"filename": "x.py", "reason": "bad"}])
        result, _ = run_bandit(1, file_json=doc)
        entry = assess(monkeypatch, tmp_path, result, summary_only=True)[
            "assessment_results"
        ][0]
        assert entry["error"]
        assert entry["counts"]["error_count"] == 1


def test_lean_schema_exposes_summary_only():
    from quality_assurance import lean_server

    source = Path(lean_server.__file__).read_text()
    start = source.index('registry["quality_execute_pixi_aware_assessment"]')
    end = source.index('registry["quality_optimize_pixi_environment"]')
    assert '"summary_only"' in source[start:end]
