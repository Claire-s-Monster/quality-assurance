"""
Regression tests for server.py handlers that drifted from the real pydantic models.

Each test drives the MCP tool function (``.fn``) with an orchestration stand-in
that returns REAL model instances, so attribute drift raises instead of being
hidden by a loose fake.

Run with: pixi run python -m pytest tests/test_server_handler_model_drift.py -v
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from adapters.direct_pixi_execution import QualityTaskTemplate  # noqa: E402
from core.models import (  # noqa: E402
    AutomatedFixResult,
    ComplexityMetric,
    ComprehensiveQualityResult,
    ExecutionStatus,
    FixType,
    FixValidationMode,
    QualityAssessmentResult,
    QualityAssessmentType,
    QualityBaseline,
    QualityComparison,
    QualityMetrics,
    QualityReport,
    QualityTool,
    ReportFormat,
    ReportTemplate,
)

NOW = "2026-01-01T00:00:00"


def _metrics(**overrides) -> QualityMetrics:
    values = dict(
        overall_score=7.5,
        total_violations=12,
        critical_violations=2,
        high_violations=3,
        medium_violations=4,
        low_violations=3,
        security_issues_count=5,
        total_lines=100,
        code_lines=80,
        comment_lines=10,
        blank_lines=10,
    )
    values.update(overrides)
    return QualityMetrics(**values)


@pytest.fixture
def server(monkeypatch):
    from quality_assurance import server as server_module

    fake = SimpleNamespace()
    monkeypatch.setattr(server_module, "orchestration_service", fake)
    monkeypatch.setattr(
        server_module,
        "container",
        SimpleNamespace(
            logging=SimpleNamespace(
                log_warning=lambda *a, **k: None, log_info=lambda *a, **k: None
            )
        ),
    )
    server_module.fake = fake
    return server_module


def test_baseline_handler_reads_real_baseline_fields(server):
    baseline = QualityBaseline(
        baseline_id="b1",
        created_at=NOW,
        project_name="p",
        metrics=_metrics(),
        python_version="3.12",
        pixi_environment={"name": "quality"},
        expires_at=NOW,
    )
    server.fake.establish_quality_baseline = lambda **kw: baseline

    result = server.quality_establish_baseline.fn()

    assert "error" not in result, result
    snapshot = result["quality_snapshot"]
    assert snapshot["overall_score"] == 7.5
    assert snapshot["total_violations"] == 12
    assert snapshot["critical_violations"] == 2
    assert snapshot["security_issues_count"] == 5
    assert result["environment_info"]["pixi_environment"] == {"name": "quality"}


def test_comparison_handler_reads_real_comparison_fields(server):
    comparison = QualityComparison(
        baseline_id="b1",
        current_assessment_id="a1",
        comparison_timestamp=NOW,
        overall_score_delta=-0.5,
        violation_count_delta=4,
        critical_violation_delta=1,
        security_issue_delta=2,
        trend_direction="degrading",
        regression_detected=True,
        regression_alerts=["score dropped"],
        trend_recommendations=["fix criticals"],
    )
    server.fake.compare_against_baseline = lambda **kw: comparison

    result = server.quality_compare_against_baseline.fn(baseline_id="b1")

    assert "error" not in result, result
    assert result["comparison_results"]["overall_score_delta"] == -0.5
    assert result["metric_deltas"]["violations_delta"] == 4
    assert result["metric_deltas"]["critical_violations_delta"] == 1
    assert result["metric_deltas"]["security_issues_delta"] == 2
    assert result["recommendations"] == ["fix criticals"]
    assert result["regression_details"]["regression_alerts"] == ["score dropped"]


def _report(content: str = "# Report", fmt=ReportFormat.MARKDOWN) -> QualityReport:
    return QualityReport(
        report_format=fmt,
        template_style=ReportTemplate.STANDARD,
        generated_at=NOW,
        project_name="p",
        assessment_period="30d",
        generated_by="test",
        executive_summary="all good",
        overall_score=8.0,
        quality_grade="B",
        trend_direction="stable",
        sections_included=["summary", "metrics"],
        quality_metrics=_metrics(),
        recommendations=["a", "b"],
        raw_results_attached=False,
        report_content=content,
    )


def test_report_handler_reads_real_report_fields(server):
    server.fake.quality_reporting = object()
    server.fake.generate_quality_report = lambda **kw: _report("# Report")

    result = server.quality_generate_comprehensive_report.fn()

    assert "error" not in result, result
    assert result["report_metadata"]["format"] == "markdown"
    assert result["report_metadata"]["template"] == "standard"
    assert result["content_summary"]["content_length_chars"] == len("# Report")
    assert result["content_summary"]["sections_included"] == ["summary", "metrics"]
    assert result["content"] == "# Report"
    assert result["report_sections"]["recommendations_count"] == 2


def _fix_result(**overrides) -> AutomatedFixResult:
    values = dict(
        requested_fix_types=[FixType.IMPORTS],
        dry_run=True,
        validation_mode=FixValidationMode.STRICT,
        start_time=NOW,
        end_time=NOW,
        execution_time_ms=1.0,
        failed_fixes=[{"file": "a.py", "reason": "boom"}],
        skipped_fixes=[{"file": "b.py", "reason": "skip"}],
        rollback_available=False,
        total_files_modified=0,
        total_changes_applied=0,
    )
    values.update(overrides)
    return AutomatedFixResult(**values)


def test_apply_fixes_serializes_dict_failed_and_skipped_entries(server):
    server.fake.automated_fix = object()
    server.fake.apply_automated_fixes = lambda **kw: _fix_result()

    result = server.quality_apply_automated_fixes.fn(fix_types=["imports"])

    assert "error" not in result, result
    assert result["fix_results"]["failed_fixes"] == [{"file": "a.py", "reason": "boom"}]
    assert result["fix_results"]["skipped_fixes"] == [
        {"file": "b.py", "reason": "skip"}
    ]


def test_fix_entry_to_dict_accepts_dicts_and_models(server):
    assert server._fix_entry_to_dict({"a": 1}) == {"a": 1}
    metrics = _metrics()
    assert server._fix_entry_to_dict(metrics) == metrics.model_dump()


def test_complexity_handler_uses_complexity_score(server, tmp_path):
    metric = ComplexityMetric(
        name="f",
        complexity_score=12,
        maintainability_index=50.0,
        lines_of_code=10,
        difficulty=1.0,
        effort=1.0,
        time_to_understand=1.0,
    )
    assessment = QualityAssessmentResult(
        assessment_type=QualityAssessmentType.COMPLEXITY,
        tool=QualityTool.RADON,
        status=ExecutionStatus.SUCCESS,
        start_time=NOW,
        end_time=NOW,
        execution_time_ms=1.0,
        pixi_task_used="complexity",
        target_path="src/",
        files_analyzed=1,
        raw_output="",
        parsed_metrics=_metrics(),
        complexity_results=[metric],
    )
    server.fake.quality_executor = SimpleNamespace(
        execute_complexity_analysis=lambda **kw: assessment,
        pixi_executor=SimpleNamespace(working_dir="/w"),
    )

    result = server.quality_execute_complexity_analysis.fn(
        project_path=str(tmp_path), complexity_threshold=10
    )

    assert "error" not in result, result
    summary = result["complexity_summary"]
    assert summary["average_complexity"] == 12
    assert summary["high_complexity_functions"] == 1


def test_generate_pixi_tasks_handles_dataclass_templates(server, monkeypatch):
    def make_template(tool_name, target_pattern, output_format):
        return QualityTaskTemplate(
            tool_name=tool_name,
            task_name=f"{tool_name}-check",
            command=f"{tool_name} {target_pattern}",
            description=f"Run {tool_name}",
            target_pattern=target_pattern,
            output_format=output_format,
            dependencies=[],
            performance_hints={},
        )

    monkeypatch.setattr(
        server.container,
        "pixi_executor",
        SimpleNamespace(generate_quality_task_template=make_template),
        raising=False,
    )

    result = server.quality_generate_pixi_tasks.fn(
        tools=["ruff"], integration_mode="integrated"
    )

    assert "error" not in result, result
    assert result["task_generation_summary"]["individual_tasks_generated"] == 1
    assert result["task_generation_summary"]["failed_generations"] == 0
    assert result["generated_tasks"]["ruff-check"]["cmd"] == "ruff src/"
    assert result["generated_tasks"]["quality-check"]["cmd"] == "pixi run ruff-check"


def test_generate_pixi_tasks_json_format_is_serializable(server, monkeypatch):
    template = QualityTaskTemplate(
        "ruff", "ruff-check", "ruff .", "d", "src/", "json", [], {}
    )
    monkeypatch.setattr(
        server.container,
        "pixi_executor",
        SimpleNamespace(generate_quality_task_template=lambda **kw: template),
        raising=False,
    )

    result = server.quality_generate_pixi_tasks.fn(tools=["ruff"], output_format="JSON")

    assert (
        result["generated_tasks"]["individual_tasks"]["ruff"]["task_name"]
        == "ruff-check"
    )


def test_validation_mode_lookup_is_case_insensitive(server):
    server.fake.automated_fix = object()
    seen = {}

    def apply(**kw):
        seen.update(kw)
        return _fix_result(validation_mode=kw["validation_mode"])

    server.fake.apply_automated_fixes = apply

    result = server.quality_apply_automated_fixes.fn(
        fix_types=["imports"], validation_mode="Permissive"
    )

    assert seen["validation_mode"] is FixValidationMode.PERMISSIVE
    assert result["validation_results"]["validation_mode"] == "permissive"


def test_validation_mode_none_and_unknown_fall_back_to_strict(server):
    server.fake.automated_fix = object()
    server.fake.apply_automated_fixes = lambda **kw: _fix_result(
        validation_mode=kw["validation_mode"]
    )

    for mode in (None, "moderate"):
        result = server.quality_apply_automated_fixes.fn(
            fix_types=["imports"], validation_mode=mode
        )
        assert result["validation_results"]["validation_mode"] == "strict"


@pytest.mark.parametrize(
    ("fmt", "template", "expected_fmt"),
    [
        ("HTML", "Executive", "html"),
        (None, None, "markdown"),
        ("bogus", "x", "markdown"),
    ],
)
def test_report_format_and_template_lookup(server, fmt, template, expected_fmt):
    server.fake.quality_reporting = object()
    seen = {}

    def generate(**kw):
        seen.update(kw)
        return _report(fmt=kw["format"])

    server.fake.generate_quality_report = generate

    result = server.quality_generate_comprehensive_report.fn(
        format=fmt, template=template
    )

    assert "error" not in result, result
    assert seen["format"] == ReportFormat(expected_fmt)
    if template == "Executive":
        assert seen["template"] is ReportTemplate.EXECUTIVE
    else:
        assert seen["template"] is ReportTemplate.STANDARD


def _suite_result(config) -> ComprehensiveQualityResult:
    return ComprehensiveQualityResult(
        configuration=config,
        start_time=NOW,
        end_time=NOW,
        total_execution_time_ms=1.0,
        executed_in_parallel=True,
        overall_metrics=_metrics(),
        overall_score=8.0,
        meets_threshold=True,
        report_generated=False,
    )


def test_suite_custom_target_paths_are_honoured_without_warning(
    server, tmp_path, monkeypatch
):
    (tmp_path / "lib").mkdir()
    (tmp_path / "pkg").mkdir()
    monkeypatch.chdir(tmp_path)
    server.fake.execute_comprehensive_suite = _suite_result

    result = server.quality_execute_comprehensive_suite.fn(
        included_tools=["ruff"], target_paths=["lib/", "pkg/"]
    )

    assert "error" not in result, result
    assert result["warnings"] == []


def test_suite_default_target_paths_produce_no_warning(server):
    server.fake.execute_comprehensive_suite = _suite_result

    result = server.quality_execute_comprehensive_suite.fn(included_tools=["ruff"])

    assert result["warnings"] == []
