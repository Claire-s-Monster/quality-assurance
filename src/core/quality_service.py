"""
Quality Assurance Service - Core business logic for quality assessments.

This service orchestrates quality assessment operations through pixi-mediated
tool execution, providing comprehensive code quality analysis capabilities.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import logging
import os
from pathlib import Path

from .models import (
    QualityTool,
    QualityAssessmentType,
    QualityAssessmentResult,
    QualityMetrics,
    ComprehensiveQualityResult,
    QualitySuiteConfiguration,
    AutomatedFixResult,
    QualityReport,
    ToolValidationResult,
    SystemHealth,
    OperationResult,
    ExecutionStatus,
)
from .ports import (
    QualityToolExecutionPort,
    LoggingPort,
)


class QualityAssuranceService:
    """
    Core service orchestrating all quality assurance operations.
    
    Provides a unified interface for quality assessment operations,
    managing tool execution through dependency injection and
    comprehensive error handling.
    """

    def __init__(
        self,
        quality_executor: QualityToolExecutionPort,
        logging: LoggingPort
    ):
        """
        Initialize service with quality tool executor and logging.
        
        Args:
            quality_executor: Port for executing quality assessment tools
            logging: Port for logging operations
        """
        self.quality_executor = quality_executor
        self.logging = logging

    # Core Quality Assessment Operations

    def execute_lint_assessment(
        self,
        tool: QualityTool = QualityTool.RUFF,
        target_path: str = "src/",
        rules: Optional[List[str]] = None,
        fix_mode: bool = False,
        output_format: str = "json",
        use_cache: bool = True
    ) -> QualityAssessmentResult:
        """
        Execute linting assessment with comprehensive error handling.

        Args:
            tool: Linting tool to use (ruff, pylint, flake8)
            target_path: Path to analyze
            rules: Specific rules to apply
            fix_mode: Whether to apply auto-fixes
            output_format: Output format preference
            use_cache: Whether to use cached results

        Returns:
            QualityAssessmentResult with lint analysis results
        """
        try:
            self.logging.log_operation("lint_assessment", {
                "tool": tool.value,
                "target_path": target_path,
                "fix_mode": fix_mode
            })

            result = self.quality_executor.execute_lint_assessment(
                tool=tool,
                target_path=target_path,
                rules=rules,
                fix_mode=fix_mode,
                output_format=output_format,
                use_cache=use_cache
            )

            self.logging.log_operation_result("lint_assessment", True, result.execution_time_ms, {
                "status": result.status.value,
                "violations": len(result.violations),
                "score": result.parsed_metrics.overall_score
            })

            return result

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "lint_assessment"})
            return self._create_error_result(
                assessment_type=QualityAssessmentType.LINT,
                tool=tool,
                error_msg=str(e),
                target_path=target_path
            )

    def execute_typecheck_assessment(
        self,
        tool: QualityTool = QualityTool.MYPY,
        target_path: str = "src/",
        strict_mode: bool = False,
        config_file: Optional[str] = None,
        incremental: bool = True,
        cache_dir: Optional[str] = None
    ) -> QualityAssessmentResult:
        """
        Execute type checking assessment.

        Args:
            tool: Type checking tool to use
            target_path: Path to analyze (default: "src/")
            strict_mode: Enable strict type checking
            config_file: Custom configuration file path
            incremental: Enable incremental checking
            cache_dir: Custom cache directory

        Returns:
            QualityAssessmentResult with type checking results
        """
        try:
            self.logging.log_operation("typecheck_assessment", {
                "tool": tool.value,
                "target_path": target_path,
                "strict_mode": strict_mode,
                "config_file": config_file
            })

            result = self.quality_executor.execute_typecheck_assessment(
                tool=tool,
                target_path=target_path,
                strict_mode=strict_mode,
                config_file=config_file,
                incremental=incremental,
                cache_dir=cache_dir
            )

            self.logging.log_operation_result("typecheck_assessment", True, result.execution_time_ms, {
                "status": result.status.value,
                "type_errors": result.parsed_metrics.type_errors,
                "score": result.parsed_metrics.overall_score
            })

            return result

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "typecheck_assessment"})
            return self._create_error_result(
                assessment_type=QualityAssessmentType.TYPECHECK,
                tool=tool,
                error_msg=str(e),
                target_path="src/"
            )

    def execute_security_scan(
        self,
        tool: QualityTool = QualityTool.BANDIT,
        target_path: str = "src/",
        severity_threshold: str = "medium",
        exclude_tests: bool = True,
        use_cache: bool = True
    ) -> QualityAssessmentResult:
        """
        Execute security vulnerability scanning.

        Args:
            tool: Security scanning tool to use
            target_path: Path to analyze (default: "src/")
            severity_threshold: Minimum severity to report
            exclude_tests: Whether to exclude test files
            use_cache: Whether to use cached results

        Returns:
            QualityAssessmentResult with security scan results
        """
        try:
            self.logging.log_operation("security_scan", {
                "tool": tool.value,
                "target_path": target_path,
                "severity_threshold": severity_threshold,
                "exclude_tests": exclude_tests
            })

            result = self.quality_executor.execute_security_scan(
                tool=tool,
                target_path=target_path,
                severity_threshold=severity_threshold,
                exclude_tests=exclude_tests
            )

            self.logging.log_operation_result("security_scan", True, result.execution_time_ms, {
                "status": result.status.value,
                "security_issues": len(result.security_issues),
                "high_severity": result.parsed_metrics.high_security_issues
            })

            return result

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "security_scan"})
            return self._create_error_result(
                assessment_type=QualityAssessmentType.SECURITY,
                tool=tool,
                error_msg=str(e),
                target_path="src/"
            )

    def execute_complexity_analysis(
        self,
        tool: QualityTool = QualityTool.RADON,
        target_path: str = "src/",
        complexity_threshold: int = 10,
        include_metrics: Optional[List[str]] = None,
        use_cache: bool = True
    ) -> QualityAssessmentResult:
        """
        Execute code complexity analysis.

        Args:
            tool: Complexity analysis tool to use
            target_path: Path to analyze (default: "src/")
            complexity_threshold: Complexity threshold for warnings
            include_metrics: Specific metrics to include
            use_cache: Whether to use cached results

        Returns:
            QualityAssessmentResult with complexity analysis results
        """
        try:
            self.logging.log_operation("complexity_analysis", {
                "tool": tool.value,
                "target_path": target_path,
                "threshold": complexity_threshold,
                "include_metrics": include_metrics
            })

            result = self.quality_executor.execute_complexity_analysis(
                tool=tool,
                target_path=target_path,
                complexity_threshold=complexity_threshold,
                include_metrics=include_metrics
            )

            self.logging.log_operation_result("complexity_analysis", True, result.execution_time_ms, {
                "status": result.status.value,
                "avg_complexity": result.parsed_metrics.average_complexity,
                "max_complexity": result.parsed_metrics.max_complexity
            })

            return result

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "complexity_analysis"})
            return self._create_error_result(
                assessment_type=QualityAssessmentType.COMPLEXITY,
                tool=tool,
                error_msg=str(e),
                target_path="src/"
            )

    def execute_dead_code_detection(
        self,
        tool: QualityTool = QualityTool.VULTURE,
        aggressive_mode: bool = False,
        exclude_patterns: Optional[List[str]] = None,
        confidence_threshold: int = 80
    ) -> QualityAssessmentResult:
        """
        Execute dead code detection analysis.
        
        Args:
            tool: Dead code detection tool to use
            aggressive_mode: Enable aggressive detection mode
            exclude_patterns: Patterns to exclude from analysis
            confidence_threshold: Minimum confidence for reporting
            
        Returns:
            QualityAssessmentResult with dead code detection results
        """
        try:
            self.logging.log_operation("dead_code_detection", {
                "tool": tool.value,
                "aggressive_mode": aggressive_mode,
                "confidence_threshold": confidence_threshold
            })

            result = self.quality_executor.execute_dead_code_detection(
                tool=tool,
                aggressive_mode=aggressive_mode,
                exclude_patterns=exclude_patterns,
                confidence_threshold=confidence_threshold
            )

            self.logging.log_operation_result("dead_code_detection", True, result.execution_time_ms, {
                "status": result.status.value,
                "dead_code_count": result.parsed_metrics.dead_code_count,
                "unused_imports": result.parsed_metrics.unused_imports
            })

            return result

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "dead_code_detection"})
            return self._create_error_result(
                assessment_type=QualityAssessmentType.DEAD_CODE,
                tool=tool,
                error_msg=str(e),
                target_path="src/"
            )

    # Comprehensive Quality Suite Operations

    def execute_comprehensive_suite(
        self,
        configuration: QualitySuiteConfiguration
    ) -> ComprehensiveQualityResult:
        """
        Execute comprehensive quality suite with all configured tools.
        
        Args:
            configuration: Suite configuration with tool selections
            
        Returns:
            ComprehensiveQualityResult with aggregated results
        """
        start_time = datetime.now()
        individual_results = []
        failed_tools = []
        skipped_tools = []

        try:
            self.logging.log_operation("comprehensive_suite", {
                "tools": [tool.value for tool in configuration.included_tools],
                "parallel": configuration.parallel_execution,
                "fail_fast": configuration.fail_fast
            })

            # Execute each tool in the configuration
            for tool in configuration.included_tools:
                try:
                    if tool in [QualityTool.RUFF, QualityTool.PYLINT, QualityTool.FLAKE8]:
                        result = self.execute_lint_assessment(tool=tool)
                    elif tool == QualityTool.MYPY:
                        result = self.execute_typecheck_assessment(tool=tool)
                    elif tool == QualityTool.BANDIT:
                        result = self.execute_security_scan(tool=tool)
                    elif tool == QualityTool.RADON:
                        result = self.execute_complexity_analysis(tool=tool)
                    elif tool == QualityTool.VULTURE:
                        result = self.execute_dead_code_detection(tool=tool)
                    else:
                        skipped_tools.append(f"Unsupported tool: {tool.value}")
                        continue

                    individual_results.append(result)

                    # Check fail-fast condition
                    if configuration.fail_fast and result.status == ExecutionStatus.FAILURE:
                        self.logging.log_warning(f"Fail-fast triggered by {tool.value}", {"operation": "comprehensive_suite"})
                        break

                except Exception as e:
                    failed_tools.append(f"{tool.value}: {str(e)}")
                    if configuration.fail_fast:
                        break

            # Aggregate metrics from all results
            overall_metrics = self._aggregate_quality_metrics(individual_results)
            overall_score = overall_metrics.overall_score
            meets_threshold = overall_score >= configuration.quality_threshold

            end_time = datetime.now()
            total_execution_time = (end_time - start_time).total_seconds() * 1000

            return ComprehensiveQualityResult(
                configuration=configuration,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                total_execution_time_ms=total_execution_time,
                executed_in_parallel=configuration.parallel_execution,
                individual_results=individual_results,
                failed_tools=failed_tools,
                skipped_tools=skipped_tools,
                overall_metrics=overall_metrics,
                overall_score=overall_score,
                meets_threshold=meets_threshold,
                critical_issues_summary=self._generate_critical_issues_summary(individual_results),
                improvement_priorities=self._generate_improvement_priorities(individual_results),
                next_steps=self._generate_next_steps(individual_results, meets_threshold),
                report_generated=configuration.generate_report,
                report_path=None  # Would be set if report generation is implemented
            )

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "comprehensive_suite"})
            # Return partial result with error information
            end_time = datetime.now()
            total_execution_time = (end_time - start_time).total_seconds() * 1000

            return ComprehensiveQualityResult(
                configuration=configuration,
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                total_execution_time_ms=total_execution_time,
                executed_in_parallel=False,
                individual_results=individual_results,
                failed_tools=failed_tools + [f"Suite execution error: {str(e)}"],
                skipped_tools=skipped_tools,
                overall_metrics=QualityMetrics(
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
                ),
                overall_score=0.0,
                meets_threshold=False,
                critical_issues_summary=[f"Suite execution failed: {str(e)}"],
                improvement_priorities=["Fix suite execution issues before proceeding"],
                next_steps=["Debug and resolve suite configuration problems"],
                report_generated=False,
                report_path=None
            )

    # Health and Monitoring

    def get_system_health(self) -> SystemHealth:
        """
        Get comprehensive system health status.
        
        Returns:
            SystemHealth with component status and metrics
        """
        try:
            active_issues: List[str] = []
            performance_alerts: List[str] = []
            recommendations: List[str] = []

            pixi_executor = getattr(self.quality_executor, "pixi_executor", None)

            # Probe pixi executable resolution for real - this is the
            # actual failure mode that this health check exists to catch.
            pixi_bin = getattr(pixi_executor, "_pixi_bin", None)
            pixi_healthy = bool(
                pixi_bin and os.path.isfile(pixi_bin) and os.access(pixi_bin, os.X_OK)
            )
            if not pixi_healthy:
                active_issues.append(
                    f"Pixi executable could not be resolved or is not executable "
                    f"(resolved path: {pixi_bin!r})"
                )
                recommendations.append(
                    "Ensure pixi is installed and on PATH, or present at ~/.pixi/bin/pixi"
                )

            # Probe quality tool availability via real pixi task lookups.
            # If we cannot probe cheaply and honestly, report None rather
            # than fabricating a positive result.
            #
            # Task naming varies from project to project (this server is
            # meant to assess *other* projects, not just itself), so the
            # optional tasks are probed under both common spellings and a
            # task is considered present if either form exists. Only a
            # missing binary/filesystem is fatal to `healthy`; absent tasks
            # are informational (recommendations), except when both
            # required tasks are absent, which is surfaced as an issue.
            tools_available: Optional[bool] = None
            required_tasks = ("lint", "typecheck")
            optional_task_aliases: dict[str, tuple[str, ...]] = {
                "security-scan": ("security-scan", "security"),
                "complexity-check": ("complexity-check", "complexity"),
                "dead-code-check": ("dead-code-check", "dead-code"),
            }
            if pixi_executor is not None:
                try:
                    def _task_exists(task_name: str) -> bool:
                        return bool(pixi_executor.task_exists(task_name).get("exists", False))

                    missing_required = [
                        task_name for task_name in required_tasks if not _task_exists(task_name)
                    ]
                    missing_optional = [
                        canonical
                        for canonical, aliases in optional_task_aliases.items()
                        if not any(_task_exists(alias) for alias in aliases)
                    ]

                    tools_available = len(missing_required) == 0

                    if len(missing_required) == len(required_tasks):
                        active_issues.append(
                            f"Missing expected pixi quality tasks: {', '.join(missing_required)} "
                            "(project may not define quality tasks)"
                        )
                    elif missing_required:
                        recommendations.append(
                            f"Missing pixi quality task(s): {', '.join(missing_required)}"
                        )

                    if missing_optional:
                        recommendations.append(
                            f"Optional pixi quality tasks not found: {', '.join(missing_optional)}"
                        )
                except Exception as probe_error:
                    tools_available = None
                    active_issues.append(
                        f"Could not probe quality tool availability: {probe_error}"
                    )
            else:
                active_issues.append("No pixi executor available to probe quality tools")

            # Filesystem health: verify the working directory is actually
            # accessible rather than assuming it.
            working_dir = getattr(pixi_executor, "working_dir", None)
            filesystem_healthy = bool(
                working_dir and os.path.isdir(working_dir) and os.access(working_dir, os.R_OK)
            )
            if not filesystem_healthy:
                active_issues.append(f"Working directory not accessible: {working_dir!r}")

            # No real cache subsystem is wired into this service, so we do
            # not fabricate a cache health signal or performance metrics.
            cache_system_healthy = True
            average_assessment_time_ms: Optional[float] = None
            cache_hit_rate: Optional[float] = None

            # Absent quality tasks (required or optional) are never fatal to
            # `healthy` — only a broken pixi binary or an inaccessible
            # working directory are genuine health failures. A project may
            # legitimately not define any quality tasks yet still be a
            # perfectly resolvable pixi environment.
            healthy = bool(pixi_healthy and cache_system_healthy and filesystem_healthy)

            return SystemHealth(
                healthy=healthy,
                timestamp=datetime.now().isoformat(),
                pixi_environment_healthy=pixi_healthy,
                quality_tools_available=tools_available,
                cache_system_healthy=cache_system_healthy,
                filesystem_healthy=filesystem_healthy,
                average_assessment_time_ms=average_assessment_time_ms,
                cache_hit_rate=cache_hit_rate,
                active_issues=active_issues,
                performance_alerts=performance_alerts,
                recommendations=recommendations
            )

        except Exception as e:
            self.logging.log_error(str(e), {"operation": "system_health"})
            return SystemHealth(
                healthy=False,
                timestamp=datetime.now().isoformat(),
                pixi_environment_healthy=False,
                quality_tools_available=None,
                cache_system_healthy=False,
                filesystem_healthy=False,
                average_assessment_time_ms=None,
                cache_hit_rate=None,
                active_issues=[f"Health check failed: {str(e)}"],
                performance_alerts=[],
                recommendations=["Debug health check system"]
            )

    # Helper Methods

    def _create_error_result(
        self,
        assessment_type: QualityAssessmentType,
        tool: QualityTool,
        error_msg: str,
        target_path: str
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
            start_time=datetime.now().isoformat(),
            end_time=datetime.now().isoformat(),
            execution_time_ms=0.0,
            pixi_task_used="unknown",
            target_path=target_path,
            files_analyzed=0,
            raw_output=f"Error: {error_msg}",
            parsed_metrics=metrics,
            violations=[],
            recommendations=[f"❌ Assessment failed: {error_msg}"]
        )

    def _aggregate_quality_metrics(
        self, 
        results: List[QualityAssessmentResult]
    ) -> QualityMetrics:
        """Aggregate metrics from multiple assessment results."""
        
        if not results:
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
                blank_lines=0
            )

        # Aggregate all metrics
        total_violations = sum(r.parsed_metrics.total_violations for r in results)
        critical_violations = sum(r.parsed_metrics.critical_violations for r in results)
        high_violations = sum(r.parsed_metrics.high_violations for r in results)
        medium_violations = sum(r.parsed_metrics.medium_violations for r in results)
        low_violations = sum(r.parsed_metrics.low_violations for r in results)
        
        # Calculate weighted overall score
        scores = [r.parsed_metrics.overall_score for r in results if r.parsed_metrics.overall_score > 0]
        overall_score = sum(scores) / len(scores) if scores else 0.0

        return QualityMetrics(
            overall_score=overall_score,
            total_violations=total_violations,
            critical_violations=critical_violations,
            high_violations=high_violations,
            medium_violations=medium_violations,
            low_violations=low_violations,
            security_issues_count=sum(len(r.security_issues) for r in results),
            high_security_issues=sum(r.parsed_metrics.high_security_issues for r in results),
            dead_code_count=sum(r.parsed_metrics.dead_code_count for r in results),
            unused_imports=sum(r.parsed_metrics.unused_imports for r in results),
            type_errors=sum(r.parsed_metrics.type_errors for r in results),
            average_complexity=sum(r.parsed_metrics.average_complexity or 0 for r in results) / len(results),
            max_complexity=max((r.parsed_metrics.max_complexity or 0 for r in results), default=0),
            total_lines=max(r.parsed_metrics.total_lines for r in results) if results else 0,
            code_lines=max(r.parsed_metrics.code_lines for r in results) if results else 0,
            comment_lines=max(r.parsed_metrics.comment_lines for r in results) if results else 0,
            blank_lines=max(r.parsed_metrics.blank_lines for r in results) if results else 0
        )

    def _generate_critical_issues_summary(
        self, 
        results: List[QualityAssessmentResult]
    ) -> List[str]:
        """Generate summary of critical issues across all results."""
        issues = []
        
        for result in results:
            if result.parsed_metrics.critical_violations > 0:
                issues.append(f"{result.tool.value}: {result.parsed_metrics.critical_violations} critical violations")
            
            if result.parsed_metrics.high_security_issues > 0:
                issues.append(f"{result.tool.value}: {result.parsed_metrics.high_security_issues} high-severity security issues")
                
            if result.parsed_metrics.type_errors > 5:  # Threshold for "too many"
                issues.append(f"{result.tool.value}: {result.parsed_metrics.type_errors} type errors")

        return issues or ["No critical issues detected"]

    def _generate_improvement_priorities(
        self, 
        results: List[QualityAssessmentResult]
    ) -> List[str]:
        """Generate prioritized improvement recommendations."""
        priorities = []
        
        # Security issues have highest priority
        security_issues = sum(len(r.security_issues) for r in results)
        if security_issues > 0:
            priorities.append(f"🚨 Address {security_issues} security vulnerabilities immediately")
        
        # Critical violations
        critical_violations = sum(r.parsed_metrics.critical_violations for r in results)
        if critical_violations > 0:
            priorities.append(f"🔥 Fix {critical_violations} critical code violations")
        
        # Type errors
        type_errors = sum(r.parsed_metrics.type_errors for r in results)
        if type_errors > 0:
            priorities.append(f"🔍 Resolve {type_errors} type checking errors")
        
        # Complex code
        max_complexity = max((r.parsed_metrics.max_complexity or 0 for r in results), default=0)
        if max_complexity > 15:
            priorities.append(f"🧩 Refactor complex code (max complexity: {max_complexity})")
        
        # Dead code cleanup
        dead_code = sum(r.parsed_metrics.dead_code_count for r in results)
        if dead_code > 0:
            priorities.append(f"🧹 Remove {dead_code} instances of dead code")

        return priorities or ["Code quality is good - focus on maintenance"]

    def _generate_next_steps(
        self, 
        results: List[QualityAssessmentResult], 
        meets_threshold: bool
    ) -> List[str]:
        """Generate recommended next steps based on results."""
        next_steps = []
        
        if not meets_threshold:
            next_steps.append("❌ Quality threshold not met - address critical issues before proceeding")
        else:
            next_steps.append("✅ Quality threshold met - code is ready for deployment")
        
        # Check for auto-fixable issues
        auto_fixable = sum(1 for r in results if r.auto_fix_available)
        if auto_fixable > 0:
            next_steps.append(f"🔧 {auto_fixable} tools offer auto-fixes - consider running fix mode")
        
        # Suggest regular monitoring
        next_steps.append("📊 Set up regular quality monitoring in CI/CD pipeline")
        next_steps.append("📈 Track quality trends over time to prevent regression")
        
        return next_steps