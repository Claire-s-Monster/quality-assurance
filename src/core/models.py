"""
Core domain models for Quality Assurance MCP Server.

These models represent the business domain for quality assessment operations,
consolidating 26 quality functions into unified pixi-first platform.
"""

from enum import Enum
from typing import Any, Optional, Dict, List
import uuid

from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Quality Tool and Execution Models
# =============================================================================


class QualityTool(str, Enum):
    """Supported quality assessment tools."""

    RUFF = "ruff"
    MYPY = "mypy"
    BANDIT = "bandit"
    RADON = "radon"
    VULTURE = "vulture"
    PYTEST = "pytest"
    COVERAGE = "coverage"
    FLAKE8 = "flake8"
    PYLINT = "pylint"


class QualityAssessmentType(str, Enum):
    """Types of quality assessments."""

    LINT = "lint"
    TYPECHECK = "typecheck"
    SECURITY = "security"
    COMPLEXITY = "complexity"
    DEAD_CODE = "dead_code"
    COMPREHENSIVE = "comprehensive"
    BASELINE = "baseline"
    COMPARISON = "comparison"


class ExecutionStatus(str, Enum):
    """Quality assessment execution status."""

    SUCCESS = "success"
    FAILURE = "failure"
    WARNING = "warning"
    TIMEOUT = "timeout"
    ERROR = "error"


