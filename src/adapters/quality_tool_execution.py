"""
Quality tool execution adapter for pixi-mediated quality assessments.

This adapter implements QualityToolExecutionPort to execute quality assessment tools
(ruff, mypy, bandit, radon, vulture) via pixi with intelligent output parsing and
comprehensive error handling.
"""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models import (
    QualityTool,
    QualityAssessmentType,
    QualityAssessmentResult,
    QualityMetrics,
    QualityViolation,
    SecurityIssue,
    ComplexityMetric,
    DeadCodeResult,
    ExecutionStatus,
    ViolationSeverity,
)
from core.ports import QualityToolExecutionPort


class QualityToolExecutionAdapter(QualityToolExecutionPort):
    """
    Adapter for executing quality assessment tools via pixi.
    
    Provides secure, pixi-mediated execution of quality tools with intelligent
    parsing of tool outputs into structured QualityAssessmentResult objects.
    """

    def __init__(self, direct_pixi_executor):
        """
        Initialize the adapter with direct pixi execution capability.
        
        Args:
            direct_pixi_executor: DirectPixiExecutionAdapter instance for pixi operations
        """
        self.pixi_executor = direct_pixi_executor

    def execute_lint_assessment(
        self,
        tool: QualityTool,
        target_path: str = "src/",
        rules: Optional[List[str]] = None,
        fix_mode: bool = False,
        output_format: str = "json",
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None
    ) -> QualityAssessmentResult:
        """
        Execute linting tools via pixi with intelligent result parsing.

        Supports ruff, pylint, and flake8 with JSON output parsing when possible.

        Args:
            tool: Linting tool to use
            target_path: Path to analyze (default: "src/")
            rules: Specific rules to apply
            fix_mode: Whether to apply auto-fixes
            output_format: Output format preference
            use_cache: Whether to use cached results (currently unused, for API compatibility)
            project_path: Absolute path to the project root to analyze (default: server working directory)
            environment: Pixi environment to run the task in (omit unless ambiguous)
        """
        start_time = datetime.now(UTC).isoformat()
        execution_start = time.time()
        
        try:
            # Map tool to pixi task
            task_mapping = {
                QualityTool.RUFF: "lint",
                QualityTool.PYLINT: "pylint", 
                QualityTool.FLAKE8: "flake8"
            }
            
            pixi_task = task_mapping.get(tool)
            if not pixi_task:
                raise ValueError(f"Unsupported lint tool: {tool}")

            # Validate task exists
            task_check = self.pixi_executor.task_exists(pixi_task, working_dir=project_path)
            if not task_check.get("exists", False):
                return self._create_error_result(
                    tool=tool,
                    assessment_type=QualityAssessmentType.LINT,
                    start_time=start_time,
                    execution_time_ms=(time.time() - execution_start) * 1000,
                    error_msg=f"Pixi task '{pixi_task}' not found",
                    target_path=target_path,
                    pixi_task_used=pixi_task
                )

            # Build task arguments
            args = []
            if target_path != "src/":
                args.append(target_path)
            if rules:
                # Add rule-specific arguments based on tool
                if tool == QualityTool.RUFF:
                    for rule in rules:
                        args.extend(["--select", rule])
                elif tool == QualityTool.PYLINT:
                    args.extend(["--enable", ",".join(rules)])
                elif tool == QualityTool.FLAKE8:
                    args.extend(["--select", ",".join(rules)])
            
            if output_format == "json" and tool == QualityTool.RUFF:
                args.append("--output-format=json")

            # Execute pixi task
            result = self.pixi_executor.run_task(pixi_task, args=args, timeout=300, working_dir=project_path, environment=environment)
            execution_time_ms = (time.time() - execution_start) * 1000
            end_time = datetime.now(UTC).isoformat()

            # Parse results based on tool and output format
            violations = []
            metrics = QualityMetrics(
                overall_score=10.0,
                total_violations=0,
                critical_violations=0,
                high_violations=0,
                medium_violations=0,
                low_violations=0,
                total_lines=0,
                code_lines=0,
                comment_lines=0,
                blank_lines=0
            )

            if result.get("success", False):
                stdout = result.get("stdout", "")
                violations, metrics = self._parse_lint_output(tool, stdout, target_path)
                status = ExecutionStatus.SUCCESS if not violations else ExecutionStatus.WARNING
            else:
                if not self._is_execution_failure(result):
                    # Tool ran and exited non-zero because it found violations.
                    stdout = result.get("stdout", "")
                    violations, metrics = self._parse_lint_output(tool, stdout, target_path)

                if not violations:
                    # Non-zero exit unexplained by any parsed finding: the analysis
                    # did not happen. Never report a score for an unmeasured target.
                    return self._create_error_result(
                        tool=tool,
                        assessment_type=QualityAssessmentType.LINT,
                        start_time=start_time,
                        execution_time_ms=execution_time_ms,
                        error_msg=self._describe_execution_failure(result, pixi_task),
                        target_path=target_path,
                        pixi_task_used=pixi_task
                    )

                status = ExecutionStatus.WARNING

            return QualityAssessmentResult(
                assessment_type=QualityAssessmentType.LINT,
                tool=tool,
                status=status,
                start_time=start_time,
                end_time=end_time,
                execution_time_ms=execution_time_ms,
                pixi_task_used=pixi_task,
                target_path=target_path,
                files_analyzed=metrics.total_lines // 50 if metrics.total_lines > 0 else 1,  # Estimate
                raw_output=result.get("stdout", "") + "\n" + result.get("stderr", ""),
                parsed_metrics=metrics,
                violations=violations,
                recommendations=self._generate_lint_recommendations(violations, tool),
                auto_fix_available=fix_mode and tool == QualityTool.RUFF,
                fix_commands=["pixi run lint --fix"] if fix_mode and tool == QualityTool.RUFF else []
            )

        except Exception as e:
            execution_time_ms = (time.time() - execution_start) * 1000
            return self._create_error_result(
                tool=tool,
                assessment_type=QualityAssessmentType.LINT,
                start_time=start_time,
                execution_time_ms=execution_time_ms,
                error_msg=str(e),
                target_path=target_path,
                pixi_task_used=pixi_task if 'pixi_task' in locals() else "unknown"
            )

    def execute_typecheck_assessment(
        self,
        tool: QualityTool = QualityTool.MYPY,
        target_path: str = "src/",
        strict_mode: bool = False,
        config_file: Optional[str] = None,
        incremental: bool = True,
        cache_dir: Optional[str] = None,
        project_path: Optional[str] = None,
        environment: Optional[str] = None
    ) -> QualityAssessmentResult:
        """
        Execute type checking tools via pixi with comprehensive analysis.

        Currently supports mypy with JSON output parsing.

        Args:
            tool: Type checking tool to use
            target_path: Path to analyze (default: "src/")
            strict_mode: Enable strict type checking mode
            config_file: Custom configuration file path
            incremental: Enable incremental checking
            cache_dir: Custom cache directory
            project_path: Absolute path to the project root to analyze (default: server working directory)
            environment: Pixi environment to run the task in (omit unless ambiguous)
        """
        start_time = datetime.now(UTC).isoformat()
        execution_start = time.time()

        try:
            pixi_task = "typecheck"

            # Validate task exists
            task_check = self.pixi_executor.task_exists(pixi_task, working_dir=project_path)
            if not task_check.get("exists", False):
                return self._create_error_result(
                    tool=tool,
                    assessment_type=QualityAssessmentType.TYPECHECK,
                    start_time=start_time,
                    execution_time_ms=(time.time() - execution_start) * 1000,
                    error_msg=f"Pixi task '{pixi_task}' not found",
                    target_path=target_path,
                    pixi_task_used=pixi_task
                )

            # Build arguments for mypy
            args = []
            if strict_mode:
                args.append("--strict")
            if not incremental:
                args.append("--no-incremental")
            if cache_dir:
                args.extend(["--cache-dir", cache_dir])
            
            # Add JSON output for parsing
            args.extend(["--show-error-codes", "--show-column-numbers"])

            # Execute pixi task
            result = self.pixi_executor.run_task(pixi_task, args=args, timeout=300, working_dir=project_path, environment=environment)
            execution_time_ms = (time.time() - execution_start) * 1000
            end_time = datetime.now(UTC).isoformat()

            # Parse mypy output
            violations = []
            type_errors = 0
            
            if result.get("success", False):
                stdout = result.get("stdout", "")
                violations, type_errors = self._parse_mypy_output(stdout, target_path)
                status = ExecutionStatus.SUCCESS if type_errors == 0 else ExecutionStatus.WARNING
            else:
                if not self._is_execution_failure(result):
                    # mypy exits non-zero when it finds type errors; parse both streams.
                    combined = result.get("stdout", "") + "\n" + result.get("stderr", "")
                    violations, type_errors = self._parse_mypy_output(combined, target_path)

                if not violations:
                    return self._create_error_result(
                        tool=tool,
                        assessment_type=QualityAssessmentType.TYPECHECK,
                        start_time=start_time,
                        execution_time_ms=execution_time_ms,
                        error_msg=self._describe_execution_failure(result, pixi_task),
                        target_path=target_path,
                        pixi_task_used=pixi_task
                    )

                status = ExecutionStatus.WARNING

            metrics = QualityMetrics(
                overall_score=max(0.0, 10.0 - (type_errors * 0.5)),
                total_violations=len(violations),
                critical_violations=sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL),
                high_violations=sum(1 for v in violations if v.severity == ViolationSeverity.HIGH),
                medium_violations=sum(1 for v in violations if v.severity == ViolationSeverity.MEDIUM),
                low_violations=sum(1 for v in violations if v.severity == ViolationSeverity.LOW),
                type_errors=type_errors,
                total_lines=0,  # Will be updated by line counting if needed
                code_lines=0,
                comment_lines=0,
                blank_lines=0
            )

            return QualityAssessmentResult(
                assessment_type=QualityAssessmentType.TYPECHECK,
                tool=tool,
                status=status,
                start_time=start_time,
                end_time=end_time,
                execution_time_ms=execution_time_ms,
                pixi_task_used=pixi_task,
                target_path=target_path,
                files_analyzed=len(set(v.file_path for v in violations)) if violations else 1,
                raw_output=result.get("stdout", "") + "\n" + result.get("stderr", ""),
                parsed_metrics=metrics,
                violations=violations,
                recommendations=self._generate_typecheck_recommendations(violations, type_errors),
                auto_fix_available=False,  # mypy doesn't support auto-fixing
                fix_commands=[]
            )

        except Exception as e:
            execution_time_ms = (time.time() - execution_start) * 1000
            return self._create_error_result(
                tool=tool,
                assessment_type=QualityAssessmentType.TYPECHECK,
                start_time=start_time,
                execution_time_ms=execution_time_ms,
                error_msg=str(e),
                target_path="src/",
                pixi_task_used=pixi_task if 'pixi_task' in locals() else "typecheck"
            )

    def execute_security_scan(
        self,
        tool: QualityTool = QualityTool.BANDIT,
        target_path: str = "src/",
        severity_threshold: str = "medium",
        exclude_tests: bool = True,
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None
    ) -> QualityAssessmentResult:
        """
        Execute security vulnerability scanning via pixi.

        Currently supports bandit with JSON output parsing.

        Args:
            tool: Security scanning tool to use
            target_path: Path to analyze (default: "src/")
            severity_threshold: Minimum severity to report ("low", "medium", "high")
            exclude_tests: Whether to exclude test files
            use_cache: Whether to use cached results (currently unused, for API compatibility)
            project_path: Absolute path to the project root to analyze (default: server working directory)
            environment: Pixi environment to run the task in (omit unless ambiguous)
        """
        start_time = datetime.now(UTC).isoformat()
        execution_start = time.time()

        try:
            pixi_task = "security"

            # Validate task exists
            task_check = self.pixi_executor.task_exists(pixi_task, working_dir=project_path)
            if not task_check.get("exists", False):
                return self._create_error_result(
                    tool=tool,
                    assessment_type=QualityAssessmentType.SECURITY,
                    start_time=start_time,
                    execution_time_ms=(time.time() - execution_start) * 1000,
                    error_msg=f"Pixi task '{pixi_task}' not found",
                    target_path=target_path,
                    pixi_task_used=pixi_task
                )

            # Build arguments for bandit
            args = ["-f", "json"]  # Always use JSON for parsing

            # Map severity threshold to bandit's severity levels
            severity_map = {"low": "all", "medium": "medium", "high": "high"}
            bandit_severity = severity_map.get(severity_threshold, "medium")
            if bandit_severity != "all":
                args.extend(["-ll" if bandit_severity == "high" else "-l"])

            # Exclude test files if requested
            if exclude_tests:
                args.extend(["--exclude", "tests,test,*_test.py,test_*.py"])

            # Add recursive scan on target path
            args.extend(["-r", target_path])

            # Execute pixi task
            result = self.pixi_executor.run_task(pixi_task, args=args, timeout=300, working_dir=project_path, environment=environment)
            execution_time_ms = (time.time() - execution_start) * 1000
            end_time = datetime.now(UTC).isoformat()

            # Parse bandit output
            security_issues = []
            violations = []
            
            stdout = result.get("stdout", "")
            if stdout:
                # Try JSON parsing first (default), fallback to text
                try:
                    security_issues, violations = self._parse_bandit_json_output(stdout, target_path)
                except (json.JSONDecodeError, KeyError):
                    security_issues, violations = self._parse_bandit_text_output(stdout, target_path)
            else:
                security_issues, violations = [], []

            # Determine status
            high_severity_issues = sum(1 for issue in security_issues if issue.severity in [ViolationSeverity.CRITICAL, ViolationSeverity.HIGH])
            if result.get("success", False):
                status = ExecutionStatus.SUCCESS if high_severity_issues == 0 else ExecutionStatus.WARNING
            else:
                status = ExecutionStatus.FAILURE

            metrics = QualityMetrics(
                overall_score=max(0.0, 10.0 - (high_severity_issues * 2.0) - (len(security_issues) * 0.5)),
                total_violations=len(violations),
                critical_violations=sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL),
                high_violations=sum(1 for v in violations if v.severity == ViolationSeverity.HIGH),
                medium_violations=sum(1 for v in violations if v.severity == ViolationSeverity.MEDIUM),
                low_violations=sum(1 for v in violations if v.severity == ViolationSeverity.LOW),
                security_issues_count=len(security_issues),
                high_security_issues=high_severity_issues,
                total_lines=0,
                code_lines=0,
                comment_lines=0,
                blank_lines=0
            )

            return QualityAssessmentResult(
                assessment_type=QualityAssessmentType.SECURITY,
                tool=tool,
                status=status,
                start_time=start_time,
                end_time=end_time,
                execution_time_ms=execution_time_ms,
                pixi_task_used=pixi_task,
                target_path=target_path,
                files_analyzed=len(set(issue.file_path for issue in security_issues)) if security_issues else 1,
                raw_output=result.get("stdout", ""),
                parsed_metrics=metrics,
                violations=violations,
                security_issues=security_issues,
                recommendations=self._generate_security_recommendations(security_issues),
                auto_fix_available=False,  # Security fixes should be manual
                fix_commands=[]
            )

        except Exception as e:
            execution_time_ms = (time.time() - execution_start) * 1000
            return self._create_error_result(
                tool=tool,
                assessment_type=QualityAssessmentType.SECURITY,
                start_time=start_time,
                execution_time_ms=execution_time_ms,
                error_msg=str(e),
                target_path="src/",
                pixi_task_used=pixi_task if 'pixi_task' in locals() else "security"
            )

    def execute_complexity_analysis(
        self,
        tool: QualityTool = QualityTool.RADON,
        target_path: str = "src/",
        complexity_threshold: int = 10,
        include_metrics: Optional[List[str]] = None,
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None
    ) -> QualityAssessmentResult:
        """
        Analyze code complexity metrics via pixi.

        Currently supports radon for cyclomatic complexity and maintainability index.

        Args:
            tool: Complexity analysis tool to use
            target_path: Path to analyze (default: "src/")
            complexity_threshold: Complexity threshold for warnings
            include_metrics: Specific metrics to include (cc, mi, hal, raw)
            use_cache: Whether to use cached results (currently unused, for API compatibility)
            project_path: Absolute path to the project root to analyze (default: server working directory)
            environment: Pixi environment to run the task in (omit unless ambiguous)
        """
        start_time = datetime.now(UTC).isoformat()
        execution_start = time.time()

        try:
            pixi_task = "complexity"

            # Validate task exists
            task_check = self.pixi_executor.task_exists(pixi_task, working_dir=project_path)
            if not task_check.get("exists", False):
                return self._create_error_result(
                    tool=tool,
                    assessment_type=QualityAssessmentType.COMPLEXITY,
                    start_time=start_time,
                    execution_time_ms=(time.time() - execution_start) * 1000,
                    error_msg=f"Pixi task '{pixi_task}' not found",
                    target_path=target_path,
                    pixi_task_used=pixi_task
                )

            # Build arguments for radon
            args = ["cc", "src/", "--json"]  # Cyclomatic complexity with JSON output
            if complexity_threshold != 10:
                args.extend(["--min", str(complexity_threshold)])

            # Execute pixi task
            result = self.pixi_executor.run_task(pixi_task, args=args, timeout=300, working_dir=project_path, environment=environment)
            execution_time_ms = (time.time() - execution_start) * 1000
            end_time = datetime.now(UTC).isoformat()

            # Parse radon output
            complexity_results = []
            violations = []
            
            stdout = result.get("stdout", "")
            if stdout:
                complexity_results, violations = self._parse_radon_output(stdout, complexity_threshold)

            # If maintainability is requested, run second command
            if include_maintainability:
                mi_args = ["mi", "src/", "--json"]
                mi_result = self.pixi_executor.run_task(pixi_task, args=mi_args, timeout=300, working_dir=project_path, environment=environment)
                if mi_result.get("success", False):
                    mi_stdout = mi_result.get("stdout", "")
                    self._update_complexity_with_maintainability(complexity_results, mi_stdout)

            # Calculate metrics
            avg_complexity = sum(cr.complexity_score for cr in complexity_results) / len(complexity_results) if complexity_results else 0
            max_complexity = max((cr.complexity_score for cr in complexity_results), default=0)
            avg_maintainability = sum(cr.maintainability_index for cr in complexity_results) / len(complexity_results) if complexity_results else 100

            status = ExecutionStatus.SUCCESS if result.get("success", False) else ExecutionStatus.FAILURE
            if avg_complexity > complexity_threshold:
                status = ExecutionStatus.WARNING

            metrics = QualityMetrics(
                overall_score=max(0.0, 10.0 - (avg_complexity - 5) * 0.5),
                total_violations=len(violations),
                critical_violations=sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL),
                high_violations=sum(1 for v in violations if v.severity == ViolationSeverity.HIGH),
                medium_violations=sum(1 for v in violations if v.severity == ViolationSeverity.MEDIUM),
                low_violations=sum(1 for v in violations if v.severity == ViolationSeverity.LOW),
                average_complexity=avg_complexity,
                max_complexity=max_complexity,
                maintainability_index=avg_maintainability,
                total_lines=sum(cr.lines_of_code for cr in complexity_results),
                code_lines=sum(cr.lines_of_code for cr in complexity_results),
                comment_lines=0,
                blank_lines=0
            )

            return QualityAssessmentResult(
                assessment_type=QualityAssessmentType.COMPLEXITY,
                tool=tool,
                status=status,
                start_time=start_time,
                end_time=end_time,
                execution_time_ms=execution_time_ms,
                pixi_task_used=pixi_task,
                target_path=target_path,
                files_analyzed=len(set(cr.name.split('.')[0] for cr in complexity_results)) if complexity_results else 1,
                raw_output=result.get("stdout", ""),
                parsed_metrics=metrics,
                violations=violations,
                complexity_results=complexity_results,
                recommendations=self._generate_complexity_recommendations(complexity_results, avg_complexity, complexity_threshold),
                auto_fix_available=False,  # Complexity requires manual refactoring
                fix_commands=[]
            )

        except Exception as e:
            execution_time_ms = (time.time() - execution_start) * 1000
            return self._create_error_result(
                tool=tool,
                assessment_type=QualityAssessmentType.COMPLEXITY,
                start_time=start_time,
                execution_time_ms=execution_time_ms,
                error_msg=str(e),
                target_path="src/",
                pixi_task_used=pixi_task if 'pixi_task' in locals() else "complexity"
            )

    def execute_dead_code_detection(
        self,
        tool: QualityTool = QualityTool.VULTURE,
        aggressive_mode: bool = False,
        exclude_patterns: Optional[List[str]] = None,
        confidence_threshold: int = 80
    ) -> QualityAssessmentResult:
        """
        Identify unused code via pixi execution.
        
        Currently supports vulture for dead code detection.
        """
        start_time = datetime.now(UTC).isoformat()
        execution_start = time.time()
        
        try:
            pixi_task = "dead-code"
            target_path = "src/"

            # Validate task exists
            task_check = self.pixi_executor.task_exists(pixi_task)
            if not task_check.get("exists", False):
                return self._create_error_result(
                    tool=tool,
                    assessment_type=QualityAssessmentType.DEAD_CODE,
                    start_time=start_time,
                    execution_time_ms=(time.time() - execution_start) * 1000,
                    error_msg=f"Pixi task '{pixi_task}' not found",
                    target_path=target_path,
                    pixi_task_used=pixi_task
                )

            # Build arguments for vulture
            args = ["src/"]
            if aggressive_mode:
                args.append("--min-confidence=0")
            else:
                args.append(f"--min-confidence={confidence_threshold}")
            
            if exclude_patterns:
                for pattern in exclude_patterns:
                    args.extend(["--exclude", pattern])

            # Execute pixi task
            result = self.pixi_executor.run_task(pixi_task, args=args, timeout=300)
            execution_time_ms = (time.time() - execution_start) * 1000
            end_time = datetime.now(UTC).isoformat()

            # Parse vulture output
            dead_code_results = []
            violations = []
            
            stdout = result.get("stdout", "")
            if stdout:
                dead_code_results, violations = self._parse_vulture_output(stdout, confidence_threshold)

            # Calculate metrics
            unused_imports = sum(1 for dcr in dead_code_results if "import" in dcr.symbol_type.lower())
            total_dead_code = len(dead_code_results)

            status = ExecutionStatus.SUCCESS if result.get("success", False) else ExecutionStatus.FAILURE
            if total_dead_code > 0:
                status = ExecutionStatus.WARNING

            metrics = QualityMetrics(
                overall_score=max(0.0, 10.0 - (total_dead_code * 0.1)),
                total_violations=len(violations),
                critical_violations=sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL),
                high_violations=sum(1 for v in violations if v.severity == ViolationSeverity.HIGH),
                medium_violations=sum(1 for v in violations if v.severity == ViolationSeverity.MEDIUM),
                low_violations=sum(1 for v in violations if v.severity == ViolationSeverity.LOW),
                dead_code_count=total_dead_code,
                unused_imports=unused_imports,
                total_lines=0,  # Not directly available from vulture
                code_lines=0,
                comment_lines=0,
                blank_lines=0
            )

            return QualityAssessmentResult(
                assessment_type=QualityAssessmentType.DEAD_CODE,
                tool=tool,
                status=status,
                start_time=start_time,
                end_time=end_time,
                execution_time_ms=execution_time_ms,
                pixi_task_used=pixi_task,
                target_path=target_path,
                files_analyzed=len(set(dcr.file_path for dcr in dead_code_results)) if dead_code_results else 1,
                raw_output=result.get("stdout", ""),
                parsed_metrics=metrics,
                violations=violations,
                dead_code_results=dead_code_results,
                recommendations=self._generate_dead_code_recommendations(dead_code_results, unused_imports),
                auto_fix_available=unused_imports > 0,  # Can auto-remove unused imports
                fix_commands=["pixi run lint --fix"] if unused_imports > 0 else []
            )

        except Exception as e:
            execution_time_ms = (time.time() - execution_start) * 1000
            return self._create_error_result(
                tool=tool,
                assessment_type=QualityAssessmentType.DEAD_CODE,
                start_time=start_time,
                execution_time_ms=execution_time_ms,
                error_msg=str(e),
                target_path="src/",
                pixi_task_used=pixi_task if 'pixi_task' in locals() else "dead-code"
            )

    # Private parsing methods for each tool type

    def _parse_lint_output(self, tool: QualityTool, stdout: str, target_path: str) -> tuple[List[QualityViolation], QualityMetrics]:
        """Parse linting tool output into violations and metrics."""
        violations = []
        total_violations = 0
        critical_violations = 0
        high_violations = 0
        medium_violations = 0
        low_violations = 0

        if tool == QualityTool.RUFF and stdout:
            try:
                # Try to parse JSON output
                if stdout.strip().startswith('[') or stdout.strip().startswith('{'):
                    json_data = json.loads(stdout)
                    if isinstance(json_data, list):
                        for item in json_data:
                            violation = self._parse_ruff_json_item(item)
                            if violation:
                                violations.append(violation)
                                severity = violation.severity
                                if severity == ViolationSeverity.CRITICAL:
                                    critical_violations += 1
                                elif severity == ViolationSeverity.HIGH:
                                    high_violations += 1
                                elif severity == ViolationSeverity.MEDIUM:
                                    medium_violations += 1
                                else:
                                    low_violations += 1
                else:
                    # Parse text output
                    violations = self._parse_ruff_text_output(stdout)
                    total_violations = len(violations)
                    # Classify by severity for text parsing
                    for v in violations:
                        if v.severity == ViolationSeverity.CRITICAL:
                            critical_violations += 1
                        elif v.severity == ViolationSeverity.HIGH:
                            high_violations += 1
                        elif v.severity == ViolationSeverity.MEDIUM:
                            medium_violations += 1
                        else:
                            low_violations += 1
            except json.JSONDecodeError:
                # Fallback to text parsing
                violations = self._parse_ruff_text_output(stdout)
                total_violations = len(violations)

        total_violations = len(violations)
        overall_score = max(0.0, 10.0 - (critical_violations * 3) - (high_violations * 2) - (medium_violations * 1) - (low_violations * 0.5))

        metrics = QualityMetrics(
            overall_score=overall_score,
            total_violations=total_violations,
            critical_violations=critical_violations,
            high_violations=high_violations,
            medium_violations=medium_violations,
            low_violations=low_violations,
            total_lines=0,  # Would need separate line counting
            code_lines=0,
            comment_lines=0,
            blank_lines=0
        )

        return violations, metrics

    def _parse_ruff_json_item(self, item: Dict[str, Any]) -> Optional[QualityViolation]:
        """Parse a single ruff JSON item into a QualityViolation."""
        try:
            # Map ruff rule codes to severity
            code = item.get("code", "")
            severity = self._map_ruff_severity(code)
            
            return QualityViolation(
                tool=QualityTool.RUFF,
                rule_code=code,
                message=item.get("message", ""),
                severity=severity,
                file_path=item.get("filename", ""),
                line_number=item.get("location", {}).get("row", 0),
                column_number=item.get("location", {}).get("column", None),
                fix_suggestion=item.get("fix", {}).get("message") if item.get("fix") else None,
                fixable=bool(item.get("fix"))
            )
        except Exception:
            return None

    def _parse_ruff_text_output(self, stdout: str) -> List[QualityViolation]:
        """Parse ruff text output into violations."""
        violations = []
        lines = stdout.strip().split('\n')
        
        for line in lines:
            # Ruff text format: path:line:column: code message
            match = re.match(r'^(.+):(\d+):(\d+):\s+(\w+)\s+(.+)$', line)
            if match:
                file_path, line_num, col_num, code, message = match.groups()
                severity = self._map_ruff_severity(code)
                
                violation = QualityViolation(
                    tool=QualityTool.RUFF,
                    rule_code=code,
                    message=message,
                    severity=severity,
                    file_path=file_path,
                    line_number=int(line_num),
                    column_number=int(col_num),
                    fixable=False  # Can't determine from text output
                )
                violations.append(violation)
        
        return violations

    def _map_ruff_severity(self, code: str) -> ViolationSeverity:
        """Map ruff rule codes to severity levels."""
        if code.startswith('E9') or code.startswith('F'):
            return ViolationSeverity.CRITICAL
        elif code.startswith('E') or code.startswith('W'):
            return ViolationSeverity.MEDIUM
        elif code.startswith('C') or code.startswith('N'):
            return ViolationSeverity.LOW
        else:
            return ViolationSeverity.INFO

    def _parse_mypy_output(self, output: str, target_path: str) -> tuple[List[QualityViolation], int]:
        """Parse mypy output into violations and error count."""
        violations = []
        error_count = 0
        
        lines = output.strip().split('\n')
        
        for line in lines:
            # mypy format: path:line: severity: message [code]
            match = re.match(r'^(.+):(\d+):(?:(\d+):)?\s+(error|warning|note):\s+(.+?)(?:\s+\[(.+)\])?$', line)
            if match:
                file_path, line_num, col_num, severity_str, message, error_code = match.groups()
                
                # Map mypy severity to our enum
                if severity_str == "error":
                    severity = ViolationSeverity.HIGH
                    error_count += 1
                elif severity_str == "warning":
                    severity = ViolationSeverity.MEDIUM
                else:
                    severity = ViolationSeverity.INFO
                
                violation = QualityViolation(
                    tool=QualityTool.MYPY,
                    rule_code=error_code or "mypy",
                    message=message,
                    severity=severity,
                    file_path=file_path,
                    line_number=int(line_num),
                    column_number=int(col_num) if col_num else None,
                    fixable=False  # mypy doesn't provide auto-fixes
                )
                violations.append(violation)
        
        return violations, error_count

    def _parse_bandit_json_output(self, stdout: str, target_path: str) -> tuple[List[SecurityIssue], List[QualityViolation]]:
        """Parse bandit JSON output into security issues and violations."""
        security_issues = []
        violations = []
        
        try:
            data = json.loads(stdout)
            results = data.get("results", [])
            
            for result in results:
                # Create SecurityIssue
                severity = self._map_bandit_severity(result.get("issue_severity", "LOW"))
                
                security_issue = SecurityIssue(
                    issue_id=result.get("test_id", ""),
                    title=result.get("test_name", ""),
                    description=result.get("issue_text", ""),
                    severity=severity,
                    confidence=result.get("issue_confidence", "MEDIUM").lower(),
                    file_path=result.get("filename", ""),
                    line_number=result.get("line_number", 0),
                    test_id=result.get("test_id", ""),
                    cwe_id=result.get("cwe", {}).get("id") if result.get("cwe") else None,
                    remediation=result.get("more_info", "")
                )
                security_issues.append(security_issue)
                
                # Also create QualityViolation for consistency
                violation = QualityViolation(
                    tool=QualityTool.BANDIT,
                    rule_code=result.get("test_id", ""),
                    message=result.get("issue_text", ""),
                    severity=severity,
                    file_path=result.get("filename", ""),
                    line_number=result.get("line_number", 0),
                    fixable=False  # Security fixes should be manual
                )
                violations.append(violation)
                
        except json.JSONDecodeError:
            # Fallback to text parsing
            return self._parse_bandit_text_output(stdout, target_path)
        
        return security_issues, violations

    def _parse_bandit_text_output(self, stdout: str, target_path: str) -> tuple[List[SecurityIssue], List[QualityViolation]]:
        """Parse bandit text output as fallback."""
        security_issues = []
        violations = []
        
        # Simple text parsing - this would need refinement for production
        lines = stdout.strip().split('\n')
        
        current_issue = {}
        for line in lines:
            if line.strip().startswith('>> Issue:'):
                if current_issue:
                    # Process previous issue
                    issue, violation = self._create_bandit_issue_from_text(current_issue)
                    if issue:
                        security_issues.append(issue)
                        violations.append(violation)
                
                current_issue = {"description": line.replace('>> Issue:', '').strip()}
            elif line.strip().startswith('   Severity:'):
                current_issue["severity"] = line.replace('   Severity:', '').strip()
            elif line.strip().startswith('   Location:'):
                current_issue["location"] = line.replace('   Location:', '').strip()
        
        # Process last issue
        if current_issue:
            issue, violation = self._create_bandit_issue_from_text(current_issue)
            if issue:
                security_issues.append(issue)
                violations.append(violation)
        
        return security_issues, violations

    def _create_bandit_issue_from_text(self, issue_data: Dict[str, str]) -> tuple[Optional[SecurityIssue], Optional[QualityViolation]]:
        """Create SecurityIssue and QualityViolation from parsed text data."""
        try:
            severity = self._map_bandit_severity(issue_data.get("severity", "LOW"))
            location = issue_data.get("location", "")
            
            # Parse location format: filename:line_number
            file_path = ""
            line_number = 0
            if ":" in location:
                parts = location.rsplit(":", 1)
                file_path = parts[0]
                try:
                    line_number = int(parts[1])
                except ValueError:
                    line_number = 0
            
            security_issue = SecurityIssue(
                issue_id="bandit-text-parsed",
                title="Security Issue",
                description=issue_data.get("description", ""),
                severity=severity,
                confidence="medium",
                file_path=file_path,
                line_number=line_number,
                test_id="bandit"
            )
            
            violation = QualityViolation(
                tool=QualityTool.BANDIT,
                rule_code="bandit",
                message=issue_data.get("description", ""),
                severity=severity,
                file_path=file_path,
                line_number=line_number,
                fixable=False
            )
            
            return security_issue, violation
            
        except Exception:
            return None, None

    def _map_bandit_severity(self, severity: str) -> ViolationSeverity:
        """Map bandit severity levels to our enum."""
        severity_map = {
            "HIGH": ViolationSeverity.HIGH,
            "MEDIUM": ViolationSeverity.MEDIUM,
            "LOW": ViolationSeverity.LOW
        }
        return severity_map.get(severity.upper(), ViolationSeverity.LOW)

    def _parse_radon_output(self, stdout: str, complexity_threshold: int) -> tuple[List[ComplexityMetric], List[QualityViolation]]:
        """Parse radon cyclomatic complexity output."""
        complexity_results = []
        violations = []
        
        try:
            # Parse JSON output
            data = json.loads(stdout)
            
            for file_path, functions in data.items():
                for func_data in functions:
                    complexity_score = func_data.get("complexity", 0)
                    
                    complexity_metric = ComplexityMetric(
                        name=f"{file_path}:{func_data.get('name', 'unknown')}",
                        complexity_score=complexity_score,
                        maintainability_index=100.0,  # Will be updated if MI data available
                        lines_of_code=func_data.get("loc", 0),
                        difficulty=0.0,  # Not provided by radon cc
                        effort=0.0,  # Not provided by radon cc
                        time_to_understand=complexity_score * 2.5  # Rough estimate
                    )
                    complexity_results.append(complexity_metric)
                    
                    # Create violation if complexity exceeds threshold
                    if complexity_score > complexity_threshold:
                        severity = ViolationSeverity.HIGH if complexity_score > complexity_threshold * 2 else ViolationSeverity.MEDIUM
                        
                        violation = QualityViolation(
                            tool=QualityTool.RADON,
                            rule_code="C901",
                            message=f"Function '{func_data.get('name', 'unknown')}' has complexity {complexity_score} (threshold: {complexity_threshold})",
                            severity=severity,
                            file_path=file_path,
                            line_number=func_data.get("lineno", 0),
                            fixable=False  # Complexity requires manual refactoring
                        )
                        violations.append(violation)
                        
        except json.JSONDecodeError:
            # Fallback to text parsing if needed
            pass
        
        return complexity_results, violations

    def _update_complexity_with_maintainability(self, complexity_results: List[ComplexityMetric], mi_output: str):
        """Update complexity results with maintainability index data."""
        try:
            mi_data = json.loads(mi_output)
            
            # Create a mapping from file path to MI score
            mi_scores = {}
            for file_path, mi_score in mi_data.items():
                mi_scores[file_path] = mi_score
            
            # Update complexity results with MI scores
            for complexity_result in complexity_results:
                file_path = complexity_result.name.split(':')[0]
                if file_path in mi_scores:
                    complexity_result.maintainability_index = mi_scores[file_path]
                    
        except (json.JSONDecodeError, AttributeError):
            # If MI parsing fails, keep default values
            pass

    def _parse_vulture_output(self, stdout: str, confidence_threshold: int) -> tuple[List[DeadCodeResult], List[QualityViolation]]:
        """Parse vulture output into dead code results and violations."""
        dead_code_results = []
        violations = []
        
        lines = stdout.strip().split('\n')
        
        for line in lines:
            if line.strip():
                # Vulture format: path:line: unused variable 'name' (confidence: X%)
                match = re.match(r'^(.+):(\d+):\s+unused\s+(\w+)\s+[\'"](.+)[\'"](?:\s+\(confidence:\s+(\d+)%\))?', line)
                if match:
                    file_path, line_num, symbol_type, symbol_name, confidence_str = match.groups()
                    confidence = int(confidence_str) if confidence_str else 60
                    
                    # Only include if confidence meets threshold
                    if confidence >= confidence_threshold:
                        dead_code_result = DeadCodeResult(
                            file_path=file_path,
                            line_number=int(line_num),
                            symbol_name=symbol_name,
                            symbol_type=symbol_type,
                            confidence=confidence,
                            used_outside_scope=confidence < 90  # Conservative estimate
                        )
                        dead_code_results.append(dead_code_result)
                        
                        # Create corresponding violation
                        severity = ViolationSeverity.LOW if "import" in symbol_type.lower() else ViolationSeverity.MEDIUM
                        
                        violation = QualityViolation(
                            tool=QualityTool.VULTURE,
                            rule_code="vulture",
                            message=f"Unused {symbol_type} '{symbol_name}' (confidence: {confidence}%)",
                            severity=severity,
                            file_path=file_path,
                            line_number=int(line_num),
                            fixable="import" in symbol_type.lower()  # Imports can be auto-removed
                        )
                        violations.append(violation)
        
        return dead_code_results, violations

    # Recommendation generation methods

    def _generate_lint_recommendations(self, violations: List[QualityViolation], tool: QualityTool) -> List[str]:
        """Generate recommendations based on lint violations."""
        recommendations = []
        
        if not violations:
            recommendations.append("✅ No linting violations found. Code follows style guidelines.")
            return recommendations
        
        # Count violations by severity
        critical_count = sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL)
        high_count = sum(1 for v in violations if v.severity == ViolationSeverity.HIGH)
        fixable_count = sum(1 for v in violations if v.fixable)
        
        if critical_count > 0:
            recommendations.append(f"🚨 Address {critical_count} critical violations immediately - these may cause runtime errors")
        
        if high_count > 0:
            recommendations.append(f"⚠️ Fix {high_count} high-priority violations to improve code quality")
        
        if fixable_count > 0 and tool == QualityTool.RUFF:
            recommendations.append(f"🔧 {fixable_count} violations can be auto-fixed with 'pixi run lint --fix'")
        
        # Tool-specific recommendations
        if tool == QualityTool.RUFF:
            recommendations.append("📖 Configure ruff rules in pyproject.toml for project-specific standards")
        elif tool == QualityTool.PYLINT:
            recommendations.append("📖 Consider configuring pylint rules in .pylintrc for better project alignment")
        
        return recommendations

    def _generate_typecheck_recommendations(self, violations: List[QualityViolation], type_errors: int) -> List[str]:
        """Generate recommendations based on type checking results."""
        recommendations = []
        
        if type_errors == 0:
            recommendations.append("✅ No type errors found. Type annotations are consistent.")
            return recommendations
        
        if type_errors > 0:
            recommendations.append(f"🔍 Fix {type_errors} type errors for better code safety and IDE support")
        
        # Count specific error types for targeted recommendations
        import_errors = sum(1 for v in violations if "import" in v.message.lower())
        annotation_errors = sum(1 for v in violations if "annotation" in v.message.lower() or "type" in v.message.lower())
        
        if import_errors > 0:
            recommendations.append("📦 Review import statements - some may be missing type stubs")
        
        if annotation_errors > 0:
            recommendations.append("🏷️ Consider adding more type annotations for better static analysis")
        
        recommendations.append("⚙️ Enable strict mode gradually with mypy --strict for maximum type safety")
        
        return recommendations

    def _generate_security_recommendations(self, security_issues: List[SecurityIssue]) -> List[str]:
        """Generate recommendations based on security scan results."""
        recommendations = []
        
        if not security_issues:
            recommendations.append("✅ No security vulnerabilities detected.")
            return recommendations
        
        high_severity = sum(1 for issue in security_issues if issue.severity in [ViolationSeverity.CRITICAL, ViolationSeverity.HIGH])
        
        if high_severity > 0:
            recommendations.append(f"🚨 Address {high_severity} high-severity security issues immediately")
        
        # Categorize common issues
        sql_injection = sum(1 for issue in security_issues if "sql" in issue.description.lower())
        hardcoded_creds = sum(1 for issue in security_issues if "password" in issue.description.lower() or "secret" in issue.description.lower())
        
        if sql_injection > 0:
            recommendations.append("💉 Review SQL queries for injection vulnerabilities - use parameterized queries")
        
        if hardcoded_creds > 0:
            recommendations.append("🔐 Remove hardcoded credentials - use environment variables or secure vaults")
        
        recommendations.append("🛡️ Regular security scans should be part of your CI/CD pipeline")
        recommendations.append("📚 Review OWASP guidelines for secure coding practices")
        
        return recommendations

    def _generate_complexity_recommendations(self, complexity_results: List[ComplexityMetric], avg_complexity: float, threshold: int) -> List[str]:
        """Generate recommendations based on complexity analysis."""
        recommendations = []
        
        if avg_complexity <= threshold:
            recommendations.append(f"✅ Average complexity ({avg_complexity:.1f}) is within acceptable limits")
            return recommendations
        
        high_complexity_functions = [cr for cr in complexity_results if cr.complexity_score > threshold * 2]
        
        if high_complexity_functions:
            recommendations.append(f"🔧 Refactor {len(high_complexity_functions)} highly complex functions")
            
            # Identify the most complex function
            most_complex = max(complexity_results, key=lambda cr: cr.complexity_score, default=None)
            if most_complex:
                recommendations.append(f"🎯 Start with '{most_complex.name}' (complexity: {most_complex.complexity_score})")
        
        low_maintainability = [cr for cr in complexity_results if cr.maintainability_index < 50]
        if low_maintainability:
            recommendations.append(f"📈 Improve maintainability of {len(low_maintainability)} functions")
        
        recommendations.append("📐 Consider breaking large functions into smaller, focused functions")
        recommendations.append("🧪 Add unit tests before refactoring complex functions")
        
        return recommendations

    def _generate_dead_code_recommendations(self, dead_code_results: List[DeadCodeResult], unused_imports: int) -> List[str]:
        """Generate recommendations based on dead code detection."""
        recommendations = []
        
        if not dead_code_results:
            recommendations.append("✅ No dead code detected. Codebase is clean.")
            return recommendations
        
        if unused_imports > 0:
            recommendations.append(f"🔧 Remove {unused_imports} unused imports - can be auto-fixed")
        
        unused_functions = sum(1 for dcr in dead_code_results if dcr.symbol_type == "function")
        unused_variables = sum(1 for dcr in dead_code_results if dcr.symbol_type == "variable")
        
        if unused_functions > 0:
            recommendations.append(f"🗑️ Review {unused_functions} unused functions - remove or document if intentional")
        
        if unused_variables > 0:
            recommendations.append(f"🧹 Clean up {unused_variables} unused variables")
        
        # Check confidence levels
        low_confidence = sum(1 for dcr in dead_code_results if dcr.confidence < 70)
        if low_confidence > 0:
            recommendations.append(f"⚠️ {low_confidence} items have low confidence - manual review recommended")
        
        recommendations.append("🔍 Run aggressive mode for more thorough detection (may have false positives)")
        
        return recommendations

    @staticmethod
    def _is_execution_failure(result: Dict[str, Any]) -> bool:
        """Determine whether a pixi result means the tool never ran.

        A non-zero exit does NOT imply execution failure: ruff exits 1 precisely
        when it has violations to report, and mypy exits 1 when it finds type
        errors. Those are successful runs with findings and must be parsed, not
        turned into errors.

        run_task's exception path returns exit_code=1, colliding with the
        "found violations" code, so the exit code alone cannot discriminate.
        The "error" key is only present on that path.
        """
        if result.get("error"):
            return True

        exit_code = result.get("exit_code")
        # 0 = clean, 1 = tool ran and reported findings. Anything else
        # (124 timeout, 126/127 not executable / not found, 2 usage error)
        # means the tool did not complete a real analysis.
        return exit_code not in (0, 1)

    @staticmethod
    def _describe_execution_failure(result: Dict[str, Any], pixi_task: str) -> str:
        """Build a diagnostic carrying exit code and stderr through to the caller."""
        parts = [f"Pixi task '{pixi_task}' did not complete an analysis"]

        exit_code = result.get("exit_code")
        if exit_code is not None:
            parts.append(f"exit_code={exit_code}")

        error = result.get("error")
        if error:
            parts.append(f"error={error}")

        stderr = (result.get("stderr") or "").strip()
        if stderr:
            parts.append(f"stderr={stderr}")

        return "; ".join(parts)

    def _create_error_result(
        self,
        tool: QualityTool,
        assessment_type: QualityAssessmentType,
        start_time: str,
        execution_time_ms: float,
        error_msg: str,
        target_path: str,
        pixi_task_used: str
    ) -> QualityAssessmentResult:
        """Create an error result for failed assessments."""
        
        metrics = QualityMetrics(
            overall_score=0.0,
            total_violations=0,
            critical_violations=0,
            high_violations=0,
            medium_violations=0,
            low_violations=0,
            total_lines=0,
            code_lines=0,
            comment_lines=0,
            blank_lines=0
        )

        return QualityAssessmentResult(
            assessment_type=assessment_type,
            tool=tool,
            status=ExecutionStatus.ERROR,
            start_time=start_time,
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=execution_time_ms,
            pixi_task_used=pixi_task_used,
            target_path=target_path,
            files_analyzed=0,
            raw_output=f"Error: {error_msg}",
            parsed_metrics=metrics,
            violations=[],
            recommendations=[f"❌ Assessment failed: {error_msg}"]
        )