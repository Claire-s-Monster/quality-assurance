"""
Quality analysis adapter for intelligent quality analysis and metrics extraction.

This adapter implements QualityAnalysisPort to provide intelligent analysis of
quality assessment results including pattern detection, scoring algorithms,
and actionable recommendations.
"""

import json
import re
from typing import Any, Dict, List
from datetime import UTC, datetime

from core.models import (
    QualityTool,
    QualityAssessmentType,
    QualityAssessmentResult,
    QualityViolation,
    SecurityIssue,
    ComplexityMetric,
    ExecutionStatus,
    ViolationSeverity,
    QualityMetrics,
)
from core.ports import QualityAnalysisPort


class QualityAnalysisAdapter(QualityAnalysisPort):
    """
    Adapter for intelligent quality analysis and metrics extraction.

    Provides sophisticated analysis capabilities including quality scoring,
    pattern detection, issue prioritization, and recommendation generation.
    """

    def __init__(self):
        """Initialize the quality analysis adapter."""
        # Severity weights for scoring calculations
        self.severity_weights = {
            ViolationSeverity.CRITICAL: 10.0,
            ViolationSeverity.HIGH: 7.0,
            ViolationSeverity.MEDIUM: 4.0,
            ViolationSeverity.LOW: 2.0,
            ViolationSeverity.INFO: 1.0,
        }

        # Quality score component weights
        self.score_weights = {
            "violations": 0.40,  # 40% - Violations impact
            "coverage": 0.20,  # 20% - Test coverage
            "complexity": 0.20,  # 20% - Code complexity
            "security": 0.10,  # 10% - Security issues
            "maintainability": 0.10,  # 10% - Maintainability metrics
        }

    def parse_tool_output(
        self, tool: QualityTool, raw_output: str, tool_exit_code: int
    ) -> QualityAssessmentResult:
        """Parse raw tool output into structured assessment result."""

        start_time = datetime.now(UTC).isoformat()

        # Determine execution status from exit code
        status = (
            ExecutionStatus.SUCCESS if tool_exit_code == 0 else ExecutionStatus.FAILURE
        )

        try:
            # Parse tool-specific output
            if tool == QualityTool.RUFF:
                parsed_data = self._parse_ruff_output(raw_output)
            elif tool == QualityTool.MYPY:
                parsed_data = self._parse_mypy_output(raw_output)
            elif tool == QualityTool.BANDIT:
                parsed_data = self._parse_bandit_output(raw_output)
            elif tool == QualityTool.RADON:
                parsed_data = self._parse_radon_output(raw_output)
            elif tool == QualityTool.VULTURE:
                parsed_data = self._parse_vulture_output(raw_output)
            elif tool == QualityTool.PYTEST:
                parsed_data = self._parse_pytest_output(raw_output)
            elif tool == QualityTool.COVERAGE:
                parsed_data = self._parse_coverage_output(raw_output)
            else:
                parsed_data = self._parse_generic_output(raw_output)

            # Build metrics from parsed data
            metrics = self._build_quality_metrics(parsed_data)

            return QualityAssessmentResult(
                assessment_type=parsed_data.get(
                    "assessment_type", QualityAssessmentType.LINT
                ),
                tool=tool,
                status=status,
                start_time=start_time,
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=0.0,  # Will be calculated by calling code
                pixi_task_used=f"{tool.value}",
                target_path=parsed_data.get("target_path", "src/"),
                files_analyzed=parsed_data.get("files_analyzed", 0),
                raw_output=raw_output,
                parsed_metrics=metrics,
                violations=parsed_data.get("violations", []),
                security_issues=parsed_data.get("security_issues", []),
                complexity_results=parsed_data.get("complexity_results", []),
                dead_code_results=parsed_data.get("dead_code_results", []),
                auto_fix_available=parsed_data.get("auto_fix_available", False),
                fix_commands=parsed_data.get("fix_commands", []),
            )

        except Exception as e:
            # Return error result if parsing fails
            return QualityAssessmentResult(
                assessment_type=QualityAssessmentType.LINT,
                tool=tool,
                status=ExecutionStatus.ERROR,
                start_time=start_time,
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=0.0,
                pixi_task_used=f"{tool.value}",
                target_path="unknown",
                files_analyzed=0,
                raw_output=raw_output,
                parsed_metrics=QualityMetrics(
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
                ),
                recommendations=[f"Failed to parse {tool.value} output: {str(e)}"],
            )

    def calculate_quality_score(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> float:
        """Calculate overall quality score from assessment results."""

        if not assessment_results:
            return 0.0

        # Aggregate metrics from all results
        total_violations = 0
        critical_violations = 0
        high_violations = 0
        security_issues = 0
        total_coverage = 0.0
        coverage_count = 0
        total_complexity = 0.0
        complexity_count = 0
        total_maintainability = 0.0
        maintainability_count = 0
        total_lines = 0

        for result in assessment_results:
            if result.status != ExecutionStatus.SUCCESS:
                continue

            metrics = result.parsed_metrics
            total_violations += metrics.total_violations
            critical_violations += metrics.critical_violations
            high_violations += metrics.high_violations
            security_issues += metrics.security_issues_count

            if metrics.test_coverage_percentage is not None:
                total_coverage += metrics.test_coverage_percentage
                coverage_count += 1

            if metrics.average_complexity is not None:
                total_complexity += metrics.average_complexity
                complexity_count += 1

            if metrics.maintainability_index is not None:
                total_maintainability += metrics.maintainability_index
                maintainability_count += 1

            total_lines += metrics.total_lines

        if total_lines == 0:
            return 0.0

        # Calculate component scores (0-10 scale)

        # 1. Violations score (higher violations = lower score)
        violations_per_100_lines = (
            (total_violations / total_lines) * 100 if total_lines > 0 else 0
        )
        critical_weight = (
            critical_violations * self.severity_weights[ViolationSeverity.CRITICAL]
        )
        high_weight = high_violations * self.severity_weights[ViolationSeverity.HIGH]
        weighted_violations_per_100 = (
            ((critical_weight + high_weight) / total_lines) * 100
            if total_lines > 0
            else 0
        )

        violations_score = max(
            0.0,
            10.0
            - (violations_per_100_lines * 0.5)
            - (weighted_violations_per_100 * 0.3),
        )

        # 2. Coverage score
        avg_coverage = (total_coverage / coverage_count) if coverage_count > 0 else 0.0
        coverage_score = min(10.0, avg_coverage / 10.0)  # Scale 0-100% to 0-10

        # 3. Complexity score (lower complexity = higher score)
        avg_complexity = (
            (total_complexity / complexity_count) if complexity_count > 0 else 5.0
        )
        complexity_score = max(
            0.0, min(10.0, 15.0 - avg_complexity)
        )  # Complexity 1-5 = score 10-5

        # 4. Security score
        security_per_100_lines = (
            (security_issues / total_lines) * 100 if total_lines > 0 else 0
        )
        security_score = max(0.0, 10.0 - (security_per_100_lines * 2.0))

        # 5. Maintainability score
        avg_maintainability = (
            (total_maintainability / maintainability_count)
            if maintainability_count > 0
            else 50.0
        )
        maintainability_score = min(
            10.0, avg_maintainability / 10.0
        )  # Scale 0-100 to 0-10

        # Weighted final score
        final_score = (
            violations_score * self.score_weights["violations"]
            + coverage_score * self.score_weights["coverage"]
            + complexity_score * self.score_weights["complexity"]
            + security_score * self.score_weights["security"]
            + maintainability_score * self.score_weights["maintainability"]
        )

        return round(final_score, 2)

    def generate_recommendations(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> List[str]:
        """Generate actionable quality improvement recommendations."""

        recommendations = []

        # Analyze patterns across results
        patterns = self.detect_quality_patterns(assessment_results)

        # Critical issues first
        if patterns.get("critical_violations", 0) > 0:
            recommendations.append(
                f"⚠️  CRITICAL: Fix {patterns['critical_violations']} critical violations immediately "
                "- these represent serious code quality or security issues"
            )

        # High violations
        if patterns.get("high_violations", 0) > 0:
            recommendations.append(
                f"🔴 HIGH: Address {patterns['high_violations']} high-severity violations "
                "to improve code reliability and maintainability"
            )

        # Coverage recommendations
        coverage = patterns.get("coverage_percentage", 0)
        if coverage < 80:
            if coverage < 50:
                recommendations.append(
                    f"📊 Test coverage is critically low at {coverage:.1f}% - "
                    "prioritize adding unit tests for core functionality"
                )
            else:
                recommendations.append(
                    f"📊 Test coverage at {coverage:.1f}% - "
                    "aim for 80%+ coverage to ensure code reliability"
                )

        # Complexity recommendations
        avg_complexity = patterns.get("average_complexity", 0)
        if avg_complexity > 10:
            recommendations.append(
                f"🔄 Average complexity is {avg_complexity:.1f} - "
                "refactor complex functions to improve maintainability (target: <10)"
            )

        # Security recommendations
        security_issues = patterns.get("security_issues", 0)
        if security_issues > 0:
            recommendations.append(
                f"🔐 Found {security_issues} security issues - "
                "review and address security vulnerabilities"
            )

        # Dead code recommendations
        dead_code = patterns.get("dead_code_count", 0)
        if dead_code > 0:
            recommendations.append(
                f"🧹 Remove {dead_code} instances of dead code to reduce maintenance burden"
            )

        # Type checking recommendations
        type_errors = patterns.get("type_errors", 0)
        if type_errors > 0:
            recommendations.append(
                f"🏷️  Fix {type_errors} type checking errors to improve code reliability"
            )

        # Tool-specific recommendations
        for result in assessment_results:
            if result.tool == QualityTool.RUFF and result.violations:
                has_imports = any("F401" in v.rule_code for v in result.violations)
                if has_imports:
                    recommendations.append(
                        "📦 Run 'ruff --fix' to automatically remove unused imports"
                    )

        # If no specific issues found, provide general guidance
        if not recommendations:
            overall_score = self.calculate_quality_score(assessment_results)
            if overall_score < 8.0:
                recommendations.append(
                    "🎯 Focus on improving code consistency and adding comprehensive tests"
                )
            else:
                recommendations.append(
                    "✅ Code quality is good - maintain current standards and consider advanced optimizations"
                )

        return recommendations

    def detect_quality_patterns(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> Dict[str, Any]:
        """Detect quality patterns and anti-patterns in results."""

        patterns = {
            "total_violations": 0,
            "critical_violations": 0,
            "high_violations": 0,
            "medium_violations": 0,
            "low_violations": 0,
            "security_issues": 0,
            "dead_code_count": 0,
            "type_errors": 0,
            "coverage_percentage": 0.0,
            "average_complexity": 0.0,
            "maintainability_index": 0.0,
            "total_files": 0,
            "total_lines": 0,
            "violation_hotspots": {},
            "most_common_violations": {},
            "tool_failures": [],
            "auto_fixable_count": 0,
        }

        violation_files = {}
        violation_rules = {}
        coverage_values = []
        complexity_values = []
        maintainability_values = []

        for result in assessment_results:
            if result.status == ExecutionStatus.FAILURE:
                patterns["tool_failures"].append(result.tool.value)
                continue

            metrics = result.parsed_metrics
            patterns["total_violations"] += metrics.total_violations
            patterns["critical_violations"] += metrics.critical_violations
            patterns["high_violations"] += metrics.high_violations
            patterns["medium_violations"] += metrics.medium_violations
            patterns["low_violations"] += metrics.low_violations
            patterns["security_issues"] += metrics.security_issues_count
            patterns["dead_code_count"] += metrics.dead_code_count
            patterns["type_errors"] += metrics.type_errors
            patterns["total_files"] += result.files_analyzed
            patterns["total_lines"] += metrics.total_lines

            if metrics.test_coverage_percentage is not None:
                coverage_values.append(metrics.test_coverage_percentage)

            if metrics.average_complexity is not None:
                complexity_values.append(metrics.average_complexity)

            if metrics.maintainability_index is not None:
                maintainability_values.append(metrics.maintainability_index)

            # Track violations by file and rule
            for violation in result.violations:
                violation_files[violation.file_path] = (
                    violation_files.get(violation.file_path, 0) + 1
                )
                violation_rules[violation.rule_code] = (
                    violation_rules.get(violation.rule_code, 0) + 1
                )

                if violation.fixable:
                    patterns["auto_fixable_count"] += 1

        # Calculate averages
        if coverage_values:
            patterns["coverage_percentage"] = sum(coverage_values) / len(
                coverage_values
            )

        if complexity_values:
            patterns["average_complexity"] = sum(complexity_values) / len(
                complexity_values
            )

        if maintainability_values:
            patterns["maintainability_index"] = sum(maintainability_values) / len(
                maintainability_values
            )

        # Find hotspots (files with most violations)
        patterns["violation_hotspots"] = dict(
            sorted(violation_files.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        # Find most common violation types
        patterns["most_common_violations"] = dict(
            sorted(violation_rules.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        # Detect anti-patterns
        anti_patterns = []

        if patterns["critical_violations"] > 0:
            anti_patterns.append("critical_quality_issues")

        if patterns["coverage_percentage"] < 50:
            anti_patterns.append("insufficient_test_coverage")

        if patterns["average_complexity"] > 15:
            anti_patterns.append("excessive_complexity")

        if patterns["security_issues"] > 0:
            anti_patterns.append("security_vulnerabilities")

        if len(patterns["violation_hotspots"]) > 0:
            max_violations = max(patterns["violation_hotspots"].values())
            if max_violations > 20:
                anti_patterns.append("quality_hotspots")

        patterns["detected_anti_patterns"] = anti_patterns

        return patterns

    def prioritize_issues(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> List[Dict[str, Any]]:
        """Prioritize quality issues by impact and effort to fix."""

        issues = []

        for result in assessment_results:
            for violation in result.violations:
                # Calculate impact score (0-10)
                impact_score = self._calculate_impact_score(violation)

                # Calculate effort score (1-10, lower = easier to fix)
                effort_score = self._calculate_effort_score(violation)

                # Priority score (impact / effort ratio, higher = more priority)
                priority_score = impact_score / effort_score if effort_score > 0 else 0

                issues.append(
                    {
                        "type": "violation",
                        "tool": result.tool.value,
                        "rule_code": violation.rule_code,
                        "message": violation.message,
                        "severity": violation.severity.value,
                        "file_path": violation.file_path,
                        "line_number": violation.line_number,
                        "impact_score": impact_score,
                        "effort_score": effort_score,
                        "priority_score": priority_score,
                        "fixable": violation.fixable,
                        "fix_suggestion": violation.fix_suggestion,
                    }
                )

            # Add security issues
            for security_issue in result.security_issues:
                impact_score = self._calculate_security_impact_score(security_issue)
                effort_score = self._calculate_security_effort_score(security_issue)
                priority_score = impact_score / effort_score if effort_score > 0 else 0

                issues.append(
                    {
                        "type": "security",
                        "tool": result.tool.value,
                        "issue_id": security_issue.issue_id,
                        "title": security_issue.title,
                        "severity": security_issue.severity.value,
                        "confidence": security_issue.confidence,
                        "file_path": security_issue.file_path,
                        "line_number": security_issue.line_number,
                        "impact_score": impact_score,
                        "effort_score": effort_score,
                        "priority_score": priority_score,
                        "fixable": False,  # Security issues typically require manual review
                        "remediation": security_issue.remediation,
                    }
                )

        # Sort by priority score (descending)
        issues.sort(key=lambda x: x["priority_score"], reverse=True)

        return issues

    def _calculate_impact_score(self, violation: QualityViolation) -> float:
        """Calculate impact score for a violation (0-10)."""
        # Base score from severity
        base_score = self.severity_weights[violation.severity] * 0.8

        # Adjust based on rule patterns
        rule_adjustments = {
            "E9": 1.5,  # Syntax errors - critical
            "F4": 1.3,  # Import issues - moderate impact
            "F8": 1.2,  # Undefined variables - high impact
            "W6": 0.8,  # Warnings - lower impact
            "C9": 1.4,  # Complexity issues - high maintenance impact
        }

        for pattern, multiplier in rule_adjustments.items():
            if violation.rule_code.startswith(pattern):
                base_score *= multiplier
                break

        return min(10.0, base_score)

    def _calculate_effort_score(self, violation: QualityViolation) -> float:
        """Calculate effort score for a violation (1-10, lower = easier)."""
        # Base effort from fixability
        if violation.fixable:
            base_effort = 2.0  # Auto-fixable issues are easy
        else:
            base_effort = 5.0  # Manual fixes require more effort

        # Adjust based on violation type
        effort_adjustments = {
            "F401": 1.0,  # Unused imports - very easy
            "E501": 2.0,  # Line too long - easy
            "F811": 3.0,  # Redefined unused - medium
            "C901": 8.0,  # Complex function - hard refactoring
            "E9": 6.0,  # Syntax errors - medium to hard
        }

        for pattern, effort in effort_adjustments.items():
            if violation.rule_code.startswith(pattern):
                return effort

        return base_effort

    def _calculate_security_impact_score(self, security_issue: SecurityIssue) -> float:
        """Calculate impact score for security issues."""
        severity_scores = {
            ViolationSeverity.CRITICAL: 10.0,
            ViolationSeverity.HIGH: 8.0,
            ViolationSeverity.MEDIUM: 6.0,
            ViolationSeverity.LOW: 4.0,
            ViolationSeverity.INFO: 2.0,
        }

        base_score = severity_scores.get(security_issue.severity, 5.0)

        # Adjust based on confidence
        confidence_multipliers = {
            "high": 1.0,
            "medium": 0.8,
            "low": 0.6,
        }

        multiplier = confidence_multipliers.get(security_issue.confidence.lower(), 0.7)
        return base_score * multiplier

    def _calculate_security_effort_score(self, security_issue: SecurityIssue) -> float:
        """Calculate effort score for security issues."""
        # Security issues typically require careful analysis
        base_effort = 6.0

        # Some issues are easier to fix than others
        if "hardcoded" in security_issue.title.lower():
            return 4.0  # Often just need to move to config
        elif "sql" in security_issue.title.lower():
            return 7.0  # SQL injection fixes can be complex
        elif "weak" in security_issue.title.lower():
            return 3.0  # Weak crypto usually easy config change

        return base_effort

    # Tool-specific parsing methods

    def _parse_ruff_output(self, output: str) -> Dict[str, Any]:
        """Parse ruff linter output."""
        violations = []
        auto_fix_available = "--fix" in output or "fixed" in output.lower()

        # Try JSON format first
        if output.strip().startswith("[") or output.strip().startswith("{"):
            try:
                data = json.loads(output)
                if isinstance(data, list):
                    for item in data:
                        violations.append(
                            QualityViolation(
                                tool=QualityTool.RUFF,
                                rule_code=item.get("code", "UNKNOWN"),
                                message=item.get("message", ""),
                                severity=self._map_severity(
                                    item.get("severity", "error")
                                ),
                                file_path=item.get("filename", ""),
                                line_number=item.get("location", {}).get("row", 0),
                                column_number=item.get("location", {}).get("column", 0),
                                fixable=item.get("fix", {}).get("applicability")
                                == "automatic",
                            )
                        )
            except (json.JSONDecodeError, KeyError):
                # JSON parsing failed, fall through to text parsing
                pass

        # Text parsing (either because it's not JSON or JSON parsing failed)
        if not violations:  # Only parse text if we haven't found violations from JSON
            lines = output.split("\n")
            for line in lines:
                # Pattern: path.py:line:col: CODE message
                match = re.match(r"^([^:]+):(\d+):(\d+): (\w+) (.+)$", line.strip())
                if match:
                    file_path, line_num, col_num, code, message = match.groups()
                    violations.append(
                        QualityViolation(
                            tool=QualityTool.RUFF,
                            rule_code=code,
                            message=message,
                            severity=self._map_ruff_severity(code),
                            file_path=file_path,
                            line_number=int(line_num),
                            column_number=int(col_num),
                            fixable="F401" in code
                            or "I001" in code,  # Common auto-fixable codes
                        )
                    )

        return {
            "assessment_type": QualityAssessmentType.LINT,
            "violations": violations,
            "auto_fix_available": auto_fix_available,
            "fix_commands": ["ruff --fix ."] if auto_fix_available else [],
            "files_analyzed": len(set(v.file_path for v in violations))
            if violations
            else 0,
        }

    def _parse_mypy_output(self, output: str) -> Dict[str, Any]:
        """Parse mypy type checker output."""
        violations = []
        lines = output.split("\n")

        for line in lines:
            # Pattern: path.py:line: error: message
            match = re.match(
                r"^([^:]+):(\d+): (error|warning|note): (.+)$", line.strip()
            )
            if match:
                file_path, line_num, level, message = match.groups()

                severity = (
                    ViolationSeverity.HIGH
                    if level == "error"
                    else ViolationSeverity.MEDIUM
                )

                violations.append(
                    QualityViolation(
                        tool=QualityTool.MYPY,
                        rule_code="type-check",
                        message=message,
                        severity=severity,
                        file_path=file_path,
                        line_number=int(line_num),
                        fixable=False,  # Type errors typically require manual fixes
                    )
                )

        return {
            "assessment_type": QualityAssessmentType.TYPECHECK,
            "violations": violations,
            "files_analyzed": len(set(v.file_path for v in violations))
            if violations
            else 0,
        }

    def _parse_bandit_output(self, output: str) -> Dict[str, Any]:
        """Parse bandit security scanner output."""
        security_issues = []

        try:
            # Bandit typically outputs JSON
            data = json.loads(output)
            results = data.get("results", [])

            for result in results:
                security_issues.append(
                    SecurityIssue(
                        issue_id=result.get("test_id", "UNKNOWN"),
                        title=result.get("test_name", "Security Issue"),
                        description=result.get("issue_text", ""),
                        severity=self._map_bandit_severity(
                            result.get("issue_severity", "MEDIUM")
                        ),
                        confidence=result.get("issue_confidence", "MEDIUM").lower(),
                        file_path=result.get("filename", ""),
                        line_number=result.get("line_number", 0),
                        test_id=result.get("test_id", ""),
                        remediation=result.get("more_info", None),
                    )
                )

        except (json.JSONDecodeError, KeyError):
            # Fall back to basic parsing
            pass

        return {
            "assessment_type": QualityAssessmentType.SECURITY,
            "security_issues": security_issues,
            "files_analyzed": len(set(issue.file_path for issue in security_issues))
            if security_issues
            else 0,
        }

    def _parse_radon_output(self, output: str) -> Dict[str, Any]:
        """Parse radon complexity analyzer output."""
        complexity_results = []

        # Parse radon's cyclomatic complexity output
        lines = output.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # File header pattern
            if line.endswith(".py"):
                continue
            # Function complexity pattern: F line:col function_name - A (score)
            elif re.match(r"^[A-F]\s+\d+:\d+", line):
                parts = line.split()
                if len(parts) >= 4:
                    grade = parts[0]
                    func_name = parts[2]
                    score_part = parts[-1]

                    # Extract complexity score
                    score_match = re.search(r"\((\d+)\)", score_part)
                    if score_match:
                        complexity_score = int(score_match.group(1))

                        complexity_results.append(
                            ComplexityMetric(
                                name=func_name,
                                complexity_score=complexity_score,
                                maintainability_index=self._grade_to_maintainability(
                                    grade
                                ),
                                lines_of_code=0,  # Not available from this output
                                difficulty=0.0,  # Would need Halstead metrics
                                effort=0.0,  # Would need Halstead metrics
                                time_to_understand=complexity_score
                                * 2.5,  # Rough estimate
                            )
                        )

        return {
            "assessment_type": QualityAssessmentType.COMPLEXITY,
            "complexity_results": complexity_results,
            "files_analyzed": len(set(r.name.split(".")[0] for r in complexity_results))
            if complexity_results
            else 0,
        }

    def _parse_vulture_output(self, output: str) -> Dict[str, Any]:
        """Parse vulture dead code detector output."""
        dead_code_results = []

        lines = output.split("\n")
        for line in lines:
            # Pattern: path.py:line: unused function 'name' (confidence%)
            match = re.match(
                r"^([^:]+):(\d+): unused (\w+) \'([^\']+)\' \((\d+)% confidence\)",
                line.strip(),
            )
            if match:
                file_path, line_num, symbol_type, symbol_name, confidence = (
                    match.groups()
                )

                dead_code_results.append(
                    DeadCodeResult(
                        file_path=file_path,
                        line_number=int(line_num),
                        symbol_name=symbol_name,
                        symbol_type=symbol_type,
                        confidence=int(confidence),
                        used_outside_scope=int(confidence)
                        < 80,  # Lower confidence suggests possible external use
                    )
                )

        return {
            "assessment_type": QualityAssessmentType.DEAD_CODE,
            "dead_code_results": dead_code_results,
            "files_analyzed": len(set(result.file_path for result in dead_code_results))
            if dead_code_results
            else 0,
        }

    def _parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """Parse pytest test runner output."""
        # Extract test results from pytest output
        passed = len(re.findall(r"\bPASSED\b", output))
        failed = len(re.findall(r"\bFAILED\b", output))
        skipped = len(re.findall(r"\bSKIPPED\b", output))

        return {
            "assessment_type": QualityAssessmentType.COMPREHENSIVE,
            "test_passed": passed,
            "test_failed": failed,
            "test_skipped": skipped,
            "files_analyzed": 0,  # Will be updated by calling code
        }

    def _parse_coverage_output(self, output: str) -> Dict[str, Any]:
        """Parse coverage report output."""
        coverage_percentage = 0.0

        # Look for coverage percentage in output
        match = re.search(r"TOTAL.*?(\d+)%", output)
        if match:
            coverage_percentage = float(match.group(1))

        return {
            "assessment_type": QualityAssessmentType.COMPREHENSIVE,
            "coverage_percentage": coverage_percentage,
            "files_analyzed": 0,
        }

    def _parse_generic_output(self, output: str) -> Dict[str, Any]:
        """Generic parser for unknown tools."""
        return {
            "assessment_type": QualityAssessmentType.LINT,
            "files_analyzed": 0,
        }

    def _build_quality_metrics(self, parsed_data: Dict[str, Any]) -> QualityMetrics:
        """Build QualityMetrics from parsed tool data."""
        violations = parsed_data.get("violations", [])
        security_issues = parsed_data.get("security_issues", [])
        complexity_results = parsed_data.get("complexity_results", [])
        dead_code_results = parsed_data.get("dead_code_results", [])

        # Count violations by severity
        critical_count = sum(
            1 for v in violations if v.severity == ViolationSeverity.CRITICAL
        )
        high_count = sum(1 for v in violations if v.severity == ViolationSeverity.HIGH)
        medium_count = sum(
            1 for v in violations if v.severity == ViolationSeverity.MEDIUM
        )
        low_count = sum(1 for v in violations if v.severity == ViolationSeverity.LOW)

        # Calculate complexity metrics
        avg_complexity = 0.0
        max_complexity = 0
        avg_maintainability = 0.0

        if complexity_results:
            complexities = [r.complexity_score for r in complexity_results]
            avg_complexity = sum(complexities) / len(complexities)
            max_complexity = max(complexities)

            maintainabilities = [r.maintainability_index for r in complexity_results]
            avg_maintainability = sum(maintainabilities) / len(maintainabilities)

        return QualityMetrics(
            overall_score=0.0,  # Will be calculated separately
            total_violations=len(violations),
            critical_violations=critical_count,
            high_violations=high_count,
            medium_violations=medium_count,
            low_violations=low_count,
            test_coverage_percentage=parsed_data.get("coverage_percentage"),
            average_complexity=avg_complexity if avg_complexity > 0 else None,
            max_complexity=max_complexity if max_complexity > 0 else None,
            maintainability_index=avg_maintainability
            if avg_maintainability > 0
            else None,
            security_issues_count=len(security_issues),
            high_security_issues=sum(
                1
                for s in security_issues
                if s.severity in [ViolationSeverity.CRITICAL, ViolationSeverity.HIGH]
            ),
            dead_code_count=len(dead_code_results),
            type_errors=sum(1 for v in violations if v.tool == QualityTool.MYPY),
            total_lines=0,  # Will be calculated from file analysis
            code_lines=0,
            comment_lines=0,
            blank_lines=0,
        )

    def _map_severity(self, severity_str: str) -> ViolationSeverity:
        """Map string severity to enum."""
        severity_mapping = {
            "error": ViolationSeverity.HIGH,
            "warning": ViolationSeverity.MEDIUM,
            "info": ViolationSeverity.INFO,
            "note": ViolationSeverity.LOW,
        }
        return severity_mapping.get(severity_str.lower(), ViolationSeverity.MEDIUM)

    def _map_ruff_severity(self, rule_code: str) -> ViolationSeverity:
        """Map ruff rule codes to severity levels."""
        if rule_code.startswith("E9"):  # Syntax errors
            return ViolationSeverity.CRITICAL
        elif rule_code.startswith("F"):  # Pyflakes errors
            return ViolationSeverity.HIGH
        elif rule_code.startswith("E"):  # pycodestyle errors
            return ViolationSeverity.MEDIUM
        elif rule_code.startswith("W"):  # pycodestyle warnings
            return ViolationSeverity.LOW
        else:
            return ViolationSeverity.MEDIUM

    def _map_bandit_severity(self, severity_str: str) -> ViolationSeverity:
        """Map bandit severity to enum."""
        severity_mapping = {
            "HIGH": ViolationSeverity.HIGH,
            "MEDIUM": ViolationSeverity.MEDIUM,
            "LOW": ViolationSeverity.LOW,
        }
        return severity_mapping.get(severity_str.upper(), ViolationSeverity.MEDIUM)

    def _grade_to_maintainability(self, grade: str) -> float:
        """Convert complexity grade to maintainability index."""
        grade_mapping = {
            "A": 90.0,  # Very maintainable
            "B": 75.0,  # Good maintainability
            "C": 60.0,  # Fair maintainability
            "D": 45.0,  # Poor maintainability
            "E": 30.0,  # Very poor maintainability
            "F": 15.0,  # Extremely poor maintainability
        }
        return grade_mapping.get(grade.upper(), 50.0)
