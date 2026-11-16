"""
Review fixes for PR #4: positive evidence for "passed", findings never hidden by
exit 0, bounded parsed_output, tempfile failure fallback, bounded recommendations.
"""

import json
from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from quality_assurance import server as main_server

from .test_bandit_findings_verdict import assess, bandit_doc, run_bandit


def enhance(tool, result):
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir="/tmp/project")
    env_info = Mock()
    env_info.available_tools = {tool}
    env_info.tool_versions = {}
    env_info.environment_health = "optimal"
    env_info.performance_indicators = {}
    env_info.recommendations = []
    return adapter._enhance_quality_result(dict(result), tool, env_info, 0.0)


def ruff_violations(n, message="msg"):
    return json.dumps(
        [{"code": "E501", "message": message, "filename": f"f{i}.py"} for i in range(n)]
    )


class TestBanditNeedsReport:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"file_json": None, "stdout": ""},
            {"file_json": "", "stdout": ""},
            {"file_json": None, "stdout": "not json at all"},
            {"file_json": "{garbage", "stdout": ""},
        ],
    )
    def test_exit_0_without_report_is_error(self, monkeypatch, tmp_path, kwargs):
        result, _ = run_bandit(0, **kwargs)
        assert result["error"] == "bandit produced no parseable report"
        out = assess(monkeypatch, tmp_path, result)
        assert out["gate_verdict"] == "error"

    def test_exit_0_with_results_is_findings(self, monkeypatch, tmp_path):
        result, _ = run_bandit(0, file_json=bandit_doc(3))
        assert result["findings_detected"] is True
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "findings"

    def test_exit_0_empty_results_list_is_passed(self, monkeypatch, tmp_path):
        result, _ = run_bandit(0, file_json=bandit_doc(0))
        assert "error" not in result
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "passed"


class TestExitZeroDoesNotHideFindings:
    def test_ruff_exit_zero_with_violations_is_findings(self, monkeypatch, tmp_path):
        base = {
            "success": True,
            "exit_code": 0,
            "stdout": ruff_violations(3),
            "stderr": "",
        }
        result = enhance("ruff", base)
        assert result["findings_detected"] is True
        out = assess(monkeypatch, tmp_path, result)
        assert out["gate_verdict"] == "findings"

    def test_ruff_exit_zero_clean_is_passed(self, monkeypatch, tmp_path):
        base = {"success": True, "exit_code": 0, "stdout": "[]", "stderr": ""}
        result = enhance("ruff", base)
        assert not result.get("findings_detected")
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "passed"

    def test_unparseable_text_exit_1_still_not_findings(self):
        base = {"success": False, "exit_code": 1, "stdout": "Traceback", "stderr": ""}
        assert not enhance("ruff", base).get("findings_detected")


class TestUnknownShapeFailsClosed:
    @pytest.mark.parametrize("shape", [{}, {"foo": 1}])
    def test_unrecognised_result_is_error(self, monkeypatch, tmp_path, shape):
        assert main_server._classify_pixi_aware_outcome(shape) == "failed"
        out = assess(monkeypatch, tmp_path, shape)
        assert out["gate_verdict"] == "error"
        assert out["execution_summary"]["tools_executed"] == 0
        assert "no execution status" in out["gate_verdict_reason"]

    @pytest.mark.parametrize(
        "shape,expected",
        [
            ({"exit_code": 0}, "executed"),
            ({"success": True}, "executed"),
            ({"success": True, "error": "boom"}, "failed"),
            ({"exit_code": 0, "status": "error"}, "failed"),
            ({"status": "unavailable"}, "unavailable"),
        ],
    )
    def test_positive_evidence(self, shape, expected):
        assert main_server._classify_pixi_aware_outcome(shape) == expected


class TestParsedOutputBounded:
    def parsed(self):
        return {
            "tool": "ruff",
            "violation_count": 200,
            "violations": [
                {"code": "E1", "message": "m" * 5000, "n": i} for i in range(200)
            ],
            "summary": "s" * 900,
        }

    def check(self, parsed):
        assert len(parsed["violations"]) == 50
        assert parsed["violations_total"] == 200
        assert parsed["violations_truncated"] is True
        assert parsed["violation_count"] == 200
        assert len(parsed["violations"][0]["message"]) <= 500
        assert len(parsed.get("summary", "")) <= 500

    def test_server_bound(self):
        bounded = main_server._bound_pixi_aware_result(
            {"parsed_output": self.parsed(), "stdout": "", "stderr": ""}
        )
        self.check(bounded["parsed_output"])

    def test_adapter_bound_any_tool(self):
        base = {
            "success": False,
            "exit_code": 1,
            "stdout": ruff_violations(200, "m" * 5000),
            "stderr": "",
        }
        result = enhance("ruff", base)
        self.check(result["parsed_output"])
        assert result["findings_detected"] is True

    def test_mypy_type_errors_capped(self):
        errors = "\n".join(f"f{i}.py:1: error: bad" for i in range(120))
        base = {"success": False, "exit_code": 1, "stdout": errors, "stderr": ""}
        parsed = enhance("mypy", base)["parsed_output"]
        assert len(parsed["type_errors"]) == 50
        assert parsed["type_errors_total"] == 120
        assert parsed["error_count"] == 120


class TestTempfileFailure:
    def test_mkstemp_oserror_falls_back_to_stdout(self, monkeypatch, tmp_path):
        with patch(
            "adapters.direct_pixi_execution.tempfile.mkstemp",
            side_effect=OSError("disk full"),
        ):
            result, seen = run_bandit(1, stdout=bandit_doc(2))
        assert "-o" not in seen["argv"]
        argv = seen["argv"]
        assert argv[argv.index("-f") + 1] == "json"
        assert result["parsed_output"]["issue_count"] == 2
        assert result["report_capture"].startswith("stdout (tempfile unavailable")
        assert "disk full" in result["report_capture"]
        assert assess(monkeypatch, tmp_path, result)["gate_verdict"] == "findings"

    def test_direct_tool_body_without_o(self):
        body = "bandit -c pyproject.toml -f txt -r hummingbot/"
        with patch(
            "adapters.direct_pixi_execution.tempfile.mkstemp",
            side_effect=OSError("nope"),
        ):
            result, seen = run_bandit(1, stdout=bandit_doc(1), body=body)
        argv = seen["argv"]
        assert "-o" not in argv and "txt" not in argv
        assert argv.count("-f") == 1 and argv[argv.index("-f") + 1] == "json"
        assert result["parsed_output"]["issue_count"] == 1


class TestRecommendationsBounded:
    STDERR = "y" * 50_000

    def failed(self):
        return {"success": False, "exit_code": 2, "stdout": "", "stderr": self.STDERR}

    def test_summary_only_omits_stderr(self, monkeypatch, tmp_path):
        out = assess(monkeypatch, tmp_path, self.failed(), summary_only=True)
        recs = out["recommendations"]
        assert len(json.dumps(recs)) < 1000
        assert "yyyy" not in json.dumps(recs)
        assert "bandit" in json.dumps(recs)

    def test_default_caps_stderr_at_300(self, monkeypatch, tmp_path):
        out = assess(monkeypatch, tmp_path, self.failed())
        recs = out["recommendations"]
        assert "yyyy" in json.dumps(recs)
        assert max(len(r) for r in recs) < 500

    def test_long_error_capped_too(self, monkeypatch, tmp_path):
        result = {"success": False, "exit_code": 2, "error": "e" * 50_000}
        out = assess(monkeypatch, tmp_path, result)
        assert max(len(r) for r in out["recommendations"]) < 500
