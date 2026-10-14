"""
Core quality orchestration service for Quality Assurance MCP Server.

This service coordinates all quality assessment operations and serves as the main
business logic layer, orchestrating multiple adapters to provide comprehensive
quality analysis capabilities.
"""

import asyncio
import concurrent.futures
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from core.models import (
    QualityTool,
    QualityAssessmentType,
    QualityAssessmentResult,
    QualityBaseline,
    QualityComparison,
    ComprehensiveQualityResult,
    QualitySuiteConfiguration,
    AutomatedFixResult,
    FixType,
    FixValidationMode,
    QualityReport,
    ReportFormat,
    ReportTemplate,
    ToolValidationResult,
    ConfigurationResult,
    ConfigurationUpdate,
    OperationResult,
    SystemHealth,
    QualityMetrics,
    ExecutionStatus,
)
from core.ports import (
    QualityToolExecutionPort,
    QualityAnalysisPort,
    QualityTrendAnalysisPort,
    QualityOrchestrationPort,
    AutomatedFixPort,
    QualityReportingPort,
    ToolManagementPort,
    PixiIntegrationPort,
    QualityCachingPort,
    QualityDataStoragePort,
    SystemIntegrationPort,
    QualityAuditPort,
    LoggingPort,
)


class QualityOrchestrationService:
    """
    Core service orchestrating all quality assessment operations.
    
    This service serves as the main business logic layer, coordinating:
    - Individual tool assessments (lint, typecheck, security, complexity, dead code)
    - Comprehensive quality suites with parallel/sequential execution
    - Quality baseline management and trend analysis
    - Automated fix application with safety validations
    - Report generation and quality recommendations
    """

    def __init__(
        self,
        quality_executor: QualityToolExecutionPort,
        quality_analyzer: QualityAnalysisPort,
        trend_analyzer: QualityTrendAnalysisPort,
        logging: LoggingPort,
        data_storage: Optional[QualityDataStoragePort] = None,
        git_integration: Optional[Any] = None,
        automated_fix: Optional[AutomatedFixPort] = None,
        quality_reporting: Optional[QualityReportingPort] = None,
        tool_management: Optional[ToolManagementPort] = None,
        pixi_integration: Optional[PixiIntegrationPort] = None,
        caching: Optional[QualityCachingPort] = None,
        system_integration: Optional[SystemIntegrationPort] = None,
        audit: Optional[QualityAuditPort] = None,
    ):
        """
        Initialize orchestration service with dependency injection.
        
        Args:
            quality_executor: Port for executing quality tools
            quality_analyzer: Port for analyzing quality results
            trend_analyzer: Port for trend analysis and baselines
            logging: Required port for logging operations
            automated_fix: Optional port for automated fixes
            quality_reporting: Optional port for report generation
            tool_management: Optional port for tool management
            pixi_integration: Optional port for pixi operations
            caching: Optional port for result caching
            data_storage: Optional port for data persistence
            system_integration: Optional port for system health
            audit: Optional port for audit logging
        """
        # Core required dependencies
        self.quality_executor = quality_executor
        self.quality_analyzer = quality_analyzer
        self.trend_analyzer = trend_analyzer
        self.logging = logging
        
        # Optional dependencies with graceful degradation
        self.data_storage = data_storage
        self.git_integration = git_integration
        self.automated_fix = automated_fix
        self.quality_reporting = quality_reporting
        self.tool_management = tool_management
        self.pixi_integration = pixi_integration
        self.caching = caching
        self.system_integration = system_integration
        self.audit = audit
        
        # Performance monitoring
        self._performance_metrics = {
            "total_assessments": 0,
            "total_execution_time_ms": 0.0,
            "cached_results": 0,
            "errors": 0,
        }
        
        # Execution thread pool for parallel operations
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="QualityOrchestration"
        )

    def execute_lint_assessment(
        self,
        tool: QualityTool = QualityTool.RUFF,
        target_path: str = "src/",
        rules: Optional[List[str]] = None,
        fix_mode: bool = False,
        output_format: str = "json",
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> QualityAssessmentResult:
        """
        Execute single tool linting assessment with caching support.

        Args:
            tool: Linting tool to use
            target_path: Path to analyze
            rules: Specific rules to apply
            fix_mode: Whether to apply fixes
            output_format: Output format preference
            use_cache: Whether to use cached results
            project_path: Absolute path to the project root to analyze (default: server working directory)
            environment: Pixi environment to run the task in (omit unless ambiguous)

        Returns:
            QualityAssessmentResult with parsed linting results
        """
        operation_start = time.time()
        
        try:
            self.logging.log_operation("execute_lint_assessment", {
                "tool": tool.value,
                "target_path": target_path,
                "fix_mode": fix_mode,
                "use_cache": use_cache
            })
            
            # Check cache first if enabled
            if use_cache and self.caching:
                cache_key = self._generate_cache_key(tool, QualityAssessmentType.LINT, target_path, {
                    "rules": rules or [],
                    "fix_mode": fix_mode,
                    "output_format": output_format,
                    "project_path": project_path,
                    "environment": environment,
                })
                
                cached_result = self.caching.get_cached_result(cache_key)
                if cached_result:
                    self.logging.log_info("Using cached lint assessment result")
                    self._performance_metrics["cached_results"] += 1
                    return cached_result
            
            # Execute linting via quality executor
            result = self.quality_executor.execute_lint_assessment(
                tool=tool,
                target_path=target_path,
                rules=rules,
                fix_mode=fix_mode,
                output_format=output_format,
                project_path=project_path,
                environment=environment
            )
            
            # Cache result if caching is available
            if use_cache and self.caching and result.status == ExecutionStatus.SUCCESS:
                self.caching.cache_result(cache_key, result, ttl_seconds=300)
            
            # Log assessment execution
            if self.audit:
                self.audit.log_assessment_execution(
                    assessment_type=QualityAssessmentType.LINT,
                    tool=tool,
                    execution_time_ms=result.execution_time_ms,
                    status=result.status.value,
                    metadata={
                        "target_path": target_path,
                        "violations_count": len(result.violations),
                        "fix_mode": fix_mode
                    }
                )
            
            # Update performance metrics
            self._update_performance_metrics(result.execution_time_ms)
            
            return result
            
        except Exception as e:
            execution_time = (time.time() - operation_start) * 1000
            error_msg = f"Lint assessment failed: {str(e)}"
            
            self.logging.log_error(error_msg, {
                "operation": "execute_lint_assessment",
                "tool": tool.value,
                "target_path": target_path
            })
            
            self._performance_metrics["errors"] += 1
            
            # Return error result
            return self._create_error_result(
                tool=tool,
                assessment_type=QualityAssessmentType.LINT,
                execution_time_ms=execution_time,
                error_msg=error_msg,
                target_path=target_path
            )

    def execute_comprehensive_suite(
        self, 
        configuration: QualitySuiteConfiguration
    ) -> ComprehensiveQualityResult:
        """
        Execute complete quality assessment suite with orchestrated tool execution.
        
        This method coordinates multiple quality tools according to the configuration,
        supporting both parallel and sequential execution modes.
        
        Args:
            configuration: Suite configuration specifying tools and execution parameters
            
        Returns:
            ComprehensiveQualityResult with aggregated results from all tools
        """
        suite_start = time.time()
        suite_id = str(uuid.uuid4())
        start_time = datetime.now(UTC).isoformat()
        
        try:
            self.logging.log_operation("execute_comprehensive_suite", {
                "suite_id": suite_id,
                "tools": [tool.value for tool in configuration.included_tools],
                "parallel_execution": configuration.parallel_execution,
                "quality_threshold": configuration.quality_threshold
            })
            
            # Validate configuration
            validation_result = self._validate_suite_configuration(configuration)
            if not validation_result.success:
                raise ValueError(f"Invalid suite configuration: {validation_result.message}")
            
            # Validate tool availability if tool management is available
            if self.tool_management:
                tool_validation = self.tool_management.validate_tool_availability(
                    configuration.included_tools
                )
                if not tool_validation.all_tools_available:
                    self.logging.log_warning(
                        f"Some tools unavailable: {tool_validation.missing_tools}",
                        {"operation": "execute_comprehensive_suite"})
            
            individual_results = []
            failed_tools = []
            skipped_tools = []
            
            # Execute tools based on configuration
            if configuration.parallel_execution:
                individual_results, failed_tools, skipped_tools = self._execute_tools_parallel(
                    configuration
                )
            else:
                individual_results, failed_tools, skipped_tools = self._execute_tools_sequential(
                    configuration
                )
            
            # Calculate execution time
            end_time = datetime.now(UTC).isoformat()
            total_execution_time = (time.time() - suite_start) * 1000
            
            # Aggregate results using quality analyzer
            overall_metrics = self._aggregate_suite_results(individual_results)
            overall_score = self.quality_analyzer.calculate_quality_score(individual_results)
            
            # Generate suite-level analysis
            improvement_priorities = self.quality_analyzer.generate_recommendations(individual_results)
            critical_issues = self._extract_critical_issues(individual_results)
            next_steps = self._generate_next_steps(individual_results, configuration)
            
            # Generate report if configured
            report_generated = False
            report_path = None
            if configuration.generate_report and self.quality_reporting:
                try:
                    report = self.quality_reporting.generate_comprehensive_report(
                        assessment_results=individual_results,
                        format=ReportFormat(configuration.report_format),
                        template=ReportTemplate.COMPREHENSIVE
                    )
                    report_generated = True
                    report_path = report.report_path
                except Exception as e:
                    self.logging.log_warning(
                        f"Report generation failed: {e}",
                        {"operation": "execute_comprehensive_suite"})
            
            # Create comprehensive result
            result = ComprehensiveQualityResult(
                suite_id=suite_id,
                configuration=configuration,
                start_time=start_time,
                end_time=end_time,
                total_execution_time_ms=total_execution_time,
                executed_in_parallel=configuration.parallel_execution,
                individual_results=individual_results,
                failed_tools=[tool.value for tool in failed_tools],
                skipped_tools=[tool.value for tool in skipped_tools],
                overall_metrics=overall_metrics,
                overall_score=overall_score,
                meets_threshold=overall_score >= configuration.quality_threshold,
                critical_issues_summary=critical_issues,
                improvement_priorities=improvement_priorities,
                next_steps=next_steps,
                report_generated=report_generated,
                report_path=report_path
            )
            
            # Store result if data storage is available
            if self.data_storage:
                for individual_result in individual_results:
                    self.data_storage.store_assessment_result(individual_result)
            
            # Update performance metrics
            self._update_performance_metrics(total_execution_time)
            
            return result
            
        except Exception as e:
            execution_time = (time.time() - suite_start) * 1000
            error_msg = f"Comprehensive suite execution failed: {str(e)}"
            
            self.logging.log_error(error_msg, {
                "operation": "execute_comprehensive_suite",
                "suite_id": suite_id,
                "tools": [tool.value for tool in configuration.included_tools]
            })
            
            self._performance_metrics["errors"] += 1
            
            # Return error result
            return ComprehensiveQualityResult(
                suite_id=suite_id,
                configuration=configuration,
                start_time=start_time,
                end_time=datetime.now(UTC).isoformat(),
                total_execution_time_ms=execution_time,
                executed_in_parallel=configuration.parallel_execution,
                individual_results=[],
                failed_tools=[tool.value for tool in configuration.included_tools],
                skipped_tools=[],
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
                critical_issues_summary=[error_msg],
                improvement_priorities=["Fix suite execution errors"],
                next_steps=["Review logs and fix configuration issues"],
                report_generated=False,
                report_path=None
            )

    def establish_quality_baseline(
        self,
        baseline_id: Optional[str] = None,
        project_name: str = "current_project",
        project_version: Optional[str] = None,
        git_commit: Optional[str] = None,
        git_branch: Optional[str] = None,
        retention_days: int = 365,
        tags: Optional[List[str]] = None,
        suite_configuration: Optional[QualitySuiteConfiguration] = None
    ) -> QualityBaseline:
        """
        Create quality baseline for trend analysis.
        
        Args:
            baseline_id: Optional custom baseline ID
            project_name: Name of the project
            project_version: Project version
            git_commit: Git commit hash
            git_branch: Git branch name
            retention_days: Days to retain baseline
            tags: Baseline tags
            suite_configuration: Configuration for quality assessment
            
        Returns:
            QualityBaseline with comprehensive quality metrics
        """
        try:
            # Auto-detect git information if not provided and git integration is available
            if self.git_integration and (git_commit is None or git_branch is None):
                try:
                    git_metadata = self.git_integration.get_git_metadata()
                    if git_metadata.get('is_git_repo', False):
                        if git_commit is None:
                            git_commit = git_metadata.get('commit_hash')
                        if git_branch is None:
                            git_branch = git_metadata.get('current_branch')
                        
                        self.logging.log_info(f"Auto-detected git info: commit={git_commit[:8] if git_commit else 'none'}, branch={git_branch}")
                    else:
                        self.logging.log_info("Not a git repository - baseline will have limited traceability")
                except Exception as e:
                    self.logging.log_warning(
                        f"Failed to auto-detect git info: {e}",
                        {"operation": "establish_quality_baseline"})
            
            # Generate baseline ID if not provided
            if not baseline_id:
                baseline_id = f"{project_name}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            
            self.logging.log_operation("establish_quality_baseline", {
                "baseline_id": baseline_id,
                "project_name": project_name,
                "git_commit": git_commit[:8] if git_commit else None,
                "git_branch": git_branch,
                "retention_days": retention_days
            })
            
            # Use default configuration if not provided
            if not suite_configuration:
                suite_configuration = QualitySuiteConfiguration(
                    included_tools=[
                        QualityTool.RUFF,
                        QualityTool.MYPY,
                        QualityTool.BANDIT,
                        QualityTool.RADON,
                        QualityTool.VULTURE
                    ],
                    parallel_execution=True,
                    quality_threshold=8.0,
                    generate_report=False
                )
            
            # Execute comprehensive quality suite
            suite_result = self.execute_comprehensive_suite(suite_configuration)
            
            # Get tool versions and environment info
            tool_versions = {}
            python_version = "3.11"  # Default fallback
            pixi_environment = {}
            
            if self.pixi_integration:
                try:
                    project_info = self.pixi_integration.get_pixi_project_info()
                    python_version = project_info.get("python_version", python_version)
                    pixi_environment = project_info
                except Exception as e:
                    self.logging.log_warning(
                        f"Failed to get pixi info: {e}",
                        {"operation": "establish_quality_baseline"})
            
            if self.tool_management:
                for tool in suite_configuration.included_tools:
                    try:
                        version = self.tool_management.get_tool_version(tool)
                        if version:
                            tool_versions[tool.value] = version
                    except Exception as e:
                        self.logging.log_warning(
                            f"Failed to get version for {tool.value}: {e}",
                            {"operation": "establish_quality_baseline"})
            
            # Create baseline using trend analyzer
            baseline = self.trend_analyzer.establish_baseline(
                baseline_id=baseline_id,
                assessment_results=suite_result.individual_results,
                project_metadata={
                    "project_name": project_name,
                    "project_version": project_version,
                    "git_commit": git_commit,
                    "git_branch": git_branch,
                    "tool_versions": tool_versions,
                    "python_version": python_version,
                    "pixi_environment": pixi_environment,
                    "tags": tags or []
                },
                retention_days=retention_days
            )
            
            # Store baseline if data storage is available
            if self.data_storage:
                self.data_storage.store_baseline(baseline)
            
            return baseline
            
        except Exception as e:
            error_msg = f"Baseline establishment failed: {str(e)}"
            self.logging.log_error(error_msg, {
                "operation": "establish_quality_baseline",
                "baseline_id": baseline_id,
                "project_name": project_name
            })
            raise RuntimeError(error_msg)

    def compare_against_baseline(
        self,
        baseline_id: str,
        suite_configuration: Optional[QualitySuiteConfiguration] = None
    ) -> QualityComparison:
        """
        Compare current quality against historical baseline.
        
        Args:
            baseline_id: ID of baseline to compare against
            suite_configuration: Configuration for current assessment
            
        Returns:
            QualityComparison with trend analysis and recommendations
        """
        try:
            self.logging.log_operation("compare_against_baseline", {
                "baseline_id": baseline_id
            })
            
            # Use default configuration if not provided
            if not suite_configuration:
                suite_configuration = QualitySuiteConfiguration(
                    included_tools=[
                        QualityTool.RUFF,
                        QualityTool.MYPY,
                        QualityTool.BANDIT,
                        QualityTool.RADON,
                        QualityTool.VULTURE
                    ],
                    parallel_execution=True,
                    generate_report=False
                )
            
            # Execute current quality assessment
            current_suite = self.execute_comprehensive_suite(suite_configuration)
            
            # Compare against baseline using trend analyzer
            comparison = self.trend_analyzer.compare_against_baseline(
                baseline_id=baseline_id,
                current_results=current_suite.individual_results
            )
            
            return comparison
            
        except Exception as e:
            error_msg = f"Baseline comparison failed: {str(e)}"
            self.logging.log_error(error_msg, {
                "operation": "compare_against_baseline",
                "baseline_id": baseline_id
            })
            raise RuntimeError(error_msg)

    def apply_automated_fixes(
        self,
        fix_types: List[FixType],
        dry_run: bool = True,
        backup_before_fix: bool = True,
        validation_mode: FixValidationMode = FixValidationMode.STRICT
    ) -> AutomatedFixResult:
        """
        Apply automated fixes with safety validations.
        
        Args:
            fix_types: Types of fixes to apply
            dry_run: Whether to perform dry run only
            backup_before_fix: Whether to create backups
            validation_mode: Validation strictness level
            
        Returns:
            AutomatedFixResult with fix details and validation results
        """
        if not self.automated_fix:
            raise RuntimeError("Automated fix capability not available")
            
        try:
            self.logging.log_operation("apply_automated_fixes", {
                "fix_types": [ft.value for ft in fix_types],
                "dry_run": dry_run,
                "validation_mode": validation_mode.value
            })
            
            # Execute fixes through automated fix port
            result = self.automated_fix.apply_automated_fixes(
                fix_types=fix_types,
                dry_run=dry_run,
                backup_before_fix=backup_before_fix,
                validation_mode=validation_mode
            )
            
            # Log fix application
            if self.audit:
                self.audit.log_fix_application(
                    fix_types=fix_types,
                    files_modified=[fix.file_path for fix in result.successful_fixes],
                    success=len(result.failed_fixes) == 0,
                    metadata={
                        "dry_run": dry_run,
                        "validation_mode": validation_mode.value,
                        "total_changes": result.total_changes_applied
                    }
                )
            
            return result
            
        except Exception as e:
            error_msg = f"Automated fix application failed: {str(e)}"
            self.logging.log_error(error_msg, {
                "operation": "apply_automated_fixes",
                "fix_types": [ft.value for ft in fix_types]
            })
            raise RuntimeError(error_msg)

    def generate_quality_report(
        self,
        assessment_results: Optional[List[QualityAssessmentResult]] = None,
        format: ReportFormat = ReportFormat.MARKDOWN,
        template: ReportTemplate = ReportTemplate.STANDARD,
        include_sections: Optional[List[str]] = None,
        attach_raw_results: bool = False,
        baseline_comparison: Optional[QualityComparison] = None
    ) -> QualityReport:
        """
        Generate comprehensive quality report.
        
        Args:
            assessment_results: Results to include in report
            format: Report format
            template: Report template style
            include_sections: Specific sections to include
            attach_raw_results: Whether to attach raw tool outputs
            baseline_comparison: Optional baseline comparison data
            
        Returns:
            QualityReport with formatted content
        """
        if not self.quality_reporting:
            raise RuntimeError("Quality reporting capability not available")
            
        try:
            self.logging.log_operation("generate_quality_report", {
                "format": format.value,
                "template": template.value,
                "include_baseline": baseline_comparison is not None
            })
            
            # Use recent results if none provided
            if not assessment_results:
                if self.data_storage:
                    assessment_results = self.data_storage.query_assessment_history(
                        project_name="current_project",
                        limit=10
                    )
                else:
                    raise ValueError("No assessment results provided and data storage unavailable")
            
            # Generate report through reporting port
            report = self.quality_reporting.generate_comprehensive_report(
                assessment_results=assessment_results,
                format=format,
                template=template,
                include_sections=include_sections,
                attach_raw_results=attach_raw_results
            )
            
            # Add baseline comparison data if provided
            if baseline_comparison:
                trend_data = {
                    "comparison_id": baseline_comparison.comparison_id,
                    "baseline_id": baseline_comparison.baseline_id,
                    "overall_score_delta": baseline_comparison.overall_score_delta,
                    "trend_direction": baseline_comparison.trend_direction,
                    "regression_detected": baseline_comparison.regression_detected,
                    "significant_changes": baseline_comparison.significant_changes
                }
                report.trend_analysis = trend_data
            
            return report
            
        except Exception as e:
            error_msg = f"Quality report generation failed: {str(e)}"
            self.logging.log_error(error_msg, {
                "operation": "generate_quality_report",
                "format": format.value,
                "template": template.value
            })
            raise RuntimeError(error_msg)

    def get_quality_recommendations(
        self,
        assessment_results: Optional[List[QualityAssessmentResult]] = None,
        prioritize_by_impact: bool = True,
        include_automated_fixes: bool = True
    ) -> Dict[str, Any]:
        """
        Generate actionable quality improvement recommendations.
        
        Args:
            assessment_results: Results to analyze for recommendations
            prioritize_by_impact: Whether to prioritize by impact
            include_automated_fixes: Whether to include automated fix options
            
        Returns:
            Dictionary with categorized recommendations
        """
        try:
            self.logging.log_operation("get_quality_recommendations", {
                "prioritize_by_impact": prioritize_by_impact,
                "include_automated_fixes": include_automated_fixes
            })
            
            # Use recent results if none provided
            if not assessment_results:
                if self.data_storage:
                    assessment_results = self.data_storage.query_assessment_history(
                        project_name="current_project",
                        limit=5
                    )
                else:
                    raise ValueError("No assessment results provided and data storage unavailable")
            
            # Generate recommendations through quality analyzer
            recommendations = self.quality_analyzer.generate_recommendations(assessment_results)
            
            # Prioritize issues if requested
            prioritized_issues = []
            if prioritize_by_impact:
                prioritized_issues = self.quality_analyzer.prioritize_issues(assessment_results)
            
            # Detect quality patterns
            patterns = self.quality_analyzer.detect_quality_patterns(assessment_results)
            
            # Generate automated fix suggestions if requested
            automated_fixes = []
            if include_automated_fixes and self.automated_fix:
                # Analyze which fixes could be automated
                fixable_violations = []
                for result in assessment_results:
                    fixable_violations.extend([v for v in result.violations if v.fixable])
                
                if fixable_violations:
                    # Group by fix type
                    fix_types = set()
                    for violation in fixable_violations:
                        if "import" in violation.message.lower():
                            fix_types.add(FixType.IMPORTS)
                        elif "format" in violation.message.lower():
                            fix_types.add(FixType.FORMATTING)
                        # Add more fix type detection logic as needed
                    
                    automated_fixes = [
                        {
                            "fix_type": ft.value,
                            "description": f"Automated {ft.value} fixes available",
                            "estimated_fixes": len([v for v in fixable_violations 
                                                  if ft.value in v.message.lower()])
                        }
                        for ft in fix_types
                    ]
            
            return {
                "recommendations": recommendations,
                "prioritized_issues": prioritized_issues,
                "quality_patterns": patterns,
                "automated_fixes": automated_fixes,
                "generated_at": datetime.now(UTC).isoformat()
            }
            
        except Exception as e:
            error_msg = f"Quality recommendations generation failed: {str(e)}"
            self.logging.log_error(error_msg, {"operation": "get_quality_recommendations"})
            raise RuntimeError(error_msg)

    def health_check(self) -> SystemHealth:
        """
        Perform comprehensive system health monitoring.
        
        Returns:
            SystemHealth with component status and performance metrics
        """
        try:
            self.logging.log_operation("health_check", {})
            
            # Use system integration port if available, otherwise basic checks
            if self.system_integration:
                return self.system_integration.check_system_health()
            
            # Basic health check
            healthy = True
            active_issues = []
            performance_alerts = []
            recommendations = []
            
            # Check pixi environment
            pixi_healthy = True
            if self.pixi_integration:
                try:
                    validation = self.pixi_integration.validate_pixi_environment()
                    pixi_healthy = validation.success
                    if not pixi_healthy:
                        active_issues.append("Pixi environment validation failed")
                except Exception as e:
                    pixi_healthy = False
                    active_issues.append(f"Pixi integration error: {e}")
            
            # Check tool availability
            tools_available = True
            if self.tool_management:
                try:
                    tool_validation = self.tool_management.validate_tool_availability([
                        QualityTool.RUFF, QualityTool.MYPY, QualityTool.BANDIT
                    ])
                    tools_available = tool_validation.all_tools_available
                    if not tools_available:
                        active_issues.extend([f"Missing tool: {tool}" 
                                            for tool in tool_validation.missing_tools])
                except Exception as e:
                    tools_available = False
                    active_issues.append(f"Tool validation error: {e}")
            
            # Check cache system
            cache_healthy = True
            cache_hit_rate = 0.0
            if self.caching:
                try:
                    cache_stats = self.caching.get_cache_statistics()
                    cache_hit_rate = cache_stats.get("hit_rate", 0.0)
                    if cache_hit_rate < 0.1:  # Less than 10% hit rate
                        performance_alerts.append("Low cache hit rate detected")
                except Exception as e:
                    cache_healthy = False
                    active_issues.append(f"Cache system error: {e}")
            
            # Check performance metrics
            avg_assessment_time = 0.0
            if self._performance_metrics["total_assessments"] > 0:
                avg_assessment_time = (
                    self._performance_metrics["total_execution_time_ms"] / 
                    self._performance_metrics["total_assessments"]
                )
                
                if avg_assessment_time > 30000:  # More than 30 seconds
                    performance_alerts.append("High average assessment time detected")
            
            # Check file system
            filesystem_healthy = True
            if self.system_integration:
                try:
                    fs_check = self.system_integration.validate_file_permissions([
                        "src/", "pyproject.toml"
                    ])
                    filesystem_healthy = fs_check.success
                except Exception as e:
                    filesystem_healthy = False
                    active_issues.append(f"File system check failed: {e}")
            
            # Determine overall health
            healthy = (pixi_healthy and tools_available and cache_healthy and 
                      filesystem_healthy and len(active_issues) == 0)
            
            # Generate recommendations
            if not healthy:
                recommendations.append("Review active issues and fix system components")
            if len(performance_alerts) > 0:
                recommendations.append("Investigate performance issues")
            if cache_hit_rate < 0.2:
                recommendations.append("Consider adjusting cache settings")
            
            return SystemHealth(
                healthy=healthy,
                timestamp=datetime.now(UTC).isoformat(),
                pixi_environment_healthy=pixi_healthy,
                quality_tools_available=tools_available,
                cache_system_healthy=cache_healthy,
                filesystem_healthy=filesystem_healthy,
                average_assessment_time_ms=avg_assessment_time,
                cache_hit_rate=cache_hit_rate,
                active_issues=active_issues,
                performance_alerts=performance_alerts,
                recommendations=recommendations
            )
            
        except Exception as e:
            error_msg = f"Health check failed: {str(e)}"
            self.logging.log_error(error_msg, {"operation": "health_check"})
            
            return SystemHealth(
                healthy=False,
                timestamp=datetime.now(UTC).isoformat(),
                pixi_environment_healthy=False,
                quality_tools_available=False,
                cache_system_healthy=False,
                filesystem_healthy=False,
                average_assessment_time_ms=0.0,
                cache_hit_rate=0.0,
                active_issues=[error_msg],
                performance_alerts=[],
                recommendations=["Check system logs and fix critical errors"]
            )

    # Private helper methods

    def _execute_tools_parallel(
        self, 
        configuration: QualitySuiteConfiguration
    ) -> tuple[List[QualityAssessmentResult], List[QualityTool], List[QualityTool]]:
        """Execute quality tools in parallel."""
        individual_results = []
        failed_tools = []
        skipped_tools = []
        
        # Create futures for each tool
        futures = {}
        
        for tool in configuration.included_tools:
            try:
                if tool == QualityTool.RUFF:
                    future = self._executor.submit(
                        self.quality_executor.execute_lint_assessment,
                        tool=tool,
                        target_path="src/",
                        fix_mode=False
                    )
                elif tool == QualityTool.MYPY:
                    future = self._executor.submit(
                        self.quality_executor.execute_typecheck_assessment,
                        tool=tool,
                        strict_mode=False
                    )
                elif tool == QualityTool.BANDIT:
                    future = self._executor.submit(
                        self.quality_executor.execute_security_scan,
                        tool=tool
                    )
                elif tool == QualityTool.RADON:
                    future = self._executor.submit(
                        self.quality_executor.execute_complexity_analysis,
                        tool=tool
                    )
                elif tool == QualityTool.VULTURE:
                    future = self._executor.submit(
                        self.quality_executor.execute_dead_code_detection,
                        tool=tool
                    )
                else:
                    # Skip unsupported tools
                    skipped_tools.append(tool)
                    continue
                
                futures[tool] = future
                
            except Exception as e:
                self.logging.log_warning(
                    f"Failed to start {tool.value}: {e}",
                    {"operation": "_execute_tools_parallel"})
                failed_tools.append(tool)
        
        # Collect results
        for tool, future in futures.items():
            try:
                result = future.result(timeout=300)  # 5 minute timeout per tool
                individual_results.append(result)
            except concurrent.futures.TimeoutError:
                self.logging.log_error(
                    f"Tool {tool.value} timed out",
                    {"operation": "_execute_tools_parallel"})
                failed_tools.append(tool)
            except Exception as e:
                self.logging.log_error(
                    f"Tool {tool.value} failed: {e}",
                    {"operation": "_execute_tools_parallel"})
                failed_tools.append(tool)
        
        return individual_results, failed_tools, skipped_tools

    def _execute_tools_sequential(
        self, 
        configuration: QualitySuiteConfiguration
    ) -> tuple[List[QualityAssessmentResult], List[QualityTool], List[QualityTool]]:
        """Execute quality tools sequentially."""
        individual_results = []
        failed_tools = []
        skipped_tools = []
        
        for tool in configuration.included_tools:
            try:
                result = None
                
                if tool == QualityTool.RUFF:
                    result = self.quality_executor.execute_lint_assessment(
                        tool=tool, target_path="src/", fix_mode=False
                    )
                elif tool == QualityTool.MYPY:
                    result = self.quality_executor.execute_typecheck_assessment(
                        tool=tool, strict_mode=False
                    )
                elif tool == QualityTool.BANDIT:
                    result = self.quality_executor.execute_security_scan(tool=tool)
                elif tool == QualityTool.RADON:
                    result = self.quality_executor.execute_complexity_analysis(tool=tool)
                elif tool == QualityTool.VULTURE:
                    result = self.quality_executor.execute_dead_code_detection(tool=tool)
                else:
                    skipped_tools.append(tool)
                    continue
                
                if result:
                    individual_results.append(result)
                    
                    # Check fail-fast mode
                    if (configuration.fail_fast and 
                        result.status != ExecutionStatus.SUCCESS):
                        self.logging.log_info("Sequential execution stopped due to fail-fast mode")
                        break
                
            except Exception as e:
                self.logging.log_error(
                    f"Tool {tool.value} failed: {e}",
                    {"operation": "_execute_tools_sequential"})
                failed_tools.append(tool)
                
                # Check fail-fast mode
                if configuration.fail_fast:
                    self.logging.log_info("Sequential execution stopped due to fail-fast mode")
                    break
        
        return individual_results, failed_tools, skipped_tools

    def _validate_suite_configuration(self, configuration: QualitySuiteConfiguration) -> OperationResult:
        """Validate suite configuration."""
        try:
            # Check required fields
            if not configuration.included_tools:
                return OperationResult(
                    success=False,
                    operation_type="validate_suite_configuration",
                    message="No tools specified in configuration",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat()
                )
            
            # Check quality threshold
            if not (0.0 <= configuration.quality_threshold <= 10.0):
                return OperationResult(
                    success=False,
                    operation_type="validate_suite_configuration",
                    message="Quality threshold must be between 0.0 and 10.0",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat()
                )
            
            return OperationResult(
                success=True,
                operation_type="validate_suite_configuration",
                message="Configuration validation passed",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat()
            )
            
        except Exception as e:
            return OperationResult(
                success=False,
                operation_type="validate_suite_configuration",
                message=f"Configuration validation failed: {e}",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat()
            )

    def _aggregate_suite_results(self, results: List[QualityAssessmentResult]) -> QualityMetrics:
        """Aggregate results from multiple tools into overall metrics."""
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
        
        # Aggregate violation counts
        total_violations = sum(len(r.violations) for r in results)
        critical_violations = sum(
            len([v for v in r.violations if v.severity.value == "critical"]) 
            for r in results
        )
        high_violations = sum(
            len([v for v in r.violations if v.severity.value == "high"]) 
            for r in results
        )
        medium_violations = sum(
            len([v for v in r.violations if v.severity.value == "medium"]) 
            for r in results
        )
        low_violations = sum(
            len([v for v in r.violations if v.severity.value == "low"]) 
            for r in results
        )
        
        # Aggregate other metrics
        security_issues_count = sum(len(r.security_issues) for r in results)
        dead_code_count = sum(len(r.dead_code_results) for r in results)
        type_errors = sum(r.parsed_metrics.type_errors for r in results)
        
        # Calculate aggregated scores
        overall_scores = [r.parsed_metrics.overall_score for r in results if r.parsed_metrics.overall_score > 0]
        overall_score = sum(overall_scores) / len(overall_scores) if overall_scores else 0.0
        
        # Lines of code (take max to avoid double counting)
        total_lines = max((r.parsed_metrics.total_lines for r in results), default=0)
        code_lines = max((r.parsed_metrics.code_lines for r in results), default=0)
        comment_lines = max((r.parsed_metrics.comment_lines for r in results), default=0)
        blank_lines = max((r.parsed_metrics.blank_lines for r in results), default=0)
        
        return QualityMetrics(
            overall_score=overall_score,
            total_violations=total_violations,
            critical_violations=critical_violations,
            high_violations=high_violations,
            medium_violations=medium_violations,
            low_violations=low_violations,
            security_issues_count=security_issues_count,
            dead_code_count=dead_code_count,
            type_errors=type_errors,
            total_lines=total_lines,
            code_lines=code_lines,
            comment_lines=comment_lines,
            blank_lines=blank_lines
        )

    def _extract_critical_issues(self, results: List[QualityAssessmentResult]) -> List[str]:
        """Extract critical issues from assessment results."""
        critical_issues = []
        
        for result in results:
            # Critical violations
            critical_violations = [v for v in result.violations if v.severity.value == "critical"]
            for violation in critical_violations[:5]:  # Limit to top 5
                critical_issues.append(
                    f"Critical {result.tool.value}: {violation.message} in {violation.file_path}:{violation.line_number}"
                )
            
            # High severity security issues
            high_security = [s for s in result.security_issues if s.severity.value == "high"]
            for issue in high_security[:3]:  # Limit to top 3
                critical_issues.append(
                    f"Security {result.tool.value}: {issue.title} in {issue.file_path}:{issue.line_number}"
                )
        
        return critical_issues[:10]  # Overall limit

    def _generate_next_steps(
        self, 
        results: List[QualityAssessmentResult], 
        configuration: QualitySuiteConfiguration
    ) -> List[str]:
        """Generate next steps based on assessment results."""
        next_steps = []
        
        # Check if quality threshold was met
        overall_score = self.quality_analyzer.calculate_quality_score(results)
        if overall_score < configuration.quality_threshold:
            next_steps.append(f"Improve quality score from {overall_score:.1f} to meet threshold {configuration.quality_threshold}")
        
        # Suggest fixes for critical issues
        critical_count = sum(
            len([v for v in r.violations if v.severity.value == "critical"]) 
            for r in results
        )
        if critical_count > 0:
            next_steps.append(f"Address {critical_count} critical violations immediately")
        
        # Suggest automated fixes if available
        fixable_count = sum(
            len([v for v in r.violations if v.fixable]) 
            for r in results
        )
        if fixable_count > 0 and self.automated_fix:
            next_steps.append(f"Apply automated fixes for {fixable_count} fixable issues")
        
        # Security recommendations
        security_count = sum(len(r.security_issues) for r in results)
        if security_count > 0:
            next_steps.append(f"Review and address {security_count} security issues")
        
        return next_steps

    def _generate_cache_key(
        self, 
        tool: QualityTool, 
        assessment_type: QualityAssessmentType, 
        target_path: str, 
        config: Dict[str, Any]
    ) -> str:
        """Generate cache key for assessment."""
        if self.caching:
            # Use proper config hash
            config_str = json.dumps(config, sort_keys=True)
            config_hash = str(hash(config_str))
            return self.caching.generate_cache_key(tool, assessment_type, target_path, config_hash)
        
        # Fallback implementation
        config_str = json.dumps(config, sort_keys=True)
        return f"{tool.value}:{assessment_type.value}:{target_path}:{hash(config_str)}"

    def _update_performance_metrics(self, execution_time_ms: float):
        """Update internal performance metrics."""
        self._performance_metrics["total_assessments"] += 1
        self._performance_metrics["total_execution_time_ms"] += execution_time_ms

    def _create_error_result(
        self,
        tool: QualityTool,
        assessment_type: QualityAssessmentType,
        execution_time_ms: float,
        error_msg: str,
        target_path: str,
        pixi_task_used: str = "unknown"
    ) -> QualityAssessmentResult:
        """Create error result for failed assessments."""
        return QualityAssessmentResult(
            assessment_type=assessment_type,
            tool=tool,
            status=ExecutionStatus.ERROR,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=execution_time_ms,
            pixi_task_used=pixi_task_used,
            target_path=target_path,
            files_analyzed=0,
            raw_output=error_msg,
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
                blank_lines=0
            ),
            violations=[],
            security_issues=[],
            complexity_results=[],
            dead_code_results=[],
            recommendations=[f"Fix error: {error_msg}"],
            auto_fix_available=False,
            fix_commands=[]
        )

    def cleanup(self):
        """Clean up resources when shutting down."""
        try:
            self._executor.shutdown(wait=True)
            self.logging.log_info("Quality orchestration service cleanup completed")
        except Exception as e:
            self.logging.log_error(f"Error during cleanup: {e}", {"operation": "cleanup"})