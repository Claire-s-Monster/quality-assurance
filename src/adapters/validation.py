"""
Agent validation adapter for comprehensive agent integrity checking.
Validates agent structure, content, dependencies, and security requirements.
"""

import re
import ast
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from datetime import datetime
import hashlib

from core.ports import AgentValidationPort
from core.models import (
    Agent,
    ValidationResult,
    ValidationIssue,
    IssueType,
    IssueSeverity,
    AgentFrontmatter,
    SecurityViolation,
    EcosystemHealth,
)
from adapters.filesystem import FilesystemAdapter


class AgentValidationAdapter(AgentValidationPort):
    """Validates agent files for structure, content, and security compliance."""

    def __init__(self, filesystem: FilesystemAdapter):
        self.filesystem = filesystem

        # Known safe tools from MCP ecosystem
        self.safe_tools = {
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Bash",
            "Glob",
            "Grep",
            "LS",
            "Task",
            "TodoWrite",
            "WebFetch",
            "ExitPlanMode",
        }

        # Known dangerous patterns to flag
        self.security_patterns = {
            r"rm\s+-rf\s+/": "Dangerous recursive delete of root",
            r"chmod\s+777": "Overly permissive file permissions",
            r"sudo\s+": "Sudo command usage",
            r"eval\s*\(": "Dynamic code evaluation",
            r"exec\s*\(": "Dynamic code execution",
            r"__import__\s*\(": "Dynamic module import",
            r"os\.system\s*\(": "System command execution",
            r"subprocess\.call": "Subprocess execution",
            r"shell=True": "Shell command injection risk",
        }

        # Required frontmatter fields
        self.required_fields = {"name", "description", "version", "tools"}

        # Valid tool parameter types
        self.valid_tool_params = {
            "str",
            "int",
            "float",
            "bool",
            "list",
            "dict",
            "Optional",
        }

    def validate_agent(
        self, agent_path: str, validation_level: str = "comprehensive"
    ) -> ValidationResult:
        """Validate agent file with specified validation level."""
        issues = []

        try:
            # Read agent content
            content = self.filesystem.read_file(agent_path)

            # Basic structural validation
            issues.extend(self._validate_structure(content, agent_path))

            # Frontmatter validation
            frontmatter_issues, frontmatter = self._validate_frontmatter(content)
            issues.extend(frontmatter_issues)

            if validation_level in ["comprehensive", "security"]:
                # Security validation
                issues.extend(self._validate_security(content, frontmatter))

            if validation_level == "comprehensive":
                # Content quality validation
                issues.extend(self._validate_content_quality(content, frontmatter))

                # Tool usage validation
                issues.extend(self._validate_tool_usage(content, frontmatter))

                # Dependencies validation
                issues.extend(self._validate_dependencies(frontmatter))

            # Calculate overall score
            score = self._calculate_validation_score(issues)

            # Determine if validation passed
            has_critical = any(
                issue.severity == IssueSeverity.CRITICAL for issue in issues
            )
            passed = not has_critical and score >= 70

            return ValidationResult(
                agent_path=agent_path,
                passed=passed,
                score=score,
                issues=issues,
                validation_level=validation_level,
                validated_at=datetime.now().isoformat(),
                file_hash=self.filesystem.calculate_file_hash(agent_path),
            )

        except Exception as e:
            # Create critical issue for validation failure
            critical_issue = ValidationIssue(
                type=IssueType.STRUCTURAL,
                severity=IssueSeverity.CRITICAL,
                message=f"Failed to validate agent: {e}",
                line_number=0,
                suggestion="Check file permissions and content encoding",
            )

            return ValidationResult(
                agent_path=agent_path,
                passed=False,
                score=0,
                issues=[critical_issue],
                validation_level=validation_level,
                validated_at=datetime.now().isoformat(),
                file_hash="",
            )

    def _validate_structure(
        self, content: str, agent_path: str
    ) -> List[ValidationIssue]:
        """Validate basic agent file structure."""
        issues = []
        lines = content.split("\n")

        # Check file extension
        if not agent_path.endswith(".md"):
            issues.append(
                ValidationIssue(
                    type=IssueType.STRUCTURAL,
                    severity=IssueSeverity.ERROR,
                    message="Agent file must have .md extension",
                    line_number=0,
                    suggestion="Rename file to have .md extension",
                )
            )

        # Check minimum content length
        if len(content.strip()) < 100:
            issues.append(
                ValidationIssue(
                    type=IssueType.STRUCTURAL,
                    severity=IssueSeverity.WARNING,
                    message="Agent content is very short",
                    line_number=0,
                    suggestion="Add more detailed description and examples",
                )
            )

        # Check for frontmatter presence
        if not (content.startswith("---") or content.startswith("+++")):
            issues.append(
                ValidationIssue(
                    type=IssueType.STRUCTURAL,
                    severity=IssueSeverity.CRITICAL,
                    message="No frontmatter found in agent file",
                    line_number=1,
                    suggestion="Add YAML frontmatter with required metadata",
                )
            )

        # Check for proper markdown structure
        has_headers = any(line.strip().startswith("#") for line in lines)
        if not has_headers:
            issues.append(
                ValidationIssue(
                    type=IssueType.STRUCTURAL,
                    severity=IssueSeverity.WARNING,
                    message="No markdown headers found",
                    line_number=0,
                    suggestion="Add section headers to organize content",
                )
            )

        return issues

    def _validate_frontmatter(
        self, content: str
    ) -> tuple[List[ValidationIssue], Optional[Dict[str, Any]]]:
        """Validate frontmatter content and structure."""
        issues = []
        frontmatter = None

        # Extract frontmatter
        if content.startswith("---"):
            try:
                import yaml

                end_marker = content.find("\n---\n", 3)
                if end_marker == -1:
                    issues.append(
                        ValidationIssue(
                            type=IssueType.FRONTMATTER,
                            severity=IssueSeverity.CRITICAL,
                            message="Unclosed YAML frontmatter",
                            line_number=1,
                            suggestion="Add closing --- marker",
                        )
                    )
                    return issues, None

                frontmatter_text = content[3:end_marker]
                frontmatter = yaml.safe_load(frontmatter_text)

            except yaml.YAMLError as e:
                issues.append(
                    ValidationIssue(
                        type=IssueType.FRONTMATTER,
                        severity=IssueSeverity.CRITICAL,
                        message=f"Invalid YAML frontmatter: {e}",
                        line_number=1,
                        suggestion="Fix YAML syntax errors",
                    )
                )
                return issues, None

        elif content.startswith("+++"):
            try:
                import toml

                end_marker = content.find("\n+++\n", 3)
                if end_marker == -1:
                    issues.append(
                        ValidationIssue(
                            type=IssueType.FRONTMATTER,
                            severity=IssueSeverity.CRITICAL,
                            message="Unclosed TOML frontmatter",
                            line_number=1,
                            suggestion="Add closing +++ marker",
                        )
                    )
                    return issues, None

                frontmatter_text = content[3:end_marker]
                frontmatter = toml.loads(frontmatter_text)

            except toml.TomlDecodeError as e:
                issues.append(
                    ValidationIssue(
                        type=IssueType.FRONTMATTER,
                        severity=IssueSeverity.CRITICAL,
                        message=f"Invalid TOML frontmatter: {e}",
                        line_number=1,
                        suggestion="Fix TOML syntax errors",
                    )
                )
                return issues, None

        if not frontmatter:
            return issues, None

        # Validate required fields
        for field in self.required_fields:
            if field not in frontmatter:
                issues.append(
                    ValidationIssue(
                        type=IssueType.FRONTMATTER,
                        severity=IssueSeverity.ERROR,
                        message=f"Missing required field: {field}",
                        line_number=0,
                        suggestion=f"Add {field} field to frontmatter",
                    )
                )

        # Validate field types and values
        if "version" in frontmatter:
            version = frontmatter["version"]
            if not isinstance(version, str) or not re.match(r"^\d+\.\d+\.\d+", version):
                issues.append(
                    ValidationIssue(
                        type=IssueType.FRONTMATTER,
                        severity=IssueSeverity.WARNING,
                        message="Invalid version format",
                        line_number=0,
                        suggestion="Use semantic versioning (e.g., 1.0.0)",
                    )
                )

        if "tools" in frontmatter:
            tools = frontmatter["tools"]
            if not isinstance(tools, list):
                issues.append(
                    ValidationIssue(
                        type=IssueType.FRONTMATTER,
                        severity=IssueSeverity.ERROR,
                        message="Tools field must be a list",
                        line_number=0,
                        suggestion="Convert tools to list format",
                    )
                )

        return issues, frontmatter

    def _validate_security(
        self, content: str, frontmatter: Optional[Dict[str, Any]]
    ) -> List[ValidationIssue]:
        """Validate security aspects of agent content."""
        issues = []

        # Check for dangerous patterns
        for pattern, description in self.security_patterns.items():
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_number = content[: match.start()].count("\n") + 1
                issues.append(
                    ValidationIssue(
                        type=IssueType.SECURITY,
                        severity=IssueSeverity.CRITICAL,
                        message=f"Security risk detected: {description}",
                        line_number=line_number,
                        suggestion="Remove or replace with safer alternative",
                    )
                )

        # Check for hardcoded secrets (basic patterns)
        secret_patterns = {
            r'password\s*=\s*["\'][^"\']+["\']': "Hardcoded password",
            r'api_key\s*=\s*["\'][^"\']+["\']': "Hardcoded API key",
            r'secret\s*=\s*["\'][^"\']+["\']': "Hardcoded secret",
            r'token\s*=\s*["\'][^"\']+["\']': "Hardcoded token",
        }

        for pattern, description in secret_patterns.items():
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_number = content[: match.start()].count("\n") + 1
                issues.append(
                    ValidationIssue(
                        type=IssueType.SECURITY,
                        severity=IssueSeverity.CRITICAL,
                        message=f"Potential secret exposure: {description}",
                        line_number=line_number,
                        suggestion="Use environment variables or secure configuration",
                    )
                )

        # Validate tool usage safety
        if frontmatter and "tools" in frontmatter:
            for tool in frontmatter["tools"]:
                if isinstance(tool, str) and tool not in self.safe_tools:
                    # Check if it's a known MCP tool pattern
                    if not (
                        tool.startswith("mcp__") or tool in ["Bash", "Read", "Write"]
                    ):
                        issues.append(
                            ValidationIssue(
                                type=IssueType.SECURITY,
                                severity=IssueSeverity.WARNING,
                                message=f"Unknown tool usage: {tool}",
                                line_number=0,
                                suggestion="Verify tool is safe and properly documented",
                            )
                        )

        return issues

    def _validate_content_quality(
        self, content: str, frontmatter: Optional[Dict[str, Any]]
    ) -> List[ValidationIssue]:
        """Validate content quality and completeness."""
        issues = []
        lines = content.split("\n")

        # Check for required sections
        required_sections = ["## Overview", "## Usage", "## Examples"]
        for section in required_sections:
            if section not in content:
                issues.append(
                    ValidationIssue(
                        type=IssueType.CONTENT,
                        severity=IssueSeverity.WARNING,
                        message=f"Missing recommended section: {section}",
                        line_number=0,
                        suggestion=f"Add {section} section for better documentation",
                    )
                )

        # Check for code examples
        has_code_blocks = "```" in content
        if not has_code_blocks:
            issues.append(
                ValidationIssue(
                    type=IssueType.CONTENT,
                    severity=IssueSeverity.INFO,
                    message="No code examples found",
                    line_number=0,
                    suggestion="Add code examples to demonstrate usage",
                )
            )

        # Check line length (readability)
        for i, line in enumerate(lines, 1):
            if len(line) > 120:
                issues.append(
                    ValidationIssue(
                        type=IssueType.CONTENT,
                        severity=IssueSeverity.INFO,
                        message="Line too long for readability",
                        line_number=i,
                        suggestion="Break long lines for better readability",
                    )
                )

        # Check for placeholder content
        placeholder_patterns = [r"\[TODO\]", r"\[PLACEHOLDER\]", r"XXX", r"FIXME"]

        for pattern in placeholder_patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                line_number = content[: match.start()].count("\n") + 1
                issues.append(
                    ValidationIssue(
                        type=IssueType.CONTENT,
                        severity=IssueSeverity.WARNING,
                        message="Placeholder content detected",
                        line_number=line_number,
                        suggestion="Replace placeholder with actual content",
                    )
                )

        return issues

    def _validate_tool_usage(
        self, content: str, frontmatter: Optional[Dict[str, Any]]
    ) -> List[ValidationIssue]:
        """Validate tool usage patterns and declarations."""
        issues = []

        if not frontmatter or "tools" not in frontmatter:
            return issues

        declared_tools = set(frontmatter["tools"])

        # Find tool usage in content
        tool_usage_pattern = r'<invoke name="(\w+)">'
        used_tools = set(re.findall(tool_usage_pattern, content))

        # Check for undeclared tool usage
        undeclared = used_tools - declared_tools
        for tool in undeclared:
            issues.append(
                ValidationIssue(
                    type=IssueType.TOOLS,
                    severity=IssueSeverity.WARNING,
                    message=f"Tool {tool} used but not declared",
                    line_number=0,
                    suggestion=f"Add {tool} to tools list in frontmatter",
                )
            )

        # Check for unused declared tools
        unused = declared_tools - used_tools
        for tool in unused:
            issues.append(
                ValidationIssue(
                    type=IssueType.TOOLS,
                    severity=IssueSeverity.INFO,
                    message=f"Tool {tool} declared but not used",
                    line_number=0,
                    suggestion=f"Remove {tool} from tools list or add usage example",
                )
            )

        return issues

    def _validate_dependencies(
        self, frontmatter: Optional[Dict[str, Any]]
    ) -> List[ValidationIssue]:
        """Validate agent dependencies."""
        issues = []

        if not frontmatter or "dependencies" not in frontmatter:
            return issues

        dependencies = frontmatter["dependencies"]
        if not isinstance(dependencies, list):
            issues.append(
                ValidationIssue(
                    type=IssueType.DEPENDENCIES,
                    severity=IssueSeverity.ERROR,
                    message="Dependencies must be a list",
                    line_number=0,
                    suggestion="Convert dependencies to list format",
                )
            )
            return issues

        # Check dependency format
        for dep in dependencies:
            if not isinstance(dep, str):
                issues.append(
                    ValidationIssue(
                        type=IssueType.DEPENDENCIES,
                        severity=IssueSeverity.WARNING,
                        message="Dependency should be a string",
                        line_number=0,
                        suggestion="Use string format for dependency names",
                    )
                )

        # Check for circular dependencies (basic check)
        agent_name = frontmatter.get("name", "")
        if agent_name in dependencies:
            issues.append(
                ValidationIssue(
                    type=IssueType.DEPENDENCIES,
                    severity=IssueSeverity.CRITICAL,
                    message="Circular dependency detected",
                    line_number=0,
                    suggestion="Remove self-reference from dependencies",
                )
            )

        return issues

    def _calculate_validation_score(self, issues: List[ValidationIssue]) -> int:
        """Calculate overall validation score based on issues."""
        base_score = 100

        for issue in issues:
            if issue.severity == IssueSeverity.CRITICAL:
                base_score -= 25
            elif issue.severity == IssueSeverity.ERROR:
                base_score -= 10
            elif issue.severity == IssueSeverity.WARNING:
                base_score -= 5
            elif issue.severity == IssueSeverity.INFO:
                base_score -= 1

        return max(0, base_score)

    def validate_bulk(
        self, agent_paths: List[str], validation_level: str = "basic"
    ) -> Dict[str, ValidationResult]:
        """Validate multiple agents in bulk."""
        results = {}

        for agent_path in agent_paths:
            try:
                results[agent_path] = self.validate_agent(agent_path, validation_level)
            except Exception as e:
                # Create failed result for exceptions
                critical_issue = ValidationIssue(
                    type=IssueType.STRUCTURAL,
                    severity=IssueSeverity.CRITICAL,
                    message=f"Validation failed: {e}",
                    line_number=0,
                    suggestion="Check file accessibility and content",
                )

                results[agent_path] = ValidationResult(
                    agent_path=agent_path,
                    passed=False,
                    score=0,
                    issues=[critical_issue],
                    validation_level=validation_level,
                    validated_at=datetime.now().isoformat(),
                    file_hash="",
                )

        return results

    # Abstract method implementations required by AgentValidationPort

    def validate_ecosystem_health(
        self, agents: list[Agent], scope: str = "both", include_performance: bool = True
    ) -> EcosystemHealth:
        """Validate overall ecosystem health."""

        total_agents = len(agents)
        active_agents = len([a for a in agents if a.status == "active"])
        deprecated_agents = len([a for a in agents if a.status == "deprecated"])
        error_agents = len([a for a in agents if a.status == "error"])

        # Calculate average validation score by validating each agent
        scores = []
        for agent in agents[:10]:  # Sample first 10 for performance
            try:
                result = self.validate_agent(agent.path)
                scores.append(result.score)
            except:
                scores.append(0)

        avg_score = sum(scores) / len(scores) if scores else 0

        return EcosystemHealth(
            total_agents=total_agents,
            active_agents=active_agents,
            deprecated_agents=deprecated_agents,
            error_agents=error_agents,
            avg_validation_score=avg_score,
            critical_issues=0,  # Would need to analyze validation results
            warnings=0,  # Would need to analyze validation results
            overall_health="good"
            if avg_score > 70
            else "warning"
            if avg_score > 40
            else "critical",
            recommendations=[],
            timestamp=datetime.now().isoformat(),
        )

    def check_agent_frontmatter(
        self, frontmatter: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Check agent frontmatter for compliance."""
        issues = []

        # Required fields
        required_fields = ["name", "description", "version", "author"]
        for field in required_fields:
            if field not in frontmatter:
                issues.append(
                    {
                        "field": field,
                        "severity": "high",
                        "message": f"Missing required field: {field}",
                        "suggestion": f"Add {field} field to frontmatter",
                    }
                )

        # Check field types
        if "tools" in frontmatter and not isinstance(frontmatter["tools"], list):
            issues.append(
                {
                    "field": "tools",
                    "severity": "medium",
                    "message": "Tools field must be a list",
                    "suggestion": "Convert tools to list format",
                }
            )

        if "tags" in frontmatter and not isinstance(frontmatter["tags"], list):
            issues.append(
                {
                    "field": "tags",
                    "severity": "low",
                    "message": "Tags field should be a list",
                    "suggestion": "Convert tags to list format",
                }
            )

        return issues

    def validate_agent_tools(self, tools: list[str]) -> list[dict[str, Any]]:
        """Validate agent tool availability and permissions."""
        issues = []

        # Check for dangerous tools
        dangerous_tools = ["Bash", "Execute", "Shell", "System"]
        for tool in tools:
            if tool in dangerous_tools:
                issues.append(
                    {
                        "tool": tool,
                        "severity": "high",
                        "message": f"Dangerous tool detected: {tool}",
                        "suggestion": "Use safer MCP alternatives",
                    }
                )

        # Check tool format
        for tool in tools:
            if not isinstance(tool, str) or len(tool.strip()) == 0:
                issues.append(
                    {
                        "tool": str(tool),
                        "severity": "medium",
                        "message": "Invalid tool format",
                        "suggestion": "Tool names must be non-empty strings",
                    }
                )

        return issues

    def check_dependency_health(
        self, dependencies: list[str], available_agents: list[Agent]
    ) -> list[dict[str, Any]]:
        """Check dependency health and availability."""
        issues = []

        available_names = {agent.name for agent in available_agents}

        for dependency in dependencies:
            if dependency not in available_names:
                issues.append(
                    {
                        "dependency": dependency,
                        "severity": "high",
                        "message": f"Missing dependency: {dependency}",
                        "suggestion": "Install missing agent or update dependency list",
                    }
                )

        # Check for circular dependencies (basic check)
        if len(dependencies) != len(set(dependencies)):
            duplicates = [dep for dep in dependencies if dependencies.count(dep) > 1]
            issues.append(
                {
                    "dependency": ", ".join(set(duplicates)),
                    "severity": "medium",
                    "message": "Duplicate dependencies detected",
                    "suggestion": "Remove duplicate entries",
                }
            )

        return issues