class ViolationSeverity(str, Enum):
    """Quality violation severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# =============================================================================
# Quality Violation and Issue Models
# =============================================================================


class QualityViolation(BaseModel):
    """Individual quality violation found during assessment."""

    tool: QualityTool = Field(description="Tool that detected the violation")
    rule_code: str = Field(description="Rule/check code (e.g., 'F401', 'E9')")
    message: str = Field(description="Violation description")
    severity: ViolationSeverity = Field(description="Violation severity")
    file_path: str = Field(description="File where violation occurred")
    line_number: int = Field(description="Line number of violation")
    column_number: Optional[int] = Field(None, description="Column number if available")
    fix_suggestion: Optional[str] = Field(None, description="Suggested fix")
    fixable: bool = Field(
        default=False, description="Whether violation can be auto-fixed"
    )


class SecurityIssue(BaseModel):
    """Security vulnerability identified by security scanning."""

    issue_id: str = Field(description="Unique issue identifier")
    title: str = Field(description="Security issue title")
    description: str = Field(description="Detailed issue description")
    severity: ViolationSeverity = Field(description="Security issue severity")
    confidence: str = Field(description="Detection confidence: high, medium, low")
    file_path: str = Field(description="File containing the issue")
    line_number: int = Field(description="Line number of issue")
    test_id: str = Field(description="Security test identifier")
    cwe_id: Optional[str] = Field(None, description="CWE identifier if applicable")
    remediation: Optional[str] = Field(None, description="Remediation guidance")


class ComplexityMetric(BaseModel):
    """Code complexity metrics for a specific function or module."""

    name: str = Field(description="Function/module name")
    complexity_score: int = Field(description="Cyclomatic complexity score")
    maintainability_index: float = Field(description="Maintainability index (0-100)")
    lines_of_code: int = Field(description="Lines of code")
    difficulty: float = Field(description="Halstead difficulty metric")
    effort: float = Field(description="Halstead effort metric")
    time_to_understand: float = Field(
        description="Estimated time to understand (seconds)"
    )


class DeadCodeResult(BaseModel):
    """Dead code detection result."""

    file_path: str = Field(description="File containing dead code")
    line_number: int = Field(description="Line number of dead code")
    symbol_name: str = Field(description="Name of unused symbol")
    symbol_type: str = Field(description="Type of symbol: function, class, variable")
    confidence: int = Field(description="Detection confidence percentage (0-100)")
    used_outside_scope: bool = Field(
        description="Whether symbol might be used outside analyzed scope"
    )


# =============================================================================
# Quality Assessment Results
# =============================================================================


class QualityMetrics(BaseModel):
    """Comprehensive quality metrics for a codebase."""

    overall_score: float = Field(description="Overall quality score (0-10)")

    # Violation counts
    total_violations: int = Field(description="Total number of violations")
    critical_violations: int = Field(description="Critical violations count")
    high_violations: int = Field(description="High severity violations")
    medium_violations: int = Field(description="Medium severity violations")
    low_violations: int = Field(description="Low severity violations")

    # Coverage metrics
    test_coverage_percentage: Optional[float] = Field(
        None, description="Test coverage percentage"
    )
    branch_coverage_percentage: Optional[float] = Field(
        None, description="Branch coverage percentage"
    )

    # Complexity metrics
    average_complexity: Optional[float] = Field(
        None, description="Average cyclomatic complexity"
    )
    max_complexity: Optional[int] = Field(None, description="Maximum complexity found")
    maintainability_index: Optional[float] = Field(
        None, description="Overall maintainability index"
    )

    # Security metrics
    security_issues_count: int = Field(
        default=0, description="Number of security issues"
    )
    high_security_issues: int = Field(
        default=0, description="High severity security issues"
    )

    # Dead code metrics
    dead_code_count: int = Field(default=0, description="Number of dead code instances")
    unused_imports: int = Field(default=0, description="Number of unused imports")

    # Type checking
    type_errors: int = Field(default=0, description="Number of type checking errors")
    type_coverage: Optional[float] = Field(
        None, description="Type annotation coverage percentage"
    )

    # Lines of code
    total_lines: int = Field(description="Total lines of code")
    code_lines: int = Field(description="Lines containing code")
    comment_lines: int = Field(description="Lines containing comments")
    blank_lines: int = Field(description="Blank lines")


class QualityAssessmentResult(BaseModel):
    """Result of a quality assessment operation."""

    assessment_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique assessment ID"
    )
    assessment_type: QualityAssessmentType = Field(
        description="Type of assessment performed"
    )
    tool: QualityTool = Field(description="Primary tool used for assessment")
    status: ExecutionStatus = Field(description="Assessment execution status")

    # Execution metadata
    start_time: str = Field(description="Assessment start timestamp (ISO8601)")
    end_time: str = Field(description="Assessment completion timestamp (ISO8601)")
    execution_time_ms: float = Field(description="Execution time in milliseconds")
    pixi_task_used: Optional[str] = Field(
        None, description="Pixi task executed for assessment (None = no task resolved)"
    )
    environment_used: Optional[str] = Field(
        None, description="Pixi environment the task ran in (None = pixi default)"
    )
    environment_auto_selected: bool = Field(
        default=False, description="Whether the environment was chosen automatically"
    )

    target_paths_mode: Optional[str] = Field(
        None,
        description=(
            "How suite target_paths were applied: 'replaced' (task's paths swapped) "
            "or 'appended' (task ran as-is with paths added, so src/ is still "
            "scanned). None when target_paths was not used."
        ),
    )
    target_paths_fallback_reason: Optional[str] = Field(
        None, description="Why target_paths were appended instead of replacing"
    )

    # Assessment scope
    target_path: str = Field(description="Path that was assessed")
    files_analyzed: int = Field(description="Number of files analyzed")
    excluded_patterns: List[str] = Field(
        default_factory=list, description="Patterns excluded from analysis"
    )

    # Results
    raw_output: str = Field(description="Raw tool output")
    parsed_metrics: QualityMetrics = Field(description="Parsed quality metrics")
    violations: List[QualityViolation] = Field(
        default_factory=list, description="Quality violations found"
    )
    security_issues: List[SecurityIssue] = Field(
        default_factory=list, description="Security issues found"
    )
    complexity_results: List[ComplexityMetric] = Field(
        default_factory=list, description="Complexity analysis results"
    )
    dead_code_results: List[DeadCodeResult] = Field(
        default_factory=list, description="Dead code detection results"
    )

    # Recommendations
    recommendations: List[str] = Field(
        default_factory=list, description="Quality improvement recommendations"
    )
    auto_fix_available: bool = Field(
        default=False, description="Whether auto-fixes are available"
    )
    fix_commands: List[str] = Field(
        default_factory=list, description="Commands to apply fixes"
    )

    # Baseline comparison (if applicable)
    baseline_comparison: Optional[Dict[str, Any]] = Field(
        None, description="Comparison with baseline metrics"
    )


# =============================================================================
# Quality Baseline and Trend Analysis
# =============================================================================


class QualityBaseline(BaseModel):
    """Quality baseline for trend analysis and comparison."""

    baseline_id: str = Field(description="Unique baseline identifier")
    created_at: str = Field(description="Baseline creation timestamp (ISO8601)")

    # Project metadata
    project_name: str = Field(description="Project name")
    project_version: Optional[str] = Field(None, description="Project version")
    git_commit: Optional[str] = Field(None, description="Git commit hash")
    git_branch: Optional[str] = Field(None, description="Git branch")

    # Quality metrics at baseline
    metrics: QualityMetrics = Field(description="Quality metrics at time of baseline")
    overall_score: Optional[float] = Field(
        None,
        description="Overall quality score for this baseline (defaults to metrics.overall_score)",
    )

    # Tool versions used
    tool_versions: Dict[str, str] = Field(
        default_factory=dict, description="Versions of tools used"
    )
    python_version: str = Field(description="Python version used")
    pixi_environment: Dict[str, Any] = Field(
        default_factory=dict, description="Pixi environment metadata"
    )

    # Retention metadata
    retention_days: int = Field(default=365, description="Days to retain this baseline")
    expires_at: str = Field(description="Baseline expiration timestamp (ISO8601)")
    tags: List[str] = Field(
        default_factory=list, description="Baseline tags for organization"
    )

    @model_validator(mode="after")
    def _default_overall_score(self) -> "QualityBaseline":
        """Derive overall_score from metrics when not supplied (older stored baselines)."""
        if self.overall_score is None:
            self.overall_score = self.metrics.overall_score
        return self


class QualityComparison(BaseModel):
    """Comparison between current metrics and a baseline."""

    comparison_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique comparison ID"
    )
    baseline_id: str = Field(description="Baseline used for comparison")
    current_assessment_id: str = Field(description="Current assessment being compared")
    comparison_timestamp: str = Field(description="Comparison timestamp (ISO8601)")

    # Metric deltas
    overall_score_delta: float = Field(description="Change in overall quality score")
    violation_count_delta: int = Field(description="Change in total violations")
    critical_violation_delta: int = Field(description="Change in critical violations")
    security_issue_delta: int = Field(description="Change in security issues")
    complexity_delta: Optional[float] = Field(
        None, description="Change in average complexity"
    )
    coverage_delta: Optional[float] = Field(None, description="Change in test coverage")

    # Trend analysis
    trend_direction: str = Field(
        description="Overall trend: improving, degrading, stable"
    )
    regression_detected: bool = Field(description="Whether quality regression detected")
    significant_changes: List[str] = Field(
        default_factory=list, description="Significant changes identified"
    )

    # Recommendations
    trend_recommendations: List[str] = Field(
        default_factory=list, description="Trend-based recommendations"
    )
    regression_alerts: List[str] = Field(
        default_factory=list, description="Regression alerts"
    )


# =============================================================================
# Comprehensive Quality Suite and Orchestration
# =============================================================================


class QualitySuiteConfiguration(BaseModel):
    """Configuration for comprehensive quality suite execution."""

    included_tools: List[QualityTool] = Field(description="Tools to include in suite")
    parallel_execution: bool = Field(
        default=True, description="Whether to run tools in parallel"
    )
    fail_fast: bool = Field(
        default=False, description="Stop execution on first failure"
    )
    quality_threshold: float = Field(
        default=8.0, description="Minimum quality score required"
    )

    # Tool-specific configurations
    lint_config: Dict[str, Any] = Field(
        default_factory=dict, description="Linting tool configuration"
    )
    typecheck_config: Dict[str, Any] = Field(
        default_factory=dict, description="Type checking configuration"
    )
    security_config: Dict[str, Any] = Field(
        default_factory=dict, description="Security scanning configuration"
    )
    complexity_config: Dict[str, Any] = Field(
        default_factory=dict, description="Complexity analysis configuration"
    )

    target_paths: Optional[List[str]] = Field(
        default=None,
        description="Validated paths (relative to project root) to analyze; "
        "None keeps each tool's default scope",
    )

    # Output configuration
    generate_report: bool = Field(
        default=True, description="Generate comprehensive report"
    )
    report_format: str = Field(
        default="markdown", description="Report format: markdown, json, html"
    )


class ComprehensiveQualityResult(BaseModel):
    """Result of comprehensive quality suite execution."""

    suite_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique suite execution ID",
    )
    configuration: QualitySuiteConfiguration = Field(
        description="Suite configuration used"
    )

    # Execution metadata
    start_time: str = Field(description="Suite start timestamp (ISO8601)")
    end_time: str = Field(description="Suite completion timestamp (ISO8601)")
    total_execution_time_ms: float = Field(
        description="Total execution time in milliseconds"
    )
    executed_in_parallel: bool = Field(
        description="Whether tools were executed in parallel"
    )

    # Individual tool results
    individual_results: List[QualityAssessmentResult] = Field(
        default_factory=list, description="Results from each tool"
    )
    failed_tools: List[str] = Field(
        default_factory=list, description="Tools that failed to execute"
    )
    skipped_tools: List[str] = Field(
        default_factory=list, description="Tools that were skipped"
    )

    # Aggregated metrics
    overall_metrics: QualityMetrics = Field(description="Aggregated quality metrics")
    overall_score: float = Field(description="Overall quality score (0-10)")
    meets_threshold: bool = Field(
        description="Whether quality meets configured threshold"
    )

    # Suite-level analysis
    critical_issues_summary: List[str] = Field(
        default_factory=list, description="Summary of critical issues"
    )
    improvement_priorities: List[str] = Field(
        default_factory=list, description="Prioritized improvement recommendations"
    )
    next_steps: List[str] = Field(
        default_factory=list, description="Recommended next steps"
    )

    # Report generation
    report_generated: bool = Field(
        description="Whether comprehensive report was generated"
    )
    report_path: Optional[str] = Field(None, description="Path to generated report")


# =============================================================================
# Automated Fix Application
# =============================================================================


class FixType(str, Enum):
    """Types of automated fixes available."""

    IMPORTS = "imports"  # Remove unused imports, sort imports
    FORMATTING = "formatting"  # Code formatting fixes
    SIMPLE_ISSUES = "simple_issues"  # Simple linting fixes (e.g., trailing whitespace)
    SECURITY = "security"  # Low-risk security fixes
    TYPE_ANNOTATIONS = "type_annotations"  # Add missing type annotations
    UNUSED_VARIABLES = "unused_variables"  # Remove unused variables and dead code


class FixValidationMode(str, Enum):
    """Validation modes for automated fixes."""

    STRICT = "strict"  # Comprehensive validation before applying
    PERMISSIVE = "permissive"  # Basic validation only
    CUSTOM = "custom"  # Custom validation rules


class FixResult(BaseModel):
    """Result of applying an automated fix."""

    fix_type: FixType = Field(description="Type of fix applied")
    file_path: str = Field(description="File that was modified")
    original_content_hash: str = Field(description="Hash of original file content")
    modified_content_hash: str = Field(description="Hash of modified file content")
    lines_changed: int = Field(description="Number of lines changed")

    # Fix details
    changes_applied: List[str] = Field(
        default_factory=list, description="Description of changes applied"
    )
    backup_created: bool = Field(description="Whether backup was created")
    backup_path: Optional[str] = Field(None, description="Path to backup file")

    # Validation
    validation_passed: bool = Field(description="Whether post-fix validation passed")
    validation_errors: List[str] = Field(
        default_factory=list, description="Validation errors if any"
    )


class AutomatedFixResult(BaseModel):
    """Result of automated fix application operation."""

    fix_session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique fix session ID"
    )
    requested_fix_types: List[FixType] = Field(description="Types of fixes requested")
    dry_run: bool = Field(description="Whether this was a dry run")
    validation_mode: FixValidationMode = Field(description="Validation mode used")

    # Execution metadata
    start_time: str = Field(description="Fix session start timestamp (ISO8601)")
    end_time: str = Field(description="Fix session completion timestamp (ISO8601)")
    execution_time_ms: float = Field(description="Total execution time in milliseconds")

    # Results
    successful_fixes: List[FixResult] = Field(
        default_factory=list, description="Successfully applied fixes"
    )
    failed_fixes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Failed fix attempts"
    )
    skipped_fixes: List[Dict[str, Any]] = Field(
        default_factory=list, description="Skipped fixes with reasons"
    )

    # Validation and safety
    pre_fix_validation: Optional[QualityAssessmentResult] = Field(
        None,
        description="Quality assessment before fixes (None if no assessment was run)",
    )
    post_fix_validation: Optional[QualityAssessmentResult] = Field(
        None, description="Quality assessment after fixes"
    )
    rollback_available: bool = Field(description="Whether rollback is available")
    rollback_commands: List[str] = Field(
        default_factory=list, description="Commands to rollback changes"
    )
    rollback_command: Optional[str] = Field(
        None, description="Primary rollback command"
    )
    backup_created: bool = Field(
        default=False, description="Whether backup was created"
    )
    backup_path: Optional[str] = Field(None, description="Path to backup directory")

    # Summary
    total_files_modified: int = Field(description="Total number of files modified")
    total_changes_applied: int = Field(description="Total number of individual changes")
    quality_improvement: Optional[float] = Field(
        None, description="Quality score improvement"
    )

    # Recommendations
    additional_manual_fixes: List[str] = Field(
        default_factory=list, description="Suggested manual fixes"
    )
    next_automation_opportunities: List[str] = Field(
        default_factory=list, description="Future automation opportunities"
    )


# =============================================================================
# Quality Reporting and Analysis
# =============================================================================


class ReportFormat(str, Enum):
    """Supported quality report formats."""

    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"
    PDF = "pdf"
    CSV = "csv"


class ReportTemplate(str, Enum):
    """Report template styles."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"
    EXECUTIVE = "executive"


