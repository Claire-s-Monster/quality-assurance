"""
Quality trend analysis adapter for baseline management and quality tracking.

This adapter implements QualityTrendAnalysisPort to provide trend analysis
capabilities including baseline creation, comparison, regression detection,
and historical analysis with JSON persistence.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models import (
    QualityAssessmentResult,
    QualityBaseline,
    QualityComparison,
    QualityMetrics,
)
from core.ports import QualityTrendAnalysisPort


class QualityTrendAnalysisAdapter(QualityTrendAnalysisPort):
    """
    Adapter for quality trend analysis and baseline management.

    Provides baseline storage, retrieval, comparison capabilities with
    JSON file persistence and comprehensive trend analysis features.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the trend analysis adapter.

        Args:
            storage_path: Path for baseline storage (defaults to ./.claude/quality-baselines/)
        """
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path("./.claude/quality-baselines")

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Storage subdirectories
        self.baselines_dir = self.storage_path / "baselines"
        self.comparisons_dir = self.storage_path / "comparisons"
        self.metadata_dir = self.storage_path / "metadata"

        for directory in [self.baselines_dir, self.comparisons_dir, self.metadata_dir]:
            directory.mkdir(exist_ok=True)

    def establish_baseline(
        self,
        baseline_id: str,
        assessment_results: List[QualityAssessmentResult],
        project_metadata: Dict[str, Any],
        retention_days: int = 365,
    ) -> QualityBaseline:
        """Create quality baseline for trend analysis."""

        current_time = datetime.now(UTC)
        expiration_time = current_time + timedelta(days=retention_days)

        # Aggregate metrics from assessment results
        aggregated_metrics = self._aggregate_metrics(assessment_results)

        # Extract tool versions (if available in metadata)
        tool_versions = project_metadata.get("tool_versions", {})
        python_version = project_metadata.get("python_version", "unknown")
        pixi_environment = project_metadata.get("pixi_environment", {})

        # Create baseline object
        baseline = QualityBaseline(
            baseline_id=baseline_id,
            created_at=current_time.isoformat(),
            project_name=project_metadata.get("project_name", "unknown"),
            project_version=project_metadata.get("project_version"),
            git_commit=project_metadata.get("git_commit"),
            git_branch=project_metadata.get("git_branch"),
            metrics=aggregated_metrics,
            tool_versions=tool_versions,
            python_version=python_version,
            pixi_environment=pixi_environment,
            retention_days=retention_days,
            expires_at=expiration_time.isoformat(),
            tags=project_metadata.get("tags", []),
        )

        # Store baseline to filesystem
        baseline_file = self.baselines_dir / f"{baseline_id}.json"
        with open(baseline_file, "w") as f:
            json.dump(baseline.model_dump(), f, indent=2, default=str)

        # Update project index
        self._update_project_index(baseline)

        # Schedule cleanup of expired baselines
        self._cleanup_expired_baselines()

        return baseline

    def compare_against_baseline(
        self, baseline_id: str, current_results: List[QualityAssessmentResult]
    ) -> QualityComparison:
        """Compare current quality against historical baseline."""

        # Load baseline
        baseline = self._load_baseline(baseline_id)
        if not baseline:
            raise ValueError(f"Baseline {baseline_id} not found")

        # Aggregate current metrics
        current_metrics = self._aggregate_metrics(current_results)

        # Calculate deltas
        overall_score_delta = (
            current_metrics.overall_score - baseline.metrics.overall_score
        )
        violation_count_delta = (
            current_metrics.total_violations - baseline.metrics.total_violations
        )
        critical_violation_delta = (
            current_metrics.critical_violations - baseline.metrics.critical_violations
        )
        security_issue_delta = (
            current_metrics.security_issues_count
            - baseline.metrics.security_issues_count
        )

        # Coverage delta (handle None values)
        coverage_delta = None
        if (
            current_metrics.test_coverage_percentage is not None
            and baseline.metrics.test_coverage_percentage is not None
        ):
            coverage_delta = (
                current_metrics.test_coverage_percentage
                - baseline.metrics.test_coverage_percentage
            )

        # Complexity delta (handle None values)
        complexity_delta = None
        if (
            current_metrics.average_complexity is not None
            and baseline.metrics.average_complexity is not None
        ):
            complexity_delta = (
                current_metrics.average_complexity - baseline.metrics.average_complexity
            )

        # Determine trend direction
        trend_direction = self._determine_trend_direction(
            overall_score_delta, violation_count_delta, critical_violation_delta
        )

        # Detect significant changes
        significant_changes = self._detect_significant_changes(
            baseline.metrics, current_metrics
        )

        # Generate trend-based recommendations
        trend_recommendations = self._generate_trend_recommendations(
            baseline.metrics, current_metrics, trend_direction
        )

        # Create comparison object
        comparison = QualityComparison(
            baseline_id=baseline_id,
            current_assessment_id=current_results[0].assessment_id
            if current_results
            else "unknown",
            comparison_timestamp=datetime.now(UTC).isoformat(),
            overall_score_delta=overall_score_delta,
            violation_count_delta=violation_count_delta,
            critical_violation_delta=critical_violation_delta,
            security_issue_delta=security_issue_delta,
            complexity_delta=complexity_delta,
            coverage_delta=coverage_delta,
            trend_direction=trend_direction,
            regression_detected=self._is_regression(
                overall_score_delta, critical_violation_delta
            ),
            significant_changes=significant_changes,
            trend_recommendations=trend_recommendations,
            regression_alerts=self._generate_regression_alerts(
                baseline.metrics, current_metrics
            ),
        )

        # Store comparison
        comparison_file = self.comparisons_dir / f"{comparison.comparison_id}.json"
        with open(comparison_file, "w") as f:
            json.dump(comparison.model_dump(), f, indent=2, default=str)

        return comparison

    def analyze_quality_trends(
        self, baseline_ids: List[str], time_window_days: int = 30
    ) -> Dict[str, Any]:
        """Analyze quality trends across multiple baselines."""

        if not baseline_ids:
            return {"error": "No baseline IDs provided"}

        # Load baselines within time window
        cutoff_time = datetime.now(UTC) - timedelta(days=time_window_days)
        baselines = []

        for baseline_id in baseline_ids:
            baseline = self._load_baseline(baseline_id)
            if baseline:
                baseline_time = datetime.fromisoformat(
                    baseline.created_at.replace("Z", "+00:00")
                )
                if baseline_time >= cutoff_time:
                    baselines.append(baseline)

        if not baselines:
            return {"error": f"No baselines found within {time_window_days} days"}

        # Sort by creation time
        baselines.sort(key=lambda x: x.created_at)

        # Extract trend data
        trend_data = {
            "overall_scores": [],
            "violation_counts": [],
            "critical_violations": [],
            "coverage_percentages": [],
            "complexity_scores": [],
            "security_issues": [],
            "timestamps": [],
        }

        for baseline in baselines:
            trend_data["overall_scores"].append(baseline.metrics.overall_score)
            trend_data["violation_counts"].append(baseline.metrics.total_violations)
            trend_data["critical_violations"].append(
                baseline.metrics.critical_violations
            )
            trend_data["security_issues"].append(baseline.metrics.security_issues_count)
            trend_data["timestamps"].append(baseline.created_at)

            if baseline.metrics.test_coverage_percentage is not None:
                trend_data["coverage_percentages"].append(
                    baseline.metrics.test_coverage_percentage
                )

            if baseline.metrics.average_complexity is not None:
                trend_data["complexity_scores"].append(
                    baseline.metrics.average_complexity
                )

        # Calculate trend statistics
        analysis = {
            "time_window_days": time_window_days,
            "baselines_analyzed": len(baselines),
            "trend_period": {
                "start": baselines[0].created_at,
                "end": baselines[-1].created_at,
            },
            "quality_trends": self._calculate_trend_statistics(trend_data),
            "pattern_analysis": self._analyze_quality_patterns_over_time(baselines),
            "recommendations": self._generate_trend_period_recommendations(trend_data),
            "volatility_analysis": self._calculate_quality_volatility(trend_data),
        }

        return analysis

    def detect_quality_regression(
        self, comparison: QualityComparison, threshold_percent: float = 5.0
    ) -> Dict[str, Any]:
        """Detect quality regressions and generate alerts."""

        regression_analysis = {
            "regression_detected": comparison.regression_detected,
            "threshold_percent": threshold_percent,
            "severity": "none",
            "affected_areas": [],
            "critical_metrics": {},
            "alerts": [],
            "recommended_actions": [],
        }

        # Check overall score regression
        if comparison.overall_score_delta < 0:
            score_regression_percent = abs(comparison.overall_score_delta) / 10.0 * 100
            if score_regression_percent > threshold_percent:
                regression_analysis["severity"] = (
                    "high" if score_regression_percent > 10 else "medium"
                )
                regression_analysis["affected_areas"].append("overall_quality")
                regression_analysis["critical_metrics"]["overall_score_regression"] = (
                    score_regression_percent
                )
                regression_analysis["alerts"].append(
                    f"Overall quality score decreased by {score_regression_percent:.1f}% "
                    f"(threshold: {threshold_percent}%)"
                )

        # Check critical violations increase
        if comparison.critical_violation_delta > 0:
            regression_analysis["severity"] = "critical"
            regression_analysis["affected_areas"].append("critical_violations")
            regression_analysis["critical_metrics"]["new_critical_violations"] = (
                comparison.critical_violation_delta
            )
            regression_analysis["alerts"].append(
                f"{comparison.critical_violation_delta} new critical violations detected"
            )

        # Check security issues increase
        if comparison.security_issue_delta > 0:
            regression_analysis["severity"] = "critical"
            regression_analysis["affected_areas"].append("security")
            regression_analysis["critical_metrics"]["new_security_issues"] = (
                comparison.security_issue_delta
            )
            regression_analysis["alerts"].append(
                f"{comparison.security_issue_delta} new security issues detected"
            )

        # Check coverage decrease
        if (
            comparison.coverage_delta is not None
            and comparison.coverage_delta < -threshold_percent
        ):
            regression_analysis["affected_areas"].append("test_coverage")
            regression_analysis["critical_metrics"]["coverage_decrease"] = abs(
                comparison.coverage_delta
            )
            regression_analysis["alerts"].append(
                f"Test coverage decreased by {abs(comparison.coverage_delta):.1f}%"
            )

        # Check complexity increase
        if (
            comparison.complexity_delta is not None
            and comparison.complexity_delta > 2.0
        ):
            regression_analysis["affected_areas"].append("complexity")
            regression_analysis["critical_metrics"]["complexity_increase"] = (
                comparison.complexity_delta
            )
            regression_analysis["alerts"].append(
                f"Average complexity increased by {comparison.complexity_delta:.1f}"
            )

        # Generate recommended actions
        if regression_analysis["affected_areas"]:
            regression_analysis["recommended_actions"] = (
                self._generate_regression_actions(
                    regression_analysis["affected_areas"], comparison
                )
            )

        return regression_analysis

    def get_baseline_history(
        self, project_name: str, limit: int = 50
    ) -> List[QualityBaseline]:
        """Get baseline history for a project."""

        # Load project index
        project_index = self._load_project_index()
        project_baselines = project_index.get(project_name, [])

        # Load and sort baselines
        baselines = []
        for baseline_id in project_baselines[
            : limit * 2
        ]:  # Load more than needed for filtering
            baseline = self._load_baseline(baseline_id)
            if baseline and not self._is_baseline_expired(baseline):
                baselines.append(baseline)

        # Sort by creation time (newest first) and limit
        baselines.sort(key=lambda x: x.created_at, reverse=True)
        return baselines[:limit]

    # Private helper methods

    def _aggregate_metrics(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> QualityMetrics:
        """Aggregate quality metrics from multiple assessment results."""

        if not assessment_results:
            return QualityMetrics(
                overall_score=0.0,
                total_violations=0,
                critical_violations=0,
                high_violations=0,
                medium_violations=0,
                low_violations=0,
                total_lines=0,
                code_lines=0,
                comment_lines=0,
                blank_lines=0,
            )

        # Aggregate metrics
        total_violations = 0
        critical_violations = 0
        high_violations = 0
        medium_violations = 0
        low_violations = 0
        security_issues = 0
        dead_code_count = 0
        type_errors = 0
        total_lines = 0
        code_lines = 0
        comment_lines = 0
        blank_lines = 0

        # Coverage and complexity need averaging
        coverage_values = []
        complexity_values = []
        maintainability_values = []

        for result in assessment_results:
            metrics = result.parsed_metrics
            total_violations += metrics.total_violations
            critical_violations += metrics.critical_violations
            high_violations += metrics.high_violations
            medium_violations += metrics.medium_violations
            low_violations += metrics.low_violations
            security_issues += metrics.security_issues_count
            dead_code_count += metrics.dead_code_count
            type_errors += metrics.type_errors
            total_lines += metrics.total_lines
            code_lines += metrics.code_lines
            comment_lines += metrics.comment_lines
            blank_lines += metrics.blank_lines

            if metrics.test_coverage_percentage is not None:
                coverage_values.append(metrics.test_coverage_percentage)

            if metrics.average_complexity is not None:
                complexity_values.append(metrics.average_complexity)

            if metrics.maintainability_index is not None:
                maintainability_values.append(metrics.maintainability_index)

        # Calculate averages
        avg_coverage = (
            sum(coverage_values) / len(coverage_values) if coverage_values else None
        )
        avg_complexity = (
            sum(complexity_values) / len(complexity_values)
            if complexity_values
            else None
        )
        max_complexity = int(max(complexity_values)) if complexity_values else None
        avg_maintainability = (
            sum(maintainability_values) / len(maintainability_values)
            if maintainability_values
            else None
        )

        # Use the original overall score if available, otherwise calculate
        if (
            assessment_results
            and assessment_results[0].parsed_metrics.overall_score > 0
        ):
            overall_score = assessment_results[0].parsed_metrics.overall_score
        else:
            # Calculate overall score using quality analysis logic
            # Simplified scoring for baseline storage
            overall_score = self._calculate_baseline_score(
                total_violations,
                critical_violations,
                high_violations,
                avg_coverage,
                avg_complexity,
                security_issues,
                total_lines,
            )

        return QualityMetrics(
            overall_score=overall_score,
            total_violations=total_violations,
            critical_violations=critical_violations,
            high_violations=high_violations,
            medium_violations=medium_violations,
            low_violations=low_violations,
            test_coverage_percentage=avg_coverage,
            average_complexity=avg_complexity,
            max_complexity=max_complexity,
            maintainability_index=avg_maintainability,
            security_issues_count=security_issues,
            high_security_issues=security_issues,  # Simplified assumption
            dead_code_count=dead_code_count,
            type_errors=type_errors,
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines,
        )

    def _calculate_baseline_score(
        self,
        total_violations: int,
        critical_violations: int,
        high_violations: int,
        coverage: Optional[float],
        complexity: Optional[float],
        security_issues: int,
        total_lines: int,
    ) -> float:
        """Calculate simplified baseline quality score."""

        if total_lines == 0:
            return 0.0

        # Base score starts at 10
        score = 10.0

        # Deduct for violations (per 100 lines)
        violations_per_100 = (total_violations / total_lines) * 100
        score -= violations_per_100 * 0.1

        # Heavy penalty for critical violations
        critical_per_100 = (critical_violations / total_lines) * 100
        score -= critical_per_100 * 2.0

        # Penalty for high violations
        high_per_100 = (high_violations / total_lines) * 100
        score -= high_per_100 * 1.0

        # Security penalty
        security_per_100 = (security_issues / total_lines) * 100
        score -= security_per_100 * 1.5

        # Coverage bonus/penalty
        if coverage is not None:
            if coverage < 80:
                score -= (80 - coverage) * 0.02
            else:
                score += (coverage - 80) * 0.01

        # Complexity penalty
        if complexity is not None and complexity > 10:
            score -= (complexity - 10) * 0.2

        return max(0.0, min(10.0, score))

    def _load_baseline(self, baseline_id: str) -> Optional[QualityBaseline]:
        """Load baseline from filesystem."""
        baseline_file = self.baselines_dir / f"{baseline_id}.json"

        if not baseline_file.exists():
            return None

        try:
            with open(baseline_file, "r") as f:
                data = json.load(f)
            return QualityBaseline.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            # Log error and return None
            print(f"Error loading baseline {baseline_id}: {e}")
            return None

    def _update_project_index(self, baseline: QualityBaseline) -> None:
        """Update project index with new baseline."""
        index_file = self.metadata_dir / "project_index.json"

        # Load existing index
        if index_file.exists():
            with open(index_file, "r") as f:
                index = json.load(f)
        else:
            index = {}

        # Add baseline to project
        project_name = baseline.project_name
        if project_name not in index:
            index[project_name] = []

        if baseline.baseline_id not in index[project_name]:
            index[project_name].append(baseline.baseline_id)

        # Sort by baseline ID (which should be chronological)
        index[project_name].sort()

        # Write updated index
        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)

    def _load_project_index(self) -> Dict[str, List[str]]:
        """Load project index."""
        index_file = self.metadata_dir / "project_index.json"

        if not index_file.exists():
            return {}

        try:
            with open(index_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _cleanup_expired_baselines(self) -> None:
        """Clean up expired baselines."""
        current_time = datetime.now(UTC)

        # Scan baseline directory
        for baseline_file in self.baselines_dir.glob("*.json"):
            try:
                with open(baseline_file, "r") as f:
                    data = json.load(f)

                expires_at = datetime.fromisoformat(
                    data["expires_at"].replace("Z", "+00:00")
                )

                if expires_at <= current_time:
                    # Remove expired baseline
                    baseline_file.unlink()

                    # Update project index
                    self._remove_from_project_index(data["baseline_id"])

            except (json.JSONDecodeError, KeyError, ValueError, OSError):
                # Skip problematic files
                continue

    def _remove_from_project_index(self, baseline_id: str) -> None:
        """Remove baseline ID from project index."""
        index_file = self.metadata_dir / "project_index.json"

        if not index_file.exists():
            return

        try:
            with open(index_file, "r") as f:
                index = json.load(f)

            # Remove from all projects
            for project_name, baseline_ids in index.items():
                if baseline_id in baseline_ids:
                    baseline_ids.remove(baseline_id)

            with open(index_file, "w") as f:
                json.dump(index, f, indent=2)

        except (json.JSONDecodeError, ValueError, OSError):
            pass

    def _is_baseline_expired(self, baseline: QualityBaseline) -> bool:
        """Check if baseline is expired."""
        current_time = datetime.now(UTC)
        expires_at = datetime.fromisoformat(baseline.expires_at.replace("Z", "+00:00"))
        return expires_at <= current_time

    def _determine_trend_direction(
        self,
        overall_score_delta: float,
        violation_count_delta: int,
        critical_violation_delta: int,
    ) -> str:
        """Determine overall trend direction."""

        # Critical violations take precedence
        if critical_violation_delta > 0:
            return "degrading"
        elif critical_violation_delta < 0:
            return "improving"

        # Overall score is primary indicator
        if overall_score_delta > 0.5:
            return "improving"
        elif overall_score_delta < -0.5:
            return "degrading"

        # Use violation count as tie-breaker
        if violation_count_delta < -5:
            return "improving"
        elif violation_count_delta > 5:
            return "degrading"

        return "stable"

    def _detect_significant_changes(
        self, baseline_metrics: QualityMetrics, current_metrics: QualityMetrics
    ) -> List[str]:
        """Detect significant changes between baseline and current metrics."""

        changes = []

        # Significant overall score change (>1 point)
        score_delta = current_metrics.overall_score - baseline_metrics.overall_score
        if abs(score_delta) > 1.0:
            direction = "increased" if score_delta > 0 else "decreased"
            changes.append(
                f"Overall quality score {direction} by {abs(score_delta):.1f} points"
            )

        # Critical violations change
        critical_delta = (
            current_metrics.critical_violations - baseline_metrics.critical_violations
        )
        if critical_delta > 0:
            changes.append(f"{critical_delta} new critical violations")
        elif critical_delta < 0:
            changes.append(f"{abs(critical_delta)} critical violations resolved")

        # Security issues change
        security_delta = (
            current_metrics.security_issues_count
            - baseline_metrics.security_issues_count
        )
        if security_delta > 0:
            changes.append(f"{security_delta} new security issues")
        elif security_delta < 0:
            changes.append(f"{abs(security_delta)} security issues resolved")

        # Coverage change (>5%)
        if (
            current_metrics.test_coverage_percentage is not None
            and baseline_metrics.test_coverage_percentage is not None
        ):
            coverage_delta = (
                current_metrics.test_coverage_percentage
                - baseline_metrics.test_coverage_percentage
            )
            if abs(coverage_delta) > 5.0:
                direction = "increased" if coverage_delta > 0 else "decreased"
                changes.append(
                    f"Test coverage {direction} by {abs(coverage_delta):.1f}%"
                )

        # Complexity change (>2 points)
        if (
            current_metrics.average_complexity is not None
            and baseline_metrics.average_complexity is not None
        ):
            complexity_delta = (
                current_metrics.average_complexity - baseline_metrics.average_complexity
            )
            if abs(complexity_delta) > 2.0:
                direction = "increased" if complexity_delta > 0 else "decreased"
                changes.append(
                    f"Average complexity {direction} by {abs(complexity_delta):.1f}"
                )

        return changes

    def _generate_trend_recommendations(
        self,
        baseline_metrics: QualityMetrics,
        current_metrics: QualityMetrics,
        trend_direction: str,
    ) -> List[str]:
        """Generate trend-based recommendations."""

        recommendations = []

        if trend_direction == "degrading":
            recommendations.append(
                "⚠️  Quality is degrading - implement immediate quality improvement measures"
            )

            # Specific degradation recommendations
            if (
                current_metrics.critical_violations
                > baseline_metrics.critical_violations
            ):
                recommendations.append(
                    "🚨 Address new critical violations before they compound"
                )

            if (
                current_metrics.test_coverage_percentage is not None
                and baseline_metrics.test_coverage_percentage is not None
                and current_metrics.test_coverage_percentage
                < baseline_metrics.test_coverage_percentage
            ):
                recommendations.append(
                    "📊 Test coverage has decreased - add tests for new code"
                )

        elif trend_direction == "improving":
            recommendations.append(
                "✅ Quality is improving - maintain current practices and standards"
            )

            # Encourage continued improvement
            if current_metrics.overall_score > 8.0:
                recommendations.append(
                    "🎯 Quality is high - consider advanced optimizations and best practices"
                )

        else:  # stable
            recommendations.append(
                "📊 Quality is stable - monitor for any emerging trends"
            )

            # Suggest proactive improvements
            if current_metrics.overall_score < 7.0:
                recommendations.append(
                    "💡 Consider proactive quality improvements to prevent future degradation"
                )

        return recommendations

    def _generate_regression_alerts(
        self, baseline_metrics: QualityMetrics, current_metrics: QualityMetrics
    ) -> List[str]:
        """Generate regression alerts."""

        alerts = []

        # Critical violation alerts
        critical_delta = (
            current_metrics.critical_violations - baseline_metrics.critical_violations
        )
        if critical_delta > 0:
            alerts.append(f"ALERT: {critical_delta} new critical violations detected")

        # Security alerts
        security_delta = (
            current_metrics.security_issues_count
            - baseline_metrics.security_issues_count
        )
        if security_delta > 0:
            alerts.append(
                f"SECURITY ALERT: {security_delta} new security issues detected"
            )

        # Significant quality drop
        score_delta = current_metrics.overall_score - baseline_metrics.overall_score
        if score_delta < -2.0:
            alerts.append(
                f"QUALITY ALERT: Overall score dropped by {abs(score_delta):.1f} points"
            )

        return alerts

    def _is_regression(
        self, overall_score_delta: float, critical_violation_delta: int
    ) -> bool:
        """Determine if metrics indicate a regression."""
        # Any new critical violations indicate regression
        if critical_violation_delta > 0:
            return True

        # Significant quality score drop indicates regression
        if overall_score_delta < -1.0:
            return True

        return False

    def _calculate_trend_statistics(
        self, trend_data: Dict[str, List]
    ) -> Dict[str, Any]:
        """Calculate statistical trends from trend data."""

        stats = {}

        for metric, values in trend_data.items():
            if not values or metric == "timestamps":
                continue

            # Basic statistics
            stats[metric] = {
                "current_value": values[-1] if values else 0,
                "min_value": min(values),
                "max_value": max(values),
                "average_value": sum(values) / len(values),
                "trend_direction": self._calculate_simple_trend(values),
                "volatility": self._calculate_volatility(values),
            }

            # Calculate change from first to last
            if len(values) > 1:
                change = values[-1] - values[0]
                change_percent = (change / values[0] * 100) if values[0] != 0 else 0
                stats[metric]["total_change"] = change
                stats[metric]["total_change_percent"] = change_percent

        return stats

    def _calculate_simple_trend(self, values: List[float]) -> str:
        """Calculate simple trend direction from list of values."""
        if len(values) < 2:
            return "stable"

        # Simple linear trend calculation
        first_half = values[: len(values) // 2]
        second_half = values[len(values) // 2 :]

        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)

        if second_avg > first_avg * 1.05:
            return "increasing"
        elif second_avg < first_avg * 0.95:
            return "decreasing"
        else:
            return "stable"

    def _calculate_volatility(self, values: List[float]) -> float:
        """Calculate volatility (coefficient of variation) for values."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0

        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance**0.5

        return std_dev / mean  # Coefficient of variation

    def _analyze_quality_patterns_over_time(
        self, baselines: List[QualityBaseline]
    ) -> Dict[str, Any]:
        """Analyze quality patterns across time."""

        if len(baselines) < 2:
            return {"insufficient_data": True}

        patterns = {
            "consistent_improvement": False,
            "consistent_degradation": False,
            "cyclical_pattern": False,
            "quality_milestones": [],
            "problematic_periods": [],
        }

        # Extract scores for pattern analysis
        scores = [b.metrics.overall_score for b in baselines]

        # Check for consistent improvement (3+ consecutive increases)
        improvements = 0
        degradations = 0

        for i in range(1, len(scores)):
            if scores[i] > scores[i - 1]:
                improvements += 1
                degradations = 0
            elif scores[i] < scores[i - 1]:
                degradations += 1
                improvements = 0

            if improvements >= 3:
                patterns["consistent_improvement"] = True
            if degradations >= 3:
                patterns["consistent_degradation"] = True

        # Identify quality milestones (scores > 9.0)
        for i, baseline in enumerate(baselines):
            if baseline.metrics.overall_score > 9.0:
                patterns["quality_milestones"].append(
                    {
                        "baseline_id": baseline.baseline_id,
                        "timestamp": baseline.created_at,
                        "score": baseline.metrics.overall_score,
                    }
                )

        # Identify problematic periods (scores < 6.0)
        for i, baseline in enumerate(baselines):
            if baseline.metrics.overall_score < 6.0:
                patterns["problematic_periods"].append(
                    {
                        "baseline_id": baseline.baseline_id,
                        "timestamp": baseline.created_at,
                        "score": baseline.metrics.overall_score,
                        "critical_violations": baseline.metrics.critical_violations,
                    }
                )

        return patterns

    def _generate_trend_period_recommendations(
        self, trend_data: Dict[str, List]
    ) -> List[str]:
        """Generate recommendations based on trend period analysis."""

        recommendations = []

        # Overall score trend
        scores = trend_data.get("overall_scores", [])
        if scores:
            current_score = scores[-1]
            trend = self._calculate_simple_trend(scores)

            if trend == "decreasing":
                recommendations.append(
                    "📉 Quality trend is decreasing - implement quality improvement initiatives"
                )
            elif trend == "increasing":
                recommendations.append(
                    "📈 Quality trend is positive - maintain current development practices"
                )

            if current_score < 7.0:
                recommendations.append(
                    "⚠️  Current quality below recommended threshold - focus on immediate improvements"
                )

        # Violation trend
        violations = trend_data.get("violation_counts", [])
        if violations:
            violation_trend = self._calculate_simple_trend(violations)
            if violation_trend == "increasing":
                recommendations.append(
                    "🔍 Violation count trending upward - review development practices and tooling"
                )

        # Coverage trend
        coverage = trend_data.get("coverage_percentages", [])
        if coverage:
            coverage_trend = self._calculate_simple_trend(coverage)
            current_coverage = coverage[-1]

            if coverage_trend == "decreasing":
                recommendations.append(
                    "📊 Test coverage trending downward - prioritize test development"
                )
            elif current_coverage < 80:
                recommendations.append(
                    f"📋 Test coverage at {current_coverage:.1f}% - aim for 80%+ coverage"
                )

        return recommendations

    def _calculate_quality_volatility(
        self, trend_data: Dict[str, List]
    ) -> Dict[str, float]:
        """Calculate volatility metrics for quality trends."""

        volatility = {}

        for metric, values in trend_data.items():
            if metric == "timestamps" or not values or len(values) < 2:
                continue

            volatility[metric] = self._calculate_volatility(values)

        return volatility

    def _generate_regression_actions(
        self, affected_areas: List[str], comparison: QualityComparison
    ) -> List[str]:
        """Generate recommended actions for quality regression."""

        actions = []

        if "critical_violations" in affected_areas:
            actions.append(
                "🚨 IMMEDIATE: Review and fix all critical violations before proceeding"
            )
            actions.append(
                "🔍 Analyze root cause of critical violations to prevent recurrence"
            )

        if "security" in affected_areas:
            actions.append(
                "🔐 URGENT: Conduct security review and address all security issues"
            )
            actions.append(
                "📋 Consider additional security scanning tools and practices"
            )

        if "test_coverage" in affected_areas:
            actions.append("📊 Add comprehensive tests for recently modified code")
            actions.append("🎯 Set up coverage tracking to prevent future regression")

        if "complexity" in affected_areas:
            actions.append("🔄 Refactor complex functions to improve maintainability")
            actions.append("📏 Consider implementing complexity limits in CI pipeline")

        if "overall_quality" in affected_areas:
            actions.append("⚖️  Implement stricter quality gates to prevent regression")
            actions.append("🔄 Review recent changes for quality impact")

        return actions

    # =============================================================================
    # Advanced Statistical Analysis Methods
    # =============================================================================

    def _calculate_moving_average(
        self, values: List[float], window: int
    ) -> List[float]:
        """Calculate moving average with specified window size."""
        if len(values) < window:
            return values.copy()

        moving_averages = []
        for i in range(len(values) - window + 1):
            window_avg = sum(values[i : i + window]) / window
            moving_averages.append(window_avg)

        # Pad with original values for first (window-1) entries
        return values[: window - 1] + moving_averages

    def _calculate_trend_strength(self, values: List[float]) -> float:
        """Calculate trend strength using linear regression slope."""
        if len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))

        # Calculate linear regression slope
        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return 0.0

        slope = numerator / denominator

        # Normalize slope to [-1, 1] range based on data range
        value_range = max(values) - min(values)
        if value_range == 0:
            return 0.0

        # Normalize by value range and time range
        normalized_strength = slope / (value_range / n)

        # Clamp to [-1, 1]
        return max(-1.0, min(1.0, normalized_strength))

    def _calculate_time_correlation(
        self, values: List[float], timestamps: List[datetime]
    ) -> float:
        """Calculate correlation between values and time progression."""
        if len(values) < 2:
            return 0.0

        # Convert timestamps to numeric (days since first timestamp)
        first_time = timestamps[0]
        time_values = [
            (ts - first_time).total_seconds() / (24 * 3600) for ts in timestamps
        ]

        # Calculate Pearson correlation coefficient
        n = len(values)
        mean_x = sum(time_values) / n
        mean_y = sum(values) / n

        numerator = sum(
            (time_values[i] - mean_x) * (values[i] - mean_y) for i in range(n)
        )

        sum_sq_x = sum((time_values[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((values[i] - mean_y) ** 2 for i in range(n))

        denominator = (sum_sq_x * sum_sq_y) ** 0.5

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _calculate_median(self, values: List[float]) -> float:
        """Calculate median value."""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        n = len(sorted_values)

        if n % 2 == 0:
            return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
        else:
            return sorted_values[n // 2]

    def _calculate_standard_deviation(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)

        return variance**0.5

    def _forecast_next_value(self, values: List[float]) -> float:
        """Simple forecast of next value using linear extrapolation."""
        if len(values) < 2:
            return values[0] if values else 0.0

        if len(values) == 2:
            # Simple linear extrapolation
            return 2 * values[-1] - values[-2]

        # Use last 3 points for better prediction
        recent_values = values[-3:]
        n = len(recent_values)
        x = list(range(n))

        # Linear regression on recent points
        x_mean = sum(x) / n
        y_mean = sum(recent_values) / n

        numerator = sum((x[i] - x_mean) * (recent_values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return recent_values[-1]

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Predict next value (x = n)
        forecast = slope * n + intercept

        # Apply reasonable bounds based on historical data
        min_val, max_val = min(values), max(values)
        value_range = max_val - min_val

        # Don't allow forecast to go beyond 1.5x historical range
        lower_bound = min_val - 0.5 * value_range
        upper_bound = max_val + 0.5 * value_range

        return max(lower_bound, min(upper_bound, forecast))

    def _detect_seasonal_patterns(
        self, values: List[float], timestamps: List[datetime]
    ) -> bool:
        """Detect seasonal patterns in quality data."""
        if len(values) < 4:
            return False

        # Simple seasonal detection - look for recurring patterns
        # This is a placeholder for more sophisticated seasonal analysis

        # Check if data spans multiple weeks/months for meaningful seasonal analysis
        time_span = timestamps[-1] - timestamps[0]
        if time_span.days < 14:  # Need at least 2 weeks of data
            return False

        # Look for weekly patterns (simplified)
        weekday_scores = {}
        for i, timestamp in enumerate(timestamps):
            weekday = timestamp.weekday()  # Monday = 0, Sunday = 6
            if weekday not in weekday_scores:
                weekday_scores[weekday] = []
            weekday_scores[weekday].append(values[i])

        # If we have data for multiple weekdays and variance between weekdays is significant
        if len(weekday_scores) >= 3:
            weekday_avgs = {
                day: sum(scores) / len(scores) for day, scores in weekday_scores.items()
            }
            avg_values = list(weekday_avgs.values())

            if len(avg_values) >= 3:
                std_dev = self._calculate_standard_deviation(avg_values)
                overall_mean = sum(avg_values) / len(avg_values)

                # If weekday variance is > 10% of mean, consider it seasonal
                return std_dev / overall_mean > 0.1

        return False

    def _assess_trend_consistency(self, values: List[float]) -> str:
        """Assess the consistency of trend direction."""
        if len(values) < 3:
            return "insufficient_data"

        volatility = self._calculate_volatility(values)
        trend_strength = abs(self._calculate_trend_strength(values))

        if volatility < 0.1 and trend_strength > 0.3:
            return "highly_consistent"
        elif volatility < 0.3 and trend_strength > 0.2:
            return "moderately_consistent"
        elif volatility > 0.5:
            return "volatile"
        else:
            return "stable"

    def _identify_improvement_periods(
        self, values: List[float], timestamps: List[datetime]
    ) -> List[Dict]:
        """Identify periods of sustained improvement."""
        if len(values) < 3:
            return []

        improvement_periods = []
        current_period = None

        for i in range(1, len(values)):
            if values[i] > values[i - 1]:  # Improvement
                if current_period is None:
                    current_period = {
                        "start_index": i - 1,
                        "start_time": timestamps[i - 1].isoformat(),
                        "start_value": values[i - 1],
                    }
                current_period["end_index"] = i
                current_period["end_time"] = timestamps[i].isoformat()
                current_period["end_value"] = values[i]
                current_period["improvement"] = (
                    values[i] - current_period["start_value"]
                )
                current_period["duration_days"] = (
                    timestamps[i]
                    - datetime.fromisoformat(
                        current_period["start_time"].replace("Z", "+00:00")
                    )
                ).days
            else:
                if (
                    current_period and current_period["improvement"] > 0.5
                ):  # Significant improvement
                    improvement_periods.append(current_period)
                current_period = None

        # Add final period if it was an improvement
        if current_period and current_period["improvement"] > 0.5:
            improvement_periods.append(current_period)

        return improvement_periods

    def _identify_regression_periods(
        self, values: List[float], timestamps: List[datetime]
    ) -> List[Dict]:
        """Identify periods of sustained regression."""
        if len(values) < 3:
            return []

        regression_periods = []
        current_period = None

        for i in range(1, len(values)):
            if values[i] < values[i - 1]:  # Regression
                if current_period is None:
                    current_period = {
                        "start_index": i - 1,
                        "start_time": timestamps[i - 1].isoformat(),
                        "start_value": values[i - 1],
                    }
                current_period["end_index"] = i
                current_period["end_time"] = timestamps[i].isoformat()
                current_period["end_value"] = values[i]
                current_period["regression"] = current_period["start_value"] - values[i]
                current_period["duration_days"] = (
                    timestamps[i]
                    - datetime.fromisoformat(
                        current_period["start_time"].replace("Z", "+00:00")
                    )
                ).days
            else:
                if (
                    current_period and current_period["regression"] > 0.3
                ):  # Significant regression
                    regression_periods.append(current_period)
                current_period = None

        # Add final period if it was a regression
        if current_period and current_period["regression"] > 0.3:
            regression_periods.append(current_period)

        return regression_periods

    def _detect_anomalies(self, values: List[float]) -> List[Dict]:
        """Detect anomalous values using statistical methods."""
        if len(values) < 5:
            return []

        mean = sum(values) / len(values)
        std_dev = self._calculate_standard_deviation(values)

        anomalies = []
        threshold = 2.0 * std_dev  # 2 standard deviations

        for i, value in enumerate(values):
            if abs(value - mean) > threshold:
                anomalies.append(
                    {
                        "index": i,
                        "value": value,
                        "expected_range": [mean - threshold, mean + threshold],
                        "deviation": abs(value - mean),
                        "severity": "high"
                        if abs(value - mean) > 3 * std_dev
                        else "medium",
                    }
                )

        return anomalies

    def _detect_change_points(self, values: List[float]) -> List[int]:
        """Detect points where trend significantly changes."""
        if len(values) < 6:
            return []

        change_points = []
        window_size = 3

        for i in range(window_size, len(values) - window_size):
            # Compare trend before and after this point
            before_values = values[i - window_size : i]
            after_values = values[i : i + window_size]

            before_trend = self._calculate_trend_strength(before_values)
            after_trend = self._calculate_trend_strength(after_values)

            # Significant change in trend direction
            if abs(before_trend - after_trend) > 0.5:
                change_points.append(i)

        return change_points

    def _calculate_quality_momentum(self, values: List[float]) -> float:
        """Calculate current quality momentum (rate of change)."""
        if len(values) < 2:
            return 0.0

        # Use last few points to calculate momentum
        recent_window = min(5, len(values))
        recent_values = values[-recent_window:]

        if len(recent_values) < 2:
            return 0.0

        # Calculate rate of change
        time_span = len(recent_values) - 1
        value_change = recent_values[-1] - recent_values[0]

        momentum = value_change / time_span

        # Normalize momentum (-1 to 1 scale)
        value_range = max(values) - min(values)
        if value_range == 0:
            return 0.0

        normalized_momentum = momentum / value_range

        return max(-1.0, min(1.0, normalized_momentum))

    def _perform_regression_analysis(
        self, values: List[float], timestamps: List[datetime]
    ) -> Dict:
        """Perform linear regression analysis on quality data."""
        if len(values) < 2:
            return {"insufficient_data": True}

        # Convert timestamps to days since first timestamp
        first_time = timestamps[0]
        x_values = [
            (ts - first_time).total_seconds() / (24 * 3600) for ts in timestamps
        ]

        n = len(values)
        x_mean = sum(x_values) / n
        y_mean = sum(values) / n

        # Calculate regression parameters
        numerator = sum((x_values[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x_values[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return {
                "slope": 0,
                "intercept": y_mean,
                "r_squared": 0,
                "trend_significance": "none",
            }

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Calculate R-squared
        ss_tot = sum((values[i] - y_mean) ** 2 for i in range(n))
        ss_res = sum(
            (values[i] - (slope * x_values[i] + intercept)) ** 2 for i in range(n)
        )

        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0

        # Determine trend significance
        if r_squared > 0.7:
            trend_significance = "strong"
        elif r_squared > 0.4:
            trend_significance = "moderate"
        elif r_squared > 0.1:
            trend_significance = "weak"
        else:
            trend_significance = "none"

        return {
            "slope": slope,
            "intercept": intercept,
            "r_squared": r_squared,
            "trend_significance": trend_significance,
            "equation": f"y = {slope:.3f}x + {intercept:.3f}",
        }

    def _calculate_correlation_matrix(self, metrics: Dict[str, List[float]]) -> Dict:
        """Calculate correlation matrix between different quality metrics."""
        metric_names = list(metrics.keys())
        correlations = {}

        for i, metric1 in enumerate(metric_names):
            correlations[metric1] = {}
            for j, metric2 in enumerate(metric_names):
                if i <= j:  # Only calculate upper triangle (symmetric matrix)
                    correlation = self._calculate_correlation(
                        metrics[metric1], metrics[metric2]
                    )
                    correlations[metric1][metric2] = correlation
                    if i != j:  # Fill symmetric entries
                        if metric2 not in correlations:
                            correlations[metric2] = {}
                        correlations[metric2][metric1] = correlation

        return correlations

    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient between two metrics."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0

        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))

        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))

        denominator = (sum_sq_x * sum_sq_y) ** 0.5

        if denominator == 0:
            return 0.0

        return numerator / denominator

    def _calculate_confidence_intervals(
        self, values: List[float], confidence: float = 0.95
    ) -> Dict:
        """Calculate confidence intervals for quality metrics."""
        if len(values) < 2:
            return {"insufficient_data": True}

        mean = sum(values) / len(values)
        std_dev = self._calculate_standard_deviation(values)

        # Use t-distribution for small samples (approximation)
        if len(values) < 30:
            # Simplified t-value for 95% confidence (approximation)
            t_value = 2.0 + 0.5 / len(values)  # Rough approximation
        else:
            t_value = 1.96  # Z-value for 95% confidence

        margin_of_error = t_value * std_dev / (len(values) ** 0.5)

        return {
            "mean": mean,
            "confidence_level": confidence,
            "lower_bound": mean - margin_of_error,
            "upper_bound": mean + margin_of_error,
            "margin_of_error": margin_of_error,
        }

    def _test_trend_significance(self, values: List[float]) -> Dict:
        """Test statistical significance of observed trend."""
        if len(values) < 3:
            return {"insufficient_data": True}

        trend_strength = self._calculate_trend_strength(values)
        volatility = self._calculate_volatility(values)

        # Simple significance test based on trend strength vs volatility
        significance_ratio = abs(trend_strength) / (
            volatility + 0.001
        )  # Avoid division by zero

        if significance_ratio > 2.0:
            significance = "statistically_significant"
        elif significance_ratio > 1.0:
            significance = "moderately_significant"
        else:
            significance = "not_significant"

        return {
            "trend_strength": trend_strength,
            "volatility": volatility,
            "significance_ratio": significance_ratio,
            "significance": significance,
            "confidence": min(
                0.95, significance_ratio * 0.3
            ),  # Rough confidence estimate
        }

    def _short_term_forecast(self, values: List[float], periods: int) -> List[float]:
        """Generate short-term forecasts for multiple periods ahead."""
        if len(values) < 2:
            return [values[0] if values else 0.0] * periods

        forecasts = []
        working_values = values.copy()

        for _ in range(periods):
            next_forecast = self._forecast_next_value(working_values)
            forecasts.append(next_forecast)
            working_values.append(next_forecast)  # Use forecast for next iteration

        return forecasts

    def _project_trend(self, values: List[float], periods: int) -> List[float]:
        """Project trend using linear extrapolation."""
        if len(values) < 2:
            return [values[0] if values else 0.0] * periods

        # Use linear regression for trend projection
        n = len(values)
        x = list(range(n))

        x_mean = sum(x) / n
        y_mean = sum(values) / n

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return [values[-1]] * periods

        slope = numerator / denominator
        intercept = y_mean - slope * x_mean

        # Project future values
        projections = []
        for i in range(1, periods + 1):
            future_x = n + i - 1
            projection = slope * future_x + intercept
            projections.append(projection)

        return projections

    def _calculate_forecast_confidence(self, values: List[float]) -> Dict:
        """Calculate confidence bounds for forecasts."""
        if len(values) < 3:
            return {"insufficient_data": True}

        # Calculate forecast error based on recent predictions vs actual
        std_dev = self._calculate_standard_deviation(values)
        recent_volatility = self._calculate_volatility(values[-5:])

        # Confidence decreases with volatility
        confidence_factor = max(0.1, 1.0 - recent_volatility)

        return {
            "confidence_level": confidence_factor,
            "error_margin": std_dev * (1.0 - confidence_factor),
            "reliability": "high"
            if confidence_factor > 0.7
            else "medium"
            if confidence_factor > 0.4
            else "low",
        }

    def _assess_forecast_accuracy(self, values: List[float]) -> Dict:
        """Assess accuracy of forecasting methods using historical data."""
        if len(values) < 6:
            return {"insufficient_data": True}

        # Use last 30% of data for accuracy testing
        test_size = max(2, len(values) // 3)
        train_values = values[:-test_size]
        test_values = values[-test_size:]

        errors = []
        for i in range(len(test_values)):
            forecast_values = train_values + test_values[:i]
            predicted = self._forecast_next_value(forecast_values)
            actual = test_values[i]
            error = abs(predicted - actual)
            errors.append(error)

        mean_error = sum(errors) / len(errors)
        max_error = max(errors)

        # Calculate accuracy as percentage
        value_range = max(values) - min(values)
        if value_range == 0:
            accuracy = 1.0
        else:
            accuracy = max(0.0, 1.0 - (mean_error / value_range))

        return {
            "mean_absolute_error": mean_error,
            "max_error": max_error,
            "accuracy_percentage": accuracy * 100,
            "forecast_reliability": "high"
            if accuracy > 0.8
            else "medium"
            if accuracy > 0.6
            else "low",
        }

    def _generate_advanced_recommendations(
        self,
        scores: List[float],
        violations: List[float],
        critical_violations: List[float],
        coverage: List[float],
        complexity: List[float],
    ) -> List[str]:
        """Generate advanced recommendations based on comprehensive trend analysis."""
        recommendations = []

        # Quality score trend analysis
        if scores:
            score_trend = self._calculate_simple_trend(scores)
            current_score = scores[-1]
            score_volatility = self._calculate_volatility(scores)

            if score_trend == "decreasing":
                momentum = self._calculate_quality_momentum(scores)
                if momentum < -0.5:
                    recommendations.append(
                        "🚨 URGENT: Quality declining rapidly - implement immediate quality interventions"
                    )
                else:
                    recommendations.append(
                        "📉 Quality trend negative - review recent changes and implement quality improvements"
                    )

            if score_volatility > 0.3:
                recommendations.append(
                    "⚠️ Quality highly volatile - establish consistent quality practices and monitoring"
                )

            if current_score < 7.0:
                forecast = self._forecast_next_value(scores)
                if forecast < current_score:
                    recommendations.append(
                        f"🔻 Quality forecast shows continued decline (predicted: {forecast:.1f}) - take immediate action"
                    )

        # Violations trend analysis
        if violations:
            violation_trend = self._calculate_simple_trend(violations)
            if violation_trend == "increasing":
                recent_violations = (
                    violations[-3:] if len(violations) >= 3 else violations
                )
                if all(v > violations[0] for v in recent_violations[1:]):
                    recommendations.append(
                        "📈 Violations consistently increasing - review development practices and tooling effectiveness"
                    )

        # Critical violations analysis
        if critical_violations and any(cv > 0 for cv in critical_violations):
            recent_critical = critical_violations[-1] if critical_violations else 0
            if recent_critical > 0:
                recommendations.append(
                    f"🚨 CRITICAL: {recent_critical} critical violations present - resolve immediately"
                )

        # Coverage trend analysis
        if coverage:
            coverage_trend = self._calculate_simple_trend(coverage)
            current_coverage = coverage[-1]

            if coverage_trend == "decreasing" and current_coverage < 80:
                recommendations.append(
                    f"📊 Test coverage declining and below 80% ({current_coverage:.1f}%) - prioritize test development"
                )

        # Complexity trend analysis
        if complexity:
            complexity_trend = self._calculate_simple_trend(complexity)
            if complexity_trend == "increasing":
                current_complexity = complexity[-1]
                if current_complexity > 8.0:
                    recommendations.append(
                        f"🔄 Code complexity increasing (avg: {current_complexity:.1f}) - implement refactoring initiatives"
                    )

        return recommendations

    def _generate_quality_alerts(
        self,
        scores: List[float],
        violations: List[float],
        critical_violations: List[float],
    ) -> List[Dict]:
        """Generate quality alerts based on trend analysis."""
        alerts = []

        if not scores:
            return alerts

        current_score = scores[-1]

        # Critical quality threshold alert
        if current_score < 6.0:
            alerts.append(
                {
                    "level": "critical",
                    "type": "quality_threshold",
                    "message": f"Quality score below critical threshold: {current_score:.1f}/10.0",
                    "recommended_action": "Immediate quality improvement required",
                }
            )

        # Rapid decline alert
        if len(scores) >= 3:
            recent_trend = scores[-3:]
            if all(
                recent_trend[i] < recent_trend[i - 1]
                for i in range(1, len(recent_trend))
            ):
                decline = scores[-3] - scores[-1]
                if decline > 1.0:
                    alerts.append(
                        {
                            "level": "high",
                            "type": "rapid_decline",
                            "message": f"Quality declining rapidly: -{decline:.1f} points in recent assessments",
                            "recommended_action": "Investigate recent changes and implement fixes",
                        }
                    )

        # Critical violations alert
        if critical_violations and critical_violations[-1] > 0:
            alerts.append(
                {
                    "level": "critical",
                    "type": "critical_violations",
                    "message": f"{critical_violations[-1]} critical violations detected",
                    "recommended_action": "Review and fix all critical violations immediately",
                }
            )

        return alerts

    def _detect_threshold_breaches(
        self, scores: List[float], violations: List[float]
    ) -> List[Dict]:
        """Detect threshold breaches in quality metrics."""
        breaches = []

        # Quality score thresholds
        quality_thresholds = [
            {"value": 9.0, "level": "excellent"},
            {"value": 8.0, "level": "good"},
            {"value": 7.0, "level": "acceptable"},
            {"value": 6.0, "level": "poor"},
            {"value": 5.0, "level": "critical"},
        ]

        if scores:
            current_score = scores[-1]
            for threshold in quality_thresholds:
                if current_score < threshold["value"]:
                    breaches.append(
                        {
                            "metric": "quality_score",
                            "threshold": threshold["value"],
                            "current_value": current_score,
                            "severity": threshold["level"],
                            "breach_type": "below_threshold",
                        }
                    )
                    break  # Only report the most relevant threshold breach

        # Violation count thresholds
        if violations:
            current_violations = violations[-1]
            if current_violations > 50:
                breaches.append(
                    {
                        "metric": "violation_count",
                        "threshold": 50,
                        "current_value": current_violations,
                        "severity": "high",
                        "breach_type": "above_threshold",
                    }
                )
            elif current_violations > 20:
                breaches.append(
                    {
                        "metric": "violation_count",
                        "threshold": 20,
                        "current_value": current_violations,
                        "severity": "medium",
                        "breach_type": "above_threshold",
                    }
                )

        return breaches

    def _calculate_early_warning_indicators(
        self, scores: List[float], violations: List[float]
    ) -> Dict:
        """Calculate early warning indicators for quality degradation."""
        if len(scores) < 3:
            return {"insufficient_data": True}

        warnings = {
            "trend_reversal_risk": 0.0,
            "volatility_increase": 0.0,
            "momentum_loss": 0.0,
            "overall_risk": "low",
        }

        # Trend reversal risk
        recent_scores = scores[-5:] if len(scores) >= 5 else scores
        trend_strength = self._calculate_trend_strength(recent_scores)
        if trend_strength > 0.2:  # Positive trend
            # Check if momentum is slowing
            momentum = self._calculate_quality_momentum(scores)
            if momentum < trend_strength * 0.5:
                warnings["trend_reversal_risk"] = 0.7

        # Volatility increase
        if len(scores) >= 6:
            early_volatility = self._calculate_volatility(scores[: len(scores) // 2])
            recent_volatility = self._calculate_volatility(scores[len(scores) // 2 :])

            if recent_volatility > early_volatility * 1.5:
                warnings["volatility_increase"] = min(
                    1.0, recent_volatility / early_volatility
                )

        # Momentum loss
        if len(scores) >= 4:
            momentum = self._calculate_quality_momentum(scores)
            if momentum < -0.2:
                warnings["momentum_loss"] = min(1.0, abs(momentum))

        # Calculate overall risk
        risk_factors = [
            warnings["trend_reversal_risk"],
            warnings["volatility_increase"],
            warnings["momentum_loss"],
        ]

        overall_risk_score = sum(risk_factors) / len(risk_factors)

        if overall_risk_score > 0.7:
            warnings["overall_risk"] = "high"
        elif overall_risk_score > 0.4:
            warnings["overall_risk"] = "medium"
        else:
            warnings["overall_risk"] = "low"

        return warnings
