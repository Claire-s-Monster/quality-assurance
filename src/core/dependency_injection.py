"""
Dependency injection container for Agent Ecosystem MCP Server.
Provides centralized configuration and instance management.
"""

from typing import Dict, Any, Optional, TypeVar, Type, List
import logging
import sys
import os
from pathlib import Path

# Add parent directory to path to access adapters
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

T = TypeVar("T")


class Container:
    """Dependency injection container with singleton management."""

    def __init__(self):
        """Initialize container with empty registry."""
        self._instances: Dict[str, Any] = {}
        self._factories: Dict[str, callable] = {}
        self._initialized = False

    def register(self, name: str, factory: callable) -> None:
        """Register a factory function for a dependency."""
        self._factories[name] = factory

    def register_instance(self, name: str, instance: Any) -> None:
        """Register a pre-created instance."""
        self._instances[name] = instance

    def get(self, name: str) -> Any:
        """Get dependency instance, creating if needed."""
        # Return existing instance if available
        if name in self._instances:
            return self._instances[name]

        # Create new instance using factory
        if name in self._factories:
            instance = self._factories[name](self)
            self._instances[name] = instance
            return instance

        raise KeyError(f"No factory registered for dependency: {name}")

    def has(self, name: str) -> bool:
        """Check if dependency is registered."""
        return name in self._factories or name in self._instances

    def clear(self) -> None:
        """Clear all instances (keeping factories)."""
        self._instances.clear()

    def initialize_defaults(self) -> None:
        """Initialize container with default dependencies."""
        if self._initialized:
            return

        # Register logging first (needed by others)
        self.register("logging", self._create_logging_adapter)

        # Register filesystem adapter
        self.register("filesystem", self._create_filesystem_adapter)

        # Register cache adapter
        self.register("cache", self._create_cache_adapter)

        # Register discovery adapter
        self.register("discovery", self._create_discovery_adapter)

        # Register validation adapter
        self.register("validation", self._create_validation_adapter)

        # Register lifecycle adapter
        self.register("lifecycle", self._create_lifecycle_adapter)

        # Register template adapter
        self.register("templates", self._create_template_adapter)

        # Register analytics adapter
        self.register("analytics", self._create_analytics_adapter)

        # Register access control adapter
        self.register("access_control", self._create_access_control_adapter)

        # Register command discovery adapter
        self.register("command_discovery", self._create_command_discovery_adapter)

        # Register command analysis adapter
        self.register("command_analysis", self._create_command_analysis_adapter)

        # Register ecosystem health adapter
        self.register("ecosystem_health", self._create_ecosystem_health_adapter)

        self._initialized = True

    def _create_logging_adapter(self, container: "Container") -> Any:
        """Create logging adapter."""
        from adapters.logging import LoggingAdapter

        return LoggingAdapter()

    def _create_filesystem_adapter(self, container: "Container") -> Any:
        """Create filesystem adapter with security constraints."""
        from adapters.filesystem import FilesystemAdapter

        # Define allowed root directories for agent access
        allowed_roots = [str(Path.home() / ".claude" / "agents"), "./claude/agents"]

        return FilesystemAdapter(allowed_roots=allowed_roots)

    def _create_cache_adapter(self, container: "Container") -> Any:
        """Create caching adapter."""
        # Import here to avoid circular dependencies
        try:
            from adapters.environment import CachingAdapter

            return CachingAdapter()
        except ImportError:
            # Fallback to simple in-memory cache
            from adapters.simple_cache import SimpleCacheAdapter

            return SimpleCacheAdapter()

    def _create_discovery_adapter(self, container: "Container") -> Any:
        """Create agent discovery adapter."""
        from adapters.discovery import AgentDiscoveryAdapter

        filesystem = container.get("filesystem")
        return AgentDiscoveryAdapter(filesystem)

    def _create_validation_adapter(self, container: "Container") -> Any:
        """Create agent validation adapter."""
        from adapters.validation import AgentValidationAdapter

        filesystem = container.get("filesystem")
        return AgentValidationAdapter(filesystem)

    def _create_lifecycle_adapter(self, container: "Container") -> Any:
        """Create agent lifecycle adapter."""
        # Import here to avoid circular dependencies
        try:
            from adapters.lifecycle import AgentLifecycleAdapter

            filesystem = container.get("filesystem")
            templates = container.get("templates")
            validation = container.get("validation")
            return AgentLifecycleAdapter(filesystem, templates, validation)
        except ImportError:
            # Create stub implementation
            from adapters.lifecycle_stub import LifecycleStubAdapter

            return LifecycleStubAdapter()

    def _create_template_adapter(self, container: "Container") -> Any:
        """Create agent template adapter."""
        try:
            from adapters.templates import AgentTemplateAdapter

            filesystem = container.get("filesystem")
            return AgentTemplateAdapter(filesystem)
        except ImportError:
            # Create stub implementation
            from adapters.template_stub import TemplateStubAdapter

            return TemplateStubAdapter()

    def _create_analytics_adapter(self, container: "Container") -> Any:
        """Create analytics adapter."""
        try:
            from adapters.analytics import AgentAnalyticsAdapter

            discovery = container.get("discovery")
            validation = container.get("validation")
            return AgentAnalyticsAdapter(discovery, validation)
        except ImportError:
            # Create stub implementation
            from adapters.analytics_stub import AnalyticsStubAdapter

            return AnalyticsStubAdapter()

    def _create_access_control_adapter(self, container: "Container") -> Any:
        """Create access control adapter."""
        try:
            from adapters.security import AccessControlAdapter

            return AccessControlAdapter()
        except ImportError:
            # Create stub implementation
            return AccessControlStubAdapter()

    def _create_command_discovery_adapter(self, container: "Container") -> Any:
        """Create command discovery adapter."""
        from adapters.command_discovery import CommandDiscoveryAdapter

        filesystem = container.get("filesystem")
        return CommandDiscoveryAdapter(filesystem)

    def _create_command_analysis_adapter(self, container: "Container") -> Any:
        """Create command analysis adapter."""
        from adapters.command_analysis import CommandAnalysisAdapter

        command_discovery = container.get("command_discovery")
        agent_discovery = container.get("discovery")
        return CommandAnalysisAdapter(command_discovery, agent_discovery)

    def _create_ecosystem_health_adapter(self, container: "Container") -> Any:
        """Create ecosystem health adapter."""
        try:
            from adapters.ecosystem_health import EcosystemHealthAdapter

            command_discovery = container.get("command_discovery")
            agent_discovery = container.get("discovery")
            command_analysis = container.get("command_analysis")
            return EcosystemHealthAdapter(
                command_discovery, agent_discovery, command_analysis
            )
        except ImportError:
            # Create stub implementation
            return EcosystemHealthStubAdapter()