class QualityReport(BaseModel):
    """Comprehensive quality assessment report."""

    report_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique report ID"
    )
    report_format: ReportFormat = Field(description="Report format")
    template_style: ReportTemplate = Field(description="Template style used")
    generated_at: str = Field(description="Report generation timestamp (ISO8601)")

    # Report metadata
    project_name: str = Field(description="Project name")
    assessment_period: str = Field(description="Time period covered by report")
    generated_by: str = Field(description="Report generation source")

    # Quality summary
    executive_summary: str = Field(description="Executive summary of quality status")
    overall_score: float = Field(description="Overall quality score")
    quality_grade: str = Field(description="Quality grade: A, B, C, D, F")
    trend_direction: str = Field(description="Quality trend direction")

    # Detailed sections
    sections_included: List[str] = Field(description="Report sections included")
    quality_metrics: QualityMetrics = Field(description="Detailed quality metrics")
    trend_analysis: Optional[Dict[str, Any]] = Field(
        None, description="Trend analysis data"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Quality improvement recommendations"
    )

    # Raw data attachment
    raw_results_attached: bool = Field(
        description="Whether raw tool results are attached"
    )
    raw_results_path: Optional[str] = Field(
        None, description="Path to raw results file"
    )

    # Report content
    report_content: str = Field(description="Formatted report content")
    report_path: Optional[str] = Field(None, description="Path to saved report file")
    export_paths: Dict[str, str] = Field(
        default_factory=dict, description="Paths to exported formats"
    )


