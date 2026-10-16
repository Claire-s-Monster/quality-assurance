"""
Port interfaces for Quality Assurance MCP Server.

This module defines the abstract interfaces for external dependencies,
following hexagonal architecture patterns for pixi-first quality assessment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict, List

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
)


# =============================================================================
# Infrastructure Ports (Required by adapters)
# =============================================================================


class LoggingPort(ABC):
    """Port for logging operations."""

    @abstractmethod
    def log_operation(
        self, operation: str, details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an operation."""
        pass

    @abstractmethod
    def log_operation_result(
        self,
        operation: str,
        success: bool,
        execution_time_ms: float,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log operation result."""
        pass

    @abstractmethod
    def log_error(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log an error (message first; put the operation name in context)."""
        pass

    @abstractmethod
    def log_warning(
        self, message: str, context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log a warning (message first; put the operation name in context)."""
        pass

    @abstractmethod
    def log_info(self, message: str, context: Optional[Dict[str, Any]] = None) -> None:
        """Log informational message."""
        pass


# =============================================================================
# Quality Tool Execution Ports
# =============================================================================


class QualityToolExecutionPort(ABC):
    """Port for executing quality assessment tools via pixi."""

    @abstractmethod
    def execute_lint_assessment(
        self,
        tool: QualityTool,
        target_path: str = "src/",
        rules: Optional[List[str]] = None,
        fix_mode: bool = False,
        output_format: str = "json",
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None,
        target_paths: Optional[List[str]] = None,
    ) -> QualityAssessmentResult:
        """Execute linting tools via pixi with intelligent result parsing."""
        pass

    @abstractmethod
    def execute_typecheck_assessment(
        self,
        tool: QualityTool = QualityTool.MYPY,
        target_path: str = "src/",
        strict_mode: bool = False,
        config_file: Optional[str] = None,
        incremental: bool = True,
        cache_dir: Optional[str] = None,
        project_path: Optional[str] = None,
        environment: Optional[str] = None,
        target_paths: Optional[List[str]] = None,
    ) -> QualityAssessmentResult:
        """Execute type checking tools via pixi with comprehensive analysis."""
        pass

    @abstractmethod
    def execute_security_scan(
        self,
        tool: QualityTool = QualityTool.BANDIT,
        target_path: str = "src/",
        severity_threshold: str = "medium",
        exclude_tests: bool = True,
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None,
        target_paths: Optional[List[str]] = None,
    ) -> QualityAssessmentResult:
        """Execute security vulnerability scanning via pixi."""
        pass

    @abstractmethod
    def execute_complexity_analysis(
        self,
        tool: QualityTool = QualityTool.RADON,
        target_path: str = "src/",
        complexity_threshold: int = 10,
        include_metrics: Optional[List[str]] = None,
        use_cache: bool = True,
        project_path: Optional[str] = None,
        environment: Optional[str] = None,
        target_paths: Optional[List[str]] = None,
    ) -> QualityAssessmentResult:
        """Analyze code complexity metrics via pixi."""
        pass

    @abstractmethod
    def execute_dead_code_detection(
        self,
        tool: QualityTool = QualityTool.VULTURE,
        aggressive_mode: bool = False,
        exclude_patterns: Optional[List[str]] = None,
        confidence_threshold: int = 80,
        target_paths: Optional[List[str]] = None,
        project_path: Optional[str] = None,
    ) -> QualityAssessmentResult:
        """Identify unused code via pixi execution."""
        pass


class QualityOrchestrationPort(ABC):
    """Port for orchestrating comprehensive quality suites."""

    @abstractmethod
    def execute_comprehensive_suite(
        self, configuration: QualitySuiteConfiguration
    ) -> ComprehensiveQualityResult:
        """Execute complete quality assessment with orchestrated tool execution."""
        pass

    @abstractmethod
    def validate_suite_configuration(
        self, configuration: QualitySuiteConfiguration
    ) -> OperationResult:
        """Validate comprehensive suite configuration."""
        pass

    @abstractmethod
    def estimate_execution_time(
        self, configuration: QualitySuiteConfiguration
    ) -> float:
        """Estimate execution time for a quality suite."""
        pass


# =============================================================================
# Quality Analysis and Intelligence Ports
# =============================================================================


class QualityAnalysisPort(ABC):
    """Port for intelligent quality analysis and metrics extraction."""

    @abstractmethod
    def parse_tool_output(
        self, tool: QualityTool, raw_output: str, tool_exit_code: int
    ) -> QualityAssessmentResult:
        """Parse raw tool output into structured assessment result."""
        pass

    @abstractmethod
    def calculate_quality_score(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> float:
        """Calculate overall quality score from assessment results."""
        pass

    @abstractmethod
    def generate_recommendations(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> List[str]:
        """Generate actionable quality improvement recommendations."""
        pass

    @abstractmethod
    def detect_quality_patterns(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> Dict[str, Any]:
        """Detect quality patterns and anti-patterns in results."""
        pass

    @abstractmethod
    def prioritize_issues(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> List[Dict[str, Any]]:
        """Prioritize quality issues by impact and effort to fix."""
        pass


class QualityTrendAnalysisPort(ABC):
    """Port for quality trend analysis and baseline management."""

    @abstractmethod
    def establish_baseline(
        self,
        baseline_id: str,
        assessment_results: List[QualityAssessmentResult],
        project_metadata: Dict[str, Any],
        retention_days: int = 365,
    ) -> QualityBaseline:
        """Create quality baseline for trend analysis."""
        pass

    @abstractmethod
    def compare_against_baseline(
        self, baseline_id: str, current_results: List[QualityAssessmentResult]
    ) -> QualityComparison:
        """Compare current quality against historical baseline."""
        pass

    @abstractmethod
    def analyze_quality_trends(
        self, baseline_ids: List[str], time_window_days: int = 30
    ) -> Dict[str, Any]:
        """Analyze quality trends across multiple baselines."""
        pass

    @abstractmethod
    def detect_quality_regression(
        self, comparison: QualityComparison, threshold_percent: float = 5.0
    ) -> Dict[str, Any]:
        """Detect quality regressions and generate alerts."""
        pass

    @abstractmethod
    def get_baseline_history(
        self, project_name: str, limit: int = 50
    ) -> List[QualityBaseline]:
        """Get baseline history for a project."""
        pass


# =============================================================================
# Automated Fix Application Ports
# =============================================================================


class AutomatedFixPort(ABC):
    """Port for applying automated fixes with safety validations."""

    @abstractmethod
    def apply_automated_fixes(
        self,
        fix_types: List[FixType],
        dry_run: bool = True,
        backup_before_fix: bool = True,
        validation_mode: FixValidationMode = FixValidationMode.STRICT,
    ) -> AutomatedFixResult:
        """Apply automated fixes with safety validations."""
        pass

    @abstractmethod
    def validate_fix_safety(
        self, fix_types: List[FixType], target_files: List[str]
    ) -> OperationResult:
        """Validate that fixes can be safely applied."""
        pass

    @abstractmethod
    def create_fix_backup(self, target_files: List[str]) -> str:
        """Create backup of files before applying fixes."""
        pass

    @abstractmethod
    def rollback_fixes(self, backup_path: str) -> OperationResult:
        """Rollback fixes using backup."""
        pass

    @abstractmethod
    def preview_fix_changes(
        self, fix_types: List[FixType], target_files: List[str]
    ) -> Dict[str, List[str]]:
        """Preview changes that would be made by fixes."""
        pass


# =============================================================================
# Quality Reporting and Documentation Ports
# =============================================================================


class QualityReportingPort(ABC):
    """Port for generating comprehensive quality reports."""

    @abstractmethod
    def generate_comprehensive_report(
        self,
        assessment_results: List[QualityAssessmentResult],
        format: ReportFormat = ReportFormat.MARKDOWN,
        template: ReportTemplate = ReportTemplate.STANDARD,
        include_sections: List[str] | None = None,
        attach_raw_results: bool = False,
    ) -> QualityReport:
        """Generate detailed quality reports in multiple formats."""
        pass

    @abstractmethod
    def generate_executive_summary(
        self, assessment_results: List[QualityAssessmentResult]
    ) -> str:
        """Generate executive summary of quality status."""
        pass

    @abstractmethod
    def export_report(
        self, report: QualityReport, target_formats: List[ReportFormat]
    ) -> Dict[str, str]:
        """Export report to multiple formats."""
        pass

    @abstractmethod
    def create_quality_dashboard(
        self,
        assessment_results: List[QualityAssessmentResult],
        baseline_comparisons: List[QualityComparison],
    ) -> str:
        """Create interactive quality dashboard."""
        pass


# =============================================================================
# Tool Management and Configuration Ports
# =============================================================================


class ToolManagementPort(ABC):
    """Port for managing quality tools and configurations."""

    @abstractmethod
    def validate_tool_availability(
        self,
        required_tools: List[QualityTool],
        version_constraints: Optional[Dict[str, str]] = None,
    ) -> ToolValidationResult:
        """Validate quality tools are available in pixi environment."""
        pass

    @abstractmethod
    def update_tool_configuration(
        self, update_request: ConfigurationUpdate
    ) -> ConfigurationResult:
        """Update quality tool configurations through centralized management."""
        pass

    @abstractmethod
    def get_tool_version(self, tool: QualityTool) -> Optional[str]:
        """Get version of a quality tool."""
        pass

    @abstractmethod
    def install_missing_tools(self, tools: List[QualityTool]) -> OperationResult:
        """Install missing quality tools via pixi."""
        pass

    @abstractmethod
    def backup_configuration(self, tool: QualityTool) -> str:
        """Backup current tool configuration."""
        pass


# =============================================================================
# Pixi Integration and Environment Ports
# =============================================================================


class PixiIntegrationPort(ABC):
    """Port for pixi environment integration and task execution."""

    @abstractmethod
    def execute_pixi_task(
        self,
        task_name: str,
        args: List[str] | None = None,
        working_dir: Optional[str] = None,
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Execute pixi task with comprehensive result capture."""
        pass

    @abstractmethod
    def validate_pixi_environment(self) -> OperationResult:
        """Validate pixi environment is properly configured."""
        pass

    @abstractmethod
    def get_pixi_project_info(self) -> Dict[str, Any]:
        """Get pixi project information and environment status."""
        pass

    @abstractmethod
    def list_available_tasks(self) -> List[str]:
        """List available pixi tasks."""
        pass

    @abstractmethod
    def check_task_exists(self, task_name: str) -> bool:
        """Check if a pixi task exists."""
        pass


# =============================================================================
# Caching and Performance Ports
# =============================================================================


class QualityCachingPort(ABC):
    """Port for quality assessment result caching."""

    @abstractmethod
    def get_cached_result(self, cache_key: str) -> Optional[QualityAssessmentResult]:
        """Get cached quality assessment result."""
        pass

    @abstractmethod
    def cache_result(
        self, cache_key: str, result: QualityAssessmentResult, ttl_seconds: int = 300
    ) -> None:
        """Cache quality assessment result."""
        pass

    @abstractmethod
    def invalidate_cache(self, pattern: str) -> int:
        """Invalidate cache entries matching pattern."""
        pass

    @abstractmethod
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        pass

    @abstractmethod
    def generate_cache_key(
        self,
        tool: QualityTool,
        assessment_type: QualityAssessmentType,
        target_path: str,
        config_hash: str,
    ) -> str:
        """Generate cache key for assessment."""
        pass


# =============================================================================
# Data Persistence and Storage Ports
# =============================================================================


class QualityDataStoragePort(ABC):
    """Port for persisting quality data and baselines."""

    @abstractmethod
    def store_baseline(self, baseline: QualityBaseline) -> OperationResult:
        """Store quality baseline for future comparisons."""
        pass

    @abstractmethod
    def retrieve_baseline(self, baseline_id: str) -> Optional[QualityBaseline]:
        """Retrieve quality baseline by ID."""
        pass

    @abstractmethod
    def store_assessment_result(
        self, result: QualityAssessmentResult
    ) -> OperationResult:
        """Store quality assessment result."""
        pass

    @abstractmethod
    def query_assessment_history(
        self,
        project_name: str,
        assessment_type: Optional[QualityAssessmentType] = None,
        limit: int = 50,
    ) -> List[QualityAssessmentResult]:
        """Query quality assessment history."""
        pass

    @abstractmethod
    def cleanup_expired_data(self, retention_days: int = 365) -> OperationResult:
        """Clean up expired quality data."""
        pass


# =============================================================================
# System Integration and Health Ports
# =============================================================================


class SystemIntegrationPort(ABC):
    """Port for system integration and health monitoring."""

    @abstractmethod
    def check_system_health(self) -> SystemHealth:
        """Perform comprehensive system health check."""
        pass

    @abstractmethod
    def monitor_performance_metrics(self) -> Dict[str, float]:
        """Monitor quality assessment performance metrics."""
        pass

    @abstractmethod
    def get_system_resource_usage(self) -> Dict[str, Any]:
        """Get current system resource usage."""
        pass

    @abstractmethod
    def validate_file_permissions(self, target_paths: List[str]) -> OperationResult:
        """Validate file system permissions for quality operations."""
        pass

    @abstractmethod
    def ensure_output_directories(self, output_paths: List[str]) -> OperationResult:
        """Ensure output directories exist and are writable."""
        pass


# =============================================================================
# Logging and Audit Ports
# =============================================================================


class QualityAuditPort(ABC):
    """Port for logging and auditing quality operations."""

    @abstractmethod
    def log_assessment_execution(
        self,
        assessment_type: QualityAssessmentType,
        tool: QualityTool,
        execution_time_ms: float,
        status: str,
        metadata: Dict[str, Any],
    ) -> None:
        """Log quality assessment execution."""
        pass

    @abstractmethod
    def log_fix_application(
        self,
        fix_types: List[FixType],
        files_modified: List[str],
        success: bool,
        metadata: Dict[str, Any],
    ) -> None:
        """Log automated fix application."""
        pass

    @abstractmethod
    def log_configuration_change(
        self, tool: QualityTool, changes: Dict[str, Any], applied_by: str
    ) -> None:
        """Log configuration changes."""
        pass

    @abstractmethod
    def get_audit_log(
        self, operation_type: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        pass
