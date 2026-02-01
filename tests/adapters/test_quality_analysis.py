"""
Unit tests for QualityAnalysisAdapter.

Tests the intelligent quality analysis and metrics extraction capabilities
including tool output parsing, quality scoring, pattern detection, and
recommendation generation.
"""

import json
import pytest
from datetime import datetime, UTC
from unittest.mock import Mock

from core.models import (
    QualityTool,
    QualityAssessmentResult,
    QualityAssessmentType,
    QualityMetrics,
    QualityViolation,
    SecurityIssue,
    ComplexityMetric,
    ExecutionStatus,
    ViolationSeverity,
)
from adapters.quality_analysis import QualityAnalysisAdapter


class TestQualityAnalysisAdapter:
    """Test suite for QualityAnalysisAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create QualityAnalysisAdapter instance."""
        return QualityAnalysisAdapter()

    @pytest.fixture
    def sample_violations(self):
        """Create sample violations for testing."""
        return [
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="F401",
                message="'os' imported but unused",
                severity=ViolationSeverity.LOW,
                file_path="src/main.py",
                line_number=1,
                fixable=True
            ),
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="E902",
                message="No newline at end of file",
                severity=ViolationSeverity.CRITICAL,
                file_path="src/utils.py",
                line_number=50,
                fixable=True
            ),
        ]

    @pytest.fixture
    def sample_assessment_result(self, sample_violations):
        """Create sample assessment result."""
        metrics = QualityMetrics(
            overall_score=7.5,
            total_violations=2,
            critical_violations=1,
            high_violations=0,
            medium_violations=0,
            low_violations=1,
            test_coverage_percentage=85.0,
            average_complexity=4.2,
            total_lines=1000,
            code_lines=800,
            comment_lines=150,
            blank_lines=50
        )
        
        return QualityAssessmentResult(
            assessment_type=QualityAssessmentType.LINT,
            tool=QualityTool.RUFF,
            status=ExecutionStatus.SUCCESS,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=1500.0,
            pixi_task_used="ruff",
            target_path="src/",
            files_analyzed=5,
            raw_output="test output",
            parsed_metrics=metrics,
            violations=sample_violations
        )

    def test_parse_ruff_json_output(self, adapter):
        """Test parsing ruff JSON output."""
        ruff_output = json.dumps([
            {
                "code": "F401",
                "message": "'os' imported but unused",
                "filename": "src/main.py",
                "location": {"row": 1, "column": 8},
                "severity": "error",
                "fix": {"applicability": "automatic"}
            }
        ])
        
        result = adapter.parse_tool_output(QualityTool.RUFF, ruff_output, 0)
        
        assert result.tool == QualityTool.RUFF
        assert result.status == ExecutionStatus.SUCCESS
        assert len(result.violations) == 1
        
        violation = result.violations[0]
        assert violation.rule_code == "F401"
        assert violation.file_path == "src/main.py"
        assert violation.line_number == 1
        assert violation.fixable is True

    def test_parse_ruff_text_output(self, adapter):
        """Test parsing ruff text output."""
        ruff_output = "src/main.py:1:8: F401 'os' imported but unused"
        
        result = adapter.parse_tool_output(QualityTool.RUFF, ruff_output, 0)
        
        assert result.tool == QualityTool.RUFF
        assert len(result.violations) == 1
        
        violation = result.violations[0]
        assert violation.rule_code == "F401"
        assert violation.file_path == "src/main.py"
        assert violation.line_number == 1
        assert violation.column_number == 8

    def test_parse_mypy_output(self, adapter):
        """Test parsing mypy output."""
        mypy_output = """src/main.py:15: error: Incompatible return value type (got "str", expected "int")
src/utils.py:23: warning: Unused 'type: ignore' comment"""
        
        result = adapter.parse_tool_output(QualityTool.MYPY, mypy_output, 1)
        
        assert result.tool == QualityTool.MYPY
        assert result.status == ExecutionStatus.FAILURE
        assert len(result.violations) == 2
        
        error_violation = result.violations[0]
        assert error_violation.severity == ViolationSeverity.HIGH
        assert error_violation.file_path == "src/main.py"
        assert error_violation.line_number == 15

    def test_parse_bandit_output(self, adapter):
        """Test parsing bandit JSON output."""
        bandit_output = json.dumps({
            "results": [
                {
                    "test_id": "B101",
                    "test_name": "assert_used",
                    "issue_text": "Use of assert detected",
                    "issue_severity": "LOW",
                    "issue_confidence": "HIGH",
                    "filename": "src/test.py",
                    "line_number": 42,
                    "more_info": "https://bandit.readthedocs.io/en/latest/"
                }
            ]
        })
        
        result = adapter.parse_tool_output(QualityTool.BANDIT, bandit_output, 0)
        
        assert result.tool == QualityTool.BANDIT
        assert len(result.security_issues) == 1
        
        security_issue = result.security_issues[0]
        assert security_issue.test_id == "B101"
        assert security_issue.severity == ViolationSeverity.LOW
        assert security_issue.confidence == "high"
        assert security_issue.file_path == "src/test.py"
        assert security_issue.line_number == 42

    def test_parse_error_handling(self, adapter):
        """Test error handling in parse_tool_output."""
        # Invalid JSON should not crash - exit code 1 means FAILURE
        result = adapter.parse_tool_output(QualityTool.RUFF, "invalid json", 1)
        
        assert result.tool == QualityTool.RUFF
        assert result.status == ExecutionStatus.FAILURE
        # Should parse as empty violations for invalid text output
        assert len(result.violations) == 0

    def test_calculate_quality_score_empty_results(self, adapter):
        """Test quality score calculation with empty results."""
        score = adapter.calculate_quality_score([])
        assert score == 0.0

    def test_calculate_quality_score_single_result(self, adapter, sample_assessment_result):
        """Test quality score calculation with single result."""
        score = adapter.calculate_quality_score([sample_assessment_result])
        
        assert isinstance(score, float)
        assert 0.0 <= score <= 10.0
        # Should be reasonable score given metrics
        assert score > 6.0  # Good coverage, low violations

    def test_calculate_quality_score_multiple_results(self, adapter, sample_assessment_result):
        """Test quality score calculation with multiple results."""
        # Create second result with different metrics
        metrics2 = QualityMetrics(
            overall_score=6.0,
            total_violations=10,
            critical_violations=2,
            high_violations=3,
            medium_violations=5,
            low_violations=0,
            test_coverage_percentage=60.0,
            average_complexity=8.0,
            security_issues_count=1,
            total_lines=1500,
            code_lines=1200,
            comment_lines=200,
            blank_lines=100
        )
        
        result2 = QualityAssessmentResult(
            assessment_type=QualityAssessmentType.SECURITY,
            tool=QualityTool.BANDIT,
            status=ExecutionStatus.SUCCESS,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=2000.0,
            pixi_task_used="bandit",
            target_path="src/",
            files_analyzed=8,
            raw_output="security scan output",
            parsed_metrics=metrics2
        )
        
        score = adapter.calculate_quality_score([sample_assessment_result, result2])
        
        assert isinstance(score, float)
        assert 0.0 <= score <= 10.0
        # Score should be reasonable given mixed quality results
        assert 5.0 <= score <= 9.0

    def test_generate_recommendations_critical_violations(self, adapter, sample_assessment_result):
        """Test recommendation generation for critical violations."""
        recommendations = adapter.generate_recommendations([sample_assessment_result])
        
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        
        # Should mention critical violations
        critical_mentioned = any("CRITICAL" in rec for rec in recommendations)
        assert critical_mentioned

    def test_generate_recommendations_low_coverage(self, adapter):
        """Test recommendations for low test coverage."""
        metrics = QualityMetrics(
            overall_score=5.0,
            total_violations=0,
            critical_violations=0,
            high_violations=0,
            medium_violations=0,
            low_violations=0,
            test_coverage_percentage=35.0,  # Low coverage
            total_lines=1000,
            code_lines=800,
            comment_lines=150,
            blank_lines=50
        )
        
        result = QualityAssessmentResult(
            assessment_type=QualityAssessmentType.COMPREHENSIVE,
            tool=QualityTool.PYTEST,
            status=ExecutionStatus.SUCCESS,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=1000.0,
            pixi_task_used="pytest",
            target_path="src/",
            files_analyzed=10,
            raw_output="coverage report",
            parsed_metrics=metrics
        )
        
        recommendations = adapter.generate_recommendations([result])
        
        # Should mention coverage
        coverage_mentioned = any("coverage" in rec.lower() for rec in recommendations)
        assert coverage_mentioned

    def test_detect_quality_patterns(self, adapter, sample_assessment_result):
        """Test quality pattern detection."""
        patterns = adapter.detect_quality_patterns([sample_assessment_result])
        
        assert isinstance(patterns, dict)
        assert 'total_violations' in patterns
        assert 'critical_violations' in patterns
        assert 'security_issues' in patterns
        assert 'violation_hotspots' in patterns
        assert 'most_common_violations' in patterns
        assert 'detected_anti_patterns' in patterns
        
        assert patterns['total_violations'] == 2
        assert patterns['critical_violations'] == 1

    def test_detect_quality_patterns_multiple_results(self, adapter):
        """Test pattern detection with multiple results."""
        # Create results with violations in same files
        violations1 = [
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="F401",
                message="Unused import",
                severity=ViolationSeverity.LOW,
                file_path="src/main.py",
                line_number=1,
                fixable=True
            ),
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="F401",
                message="Another unused import",
                severity=ViolationSeverity.LOW,
                file_path="src/main.py",
                line_number=2,
                fixable=True
            ),
        ]
        
        violations2 = [
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="E501",
                message="Line too long",
                severity=ViolationSeverity.MEDIUM,
                file_path="src/main.py",
                line_number=50,
                fixable=True
            ),
        ]
        
        # Create assessment results
        results = []
        for i, violations in enumerate([violations1, violations2]):
            metrics = QualityMetrics(
                overall_score=7.0,
                total_violations=len(violations),
                critical_violations=0,
                high_violations=0,
                medium_violations=sum(1 for v in violations if v.severity == ViolationSeverity.MEDIUM),
                low_violations=sum(1 for v in violations if v.severity == ViolationSeverity.LOW),
                total_lines=1000,
                code_lines=800,
                comment_lines=150,
                blank_lines=50
            )
            
            result = QualityAssessmentResult(
                assessment_type=QualityAssessmentType.LINT,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=1000.0,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=5,
                raw_output="ruff output",
                parsed_metrics=metrics,
                violations=violations
            )
            results.append(result)
        
        patterns = adapter.detect_quality_patterns(results)
        
        # Should detect hotspot (main.py has 3 violations)
        assert 'src/main.py' in patterns['violation_hotspots']
        assert patterns['violation_hotspots']['src/main.py'] == 3
        
        # Should detect common violation (F401 appears twice)
        assert 'F401' in patterns['most_common_violations']
        assert patterns['most_common_violations']['F401'] == 2

    def test_prioritize_issues(self, adapter, sample_assessment_result):
        """Test issue prioritization."""
        issues = adapter.prioritize_issues([sample_assessment_result])
        
        assert isinstance(issues, list)
        assert len(issues) == 2  # Two violations in sample
        
        # Issues should be sorted by priority
        if len(issues) > 1:
            assert issues[0]['priority_score'] >= issues[1]['priority_score']
        
        # Check issue structure
        issue = issues[0]
        assert 'type' in issue
        assert 'impact_score' in issue
        assert 'effort_score' in issue
        assert 'priority_score' in issue
        assert 'fixable' in issue

    def test_prioritize_issues_security(self, adapter):
        """Test prioritization includes security issues."""
        security_issues = [
            SecurityIssue(
                issue_id="B101",
                title="Use of assert detected",
                description="Assert usage detected",
                severity=ViolationSeverity.HIGH,
                confidence="HIGH",
                file_path="src/test.py",
                line_number=42,
                test_id="B101"
            )
        ]
        
        metrics = QualityMetrics(
            overall_score=8.0,
            total_violations=0,
            critical_violations=0,
            high_violations=0,
            medium_violations=0,
            low_violations=0,
            security_issues_count=1,
            total_lines=1000,
            code_lines=800,
            comment_lines=150,
            blank_lines=50
        )
        
        result = QualityAssessmentResult(
            assessment_type=QualityAssessmentType.SECURITY,
            tool=QualityTool.BANDIT,
            status=ExecutionStatus.SUCCESS,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=1000.0,
            pixi_task_used="bandit",
            target_path="src/",
            files_analyzed=5,
            raw_output="bandit output",
            parsed_metrics=metrics,
            security_issues=security_issues
        )
        
        issues = adapter.prioritize_issues([result])
        
        assert len(issues) == 1
        assert issues[0]['type'] == 'security'
        assert issues[0]['severity'] == 'high'

    def test_impact_score_calculation(self, adapter):
        """Test impact score calculation for violations."""
        # Critical violation should have high impact
        critical_violation = QualityViolation(
            tool=QualityTool.RUFF,
            rule_code="E902",
            message="Syntax error",
            severity=ViolationSeverity.CRITICAL,
            file_path="src/main.py",
            line_number=1,
            fixable=False
        )
        
        critical_score = adapter._calculate_impact_score(critical_violation)
        
        # Low violation should have lower impact
        low_violation = QualityViolation(
            tool=QualityTool.RUFF,
            rule_code="W503",
            message="Line break before binary operator",
            severity=ViolationSeverity.LOW,
            file_path="src/main.py",
            line_number=1,
            fixable=True
        )
        
        low_score = adapter._calculate_impact_score(low_violation)
        
        assert critical_score > low_score
        assert 0 <= critical_score <= 10
        assert 0 <= low_score <= 10

    def test_effort_score_calculation(self, adapter):
        """Test effort score calculation for violations."""
        # Auto-fixable violation should have low effort
        fixable_violation = QualityViolation(
            tool=QualityTool.RUFF,
            rule_code="F401",
            message="Unused import",
            severity=ViolationSeverity.LOW,
            file_path="src/main.py",
            line_number=1,
            fixable=True
        )
        
        fixable_effort = adapter._calculate_effort_score(fixable_violation)
        
        # Non-fixable violation should have higher effort
        manual_violation = QualityViolation(
            tool=QualityTool.RUFF,
            rule_code="C901",
            message="Function too complex",
            severity=ViolationSeverity.HIGH,
            file_path="src/main.py",
            line_number=1,
            fixable=False
        )
        
        manual_effort = adapter._calculate_effort_score(manual_violation)
        
        assert fixable_effort < manual_effort
        assert 1 <= fixable_effort <= 10
        assert 1 <= manual_effort <= 10

    def test_severity_mapping(self, adapter):
        """Test severity mapping functions."""
        # Test general severity mapping
        assert adapter._map_severity("error") == ViolationSeverity.HIGH
        assert adapter._map_severity("warning") == ViolationSeverity.MEDIUM
        assert adapter._map_severity("info") == ViolationSeverity.INFO
        
        # Test ruff-specific mapping
        assert adapter._map_ruff_severity("E902") == ViolationSeverity.CRITICAL
        assert adapter._map_ruff_severity("F401") == ViolationSeverity.HIGH
        assert adapter._map_ruff_severity("E501") == ViolationSeverity.MEDIUM
        assert adapter._map_ruff_severity("W503") == ViolationSeverity.LOW
        
        # Test bandit severity mapping
        assert adapter._map_bandit_severity("HIGH") == ViolationSeverity.HIGH
        assert adapter._map_bandit_severity("MEDIUM") == ViolationSeverity.MEDIUM
        assert adapter._map_bandit_severity("LOW") == ViolationSeverity.LOW

    def test_build_quality_metrics(self, adapter):
        """Test QualityMetrics building from parsed data."""
        violations = [
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="E902",
                message="Syntax error",
                severity=ViolationSeverity.CRITICAL,
                file_path="src/main.py",
                line_number=1,
                fixable=False
            ),
            QualityViolation(
                tool=QualityTool.RUFF,
                rule_code="F401",
                message="Unused import",
                severity=ViolationSeverity.LOW,
                file_path="src/main.py",
                line_number=2,
                fixable=True
            ),
        ]
        
        complexity_results = [
            ComplexityMetric(
                name="test_function",
                complexity_score=5,
                maintainability_index=75.0,
                lines_of_code=20,
                difficulty=2.5,
                effort=50.0,
                time_to_understand=12.5
            ),
        ]
        
        parsed_data = {
            'violations': violations,
            'complexity_results': complexity_results,
        }
        
        metrics = adapter._build_quality_metrics(parsed_data)
        
        assert metrics.total_violations == 2
        assert metrics.critical_violations == 1
        assert metrics.low_violations == 1
        assert metrics.average_complexity == 5.0
        assert metrics.max_complexity == 5
        assert metrics.maintainability_index == 75.0