# =============================================================================
# Tool Management and Configuration
# =============================================================================


class ToolAvailability(BaseModel):
    """Tool availability and version information."""

    tool: QualityTool = Field(description="Quality tool")
    available: bool = Field(description="Whether tool is available in environment")
    version: Optional[str] = Field(None, description="Tool version if available")
    pixi_installed: bool = Field(description="Whether tool is installed via pixi")
    meets_requirements: bool = Field(description="Whether version meets requirements")
    required_version: Optional[str] = Field(
        None, description="Minimum required version"
    )
    installation_command: Optional[str] = Field(
        None, description="Command to install tool"
    )


class ToolValidationResult(BaseModel):
    """Result of tool availability validation."""

    validation_timestamp: str = Field(description="Validation timestamp (ISO8601)")
    all_tools_available: bool = Field(
        description="Whether all required tools are available"
    )

    # Individual tool status
    tool_status: List[ToolAvailability] = Field(description="Status of each tool")
    missing_tools: List[str] = Field(
        default_factory=list, description="Tools that are missing"
    )
    outdated_tools: List[str] = Field(
        default_factory=list, description="Tools that need updating"
    )

    # Environment information
    pixi_environment_active: bool = Field(
        description="Whether pixi environment is active"
    )
    python_version: str = Field(description="Python version in environment")
    pixi_project_status: Dict[str, Any] = Field(
        default_factory=dict, description="Pixi project status"
    )

    # Recommendations
    installation_commands: List[str] = Field(
        default_factory=list, description="Commands to install missing tools"
    )
    update_commands: List[str] = Field(
        default_factory=list, description="Commands to update outdated tools"
    )


