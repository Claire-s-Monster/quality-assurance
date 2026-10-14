"""Regression tests: callers must use the message-first LoggingAdapter contract."""

import logging
from unittest.mock import MagicMock

import pytest

from adapters.git_integration import GitIntegrationAdapter
from adapters.logging import LoggingAdapter
from core.models import QualityBaseline, QualityMetrics
from core.quality_orchestration_service import QualityOrchestrationService


@pytest.fixture
def real_logging():
    return LoggingAdapter()


def _service(real_logging, trend_analyzer):
    return QualityOrchestrationService(
        quality_executor=MagicMock(),
        quality_analyzer=MagicMock(),
        trend_analyzer=trend_analyzer,
        logging=real_logging,
    )


def test_compare_against_baseline_error_logs_with_real_logger(real_logging, caplog):
    trend = MagicMock()
    trend.compare_against_baseline.side_effect = ValueError("boom")
    service = _service(real_logging, trend)
    service.execute_comprehensive_suite = MagicMock()

    with caplog.at_level(logging.ERROR, logger="agent_ecosystem"):
        with pytest.raises(RuntimeError, match="Baseline comparison failed"):
            service.compare_against_baseline("base-1")

    messages = [r.getMessage() for r in caplog.records]
    assert any("compare_against_baseline" in m and "boom" in m for m in messages)


def test_git_metadata_error_logs_with_real_logger(tmp_path, caplog):
    adapter = GitIntegrationAdapter(working_dir=str(tmp_path), logging=LoggingAdapter())
    adapter._is_git_repository = MagicMock(return_value=True)
    adapter._get_commit_info = MagicMock(side_effect=RuntimeError("git exploded"))

    with caplog.at_level(logging.ERROR, logger="agent_ecosystem"):
        result = adapter.get_git_metadata()

    assert result["is_git_repo"] is False
    messages = [r.getMessage() for r in caplog.records]
    assert any("get_git_metadata" in m and "git exploded" in m for m in messages)


def test_log_operation_result_signature_matches_port(real_logging, caplog):
    with caplog.at_level(logging.INFO, logger="agent_ecosystem.operations"):
        real_logging.log_operation_result("lint_assessment", True, 12.5, {"score": 9})
    assert any("lint_assessment" in r.getMessage() for r in caplog.records)


def _metrics_dict(score: float) -> dict:
    return {
        "overall_score": score,
        "total_violations": 0,
        "critical_violations": 0,
        "high_violations": 0,
        "medium_violations": 0,
        "low_violations": 0,
        "total_lines": 10,
        "code_lines": 8,
        "comment_lines": 1,
        "blank_lines": 1,
    }


def _metrics(score: float) -> QualityMetrics:
    return QualityMetrics(**_metrics_dict(score))


def _baseline_kwargs(metrics):
    return dict(
        baseline_id="b1",
        created_at="2026-01-01T00:00:00Z",
        project_name="p",
        metrics=metrics,
        python_version="3.12",
        expires_at="2027-01-01T00:00:00Z",
    )


def test_baseline_overall_score_defaults_from_metrics():
    baseline = QualityBaseline(**_baseline_kwargs(_metrics(7.5)))
    assert baseline.overall_score == 7.5


def test_baseline_explicit_overall_score_is_kept():
    baseline = QualityBaseline(**_baseline_kwargs(_metrics(7.5)), overall_score=3.0)
    assert baseline.overall_score == 3.0


def test_baseline_model_validate_dict_without_overall_score():
    data = _baseline_kwargs(_metrics(6.0))
    data["metrics"] = _metrics_dict(6.0)
    baseline = QualityBaseline.model_validate(data)
    assert baseline.overall_score == 6.0
