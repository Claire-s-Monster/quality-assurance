"""
Unit tests for QualityTrendAnalysisAdapter.

Tests baseline management, trend analysis, comparison capabilities,
and regression detection with JSON persistence.
"""

import json
import tempfile
from datetime import datetime, UTC, timedelta
from pathlib import Path
import pytest
from unittest.mock import patch

from core.models import (
    QualityAssessmentResult,
    QualityAssessmentType,
    QualityBaseline,
    QualityComparison,
    QualityMetrics,
    QualityTool,
    ExecutionStatus,
)
from adapters.quality_trend_analysis import QualityTrendAnalysisAdapter


class TestQualityTrendAnalysisAdapter:
    """Test suite for QualityTrendAnalysisAdapter."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def adapter(self, temp_storage):
        """Create QualityTrendAnalysisAdapter with temporary storage."""
        return QualityTrendAnalysisAdapter(storage_path=temp_storage)

    @pytest.fixture
    def sample_metrics(self):
        """Create sample quality metrics."""
        return QualityMetrics(
            overall_score=7.5,
            total_violations=10,
            critical_violations=1,
            high_violations=2,
            medium_violations=5,
            low_violations=2,
            test_coverage_percentage=85.0,
            average_complexity=6.2,
            max_complexity=12,
            maintainability_index=78.5,
            security_issues_count=0,
            dead_code_count=3,
            type_errors=1,
            total_lines=2500,
            code_lines=2000,
            comment_lines=400,
            blank_lines=100,
        )

    @pytest.fixture
    def sample_assessment_results(self, sample_metrics):
        """Create sample assessment results."""
        return [
            QualityAssessmentResult(
                assessment_type=QualityAssessmentType.LINT,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=1500.0,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=15,
                raw_output="ruff output",
                parsed_metrics=sample_metrics,
            )
        ]

    @pytest.fixture
    def sample_project_metadata(self):
        """Create sample project metadata."""
        return {
            "project_name": "test-project",
            "project_version": "1.0.0",
            "git_commit": "abc123def456",
            "git_branch": "main",
            "tool_versions": {
                "ruff": "0.1.0",
                "mypy": "1.5.0",
            },
            "python_version": "3.11.0",
            "pixi_environment": {
                "platform": "linux-64",
                "channels": ["conda-forge"],
            },
            "tags": ["baseline", "release"],
        }

    def test_adapter_initialization(self, temp_storage):
        """Test adapter initialization and directory creation."""
        adapter = QualityTrendAnalysisAdapter(storage_path=temp_storage)

        # Check storage path
        assert adapter.storage_path == Path(temp_storage)

        # Check subdirectories created
        assert (adapter.storage_path / "baselines").exists()
        assert (adapter.storage_path / "comparisons").exists()
        assert (adapter.storage_path / "metadata").exists()

    def test_adapter_default_initialization(self):
        """Test adapter initialization with default storage path."""
        adapter = QualityTrendAnalysisAdapter()

        assert adapter.storage_path == Path("./.claude/quality-baselines")

    def test_establish_baseline(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test baseline creation and storage."""
        baseline_id = "baseline-2024-01-01"

        baseline = adapter.establish_baseline(
            baseline_id=baseline_id,
            assessment_results=sample_assessment_results,
            project_metadata=sample_project_metadata,
            retention_days=180,
        )

        # Check baseline properties
        assert baseline.baseline_id == baseline_id
        assert baseline.project_name == "test-project"
        assert baseline.project_version == "1.0.0"
        assert baseline.git_commit == "abc123def456"
        assert baseline.retention_days == 180
        assert "baseline" in baseline.tags

        # Check metrics aggregation
        assert baseline.metrics.overall_score == 7.5
        assert baseline.metrics.total_violations == 10
        assert baseline.metrics.test_coverage_percentage == 85.0

        # Check file storage
        baseline_file = adapter.baselines_dir / f"{baseline_id}.json"
        assert baseline_file.exists()

        # Verify JSON content
        with open(baseline_file, "r") as f:
            stored_data = json.load(f)

        assert stored_data["baseline_id"] == baseline_id
        assert stored_data["project_name"] == "test-project"

    def test_establish_baseline_project_index_update(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test that establishing baseline updates project index."""
        baseline_id = "baseline-2024-01-01"

        adapter.establish_baseline(
            baseline_id=baseline_id,
            assessment_results=sample_assessment_results,
            project_metadata=sample_project_metadata,
        )

        # Check project index
        index_file = adapter.metadata_dir / "project_index.json"
        assert index_file.exists()

        with open(index_file, "r") as f:
            index = json.load(f)

        assert "test-project" in index
        assert baseline_id in index["test-project"]

    def test_compare_against_baseline(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test comparison against baseline."""
        # Create baseline
        baseline_id = "baseline-2024-01-01"
        baseline = adapter.establish_baseline(
            baseline_id=baseline_id,
            assessment_results=sample_assessment_results,
            project_metadata=sample_project_metadata,
        )

        # Create improved current results
        improved_metrics = QualityMetrics(
            overall_score=8.5,  # Improved
            total_violations=5,  # Reduced
            critical_violations=0,  # Resolved
            high_violations=1,  # Reduced
            medium_violations=3,
            low_violations=1,
            test_coverage_percentage=90.0,  # Improved
            average_complexity=5.8,  # Slightly improved
            total_lines=2500,
            code_lines=2000,
            comment_lines=400,
            blank_lines=100,
        )

        current_results = [
            QualityAssessmentResult(
                assessment_type=QualityAssessmentType.COMPREHENSIVE,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=1200.0,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=15,
                raw_output="improved ruff output",
                parsed_metrics=improved_metrics,
            )
        ]

        comparison = adapter.compare_against_baseline(baseline_id, current_results)

        # Check comparison properties
        assert comparison.baseline_id == baseline_id
        assert comparison.overall_score_delta == 1.0  # 8.5 - 7.5
        assert comparison.violation_count_delta == -5  # 5 - 10
        assert comparison.critical_violation_delta == -1  # 0 - 1
        assert comparison.coverage_delta == 5.0  # 90.0 - 85.0
        assert comparison.trend_direction == "improving"
        assert comparison.regression_detected is False

        # Should have positive recommendations
        assert len(comparison.trend_recommendations) > 0
        assert len(comparison.regression_alerts) == 0

    def test_compare_against_baseline_regression(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test comparison detecting regression."""
        # Create baseline
        baseline_id = "baseline-2024-01-01"
        adapter.establish_baseline(
            baseline_id=baseline_id,
            assessment_results=sample_assessment_results,
            project_metadata=sample_project_metadata,
        )

        # Create degraded current results
        degraded_metrics = QualityMetrics(
            overall_score=5.0,  # Degraded
            total_violations=25,  # Increased
            critical_violations=5,  # New critical issues
            high_violations=8,
            medium_violations=10,
            low_violations=2,
            test_coverage_percentage=65.0,  # Decreased
            average_complexity=9.2,  # Increased complexity
            security_issues_count=2,  # New security issues
            total_lines=2500,
            code_lines=2000,
            comment_lines=400,
            blank_lines=100,
        )

        current_results = [
            QualityAssessmentResult(
                assessment_type=QualityAssessmentType.COMPREHENSIVE,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=2000.0,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=15,
                raw_output="degraded output",
                parsed_metrics=degraded_metrics,
            )
        ]

        comparison = adapter.compare_against_baseline(baseline_id, current_results)

        # Check regression detection
        assert comparison.overall_score_delta == -2.5
        assert comparison.violation_count_delta == 15
        assert comparison.critical_violation_delta == 4
        assert comparison.security_issue_delta == 2
        assert comparison.trend_direction == "degrading"
        assert comparison.regression_detected is True

        # Should have regression alerts
        assert len(comparison.regression_alerts) > 0

    def test_compare_against_nonexistent_baseline(
        self, adapter, sample_assessment_results
    ):
        """Test comparison against non-existent baseline raises error."""
        with pytest.raises(ValueError, match="Baseline nonexistent not found"):
            adapter.compare_against_baseline("nonexistent", sample_assessment_results)

    def test_analyze_quality_trends_empty_baselines(self, adapter):
        """Test trend analysis with empty baseline list."""
        result = adapter.analyze_quality_trends([])
        assert "error" in result

    def test_analyze_quality_trends_no_baselines_in_window(self, adapter):
        """Test trend analysis with no baselines in time window."""
        # Create baseline that's too old
        old_baseline_id = "old-baseline"
        old_time = datetime.now(UTC) - timedelta(days=60)

        # Manually create old baseline file
        baseline_data = {
            "baseline_id": old_baseline_id,
            "created_at": old_time.isoformat(),
            "project_name": "test-project",
            "metrics": {
                "overall_score": 7.0,
                "total_violations": 10,
                "critical_violations": 0,
                "high_violations": 2,
                "medium_violations": 5,
                "low_violations": 3,
                "total_lines": 1000,
                "code_lines": 800,
                "comment_lines": 150,
                "blank_lines": 50,
            },
        }

        baseline_file = adapter.baselines_dir / f"{old_baseline_id}.json"
        with open(baseline_file, "w") as f:
            json.dump(baseline_data, f)

        # Analyze with 30-day window (baseline is 60 days old)
        result = adapter.analyze_quality_trends([old_baseline_id], time_window_days=30)
        assert "error" in result
        assert "No baselines found within 30 days" in result["error"]

    def test_analyze_quality_trends_multiple_baselines(
        self, adapter, sample_project_metadata
    ):
        """Test trend analysis with multiple baselines."""
        # Create multiple baselines with different metrics
        baselines_data = [
            ("baseline-1", 6.0, 20, 2, datetime.now(UTC) - timedelta(days=20)),
            ("baseline-2", 7.0, 15, 1, datetime.now(UTC) - timedelta(days=15)),
            ("baseline-3", 8.0, 10, 0, datetime.now(UTC) - timedelta(days=10)),
            ("baseline-4", 8.5, 8, 0, datetime.now(UTC) - timedelta(days=5)),
        ]

        for baseline_id, score, violations, critical, created_at in baselines_data:
            metrics = QualityMetrics(
                overall_score=score,
                total_violations=violations,
                critical_violations=critical,
                high_violations=2,
                medium_violations=5,
                low_violations=3,
                test_coverage_percentage=75.0 + score,  # Correlate with score
                average_complexity=12.0 - score,  # Inverse correlation
                security_issues_count=0,
                total_lines=1000,
                code_lines=800,
                comment_lines=150,
                blank_lines=50,
            )

            assessment_result = QualityAssessmentResult(
                assessment_type=QualityAssessmentType.COMPREHENSIVE,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=created_at.isoformat(),
                end_time=created_at.isoformat(),
                execution_time_ms=1000.0,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=10,
                raw_output="test output",
                parsed_metrics=metrics,
            )

            adapter.establish_baseline(
                baseline_id=baseline_id,
                assessment_results=[assessment_result],
                project_metadata=sample_project_metadata,
            )

        # Analyze trends
        baseline_ids = ["baseline-1", "baseline-2", "baseline-3", "baseline-4"]
        result = adapter.analyze_quality_trends(baseline_ids, time_window_days=30)

        # Check analysis structure
        assert "baselines_analyzed" in result
        assert "quality_trends" in result
        assert "pattern_analysis" in result
        assert "recommendations" in result

        assert result["baselines_analyzed"] == 4

        # Check trend statistics
        trends = result["quality_trends"]
        assert "overall_scores" in trends
        assert "violation_counts" in trends

        # Scores should show improvement trend
        score_stats = trends["overall_scores"]
        assert score_stats["trend_direction"] == "increasing"
        assert score_stats["current_value"] == 8.5

    def test_detect_quality_regression_no_regression(self, adapter):
        """Test regression detection with no regression."""
        comparison = QualityComparison(
            baseline_id="test-baseline",
            current_assessment_id="test-assessment",
            comparison_timestamp=datetime.now(UTC).isoformat(),
            overall_score_delta=1.0,  # Improvement
            violation_count_delta=-5,  # Fewer violations
            critical_violation_delta=0,  # No new critical
            security_issue_delta=0,  # No new security issues
            trend_direction="improving",
            regression_detected=False,
            significant_changes=["Quality improved"],
            trend_recommendations=["Keep up good work"],
            regression_alerts=[],
        )

        regression_analysis = adapter.detect_quality_regression(
            comparison, threshold_percent=5.0
        )

        assert regression_analysis["regression_detected"] is False
        assert regression_analysis["severity"] == "none"
        assert len(regression_analysis["affected_areas"]) == 0
        assert len(regression_analysis["alerts"]) == 0

    def test_detect_quality_regression_critical_violations(self, adapter):
        """Test regression detection with new critical violations."""
        comparison = QualityComparison(
            baseline_id="test-baseline",
            current_assessment_id="test-assessment",
            comparison_timestamp=datetime.now(UTC).isoformat(),
            overall_score_delta=-0.5,
            violation_count_delta=3,
            critical_violation_delta=2,  # New critical violations
            security_issue_delta=0,
            trend_direction="degrading",
            regression_detected=True,
            significant_changes=["2 new critical violations"],
            trend_recommendations=["Fix critical issues"],
            regression_alerts=["Critical regression detected"],
        )

        regression_analysis = adapter.detect_quality_regression(comparison)

        assert regression_analysis["regression_detected"] is True
        assert regression_analysis["severity"] == "critical"
        assert "critical_violations" in regression_analysis["affected_areas"]
        assert regression_analysis["critical_metrics"]["new_critical_violations"] == 2
        assert len(regression_analysis["alerts"]) > 0
        assert "critical violations" in regression_analysis["alerts"][0].lower()

    def test_detect_quality_regression_security_issues(self, adapter):
        """Test regression detection with new security issues."""
        comparison = QualityComparison(
            baseline_id="test-baseline",
            current_assessment_id="test-assessment",
            comparison_timestamp=datetime.now(UTC).isoformat(),
            overall_score_delta=0.0,
            violation_count_delta=0,
            critical_violation_delta=0,
            security_issue_delta=3,  # New security issues
            trend_direction="degrading",
            regression_detected=True,
            significant_changes=["3 new security issues"],
            trend_recommendations=["Address security concerns"],
            regression_alerts=["Security regression detected"],
        )

        regression_analysis = adapter.detect_quality_regression(comparison)

        assert regression_analysis["regression_detected"] is True
        assert regression_analysis["severity"] == "critical"
        assert "security" in regression_analysis["affected_areas"]
        assert regression_analysis["critical_metrics"]["new_security_issues"] == 3

    def test_detect_quality_regression_coverage_decrease(self, adapter):
        """Test regression detection with coverage decrease."""
        comparison = QualityComparison(
            baseline_id="test-baseline",
            current_assessment_id="test-assessment",
            comparison_timestamp=datetime.now(UTC).isoformat(),
            overall_score_delta=0.0,
            violation_count_delta=0,
            critical_violation_delta=0,
            security_issue_delta=0,
            coverage_delta=-8.0,  # 8% coverage decrease
            trend_direction="stable",
            regression_detected=False,
            significant_changes=["Coverage decreased"],
            trend_recommendations=["Add more tests"],
            regression_alerts=[],
        )

        regression_analysis = adapter.detect_quality_regression(
            comparison, threshold_percent=5.0
        )

        assert "test_coverage" in regression_analysis["affected_areas"]
        assert regression_analysis["critical_metrics"]["coverage_decrease"] == 8.0

    def test_get_baseline_history_empty_project(self, adapter):
        """Test getting baseline history for non-existent project."""
        history = adapter.get_baseline_history("nonexistent-project")
        assert len(history) == 0

    def test_get_baseline_history_with_baselines(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test getting baseline history with existing baselines."""
        # Create multiple baselines for same project
        baseline_ids = ["baseline-1", "baseline-2", "baseline-3"]

        # Just create baselines normally - the timing doesn't matter for this test
        for baseline_id in baseline_ids:
            adapter.establish_baseline(
                baseline_id=baseline_id,
                assessment_results=sample_assessment_results,
                project_metadata=sample_project_metadata,
            )

        # Get history
        history = adapter.get_baseline_history("test-project", limit=10)

        # Should return all baselines
        assert len(history) == 3

        # Should contain all created baselines
        returned_ids = [b.baseline_id for b in history]
        assert set(returned_ids) == set(baseline_ids)

    def test_get_baseline_history_limit(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test baseline history respects limit parameter."""
        # Create 5 baselines
        for i in range(5):
            baseline_id = f"baseline-{i}"
            adapter.establish_baseline(
                baseline_id=baseline_id,
                assessment_results=sample_assessment_results,
                project_metadata=sample_project_metadata,
            )

        # Get limited history
        history = adapter.get_baseline_history("test-project", limit=3)
        assert len(history) == 3

    def test_aggregate_metrics_empty_results(self, adapter):
        """Test metric aggregation with empty results."""
        metrics = adapter._aggregate_metrics([])

        assert metrics.overall_score == 0.0
        assert metrics.total_violations == 0
        assert metrics.total_lines == 0

    def test_aggregate_metrics_multiple_results(self, adapter):
        """Test metric aggregation with multiple results."""
        # Create two different metric sets
        metrics1 = QualityMetrics(
            overall_score=8.0,
            total_violations=5,
            critical_violations=1,
            high_violations=1,
            medium_violations=2,
            low_violations=1,
            test_coverage_percentage=80.0,
            average_complexity=5.0,
            total_lines=1000,
            code_lines=800,
            comment_lines=150,
            blank_lines=50,
        )

        metrics2 = QualityMetrics(
            overall_score=7.0,
            total_violations=10,
            critical_violations=2,
            high_violations=3,
            medium_violations=4,
            low_violations=1,
            test_coverage_percentage=70.0,
            average_complexity=7.0,
            total_lines=1500,
            code_lines=1200,
            comment_lines=200,
            blank_lines=100,
        )

        results = [
            QualityAssessmentResult(
                assessment_type=QualityAssessmentType.LINT,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=1000.0,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=10,
                raw_output="output1",
                parsed_metrics=metrics1,
            ),
            QualityAssessmentResult(
                assessment_type=QualityAssessmentType.TYPECHECK,
                tool=QualityTool.MYPY,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=2000.0,
                pixi_task_used="mypy",
                target_path="src/",
                files_analyzed=15,
                raw_output="output2",
                parsed_metrics=metrics2,
            ),
        ]

        aggregated = adapter._aggregate_metrics(results)

        # Check aggregation
        assert aggregated.total_violations == 15  # 5 + 10
        assert aggregated.critical_violations == 3  # 1 + 2
        assert aggregated.total_lines == 2500  # 1000 + 1500
        assert aggregated.code_lines == 2000  # 800 + 1200

        # Check averages
        assert aggregated.test_coverage_percentage == 75.0  # (80 + 70) / 2
        assert aggregated.average_complexity == 6.0  # (5 + 7) / 2

    def test_cleanup_expired_baselines(
        self, adapter, sample_assessment_results, sample_project_metadata
    ):
        """Test cleanup of expired baselines."""
        # Create baseline with short retention
        baseline_id = "short-lived-baseline"

        # Create expired baseline by manipulating the file directly
        expired_time = datetime.now(UTC) - timedelta(days=1)
        baseline_data = {
            "baseline_id": baseline_id,
            "created_at": expired_time.isoformat(),
            "expires_at": expired_time.isoformat(),  # Already expired
            "project_name": "test-project",
            "metrics": {
                "overall_score": 7.0,
                "total_violations": 5,
                "critical_violations": 0,
                "high_violations": 1,
                "medium_violations": 3,
                "low_violations": 1,
                "total_lines": 1000,
                "code_lines": 800,
                "comment_lines": 150,
                "blank_lines": 50,
            },
        }

        # Write expired baseline file
        baseline_file = adapter.baselines_dir / f"{baseline_id}.json"
        with open(baseline_file, "w") as f:
            json.dump(baseline_data, f, indent=2, default=str)

        # Add to project index
        index_file = adapter.metadata_dir / "project_index.json"
        index_data = {"test-project": [baseline_id]}
        with open(index_file, "w") as f:
            json.dump(index_data, f)

        # Verify file exists before cleanup
        assert baseline_file.exists()

        # Run cleanup
        adapter._cleanup_expired_baselines()

        # File should be removed
        assert not baseline_file.exists()

        # Should be removed from index
        with open(index_file, "r") as f:
            updated_index = json.load(f)

        assert baseline_id not in updated_index.get("test-project", [])

    def test_trend_direction_determination(self, adapter):
        """Test trend direction determination logic."""
        # Improving trend - positive score delta
        trend = adapter._determine_trend_direction(1.5, -5, 0)
        assert trend == "improving"

        # Degrading trend - negative score delta
        trend = adapter._determine_trend_direction(-1.0, 10, 0)
        assert trend == "degrading"

        # Stable trend - small changes
        trend = adapter._determine_trend_direction(0.2, 2, 0)
        assert trend == "stable"

        # Critical violations override - degrading
        trend = adapter._determine_trend_direction(0.5, -5, 2)
        assert trend == "degrading"

        # Critical violations resolved - improving
        trend = adapter._determine_trend_direction(-0.2, 3, -1)
        assert trend == "improving"

    def test_calculate_baseline_score(self, adapter):
        """Test baseline quality score calculation."""
        # Perfect scenario - no violations, good coverage
        score = adapter._calculate_baseline_score(0, 0, 0, 95.0, 3.0, 0, 1000)
        assert score > 9.0

        # Poor scenario - many violations, low coverage, high complexity
        score = adapter._calculate_baseline_score(100, 10, 20, 30.0, 15.0, 5, 1000)
        assert score < 3.0

        # Edge case - no code
        score = adapter._calculate_baseline_score(5, 1, 2, None, None, 0, 0)
        assert score == 0.0

    def test_volatility_calculation(self, adapter):
        """Test volatility calculation for trend analysis."""
        # Stable values should have low volatility
        stable_values = [5.0, 5.1, 4.9, 5.2, 4.8]
        volatility = adapter._calculate_volatility(stable_values)
        assert volatility < 0.1

        # Volatile values should have high volatility
        volatile_values = [5.0, 8.0, 2.0, 9.0, 1.0]
        volatility = adapter._calculate_volatility(volatile_values)
        assert volatility > 0.5

        # Single value should have zero volatility
        single_value = [5.0]
        volatility = adapter._calculate_volatility(single_value)
        assert volatility == 0.0

    def test_simple_trend_calculation(self, adapter):
        """Test simple trend direction calculation."""
        # Increasing trend
        increasing_values = [5.0, 6.0, 7.0, 8.0]
        trend = adapter._calculate_simple_trend(increasing_values)
        assert trend == "increasing"

        # Decreasing trend
        decreasing_values = [8.0, 7.0, 6.0, 5.0]
        trend = adapter._calculate_simple_trend(decreasing_values)
        assert trend == "decreasing"

        # Stable trend
        stable_values = [5.0, 5.1, 4.9, 5.0]
        trend = adapter._calculate_simple_trend(stable_values)
        assert trend == "stable"

        # Single value should be stable
        single_value = [5.0]
        trend = adapter._calculate_simple_trend(single_value)
        assert trend == "stable"