class ConfigurationUpdate(BaseModel):
    """Configuration update for quality tools."""

    tool: QualityTool = Field(description="Tool to configure")
    config_updates: Dict[str, Any] = Field(description="Configuration changes to apply")
    validate_before_apply: bool = Field(
        default=True, description="Validate configuration before applying"
    )
    backup_existing: bool = Field(
        default=True, description="Backup existing configuration"
    )

    # Update metadata
    update_reason: str = Field(description="Reason for configuration update")
    applied_by: str = Field(description="Who/what applied the update")


class ConfigurationResult(BaseModel):
    """Result of configuration update operation."""

    tool: QualityTool = Field(description="Tool that was configured")
    update_successful: bool = Field(description="Whether update was successful")

    # Configuration details
    config_file_path: str = Field(description="Path to configuration file")
    backup_created: bool = Field(description="Whether backup was created")
    backup_path: Optional[str] = Field(None, description="Path to backup file")

    # Validation
    validation_passed: bool = Field(
        description="Whether configuration validation passed"
    )
    validation_errors: List[str] = Field(
        default_factory=list, description="Validation errors if any"
    )

    # Changes applied
    changes_summary: List[str] = Field(
        default_factory=list, description="Summary of changes applied"
    )
    rollback_available: bool = Field(description="Whether rollback is available")
    rollback_commands: List[str] = Field(
        default_factory=list, description="Commands to rollback changes"
    )

    # Metadata
    applied_at: str = Field(description="Configuration update timestamp (ISO8601)")
    applied_by: str = Field(description="Update source identifier")