# Create stub adapters for components not yet implemented


class SimpleCacheAdapter:
    """Simple in-memory cache adapter."""

    def __init__(self):
        self._cache = {}

    def get(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set(self, key: str, value: Any, ttl: int = 3600) -> None:
        # Simple implementation ignores TTL
        self._cache[key] = value

    def invalidate_pattern(self, pattern: str) -> int:
        # Simple pattern matching (startswith)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]
        else:
            keys_to_remove = [k for k in self._cache.keys() if k == pattern]

        for key in keys_to_remove:
            del self._cache[key]

        return len(keys_to_remove)

    def clear_all(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_statistics(self) -> Dict[str, Any]:
        return {"total_entries": len(self._cache), "cache_type": "simple_memory"}


class LifecycleStubAdapter:
    """Stub adapter for agent lifecycle operations."""

    def create_agent(self, request) -> Any:
        from core.models import OperationResult
        from datetime import datetime

        return OperationResult(
            success=False,
            message="Agent creation not yet implemented",
            details={"stub": True},
            timestamp=datetime.now().isoformat(),
        )

    def update_agent(self, agent_path: str, request) -> Any:
        from core.models import OperationResult
        from datetime import datetime

        return OperationResult(
            success=False,
            message="Agent update not yet implemented",
            details={"stub": True},
            timestamp=datetime.now().isoformat(),
        )

    def delete_agent(self, agent_path: str) -> Any:
        from core.models import OperationResult
        from datetime import datetime

        return OperationResult(
            success=False,
            message="Agent deletion not yet implemented",
            details={"stub": True},
            timestamp=datetime.now().isoformat(),
        )


class TemplateStubAdapter:
    """Stub adapter for agent templates."""

    def get_available_templates(self) -> List[str]:
        return ["basic", "validator", "reporter", "orchestrator"]

    def generate_agent_from_template(
        self, template_name: str, context: Dict[str, Any]
    ) -> str:
        return f"# {context.get('name', 'Unnamed Agent')}\n\nTemplate: {template_name}\n\nNot yet implemented."


class AnalyticsStubAdapter:
    """Stub adapter for analytics."""

    def generate_ecosystem_report(self) -> Any:
        from core.models import AnalyticsData
        from datetime import datetime

        return AnalyticsData(
            total_agents=0,
            by_classification={},
            by_access_level={},
            by_status={},
            validation_summary={},
            dependency_graph={},
            usage_patterns={},
            generated_at=datetime.now().isoformat(),
        )


class AccessControlStubAdapter:
    """Stub adapter for access control."""

    def can_read_agent(self, agent_path: str) -> bool:
        return True

    def can_modify_agent(self, agent_path: str) -> bool:
        return True

    def can_create_agent(self, access_level) -> bool:
        return True

    def can_delete_agent(self, agent_path: str) -> bool:
        return True

    def check_access_level(self, agent_level, required_level) -> bool:
        return True


class EcosystemHealthStubAdapter:
    """Stub adapter for ecosystem health analysis."""

    def generate_health_report(
        self,
        include_commands: bool = True,
        include_agents: bool = True,
        deep_analysis: bool = False,
    ):
        from core.models import EcosystemHealthReport
        from datetime import datetime

        return EcosystemHealthReport(
            total_agents=0,
            total_commands=0,
            healthy_agents=0,
            healthy_commands=0,
            broken_dependencies=0,
            deprecated_dependencies=0,
            circular_dependencies=0,
            orphaned_agents=0,
            high_risk_commands=[],
            agents_safe_to_delete=[],
            agents_requiring_migration=[],
            recommendations=["Ecosystem health analysis not yet implemented"],
            generated_at=datetime.now().isoformat(),
            scan_coverage={"agents": include_agents, "commands": include_commands},
            execution_time_ms=0.0,
        )

    def identify_broken_dependencies(self):
        return []

    def recommend_cleanup_actions(self):
        return [
            "No cleanup recommendations available - health analysis not yet implemented"
        ]

    def assess_migration_risk(self, agent_name: str):
        return {
            "agent": agent_name,
            "risk_level": "unknown",
            "message": "Migration risk assessment not yet implemented",
        }
