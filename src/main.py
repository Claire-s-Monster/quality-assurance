"""
Agent Ecosystem MCP Server - Main Entry Point

Provides comprehensive agent management capabilities through Model Context Protocol.
Supports discovery, validation, lifecycle management, and analytics for Claude Code agents.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime

import uvicorn
from fastmcp import FastMCP

from .core.service import AgentEcosystemService
from .core.dependency_injection import Container
from .core.models import (
    Agent, DiscoveryResult, ValidationResult, AccessLevel, AgentCreationRequest,
    AgentUpdateRequest, OperationResult, AnalyticsData, SecurityViolation,
    CommandDiscoveryResult, Command, AgentUsageAnalysis, CommandAgentDependency,
    EcosystemHealthReport
)

# Initialize FastMCP app
app = FastMCP("Agent Ecosystem MCP Server")

# Initialize dependency injection container
container = Container()
container.initialize_defaults()

# Initialize core service
service = AgentEcosystemService(container)


# Agent Discovery Functions

@app.tool()
def discover_agents(
    scope: str = "both",
    categories: Optional[List[str]] = None,
    access_level: Optional[str] = None
) -> Dict[str, Any]:
    """
    Discover agents from global and/or local directories with optional filtering.
    
    Args:
        scope: Search scope ("global", "local", or "both")
        categories: Optional list of categories to filter by
        access_level: Optional access level filter ("meta", "validator", "infrastructure", "domain")
    
    Returns:
        Discovery result with agents, counts, and statistics
    """
    try:
        # Convert access level string to enum if provided
        access_enum = None
        if access_level:
            try:
                access_enum = AccessLevel(access_level.lower())
            except ValueError:
                return {
                    "error": f"Invalid access level: {access_level}",
                    "valid_levels": [level.value for level in AccessLevel]
                }
        
        result = service.discover_agents(scope, categories, access_enum)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def search_agents(query: str, scope: str = "both") -> Dict[str, Any]:
    """
    Search agents by name, description, or tags using text query.
    
    Args:
        query: Search query string
        scope: Search scope ("global", "local", or "both")
    
    Returns:
        List of matching agents with metadata
    """
    try:
        agents = service.search_agents(query, scope)
        return {
            "agents": [agent.dict() for agent in agents],
            "total_found": len(agents),
            "query": query,
            "scope": scope,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def get_agent_by_id(agent_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific agent by ID.
    
    Args:
        agent_id: Unique agent identifier
    
    Returns:
        Agent details or error if not found
    """
    try:
        agent = service.get_agent_by_id(agent_id)
        if agent:
            return {
                "agent": agent.dict(),
                "found": True,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "found": False,
                "agent_id": agent_id,
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Agent Validation Functions

@app.tool()
def validate_agent(
    agent_path: str,
    validation_level: str = "comprehensive"
) -> Dict[str, Any]:
    """
    Validate agent file for structure, content, and security compliance.
    
    Args:
        agent_path: Absolute path to agent file
        validation_level: Validation depth ("basic", "security", "comprehensive")
    
    Returns:
        Validation result with score, issues, and recommendations
    """
    try:
        result = service.validate_agent(agent_path, validation_level)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def validate_agents_bulk(
    agent_paths: List[str],
    validation_level: str = "basic"
) -> Dict[str, Any]:
    """
    Validate multiple agents in bulk with progress tracking.
    
    Args:
        agent_paths: List of absolute paths to agent files
        validation_level: Validation depth ("basic", "security", "comprehensive")
    
    Returns:
        Dictionary mapping agent paths to validation results
    """
    try:
        results = service.validate_agents_bulk(agent_paths, validation_level)
        
        # Convert to serializable format
        serialized_results = {}
        for path, result in results.items():
            serialized_results[path] = result.dict()
        
        # Calculate summary statistics
        total_agents = len(results)
        passed_agents = sum(1 for r in results.values() if r.passed)
        
        return {
            "results": serialized_results,
            "summary": {
                "total_agents": total_agents,
                "passed_agents": passed_agents,
                "failed_agents": total_agents - passed_agents,
                "pass_rate": (passed_agents / total_agents * 100) if total_agents > 0 else 0
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Agent Lifecycle Functions

@app.tool()
def create_agent(
    name: str,
    description: str,
    access_level: str,
    tools: List[str],
    template: str = "basic",
    category: Optional[str] = None,
    dependencies: Optional[List[str]] = None,
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a new agent from template with validation and security checks.
    
    Args:
        name: Agent name (unique identifier)
        description: Agent description and purpose
        access_level: Access control level ("meta", "validator", "infrastructure", "domain")
        tools: List of tools the agent can use
        template: Template to use for creation ("basic", "validator", "reporter", "orchestrator")
        category: Agent category classification
        dependencies: Optional list of agent dependencies
        tags: Optional list of tags for organization
    
    Returns:
        Operation result with success status and details
    """
    try:
        # Convert access level string to enum
        try:
            access_enum = AccessLevel(access_level.lower())
        except ValueError:
            return {
                "error": f"Invalid access level: {access_level}",
                "valid_levels": [level.value for level in AccessLevel]
            }
        
        # Create agent creation request
        request = AgentCreationRequest(
            name=name,
            description=description,
            access_level=access_enum,
            tools=tools,
            template=template,
            category=category,
            dependencies=dependencies or [],
            tags=tags or []
        )
        
        result = service.create_agent(request)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def update_agent(
    agent_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    tools: Optional[List[str]] = None,
    dependencies: Optional[List[str]] = None,
    tags: Optional[List[str]] = None,
    status: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update existing agent with new metadata and configuration.
    
    Args:
        agent_id: Unique agent identifier
        name: Optional new name
        description: Optional new description
        tools: Optional new tools list
        dependencies: Optional new dependencies list
        tags: Optional new tags list
        status: Optional new status ("active", "deprecated", "inactive")
    
    Returns:
        Operation result with success status and details
    """
    try:
        # Create update request with only provided fields
        request_data = {}
        if name is not None:
            request_data["name"] = name
        if description is not None:
            request_data["description"] = description
        if tools is not None:
            request_data["tools"] = tools
        if dependencies is not None:
            request_data["dependencies"] = dependencies
        if tags is not None:
            request_data["tags"] = tags
        if status is not None:
            request_data["status"] = status
        
        request = AgentUpdateRequest(**request_data)
        result = service.update_agent(agent_id, request)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def delete_agent(agent_id: str, force: bool = False) -> Dict[str, Any]:
    """
    🚨 **DANGEROUS OPERATION** 🚨
    Delete agent with dependency checking and safety controls.
    
    ⚠️  **MANDATORY PREREQUISITE** ⚠️
    You MUST call analyze_agent_deletion_impact(agent_name) FIRST and verify:
    1. safe_to_delete: true 
    2. No critical dependencies
    3. Follow all recommendations
    
    Args:
        agent_id: Unique agent identifier
        force: Skip dependency checks (⚠️ EXTREMELY DANGEROUS - avoid using)
    
    Returns:
        Operation result with success status and details
        
    Safety Protocol:
        1. ALWAYS: analyze_agent_deletion_impact(agent_name) first
        2. CHECK: safe_to_delete status in result
        3. REVIEW: affected_commands list
        4. ONLY PROCEED: if safe_to_delete is true
        5. CONSIDER: deprecate_agent() instead for gradual migration
        
    Alternative: Use deprecate_agent() for safer gradual retirement
    """
    try:
        result = service.delete_agent(agent_id, force)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def deprecate_agent(agent_id: str, reason: str) -> Dict[str, Any]:
    """
    Mark agent as deprecated with migration guidance.
    
    Args:
        agent_id: Unique agent identifier
        reason: Deprecation reason and migration guidance
    
    Returns:
        Operation result with success status and details
    """
    try:
        result = service.deprecate_agent(agent_id, reason)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Analytics and Reporting Functions

@app.tool()
def get_ecosystem_analytics(include_cache_stats: bool = False) -> Dict[str, Any]:
    """
    Get comprehensive ecosystem analytics and health metrics.
    
    Args:
        include_cache_stats: Include cache performance statistics
    
    Returns:
        Analytics data with agent counts, classifications, and trends
    """
    try:
        result = service.get_ecosystem_analytics(include_cache_stats)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def get_agent_dependencies(agent_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get agent dependency graph and relationships.
    
    Args:
        agent_id: Optional specific agent ID to analyze (analyzes all if not provided)
    
    Returns:
        Dependency graph with relationships and potential issues
    """
    try:
        if agent_id:
            # Get specific agent dependencies
            agent = service.get_agent_by_id(agent_id)
            if not agent:
                return {
                    "error": f"Agent not found: {agent_id}",
                    "timestamp": datetime.now().isoformat()
                }
            
            return {
                "agent_id": agent_id,
                "dependencies": agent.dependencies,
                "dependents": [],  # Would need to implement reverse lookup
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Get ecosystem-wide dependency analysis
            analytics = service.get_ecosystem_analytics()
            return {
                "dependency_graph": analytics.dependency_graph,
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Template and Classification Functions

@app.tool()
def list_agent_templates() -> Dict[str, Any]:
    """
    List available agent templates with descriptions and use cases.
    
    Returns:
        Available templates with metadata and examples
    """
    try:
        # Get available templates from template adapter
        templates = container.get("templates").get_available_templates()
        
        # Add template descriptions and metadata
        template_info = {
            "basic": {
                "name": "basic",
                "description": "General-purpose agent template with common tools",
                "use_cases": ["Simple automation", "Basic interactions", "Prototype development"],
                "default_tools": ["Read", "Write", "Edit", "Bash"]
            },
            "validator": {
                "name": "validator", 
                "description": "Specialized template for validation and checking operations",
                "use_cases": ["Code validation", "Quality checks", "Compliance verification"],
                "default_tools": ["Read", "Grep", "Glob", "Edit"]
            },
            "reporter": {
                "name": "reporter",
                "description": "Template for data analysis and reporting agents",
                "use_cases": ["Data analysis", "Report generation", "Metrics collection"],
                "default_tools": ["Read", "Grep", "Glob", "Write"]
            },
            "orchestrator": {
                "name": "orchestrator",
                "description": "Template for complex workflow coordination",
                "use_cases": ["Multi-step processes", "Workflow coordination", "Task delegation"],
                "default_tools": ["Task", "Read", "Write", "Edit", "Bash"]
            }
        }
        
        return {
            "templates": template_info,
            "available_count": len(templates),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def classify_agent_access_level(agent_path: str) -> Dict[str, Any]:
    """
    Classify agent's appropriate access level based on content and patterns.
    
    Args:
        agent_path: Absolute path to agent file
    
    Returns:
        Recommended access level with justification
    """
    try:
        # Read and analyze agent
        filesystem = container.get("filesystem")
        content = filesystem.read_file(agent_path)
        
        # Simple classification based on filename and content patterns
        filename = agent_path.split("/")[-1].lower()
        
        if filename.startswith("meta-"):
            recommended_level = AccessLevel.META
            justification = "Filename indicates META-level operations"
        elif "validate" in filename or "check" in filename:
            recommended_level = AccessLevel.VALIDATOR
            justification = "Validation-focused agent identified by filename"
        elif filename.startswith("micro-") or filename.startswith("rapid-"):
            recommended_level = AccessLevel.INFRASTRUCTURE
            justification = "Fast, lightweight operations indicated by filename"
        else:
            recommended_level = AccessLevel.DOMAIN
            justification = "General domain-specific agent (default classification)"
        
        # Additional content-based analysis could be added here
        
        return {
            "agent_path": agent_path,
            "recommended_access_level": recommended_level.value,
            "justification": justification,
            "confidence": "medium",  # Would be calculated based on multiple factors
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Cache and Performance Functions

@app.tool()
def clear_cache(pattern: Optional[str] = None) -> Dict[str, Any]:
    """
    Clear server cache with optional pattern matching.
    
    Args:
        pattern: Optional pattern to match cache keys (e.g., "discovery:*")
    
    Returns:
        Cache clearing result with statistics
    """
    try:
        result = service.clear_cache(pattern)
        return result
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def get_cache_statistics() -> Dict[str, Any]:
    """
    Get cache performance statistics and health metrics.
    
    Returns:
        Cache statistics including hit rates, sizes, and performance metrics
    """
    try:
        stats = service.get_cache_stats()
        return {
            "cache_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Health and Monitoring Functions

@app.tool()
def health_check() -> Dict[str, Any]:
    """
    Perform comprehensive health check of all server components.
    
    Returns:
        Health status with component-level diagnostics
    """
    try:
        health_status = service.health_check()
        return health_status
        
    except Exception as e:
        return {
            "timestamp": datetime.now().isoformat(),
            "status": "error",
            "error": str(e)
        }


@app.tool() 
def get_server_info() -> Dict[str, Any]:
    """
    Get server information and capabilities.
    
    Returns:
        Server version, capabilities, and configuration
    """
    return {
        "server_name": "Agent Ecosystem MCP Server",
        "version": "1.0.0",
        "capabilities": {
            "discovery": True,
            "validation": True, 
            "lifecycle_management": True,
            "analytics": True,
            "caching": True,
            "access_control": True
        },
        "supported_access_levels": [level.value for level in AccessLevel],
        "supported_validation_levels": ["basic", "security", "comprehensive"],
        "available_templates": ["basic", "validator", "reporter", "orchestrator"],
        "command_discovery": True,
        "agent_command_analysis": True,
        "timestamp": datetime.now().isoformat()
    }


# Command Discovery and Analysis Functions

@app.tool()
def discover_commands(
    scope: str = "both",
    command_types: Optional[List[str]] = None,
    include_agent_analysis: bool = True
) -> Dict[str, Any]:
    """
    Discover Claude Code commands from ~/.claude/commands/ and local directories.
    Critical for understanding agent dependencies before deletion.
    
    Args:
        scope: Search scope ("global", "local", or "both")
        command_types: Optional list of command types to filter by ("slash", "system_prompt", "hook", "custom")
        include_agent_analysis: Whether to analyze agent references within commands
    
    Returns:
        Discovery result with commands, agent dependencies, and statistics
    """
    try:
        # Get command discovery adapter from container
        command_discovery = container.get("command_discovery")
        result = command_discovery.discover_commands(scope, command_types, include_agent_analysis)
        return result.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def search_commands(
    query: str, 
    scope: str = "both", 
    search_content: bool = False
) -> Dict[str, Any]:
    """
    Search commands by name, description, or content using text query.
    
    Args:
        query: Search query string
        scope: Search scope ("global", "local", or "both") 
        search_content: Whether to search within command content (slower but thorough)
    
    Returns:
        List of matching commands with metadata
    """
    try:
        command_discovery = container.get("command_discovery")
        commands = command_discovery.search_commands(query, scope, search_content)
        
        return {
            "commands": [command.dict() for command in commands],
            "total_found": len(commands),
            "query": query,
            "scope": scope,
            "searched_content": search_content,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def analyze_agent_usage_in_commands(agent_name: str) -> Dict[str, Any]:
    """
    Analyze how a specific agent is used across all commands.
    CRITICAL: Use this before deleting an agent to understand impact.
    
    Args:
        agent_name: Name of the agent to analyze
    
    Returns:
        Usage analysis including affected commands, references, and deletion impact
    """
    try:
        command_analysis = container.get("command_analysis")
        analysis = command_analysis.analyze_agent_usage(agent_name)
        return analysis.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def find_commands_using_agent(
    agent_name: str, 
    scope: str = "both"
) -> Dict[str, Any]:
    """
    Find all commands that reference a specific agent.
    Essential for dependency management and safe agent operations.
    
    Args:
        agent_name: Name of the agent to find references for
        scope: Search scope ("global", "local", or "both")
    
    Returns:
        List of command dependencies with details about how agent is used
    """
    try:
        command_analysis = container.get("command_analysis") 
        dependencies = command_analysis.find_commands_using_agent(agent_name, scope)
        
        return {
            "agent_name": agent_name,
            "dependencies": [dep.dict() for dep in dependencies],
            "total_commands": len(dependencies),
            "scope": scope,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def analyze_agent_deletion_impact(agent_name: str) -> Dict[str, Any]:
    """
    🚨 **CRITICAL SAFETY FUNCTION** 🚨
    Analyze the impact of deleting an agent on the command ecosystem.
    
    ⚠️  **MANDATORY BEFORE ANY AGENT DELETION** ⚠️
    This function MUST be called before delete_agent() or deprecate_agent() operations.
    It identifies which commands will break and provides safety recommendations.
    
    Args:
        agent_name: Name of the agent to analyze for deletion
    
    Returns:
        Impact analysis with:
        - safe_to_delete: boolean indicating if deletion is safe
        - affected_commands: list of commands that will break
        - total_references: number of places agent is used
        - recommendations: specific safety guidance
        - risk_level: "low", "medium", "high", or "critical"
    
    Example Usage:
        Before: delete_agent("my-agent") 
        REQUIRED: analyze_agent_deletion_impact("my-agent") FIRST
        Only proceed if result["safe_to_delete"] is True
    """
    try:
        command_analysis = container.get("command_analysis")
        impact = command_analysis.analyze_deletion_impact(agent_name)
        return impact
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def generate_agent_migration_plan(
    old_agent: str, 
    new_agent: str
) -> Dict[str, Any]:
    """
    Generate comprehensive migration plan for replacing one agent with another.
    
    Args:
        old_agent: Name of agent to be replaced
        new_agent: Name of replacement agent
    
    Returns:
        Migration plan with steps, timeline, risks, and rollback procedures
    """
    try:
        command_analysis = container.get("command_analysis")
        plan = command_analysis.generate_migration_plan(old_agent, new_agent)
        return plan
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def get_command_by_id(command_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific command by ID.
    
    Args:
        command_id: Unique command identifier
    
    Returns:
        Command details including agent dependencies and metadata
    """
    try:
        command_discovery = container.get("command_discovery")
        command = command_discovery.get_command_by_id(command_id)
        
        if command:
            return {
                "command": command.dict(),
                "found": True,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "found": False,
                "command_id": command_id,
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool()
def generate_ecosystem_health_report(
    include_commands: bool = True,
    include_agents: bool = True,
    deep_analysis: bool = False
) -> Dict[str, Any]:
    """
    Generate comprehensive ecosystem health report including both agents and commands.
    
    Args:
        include_commands: Include command analysis in report
        include_agents: Include agent analysis in report  
        deep_analysis: Perform deep dependency analysis (slower but more thorough)
    
    Returns:
        Health report with dependency issues, recommendations, and risk assessment
    """
    try:
        ecosystem_health = container.get("ecosystem_health")
        report = ecosystem_health.generate_health_report(
            include_commands, include_agents, deep_analysis
        )
        return report.dict()
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.tool() 
def identify_broken_dependencies() -> Dict[str, Any]:
    """
    Identify broken dependencies between commands and agents.
    
    Returns:
        List of broken dependencies with details and remediation suggestions
    """
    try:
        ecosystem_health = container.get("ecosystem_health")
        broken_deps = ecosystem_health.identify_broken_dependencies()
        
        return {
            "broken_dependencies": broken_deps,
            "total_issues": len(broken_deps),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# Initialize server for development
if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="localhost", 
        port=8002,
        reload=True
    )