# =============================================================================
# Operation Results and System Models
# =============================================================================


class OperationResult(BaseModel):
    """Generic operation result."""

    success: bool = Field(description="Whether operation succeeded")
    operation_type: str = Field(description="Type of operation performed")
    message: str = Field(description="Operation result message")

    # Execution details
    execution_time_ms: float = Field(description="Execution time in milliseconds")
    timestamp: str = Field(description="Operation timestamp (ISO8601)")

    # Additional data
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional operation details"
    )
    warnings: List[str] = Field(default_factory=list, description="Operation warnings")
    errors: List[str] = Field(default_factory=list, description="Operation errors")


class SystemHealth(BaseModel):
    """Quality assurance system health status."""

    healthy: bool = Field(description="Overall system health status")
    timestamp: str = Field(description="Health check timestamp (ISO8601)")

    # Component health
    pixi_environment_healthy: bool = Field(description="Pixi environment health")
    quality_tools_available: Optional[bool] = Field(
        None, description="Quality tools availability (None if not cheaply probeable)"
    )
    cache_system_healthy: bool = Field(description="Cache system health")
    filesystem_healthy: bool = Field(description="File system health")

    # Performance metrics
    average_assessment_time_ms: Optional[float] = Field(
        None,
        description="Average assessment execution time (None if no real data recorded)",
    )
    cache_hit_rate: Optional[float] = Field(
        None, description="Cache hit rate percentage (None if no real data recorded)"
    )

    # Issues and alerts
    active_issues: List[str] = Field(
        default_factory=list, description="Active system issues"
    )
    performance_alerts: List[str] = Field(
        default_factory=list, description="Performance alerts"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="System health recommendations"
    )


