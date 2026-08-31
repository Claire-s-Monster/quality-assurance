"""
Quality Assurance Lean MCP Server.

This is a simplified lean MCP server that exposes only 3 meta-tools instead of 18+ verbose tools.
Reduces context consumption from 50-100K tokens down to ~300 tokens while maintaining
full functionality through dynamic tool discovery.

Context Consumption Comparison:
- Traditional MCP: 18 tools × 3-6K tokens each = 50-100K tokens
- Lean MCP: 3 meta-tools × ~100 tokens each = ~300 tokens
- Savings: 99%+ reduction in context consumption

Usage:
- Agents use discover_tools() to find relevant tools by name pattern
- Agents use get_tool_spec() to get full schemas only when needed
- Agents use execute_tool() for actual execution
- Zero functionality loss, massive context savings
"""

import argparse
import logging
import sys
import os
from pathlib import Path
from typing import Dict, Optional, Any

from fastmcp import FastMCP

# Add parent directories to path to access core modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.container import Container

logger = logging.getLogger(__name__)


class QualityAssuranceLeanMCP:
    """
    Lean MCP Interface for Quality Assurance Server.

    Exposes 19 quality functions through 3 meta-tools with minimal context consumption.
    """

    def __init__(self, working_dir: str):
        self.working_dir = working_dir
        self.app = FastMCP("quality-assurance-lean")

        # Initialize container and services
        self.container = Container(working_dir=working_dir)
        self.orchestration_service = self.container.orchestration_service

        # Build tool registry with all 19 quality functions
        self.tool_registry = self._build_tool_registry()

        # Setup the 3 meta-tools
        self._setup_meta_tools()

        logger.info(
            f"Quality Assurance Lean MCP initialized with {len(self.tool_registry)} tools"
        )

    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """Build registry of all 19 quality assurance tools."""
        registry = {}

        # Core Assessment Functions (Functions 1-5)
        registry["quality_execute_lint_assessment"] = {
            "description": "Execute linting assessment with intelligent parsing and pixi-mediated execution",
            "schema": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "default": "ruff",
                        "description": "Linting tool to use",
                    },
                    "target_path": {
                        "type": "string",
                        "default": "src/",
                        "description": "Path to analyze",
                    },
                    "rules": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific rules to apply",
                    },
                    "fix_mode": {
                        "type": "boolean",
                        "default": False,
                        "description": "Whether to apply fixes automatically",
                    },
                    "output_format": {
                        "type": "string",
                        "default": "json",
                        "description": "Output format preference",
                    },
                    "use_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to use cached results",
                    },
                },
            },
        }

        registry["quality_execute_typecheck_assessment"] = {
            "description": "Execute type checking analysis with intelligent error categorization",
            "schema": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "default": "mypy",
                        "description": "Type checker to use",
                    },
                    "target_path": {
                        "type": "string",
                        "default": "src/",
                        "description": "Path to analyze",
                    },
                    "strict_mode": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable strict type checking mode",
                    },
                    "config_file": {
                        "type": "string",
                        "description": "Custom configuration file path",
                    },
                    "use_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to use cached results",
                    },
                },
            },
        }

        registry["quality_execute_security_scan"] = {
            "description": "Execute security vulnerability detection with risk categorization",
            "schema": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "default": "bandit",
                        "description": "Security scanner to use",
                    },
                    "target_path": {
                        "type": "string",
                        "default": "src/",
                        "description": "Path to analyze",
                    },
                    "severity_threshold": {
                        "type": "string",
                        "default": "medium",
                        "description": "Minimum severity to report",
                    },
                    "exclude_tests": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to exclude test files",
                    },
                    "use_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to use cached results",
                    },
                },
            },
        }

        registry["quality_execute_complexity_analysis"] = {
            "description": "Execute code complexity metrics analysis with intelligent categorization",
            "schema": {
                "type": "object",
                "properties": {
                    "tool": {
                        "type": "string",
                        "default": "radon",
                        "description": "Complexity analysis tool",
                    },
                    "target_path": {
                        "type": "string",
                        "default": "src/",
                        "description": "Path to analyze",
                    },
                    "complexity_threshold": {
                        "type": "integer",
                        "default": 10,
                        "description": "Complexity threshold for warnings",
                    },
                    "include_metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific metrics to include",
                    },
                    "use_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "Whether to use cached results",
                    },
                },
            },
        }

        registry["quality_execute_comprehensive_suite"] = {
            "description": "Execute complete quality assessment suite with orchestrated tool execution",
            "schema": {
                "type": "object",
                "properties": {
                    "included_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["ruff", "mypy", "bandit", "radon"],
                        "description": "Tools to include in suite",
                    },
                    "target_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["src/"],
                        "description": "Paths to analyze",
                    },
                    "parallel_execution": {
                        "type": "boolean",
                        "default": True,
                        "description": "Execute tools in parallel",
                    },
                    "quality_threshold": {
                        "type": "number",
                        "default": 8.0,
                        "description": "Minimum quality score threshold",
                    },
                    "fail_fast": {
                        "type": "boolean",
                        "default": False,
                        "description": "Stop on first critical failure",
                    },
                    "generate_report": {
                        "type": "boolean",
                        "default": True,
                        "description": "Generate comprehensive report",
                    },
                    "report_format": {
                        "type": "string",
                        "default": "markdown",
                        "description": "Report format",
                    },
                    "use_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "Use cached results for performance",
                    },
                },
            },
        }

        # Analysis & Intelligence Functions (Functions 6-9)
        registry["quality_calculate_quality_score"] = {
            "description": "Calculate overall quality score with intelligent weighting algorithms",
            "schema": {
                "type": "object",
                "properties": {
                    "assessment_results": {
                        "type": "array",
                        "description": "Results to calculate score from",
                    },
                    "weighting_strategy": {
                        "type": "string",
                        "default": "balanced",
                        "description": "Scoring strategy",
                    },
                    "custom_weights": {
                        "type": "object",
                        "description": "Custom tool weighting",
                    },
                    "include_breakdown": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include detailed score breakdown",
                    },
                },
            },
        }

        registry["quality_generate_recommendations"] = {
            "description": "Generate actionable quality improvement recommendations with intelligent prioritization",
            "schema": {
                "type": "object",
                "properties": {
                    "assessment_results": {
                        "type": "array",
                        "description": "Results to analyze",
                    },
                    "prioritize_by_impact": {
                        "type": "boolean",
                        "default": True,
                        "description": "Sort recommendations by impact",
                    },
                    "include_automated_fixes": {
                        "type": "boolean",
                        "default": True,
                        "description": "Include automated fix suggestions",
                    },
                    "max_recommendations": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of recommendations",
                    },
                },
            },
        }

        registry["quality_detect_quality_patterns"] = {
            "description": "Detect quality patterns and anti-patterns with machine learning-based analysis",
            "schema": {
                "type": "object",
                "properties": {
                    "assessment_results": {
                        "type": "array",
                        "description": "Results to analyze for patterns",
                    },
                    "pattern_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific pattern types to look for",
                    },
                    "confidence_threshold": {
                        "type": "number",
                        "default": 0.7,
                        "description": "Minimum confidence score for pattern reporting",
                    },
                },
            },
        }

        registry["quality_prioritize_issues"] = {
            "description": "Prioritize quality issues by impact and effort analysis with intelligent ranking",
            "schema": {
                "type": "object",
                "properties": {
                    "assessment_results": {
                        "type": "array",
                        "description": "Results to prioritize issues from",
                    },
                    "priority_strategy": {
                        "type": "string",
                        "default": "impact_effort",
                        "description": "Prioritization strategy",
                    },
                    "max_issues": {
                        "type": "integer",
                        "default": 50,
                        "description": "Maximum number of issues to return",
                    },
                },
            },
        }

        # Baseline & Trend Functions (Functions 10-12)
        registry["quality_establish_baseline"] = {
            "description": "Create quality baseline for tracking trends and regression detection",
            "schema": {
                "type": "object",
                "properties": {
                    "baseline_id": {
                        "type": "string",
                        "description": "Custom baseline identifier",
                    },
                    "project_name": {
                        "type": "string",
                        "default": "current_project",
                        "description": "Project name for baseline organization",
                    },
                    "project_version": {
                        "type": "string",
                        "description": "Project version for release tracking",
                    },
                    "git_commit": {
                        "type": "string",
                        "description": "Git commit hash for version tracking",
                    },
                    "git_branch": {
                        "type": "string",
                        "description": "Git branch for baseline context",
                    },
                    "retention_days": {
                        "type": "integer",
                        "default": 365,
                        "description": "Days to retain baseline data",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Custom tags for baseline organization",
                    },
                    "suite_configuration": {
                        "type": "object",
                        "description": "Custom suite configuration for baseline",
                    },
                },
            },
        }

        registry["quality_compare_against_baseline"] = {
            "description": "Compare current quality metrics against historical baseline with trend analysis",
            "schema": {
                "type": "object",
                "properties": {
                    "baseline_id": {
                        "type": "string",
                        "description": "ID of baseline to compare against",
                    },
                    "suite_configuration": {
                        "type": "object",
                        "description": "Custom configuration for current assessment",
                    },
                },
                "required": ["baseline_id"],
            },
        }

        registry["quality_analyze_trends"] = {
            "description": "Analyze quality trends across multiple periods with predictive insights",
            "schema": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "default": "current_project",
                        "description": "Project to analyze trends for",
                    },
                    "time_period": {
                        "type": "string",
                        "default": "30d",
                        "description": "Time period for analysis",
                    },
                    "baseline_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific baselines to include",
                    },
                    "metrics_filter": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific metrics to focus on",
                    },
                },
            },
        }

        # Automation & Reporting Functions (Functions 13-14)
        registry["quality_apply_automated_fixes"] = {
            "description": "Apply automated quality fixes with comprehensive safety validations",
            "schema": {
                "type": "object",
                "properties": {
                    "fix_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Types of fixes to apply",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": True,
                        "description": "Perform dry run to preview changes",
                    },
                    "backup_before_fix": {
                        "type": "boolean",
                        "default": True,
                        "description": "Create backup before applying fixes",
                    },
                    "validation_mode": {
                        "type": "string",
                        "default": "strict",
                        "description": "Validation strictness",
                    },
                },
                "required": ["fix_types"],
            },
        }

        registry["quality_generate_comprehensive_report"] = {
            "description": "Generate comprehensive quality reports in multiple formats with rich visualizations",
            "schema": {
                "type": "object",
                "properties": {
                    "assessment_results": {
                        "type": "array",
                        "description": "Results to include in report",
                    },
                    "format": {
                        "type": "string",
                        "default": "markdown",
                        "description": "Output format",
                    },
                    "template": {
                        "type": "string",
                        "default": "standard",
                        "description": "Report template",
                    },
                    "include_sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific sections to include",
                    },
                    "attach_raw_results": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include raw tool outputs",
                    },
                    "baseline_comparison": {
                        "type": "object",
                        "description": "Optional baseline comparison data",
                    },
                },
            },
        }

        # Pixi-Quality Integration Functions (Functions 15-19)
        registry["quality_execute_pixi_aware_assessment"] = {
            "description": "Execute quality assessment using pixi-aware task orchestration",
            "schema": {
                "type": "object",
                "properties": {
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["ruff", "mypy", "bandit"],
                        "description": "Quality tools to use",
                    },
                    "target_paths": {
                        "type": "array",
                        "items": {"type": "string"},
                        "default": ["src/"],
                        "description": "Paths to analyze",
                    },
                    "environment_optimization": {
                        "type": "boolean",
                        "default": True,
                        "description": "Enable environment optimization",
                    },
                    "use_pixi_templates": {
                        "type": "boolean",
                        "default": True,
                        "description": "Use pixi task templates",
                    },
                },
            },
        }

        registry["quality_optimize_pixi_environment"] = {
            "description": "Optimize pixi environment for quality tool execution",
            "schema": {
                "type": "object",
                "properties": {
                    "working_dir": {
                        "type": "string",
                        "description": "Directory to optimize",
                    },
                    "target_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools to optimize for",
                    },
                    "generate_tasks": {
                        "type": "boolean",
                        "default": True,
                        "description": "Generate pixi task templates",
                    },
                },
            },
        }

        registry["quality_generate_pixi_tasks"] = {
            "description": "Generate pixi task definitions for quality tools",
            "schema": {
                "type": "object",
                "properties": {
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of quality tools to generate tasks for",
                    },
                    "project_structure": {
                        "type": "string",
                        "default": "src/",
                        "description": "Project source directory",
                    },
                    "output_format": {
                        "type": "string",
                        "default": "toml",
                        "description": "Output format",
                    },
                    "integration_mode": {
                        "type": "string",
                        "default": "standalone",
                        "description": "Integration approach",
                    },
                },
                "required": ["tools"],
            },
        }

        registry["quality_validate_pixi_integration"] = {
            "description": "Validate quality tool integration with pixi environment",
            "schema": {
                "type": "object",
                "properties": {
                    "working_dir": {
                        "type": "string",
                        "description": "Directory to validate",
                    },
                    "check_environment_health": {
                        "type": "boolean",
                        "default": True,
                        "description": "Perform environment health checks",
                    },
                    "suggest_improvements": {
                        "type": "boolean",
                        "default": True,
                        "description": "Generate improvement suggestions",
                    },
                },
            },
        }

        # Health & Diagnostics Function (Function 19)
        registry["quality_get_system_health"] = {
            "description": "Report server self-diagnosis: tool availability, adapter health, and whether the pixi executable can be resolved. Call this first when assessments return unexpected or empty results.",
            "schema": {"type": "object", "properties": {}},
        }

        return registry

    def _setup_meta_tools(self):
        """Setup the 3 meta-tools for dynamic discovery without filtering."""

        @self.app.tool(
            description="Discover quality assurance tools for linting, type-checking, security scanning, and code quality analysis (19 tools). USE WHEN: checking code quality, running ruff/mypy/bandit, analyzing quality trends, generating quality reports"
        )
        def discover_tools(pattern: Optional[str] = None) -> Dict[str, Any]:
            """
            [STEP 1] Discover available quality assurance tools in this MCP server.

            USE WHEN:
            - You need to run linting, type-checking, or security scans
            - You want to see all available quality tools before execution
            - You need to find the exact tool name before calling get_tool_spec()
            - You're exploring what quality operations are available

            COMMON TASKS:
            - Lint analysis: quality_execute_lint_assessment (ruff)
            - Type checking: quality_execute_typecheck_assessment (mypy)
            - Security scan: quality_execute_security_scan (bandit)
            - Full suite: quality_execute_comprehensive_suite (all tools)
            - Baselines: quality_establish_baseline, quality_compare_against_baseline
            - Auto-fix: quality_apply_automated_fixes

            This lean interface provides 19 quality tools, saving ~50-100K tokens
            vs loading all tool schemas upfront.

            WORKFLOW:
            1. discover_tools(pattern) <- YOU ARE HERE
            2. get_tool_spec(tool_name) <- Get schema/parameters for a specific tool
            3. execute_tool(tool_name, params) <- Execute the quality operation

            Args:
                pattern: Filter tools by name (e.g., "lint", "security", "baseline")
                         Leave empty or None to see all 19 tools

            Returns:
                Dictionary containing:
                - available_tools: List of tools, each with:
                  * name: Tool name to use in get_tool_spec() or execute_tool()
                  * description: What the tool does
                - total_tools: Total tools in registry (19)
                - filtered_count: How many matched your pattern

                Example output for discover_tools("lint"):
                {
                  "available_tools": [
                    {"name": "quality_execute_lint_assessment", "description": "Execute linting assessment with intelligent parsing..."}
                  ],
                  "filtered_count": 1,
                  "total_tools": 19
                }

            Examples:
                discover_tools()              # List all 19 tools
                discover_tools("lint")        # Find linting tools
                discover_tools("security")    # Find security scanning tools
                discover_tools("baseline")    # Find baseline/trend tools
                discover_tools("pixi")        # Find pixi integration tools

            MISSING TOOL? If you need a quality operation that's not available:
            File an issue at the quality-assurance MCP server repository.
            """
            tools = []

            for name, info in self.tool_registry.items():
                # Apply pattern filter if provided
                if pattern and pattern.lower() not in name.lower():
                    continue

                tools.append({"name": name, "description": info["description"]})

            return {
                "available_tools": tools,
                "total_tools": len(self.tool_registry),
                "filtered_count": len(tools),
            }

        @self.app.tool(
            description="Get full specification for specific quality assurance tool including schema and examples. USE WHEN: need parameter details for lint/typecheck/security tools before execution"
        )
        def get_tool_spec(tool_name: str) -> Dict[str, Any]:
            """
            [STEP 2] Get detailed schema and parameters for a specific quality tool.

            USE WHEN:
            - You know the tool name but don't know what parameters it needs
            - You need to see required vs optional parameters before calling execute_tool()
            - You want to understand parameter types and defaults
            - You're debugging parameter validation errors from execute_tool()

            DON'T SKIP THIS STEP! Calling execute_tool() without checking the schema first
            will likely fail parameter validation. This tool shows you exactly what to pass.

            WORKFLOW:
            1. discover_tools(pattern) <- Already done
            2. get_tool_spec(tool_name) <- YOU ARE HERE
            3. execute_tool(tool_name, params) <- Execute with correct parameters

            Args:
                tool_name: Exact tool name from discover_tools() output
                           Examples: "quality_execute_lint_assessment",
                                     "quality_execute_security_scan",
                                     "quality_establish_baseline"

            Returns:
                Dictionary containing:
                - name: Tool name (same as input)
                - description: What the tool does
                - schema: JSON Schema with:
                  * properties: Each parameter's type, description, default value
                  * required: List of required parameters (if any)

                Example output for get_tool_spec("quality_execute_lint_assessment"):
                {
                  "name": "quality_execute_lint_assessment",
                  "description": "Execute linting assessment with intelligent parsing...",
                  "schema": {
                    "type": "object",
                    "properties": {
                      "tool": {"type": "string", "default": "ruff"},
                      "target_path": {"type": "string", "default": "src/"},
                      "fix_mode": {"type": "boolean", "default": false}
                    }
                  }
                }

                Example for get_tool_spec("quality_compare_against_baseline"):
                {
                  "name": "quality_compare_against_baseline",
                  "schema": {
                    "properties": {...},
                    "required": ["baseline_id"]  # Note required parameter!
                  }
                }

            ERROR RESPONSE:
                If tool_name not found:
                {
                  "error": "Tool 'invalid_name' not found",
                  "available_tools": ["quality_execute_lint_assessment", ...]
                }

            Examples:
                get_tool_spec("quality_execute_lint_assessment")   # See lint params
                get_tool_spec("quality_execute_security_scan")     # See security params
                get_tool_spec("quality_establish_baseline")        # See baseline params
                get_tool_spec("quality_apply_automated_fixes")     # See auto-fix params

            TOOL NOT FOUND? Use discover_tools() first to find the correct tool name.
            """
            if tool_name not in self.tool_registry:
                available_tools = list(self.tool_registry.keys())
                return {
                    "error": f"Tool '{tool_name}' not found",
                    "available_tools": available_tools,
                }

            tool_info = self.tool_registry[tool_name]
            return {
                "name": tool_name,
                "description": tool_info["description"],
                "schema": tool_info["schema"],
            }

        @self.app.tool(
            description="Execute quality assurance tool with parameters. Supports lint, typecheck, security, formatting, and trend analysis. USE WHEN: running quality checks, applying auto-fixes, generating baseline reports"
        )
        def execute_tool(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
            """
            [STEP 3] Execute a quality assurance operation.

            USE WHEN: You have the tool name and parameters ready to perform a quality check.

            WORKFLOW:
            1. discover_tools(pattern) <- Found the right tool
            2. get_tool_spec(tool_name) <- Got the parameter schema
            3. execute_tool(tool_name, params) <- YOU ARE HERE

            VALIDATION: Parameters are validated against the tool schema before execution.
            Unexpected parameters will be rejected with an error listing valid parameters.

            Args:
                tool_name: Exact tool name from discover_tools()
                           Examples: "quality_execute_lint_assessment",
                                     "quality_execute_security_scan"
                parameters: Dictionary of parameters matching the tool schema
                            Use get_tool_spec() if unsure what parameters are needed

            Returns:
                SUCCESS: Tool execution result containing:
                - quality_execute_lint_assessment: Lint violations, severity counts, file details
                - quality_execute_typecheck_assessment: Type errors, categorization, suggestions
                - quality_execute_security_scan: Security issues, severity levels, risk assessment
                - quality_execute_comprehensive_suite: Full report with all tool results
                - quality_establish_baseline: Baseline ID, timestamp, metrics snapshot
                - quality_compare_against_baseline: Regression analysis, delta metrics
                - quality_apply_automated_fixes: Files modified, changes applied, backup locations

                Response format:
                {
                  "tool": "quality_execute_lint_assessment",
                  "status": "success",
                  "result": {
                    "violations": [...],
                    "summary": {...}
                  }
                }

                ERROR: Validation/execution failure with:
                {
                  "tool": "quality_execute_lint_assessment",
                  "status": "error",
                  "error": "Error message explaining what went wrong"
                }

                If tool not found:
                {
                  "error": "Tool 'invalid_name' not found",
                  "available_tools": ["quality_execute_lint_assessment", ...]
                }

            DON'T KNOW WHAT TOOL TO USE?
            Call discover_tools(pattern) first to find the right tool for your task.

            Examples:
                # Run linting with defaults
                execute_tool("quality_execute_lint_assessment", {})

                # Run linting with auto-fix
                execute_tool("quality_execute_lint_assessment", {
                    "target_path": "src/",
                    "fix_mode": True
                })

                # Run security scan
                execute_tool("quality_execute_security_scan", {
                    "severity_threshold": "high",
                    "exclude_tests": True
                })

                # Create quality baseline
                execute_tool("quality_establish_baseline", {
                    "baseline_id": "v1.0.0",
                    "git_branch": "main"
                })

                # Compare against baseline
                execute_tool("quality_compare_against_baseline", {
                    "baseline_id": "v1.0.0"  # Required parameter
                })

            FOUND A BUG OR MISSING FEATURE?
            File an issue with: tool name, parameters used, error message, expected vs actual behavior.
            """
            if tool_name not in self.tool_registry:
                available_tools = list(self.tool_registry.keys())
                return {
                    "error": f"Tool '{tool_name}' not found",
                    "available_tools": available_tools,
                }

            try:
                # Import the main server module dynamically to access the tool functions
                from . import server as main_server

                # Get the tool from the main server
                # Note: @app.tool() decorator returns a FunctionTool object, not the function
                # The FunctionTool object is not callable directly - access the .fn attribute
                if hasattr(main_server, tool_name):
                    tool_obj = getattr(main_server, tool_name)
                    # FunctionTool stores the original function in .fn attribute
                    if hasattr(tool_obj, "fn"):
                        result = tool_obj.fn(**parameters)
                    else:
                        # Fallback for direct function (shouldn't happen with @app.tool)
                        result = tool_obj(**parameters)
                    return {"tool": tool_name, "status": "success", "result": result}
                else:
                    return {
                        "tool": tool_name,
                        "status": "error",
                        "error": f"Function '{tool_name}' not implemented in main server",
                    }

            except Exception as e:
                logger.error(f"Error executing {tool_name}: {e}")
                return {"tool": tool_name, "status": "error", "error": str(e)}

    def get_app(self) -> FastMCP:
        """Get the FastMCP app instance."""
        return self.app


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Quality Assurance Lean MCP Server")
    parser.add_argument(
        "--working-dir",
        type=str,
        default=".",
        help="Working directory path (default: current directory)",
    )
    parser.add_argument(
        "--repository",
        type=str,
        default=None,
        help="Repository path (alias for --working-dir, for MCP compatibility)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    return parser.parse_args()


def setup_logging(log_level: str):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main():
    """Main entry point for the lean MCP server."""
    try:
        args = parse_args()
        setup_logging(args.log_level)

        # Resolve working directory path - support both --working-dir and --repository
        working_dir_arg = args.repository if args.repository else args.working_dir
        working_dir = Path(working_dir_arg).resolve()
        logger.info(f"Initializing Quality Assurance Lean MCP server in: {working_dir}")

        # Create lean interface
        lean_mcp = QualityAssuranceLeanMCP(str(working_dir))
        app = lean_mcp.get_app()

        logger.info("Starting Quality Assurance Lean MCP server with meta-tool pattern")
        logger.info(
            "Context consumption: ~300 tokens (vs 50-100K tokens for traditional MCP)"
        )
        logger.info("Available functions: 19 quality tools via 3 meta-tools")

        # Run the server
        app.run()

    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == "__main__":
    main()
