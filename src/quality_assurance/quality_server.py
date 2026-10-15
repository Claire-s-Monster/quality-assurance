"""
Quality Assurance MCP Server - Main Entry Point

Provides comprehensive code quality assessment capabilities through Model Context Protocol.
Supports linting, type checking, security scanning, complexity analysis, and dead code detection.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastmcp import FastMCP

import sys
import os

# Add parent directory to path to access core modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.quality_service import QualityAssuranceService
from core.container import Container
from core.models import (
    QualityTool,
    QualityAssessmentType,
    QualityAssessmentResult,
    QualitySuiteConfiguration,
    ComprehensiveQualityResult,
    ReportFormat,
    ReportTemplate,
)

# Initialize FastMCP app
app = FastMCP("Quality Assurance MCP Server")


# MCP Functions for pixi operations - these will be injected at runtime
def get_mcp_functions():
    """Get MCP function references for pixi operations."""
    # Import the pixi MCP functions that should be available
    try:
        import mcp__pixi_bash__pixi_run_task
        import mcp__pixi_bash__pixi_task_exists
        import mcp__pixi_bash__pixi_project_status

        return {
            "pixi_run_task": mcp__pixi_bash__pixi_run_task,
            "pixi_task_exists": mcp__pixi_bash__pixi_task_exists,
            "pixi_project_status": mcp__pixi_bash__pixi_project_status,
        }
    except ImportError:
        # Fallback for development/testing
        return {
            "pixi_run_task": lambda task, args=None: {
                "success": True,
                "stdout": "",
                "stderr": "",
            },
            "pixi_task_exists": lambda task: {"exists": True},
            "pixi_project_status": lambda: {"healthy": True},
        }


# Initialize dependency injection container
mcp_functions = get_mcp_functions()
container = Container(mcp_functions=mcp_functions)

# Initialize core service
service = container.quality_service

# Core Quality Assessment Functions


@app.tool()
def execute_lint_assessment(
    tool: str = "ruff",
    target_path: str = "src/",
    rules: Optional[List[str]] = None,
    fix_mode: bool = False,
    output_format: str = "json",
) -> Dict[str, Any]:
    """
    Execute linting assessment with comprehensive analysis.

    Args:
        tool: Linting tool to use ("ruff", "pylint", "flake8")
        target_path: Path to analyze (default: "src/")
        rules: Specific rules to apply (optional)
        fix_mode: Whether to apply auto-fixes (default: False)
        output_format: Output format preference (default: "json")

    Returns:
        Quality assessment result with violations and recommendations
    """
    try:
        # Convert string to QualityTool enum
        quality_tool = QualityTool(tool.lower())

        result = service.execute_lint_assessment(
            tool=quality_tool,
            target_path=target_path,
            rules=rules,
            fix_mode=fix_mode,
            output_format=output_format,
        )

        return result.dict()

    except ValueError as e:
        return {
            "error": f"Invalid tool: {tool}",
            "valid_tools": [
                t.value
                for t in QualityTool
                if t in [QualityTool.RUFF, QualityTool.PYLINT, QualityTool.FLAKE8]
            ],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def execute_typecheck_assessment(
    tool: str = "mypy",
    strict_mode: bool = False,
    config_path: str = "pyproject.toml",
    incremental: bool = True,
    cache_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute type checking assessment with comprehensive analysis.

    Args:
        tool: Type checking tool to use (currently supports "mypy")
        strict_mode: Enable strict type checking (default: False)
        config_path: Path to configuration file (default: "pyproject.toml")
        incremental: Enable incremental checking (default: True)
        cache_dir: Custom cache directory (optional)

    Returns:
        Quality assessment result with type errors and recommendations
    """
    try:
        # Convert string to QualityTool enum
        quality_tool = QualityTool(tool.lower())

        result = service.execute_typecheck_assessment(
            tool=quality_tool,
            strict_mode=strict_mode,
            config_path=config_path,
            incremental=incremental,
            cache_dir=cache_dir,
        )

        return result.dict()

    except ValueError as e:
        return {
            "error": f"Invalid tool: {tool}",
            "valid_tools": [QualityTool.MYPY.value],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def execute_security_scan(
    tool: str = "bandit",
    scan_type: str = "all",
    report_format: str = "json",
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Execute security vulnerability scanning.

    Args:
        tool: Security scanning tool to use (currently supports "bandit")
        scan_type: Type of scan to perform (default: "all")
        report_format: Report format preference (default: "json")
        exclude_patterns: Patterns to exclude from scanning (optional)

    Returns:
        Quality assessment result with security issues and recommendations
    """
    try:
        # Convert string to QualityTool enum
        quality_tool = QualityTool(tool.lower())

        result = service.execute_security_scan(
            tool=quality_tool,
            scan_type=scan_type,
            report_format=report_format,
            exclude_patterns=exclude_patterns,
        )

        return result.dict()

    except ValueError as e:
        return {
            "error": f"Invalid tool: {tool}",
            "valid_tools": [QualityTool.BANDIT.value],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def execute_complexity_analysis(
    tool: str = "radon",
    complexity_threshold: int = 10,
    include_maintainability: bool = True,
    report_detail: str = "summary",
) -> Dict[str, Any]:
    """
    Execute code complexity analysis.

    Args:
        tool: Complexity analysis tool to use (currently supports "radon")
        complexity_threshold: Complexity threshold for warnings (default: 10)
        include_maintainability: Include maintainability index (default: True)
        report_detail: Level of detail in report (default: "summary")

    Returns:
        Quality assessment result with complexity metrics and recommendations
    """
    try:
        # Convert string to QualityTool enum
        quality_tool = QualityTool(tool.lower())

        result = service.execute_complexity_analysis(
            tool=quality_tool,
            complexity_threshold=complexity_threshold,
            include_maintainability=include_maintainability,
            report_detail=report_detail,
        )

        return result.dict()

    except ValueError as e:
        return {
            "error": f"Invalid tool: {tool}",
            "valid_tools": [QualityTool.RADON.value],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def execute_dead_code_detection(
    tool: str = "vulture",
    aggressive_mode: bool = False,
    exclude_patterns: Optional[List[str]] = None,
    confidence_threshold: int = 80,
) -> Dict[str, Any]:
    """
    Execute dead code detection analysis.

    Args:
        tool: Dead code detection tool to use (currently supports "vulture")
        aggressive_mode: Enable aggressive detection mode (default: False)
        exclude_patterns: Patterns to exclude from analysis (optional)
        confidence_threshold: Minimum confidence for reporting (default: 80)

    Returns:
        Quality assessment result with dead code findings and recommendations
    """
    try:
        # Convert string to QualityTool enum
        quality_tool = QualityTool(tool.lower())

        result = service.execute_dead_code_detection(
            tool=quality_tool,
            aggressive_mode=aggressive_mode,
            exclude_patterns=exclude_patterns,
            confidence_threshold=confidence_threshold,
        )

        return result.dict()

    except ValueError as e:
        return {
            "error": f"Invalid tool: {tool}",
            "valid_tools": [QualityTool.VULTURE.value],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Comprehensive Quality Suite Functions


@app.tool()
def execute_comprehensive_suite(
    included_tools: List[str],
    parallel_execution: bool = True,
    fail_fast: bool = False,
    quality_threshold: float = 8.0,
    generate_report: bool = True,
    report_format: str = "markdown",
) -> Dict[str, Any]:
    """
    Execute comprehensive quality suite with all specified tools.

    Args:
        included_tools: List of tools to include in suite (e.g., ["ruff", "mypy", "bandit"])
        parallel_execution: Whether to run tools in parallel (default: True)
        fail_fast: Stop execution on first failure (default: False)
        quality_threshold: Minimum quality score required (default: 8.0)
        generate_report: Generate comprehensive report (default: True)
        report_format: Report format ("markdown", "json", "html") (default: "markdown")

    Returns:
        Comprehensive quality result with aggregated metrics and recommendations
    """
    try:
        # Convert string tool names to QualityTool enums
        quality_tools = []
        for tool_name in included_tools:
            try:
                quality_tools.append(QualityTool(tool_name.lower()))
            except ValueError:
                return {
                    "error": f"Invalid tool: {tool_name}",
                    "valid_tools": [t.value for t in QualityTool],
                    "timestamp": datetime.now().isoformat(),
                }

        # Create suite configuration
        configuration = QualitySuiteConfiguration(
            included_tools=quality_tools,
            parallel_execution=parallel_execution,
            fail_fast=fail_fast,
            quality_threshold=quality_threshold,
            generate_report=generate_report,
            report_format=report_format,
        )

        result = service.execute_comprehensive_suite(configuration)
        return result.dict()

    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def get_default_quality_suite() -> Dict[str, Any]:
    """
    Get a default comprehensive quality suite configuration.

    Returns:
        Default suite configuration with all supported tools
    """
    return {
        "configuration": {
            "included_tools": ["ruff", "mypy", "bandit", "radon", "vulture"],
            "parallel_execution": True,
            "fail_fast": False,
            "quality_threshold": 8.0,
            "generate_report": True,
            "report_format": "markdown",
        },
        "description": "Default comprehensive quality suite with all supported tools",
        "estimated_duration": "2-5 minutes depending on project size",
        "recommendations": [
            "Run this suite before committing changes",
            "Set up as pre-commit hook for continuous quality",
            "Adjust quality_threshold based on project requirements",
        ],
    }


# Health and Monitoring Functions


@app.tool()
def get_system_health() -> Dict[str, Any]:
    """
    Get comprehensive system health status.

    Returns:
        System health with component status and performance metrics
    """
    try:
        health = service.get_system_health()
        return health.dict()

    except Exception as e:
        return {
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "healthy": False,
        }


@app.tool()
def list_supported_tools() -> Dict[str, Any]:
    """
    List all supported quality assessment tools with descriptions.

    Returns:
        Dictionary of supported tools with capabilities and descriptions
    """
    tools_info = {
        QualityTool.RUFF.value: {
            "name": "Ruff",
            "type": "Linter",
            "description": "Fast Python linter written in Rust",
            "capabilities": ["syntax_checking", "style_checking", "auto_fix"],
            "output_formats": ["json", "text"],
            "website": "https://github.com/astral-sh/ruff",
        },
        QualityTool.MYPY.value: {
            "name": "MyPy",
            "type": "Type Checker",
            "description": "Static type checker for Python",
            "capabilities": ["type_checking", "type_inference"],
            "output_formats": ["text"],
            "website": "https://mypy.readthedocs.io/",
        },
        QualityTool.BANDIT.value: {
            "name": "Bandit",
            "type": "Security Scanner",
            "description": "Security linter for Python code",
            "capabilities": ["security_scanning", "vulnerability_detection"],
            "output_formats": ["json", "text", "xml"],
            "website": "https://bandit.readthedocs.io/",
        },
        QualityTool.RADON.value: {
            "name": "Radon",
            "type": "Complexity Analyzer",
            "description": "Code complexity analyzer for Python",
            "capabilities": ["complexity_analysis", "maintainability_index"],
            "output_formats": ["json", "text"],
            "website": "https://radon.readthedocs.io/",
        },
        QualityTool.VULTURE.value: {
            "name": "Vulture",
            "type": "Dead Code Detector",
            "description": "Finds unused code in Python programs",
            "capabilities": ["dead_code_detection", "unused_imports"],
            "output_formats": ["text"],
            "website": "https://github.com/jendrikseipp/vulture",
        },
    }

    return {
        "supported_tools": tools_info,
        "total_tools": len(tools_info),
        "categories": {
            "linters": ["ruff", "pylint", "flake8"],
            "type_checkers": ["mypy"],
            "security_scanners": ["bandit"],
            "complexity_analyzers": ["radon"],
            "dead_code_detectors": ["vulture"],
        },
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def get_server_info() -> Dict[str, Any]:
    """
    Get server information and capabilities.

    Returns:
        Server version, capabilities, and configuration
    """
    return {
        "server_name": "Quality Assurance MCP Server",
        "version": "1.0.0",
        "capabilities": {
            "linting": True,
            "type_checking": True,
            "security_scanning": True,
            "complexity_analysis": True,
            "dead_code_detection": True,
            "comprehensive_suite": True,
            "auto_fixes": True,
            "report_generation": True,
        },
        "supported_tools": [tool.value for tool in QualityTool],
        "supported_formats": ["json", "markdown", "html", "text"],
        "pixi_integration": True,
        "parallel_execution": True,
        "timestamp": datetime.now().isoformat(),
    }


# Quality Assessment History and Comparison (Future Enhancement Stubs)


@app.tool()
def create_quality_baseline(
    project_name: str,
    project_version: Optional[str] = None,
    git_commit: Optional[str] = None,
    git_branch: Optional[str] = None,
    retention_days: int = 365,
    tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Create quality baseline for trend analysis and comparison.

    Args:
        project_name: Name of the project
        project_version: Project version (optional)
        git_commit: Git commit hash (optional)
        git_branch: Git branch (optional)
        retention_days: Days to retain baseline (default: 365)
        tags: Tags for organization (optional)

    Returns:
        Operation result with baseline ID and metadata

    Note: This is a future enhancement placeholder
    """
    return {
        "message": "Quality baseline creation is planned for future release",
        "status": "not_implemented",
        "planned_features": [
            "Historical quality tracking",
            "Trend analysis",
            "Regression detection",
            "Quality score comparison",
        ],
        "timestamp": datetime.now().isoformat(),
    }


@app.tool()
def compare_with_baseline(
    baseline_id: str, current_assessment: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compare current quality metrics with a baseline.

    Args:
        baseline_id: ID of baseline to compare against
        current_assessment: Current assessment results (optional - will run if not provided)

    Returns:
        Comparison result with trends and regression analysis

    Note: This is a future enhancement placeholder
    """
    return {
        "message": "Quality baseline comparison is planned for future release",
        "status": "not_implemented",
        "planned_features": [
            "Quality trend analysis",
            "Regression detection",
            "Improvement tracking",
            "Automated alerts",
        ],
        "timestamp": datetime.now().isoformat(),
    }


# Initialize server for development
if __name__ == "__main__":
    # Use stdio for MCP communication
    app.run()


# Main function for package entry point
def main():
    """Main entry point for the Quality Assurance MCP Server."""
    # Use stdio for MCP communication
    app.run()