# =============================================================================
# Pixi Execution Models
# =============================================================================


class PixiExecutionContext(BaseModel):
    """Context for pixi task execution."""

    working_dir: str = Field(description="Working directory for execution")
    environment_vars: Dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )
    timeout_seconds: int = Field(
        default=300, description="Execution timeout in seconds"
    )
    capture_output: bool = Field(
        default=True, description="Whether to capture stdout/stderr"
    )


class PixiTaskResult(BaseModel):
    """Result of pixi task execution."""

    success: bool = Field(description="Whether task executed successfully")
    stdout: str = Field(description="Standard output from task")
    stderr: str = Field(description="Standard error from task")
    exit_code: int = Field(description="Task exit code")
    execution_time: float = Field(description="Execution time in seconds")


class PixiHealthCheck(BaseModel):
    """Pixi environment health check result."""

    pixi_available: bool = Field(description="Whether pixi is available")
    project_exists: bool = Field(description="Whether pixi.toml exists")
    environment_synced: bool = Field(description="Whether environment is synced")
    lock_file_exists: bool = Field(description="Whether pixi.lock exists")
    issues: List[str] = Field(default_factory=list, description="Health check issues")
    recommendations: List[str] = Field(
        default_factory=list, description="Health recommendations"
    )


class PixiOperationResult(BaseModel):
    """Result of pixi operation."""

    success: bool = Field(description="Whether operation succeeded")
    message: str = Field(description="Operation result message")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Operation details"
    )
    execution_time_ms: float = Field(description="Execution time in milliseconds")
    timestamp: str = Field(description="Operation timestamp")


class PixiProjectInfo(BaseModel):
    """Information about pixi project."""

    project_name: str = Field(description="Project name")
    project_path: str = Field(description="Project root path")
    has_pixi_toml: bool = Field(description="Whether pixi.toml exists")
    has_lock_file: bool = Field(description="Whether pixi.lock exists")
    environment_synced: bool = Field(description="Whether environment is synced")
    available_tasks: List[str] = Field(
        default_factory=list, description="Available pixi tasks"
    )
    python_version: Optional[str] = Field(None, description="Python version")
    dependencies: Dict[str, str] = Field(
        default_factory=dict, description="Project dependencies"
    )


class PixiEnvironmentInfo(BaseModel):
    """Information about pixi environment."""

    environment_active: bool = Field(description="Whether pixi environment is active")
    environment_path: str = Field(description="Path to environment")
    python_executable: str = Field(description="Path to Python executable")
    packages_installed: Dict[str, str] = Field(
        default_factory=dict, description="Installed packages"
    )
    environment_variables: Dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )


# =============================================================================
# Error and Exception Models
# =============================================================================


class QualityAssessmentError(Exception):
    """Quality assessment operation error."""

    def __init__(
        self, message: str, tool: Optional[str] = None, error_code: Optional[str] = None
    ):
        self.message = message
        self.tool = tool
        self.error_code = error_code
        super().__init__(self.message)


class ToolExecutionError(Exception):
    """Tool execution error."""

    def __init__(self, tool: str, command: str, exit_code: int, stderr: str):
        self.tool = tool
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr
        super().__init__(
            f"Tool {tool} execution failed with exit code {exit_code}: {stderr}"
        )


class ValidationError(Exception):
    """Configuration or input validation error."""

    def __init__(self, message: str, field: Optional[str] = None):
        self.message = message
        self.field = field
        super().__init__(self.message)
