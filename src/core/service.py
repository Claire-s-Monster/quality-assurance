"""
Core business logic service for Agent Ecosystem MCP Server.
Orchestrates agent operations through dependency injection container.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime

from .models import (
    Agent,
    DiscoveryResult,
    ValidationResult,
    AccessLevel,
    OperationResult,
    SecurityViolation,
    AgentCreationRequest,
    AgentUpdateRequest,
    AnalyticsData,
    CacheInfo,
)
from .dependency_injection import Container


class AgentEcosystemService:
    """Core service orchestrating all agent ecosystem operations."""

    def __init__(self, container: Container):
        """Initialize service with dependency injection container."""
        self.container = container
        self.logger = container.get("logging")

        # Get adapters through DI container
        self.discovery = container.get("discovery")
        self.validation = container.get("validation")
        self.lifecycle = container.get("lifecycle")
        self.templates = container.get("templates")
        self.analytics = container.get("analytics")
        self.access_control = container.get("access_control")
        self.filesystem = container.get("filesystem")
        self.cache = container.get("cache")

    # Agent Discovery Operations

    def discover_agents(
        self,
        scope: str = "both",
        categories: Optional[List[str]] = None,
        access_level: Optional[AccessLevel] = None,
    ) -> DiscoveryResult:
        """Discover agents with optional filtering and access control."""
        try:
            self.logger.log_operation(
                "discover_agents",
                {
                    "scope": scope,
                    "categories": categories,
                    "access_level": access_level.value if access_level else None,
                },
            )

            # Check cache first
            cache_key = f"discovery:{scope}:{','.join(categories or [])}:{access_level.value if access_level else 'all'}"
            cached_result = self.cache.get(cache_key)
            if cached_result:
                return DiscoveryResult(**cached_result)

            # Perform discovery
            result = self.discovery.discover_agents(scope, categories)

            # Apply access level filtering if specified
            if access_level:
                filtered_agents = [
                    agent
                    for agent in result.agents
                    if self.access_control.check_access_level(
                        agent.access_level, access_level
                    )
                ]
                result.agents = filtered_agents
                result.total_count = len(filtered_agents)
                result.by_access_level = {access_level.value: len(filtered_agents)}

            # Cache result for 5 minutes
            self.cache.set(cache_key, result.dict(), 300)

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "discover_agents"})
            raise SecurityViolation(f"Agent discovery failed: {e}")

    def search_agents(self, query: str, scope: str = "both") -> List[Agent]:
        """Search agents by query with caching."""
        try:
            self.logger.log_operation("search_agents", {"query": query, "scope": scope})

            # Check cache first
            cache_key = f"search:{scope}:{query}"
            cached_result = self.cache.get(cache_key)
            if cached_result:
                return [Agent(**agent_data) for agent_data in cached_result]

            # Perform search
            result = self.discovery.search_agents(query, scope)

            # Cache result for 2 minutes
            self.cache.set(cache_key, [agent.dict() for agent in result], 120)

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "search_agents"})
            raise SecurityViolation(f"Agent search failed: {e}")

    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get specific agent by ID with caching."""
        try:
            self.logger.log_operation("get_agent_by_id", {"agent_id": agent_id})

            # Check cache first
            cache_key = f"agent:{agent_id}"
            cached_result = self.cache.get(cache_key)
            if cached_result:
                return Agent(**cached_result)

            # Find agent
            result = self.discovery.find_agent_by_id(agent_id)

            # Cache result for 10 minutes
            if result:
                self.cache.set(cache_key, result.dict(), 600)

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "get_agent_by_id"})
            raise SecurityViolation(f"Agent retrieval failed: {e}")

    # Agent Validation Operations

    def validate_agent(
        self, agent_path: str, validation_level: str = "comprehensive"
    ) -> ValidationResult:
        """Validate agent with comprehensive checks."""
        try:
            # Verify access to agent file
            if not self.access_control.can_read_agent(agent_path):
                raise SecurityViolation(f"Access denied to agent: {agent_path}")

            self.logger.log_operation(
                "validate_agent",
                {"agent_path": agent_path, "validation_level": validation_level},
            )

            # Check cache first
            file_hash = self.filesystem.calculate_file_hash(agent_path)
            cache_key = f"validation:{file_hash}:{validation_level}"
            cached_result = self.cache.get(cache_key)
            if cached_result:
                return ValidationResult(**cached_result)

            # Perform validation
            result = self.validation.validate_agent(agent_path, validation_level)

            # Cache result for 5 minutes
            self.cache.set(cache_key, result.dict(), 300)

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "validate_agent"})
            raise SecurityViolation(f"Agent validation failed: {e}")

    def validate_agents_bulk(
        self, agent_paths: List[str], validation_level: str = "basic"
    ) -> Dict[str, ValidationResult]:
        """Validate multiple agents in bulk with progress tracking."""
        try:
            self.logger.log_operation(
                "validate_agents_bulk",
                {"agent_count": len(agent_paths), "validation_level": validation_level},
            )

            results = {}

            for agent_path in agent_paths:
                # Check access for each agent
                if not self.access_control.can_read_agent(agent_path):
                    results[agent_path] = ValidationResult(
                        agent_path=agent_path,
                        passed=False,
                        score=0,
                        issues=[],
                        validation_level=validation_level,
                        validated_at=datetime.now().isoformat(),
                        file_hash="",
                    )
                    continue

                # Validate individual agent
                try:
                    results[agent_path] = self.validate_agent(
                        agent_path, validation_level
                    )
                except Exception as e:
                    self.logger.log_error(
                        f"Failed to validate {agent_path}: {e}",
                        {"operation": "validate_agents_bulk"},
                    )
                    # Continue with other agents
                    continue

            return results

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "validate_agents_bulk"})
            raise SecurityViolation(f"Bulk validation failed: {e}")

    # Agent Lifecycle Operations

    def create_agent(self, request: AgentCreationRequest) -> OperationResult:
        """Create new agent with validation and access control."""
        try:
            # Check creation permissions
            if not self.access_control.can_create_agent(request.access_level):
                raise SecurityViolation(
                    f"Insufficient permissions to create {request.access_level.value} agent"
                )

            self.logger.log_operation(
                "create_agent",
                {"name": request.name, "access_level": request.access_level.value},
            )

            # Validate request
            if not self._validate_creation_request(request):
                return OperationResult(
                    success=False,
                    message="Invalid agent creation request",
                    details={},
                    timestamp=datetime.now().isoformat(),
                )

            # Create agent through lifecycle port
            result = self.lifecycle.create_agent(request)

            # Invalidate discovery cache
            self.cache.invalidate_pattern("discovery:*")

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "create_agent"})
            raise SecurityViolation(f"Agent creation failed: {e}")

    def update_agent(
        self, agent_id: str, request: AgentUpdateRequest
    ) -> OperationResult:
        """Update existing agent with validation."""
        try:
            # Find existing agent
            existing_agent = self.get_agent_by_id(agent_id)
            if not existing_agent:
                return OperationResult(
                    success=False,
                    message=f"Agent not found: {agent_id}",
                    details={},
                    timestamp=datetime.now().isoformat(),
                )

            # Check update permissions
            if not self.access_control.can_modify_agent(existing_agent.path):
                raise SecurityViolation(
                    f"Insufficient permissions to update agent: {agent_id}"
                )

            self.logger.log_operation(
                "update_agent",
                {
                    "agent_id": agent_id,
                    "update_fields": list(request.dict(exclude_unset=True).keys()),
                },
            )

            # Update agent through lifecycle port
            result = self.lifecycle.update_agent(existing_agent.path, request)

            # Invalidate related caches
            self.cache.invalidate_pattern(f"agent:{agent_id}*")
            self.cache.invalidate_pattern("discovery:*")

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "update_agent"})
            raise SecurityViolation(f"Agent update failed: {e}")

    def delete_agent(self, agent_id: str, force: bool = False) -> OperationResult:
        """Delete agent with safety checks."""
        try:
            # Find existing agent
            existing_agent = self.get_agent_by_id(agent_id)
            if not existing_agent:
                return OperationResult(
                    success=False,
                    message=f"Agent not found: {agent_id}",
                    details={},
                    timestamp=datetime.now().isoformat(),
                )

            # Check deletion permissions
            if not self.access_control.can_delete_agent(existing_agent.path):
                raise SecurityViolation(
                    f"Insufficient permissions to delete agent: {agent_id}"
                )

            self.logger.log_operation(
                "delete_agent", {"agent_id": agent_id, "force": force}
            )

            # Check dependencies if not forced
            if not force:
                # Find agents that depend on this one
                dependent_agents = self._find_dependent_agents(existing_agent.name)
                if dependent_agents:
                    return OperationResult(
                        success=False,
                        message=f"Cannot delete agent: {len(dependent_agents)} agents depend on it",
                        details={
                            "dependent_agents": [
                                agent.name for agent in dependent_agents
                            ]
                        },
                        timestamp=datetime.now().isoformat(),
                    )

            # Delete agent through lifecycle port
            result = self.lifecycle.delete_agent(existing_agent.path)

            # Invalidate all related caches
            self.cache.invalidate_pattern(f"agent:{agent_id}*")
            self.cache.invalidate_pattern("discovery:*")

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "delete_agent"})
            raise SecurityViolation(f"Agent deletion failed: {e}")

    def deprecate_agent(self, agent_id: str, reason: str) -> OperationResult:
        """Mark agent as deprecated with migration guidance."""
        try:
            # Find existing agent
            existing_agent = self.get_agent_by_id(agent_id)
            if not existing_agent:
                return OperationResult(
                    success=False,
                    message=f"Agent not found: {agent_id}",
                    details={},
                    timestamp=datetime.now().isoformat(),
                )

            # Check modification permissions
            if not self.access_control.can_modify_agent(existing_agent.path):
                raise SecurityViolation(
                    f"Insufficient permissions to deprecate agent: {agent_id}"
                )

            self.logger.log_operation(
                "deprecate_agent", {"agent_id": agent_id, "reason": reason}
            )

            # Update agent status to deprecated
            request = AgentUpdateRequest(
                status="deprecated",
                tags=existing_agent.tags + ["deprecated"],
                description=f"{existing_agent.description}\n\n**DEPRECATED:** {reason}",
            )

            result = self.update_agent(agent_id, request)

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "deprecate_agent"})
            raise SecurityViolation(f"Agent deprecation failed: {e}")

    # Analytics and Reporting

    def get_ecosystem_analytics(
        self, include_cache_stats: bool = False
    ) -> AnalyticsData:
        """Get comprehensive ecosystem analytics."""
        try:
            self.logger.log_operation(
                "get_ecosystem_analytics", {"include_cache_stats": include_cache_stats}
            )

            # Check cache first
            cache_key = f"analytics:ecosystem:{include_cache_stats}"
            cached_result = self.cache.get(cache_key)
            if cached_result:
                return AnalyticsData(**cached_result)

            # Generate analytics
            result = self.analytics.generate_ecosystem_report()

            # Add cache statistics if requested
            if include_cache_stats:
                cache_stats = self.cache.get_statistics()
                result.cache_info = CacheInfo(**cache_stats)

            # Cache result for 10 minutes
            self.cache.set(cache_key, result.dict(), 600)

            return result

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "get_ecosystem_analytics"})
            raise SecurityViolation(f"Analytics generation failed: {e}")

    # Helper Methods

    def _validate_creation_request(self, request: AgentCreationRequest) -> bool:
        """Validate agent creation request."""
        # Check required fields
        if not request.name or not request.description:
            return False

        # Check name uniqueness
        existing_agent = self.discovery.search_agents(request.name)
        if any(agent.name == request.name for agent in existing_agent):
            return False

        # Validate tools list
        if not request.tools or not isinstance(request.tools, list):
            return False

        return True

    def _find_dependent_agents(self, agent_name: str) -> List[Agent]:
        """Find agents that depend on the specified agent."""
        all_agents = self.discovery.discover_agents(scope="both")
        dependent_agents = []

        for agent in all_agents.agents:
            if agent_name in agent.dependencies:
                dependent_agents.append(agent)

        return dependent_agents

    # Cache Management

    def clear_cache(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """Clear cache with optional pattern matching."""
        try:
            self.logger.log_operation("clear_cache", {"pattern": pattern})

            if pattern:
                cleared_count = self.cache.invalidate_pattern(pattern)
            else:
                cleared_count = self.cache.clear_all()

            return {
                "cleared_entries": cleared_count,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "clear_cache"})
            raise SecurityViolation(f"Cache clearing failed: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            self.logger.log_operation("get_cache_stats", {})
            return self.cache.get_statistics()

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "get_cache_stats"})
            raise SecurityViolation(f"Cache stats retrieval failed: {e}")

    # Health and Status

    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        try:
            health_status = {
                "timestamp": datetime.now().isoformat(),
                "status": "healthy",
                "components": {},
            }

            # Check each component
            components = [
                ("discovery", self.discovery),
                ("validation", self.validation),
                ("filesystem", self.filesystem),
                ("cache", self.cache),
            ]

            for name, component in components:
                try:
                    # Basic functionality check
                    if hasattr(component, "health_check"):
                        health_status["components"][name] = component.health_check()
                    else:
                        health_status["components"][name] = {"status": "available"}
                except Exception as e:
                    health_status["components"][name] = {
                        "status": "error",
                        "error": str(e),
                    }
                    health_status["status"] = "degraded"

            return health_status

        except Exception as e:
            self.logger.log_error(str(e), {"operation": "health_check"})
            return {
                "timestamp": datetime.now().isoformat(),
                "status": "error",
                "error": str(e),
            }
