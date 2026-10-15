"""
Command-agent analysis adapter for dependency impact assessment.
Critical for safe agent deletion and ecosystem health monitoring.
"""

from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import time

from core.ports import AgentCommandAnalysisPort, EcosystemHealthPort
from core.models import (
    AgentUsageAnalysis,
    CommandAgentDependency,
    EcosystemHealthReport,
    Command,
    Agent,
    CommandDiscoveryResult,
    DiscoveryResult,
)
from adapters.command_discovery import CommandDiscoveryAdapter
from adapters.discovery import AgentDiscoveryAdapter


class CommandAnalysisAdapter(AgentCommandAnalysisPort):
    """Analyzes relationships between agents and commands for impact assessment."""

    def __init__(
        self,
        command_discovery: CommandDiscoveryAdapter,
        agent_discovery: AgentDiscoveryAdapter,
    ):
        self.command_discovery = command_discovery
        self.agent_discovery = agent_discovery

    def analyze_agent_usage(
        self, agent_name: str, include_commands: bool = True
    ) -> AgentUsageAnalysis:
        """Analyze how an agent is used across commands."""
        # Find the agent first
        agent = self.agent_discovery.find_agent_by_id(agent_name)
        if not agent:
            # Search by name
            search_results = self.agent_discovery.search_agents(agent_name)
            agent = search_results[0] if search_results else None

        # Initialize analysis result
        analysis = AgentUsageAnalysis(
            agent_name=agent_name,
            agent_path=agent.path if agent else None,
            agent_status=agent.status if agent else None,
            total_references=0,
            command_count=0,
            referencing_commands=[],
            usage_types={},
            reference_strength={},
            deletion_impact="unknown",
            affected_commands=[],
            migration_effort="unknown",
        )

        if not include_commands:
            return analysis

        # Discover all commands
        commands_result = self.command_discovery.discover_commands(scope="both")

        # Find commands that reference this agent
        referencing_commands = []
        total_references = 0
        usage_types = {}
        reference_strength = {}

        for command in commands_result.commands:
            command_references = 0
            command_usage_types = []
            command_strengths = []

            for ref in command.agent_references:
                if ref.agent_name == agent_name:
                    command_references += 1
                    total_references += 1
                    command_usage_types.append(ref.usage_pattern)

                    # Determine reference strength
                    strength = self._assess_reference_strength(ref)
                    command_strengths.append(strength)

            if command_references > 0:
                referencing_commands.append(command.name)

                # Track usage types
                for usage_type in command_usage_types:
                    usage_types[usage_type] = usage_types.get(usage_type, 0) + 1

                # Track reference strengths
                for strength in command_strengths:
                    reference_strength[strength] = (
                        reference_strength.get(strength, 0) + 1
                    )

                # Create dependency object
                dependency = CommandAgentDependency(
                    command_id=command.id,
                    command_name=command.name,
                    command_path=command.path,
                    agent_name=agent_name,
                    reference_count=command_references,
                    reference_types=[
                        ref.reference_type
                        for ref in command.agent_references
                        if ref.agent_name == agent_name
                    ],
                    usage_patterns=command_usage_types,
                    dependency_strength=self._calculate_dependency_strength(
                        command_references, command_strengths
                    ),
                    breaking_change_risk=self._assess_breaking_change_risk(
                        command_usage_types
                    ),
                    migration_complexity=self._assess_migration_complexity(
                        command_usage_types, command_references
                    ),
                )

                analysis.affected_commands.append(dependency)

        # Update analysis with findings
        analysis.total_references = total_references
        analysis.command_count = len(referencing_commands)
        analysis.referencing_commands = referencing_commands
        analysis.usage_types = usage_types
        analysis.reference_strength = reference_strength
        analysis.deletion_impact = self._assess_deletion_impact(
            total_references, len(referencing_commands)
        )
        analysis.migration_effort = self._assess_overall_migration_effort(
            analysis.affected_commands
        )

        return analysis

    def find_commands_using_agent(
        self, agent_name: str, scope: str = "both"
    ) -> List[CommandAgentDependency]:
        """Find all commands that reference a specific agent."""
        commands_result = self.command_discovery.discover_commands(scope=scope)
        dependencies = []

        for command in commands_result.commands:
            agent_refs = [
                ref for ref in command.agent_references if ref.agent_name == agent_name
            ]

            if agent_refs:
                dependency = CommandAgentDependency(
                    command_id=command.id,
                    command_name=command.name,
                    command_path=command.path,
                    agent_name=agent_name,
                    reference_count=len(agent_refs),
                    reference_types=[ref.reference_type for ref in agent_refs],
                    usage_patterns=[ref.usage_pattern for ref in agent_refs],
                    dependency_strength=self._calculate_dependency_strength(
                        len(agent_refs),
                        [self._assess_reference_strength(ref) for ref in agent_refs],
                    ),
                    breaking_change_risk=self._assess_breaking_change_risk(
                        [ref.usage_pattern for ref in agent_refs]
                    ),
                    migration_complexity=self._assess_migration_complexity(
                        [ref.usage_pattern for ref in agent_refs], len(agent_refs)
                    ),
                )
                dependencies.append(dependency)

        return dependencies

    def analyze_deletion_impact(self, agent_name: str) -> Dict[str, Any]:
        """Analyze the impact of deleting an agent on commands."""
        usage_analysis = self.analyze_agent_usage(agent_name)

        impact_analysis = {
            "agent_name": agent_name,
            "safe_to_delete": usage_analysis.total_references == 0,
            "total_impact_score": self._calculate_impact_score(usage_analysis),
            "affected_commands": len(usage_analysis.referencing_commands),
            "total_references": usage_analysis.total_references,
            "high_risk_commands": [
                dep.command_name
                for dep in usage_analysis.affected_commands
                if dep.breaking_change_risk == "high"
            ],
            "migration_required_commands": [
                dep.command_name
                for dep in usage_analysis.affected_commands
                if dep.dependency_strength in ["moderate", "strong"]
            ],
            "recommendations": self._generate_deletion_recommendations(usage_analysis),
            "estimated_migration_time": self._estimate_migration_time(
                usage_analysis.affected_commands
            ),
            "risk_level": usage_analysis.deletion_impact,
            "analysis_timestamp": datetime.now().isoformat(),
        }

        return impact_analysis

    def generate_migration_plan(self, old_agent: str, new_agent: str) -> Dict[str, Any]:
        """Generate migration plan for replacing an agent."""
        # Analyze current usage
        old_usage = self.analyze_agent_usage(old_agent)

        # Check if new agent exists
        new_agent_obj = self.agent_discovery.find_agent_by_id(new_agent)
        if not new_agent_obj:
            return {
                "error": f"New agent '{new_agent}' not found",
                "migration_possible": False,
            }

        # Generate migration steps
        migration_steps = []

        for command_dep in old_usage.affected_commands:
            step = {
                "command": command_dep.command_name,
                "command_path": command_dep.command_path,
                "references_to_update": command_dep.reference_count,
                "migration_complexity": command_dep.migration_complexity,
                "estimated_time_minutes": self._estimate_command_migration_time(
                    command_dep
                ),
                "risk_level": command_dep.breaking_change_risk,
                "backup_recommended": command_dep.breaking_change_risk
                in ["medium", "high"],
                "testing_required": command_dep.dependency_strength
                in ["moderate", "strong"],
            }
            migration_steps.append(step)

        # Calculate total effort
        total_time = sum(step["estimated_time_minutes"] for step in migration_steps)
        high_risk_count = len(
            [step for step in migration_steps if step["risk_level"] == "high"]
        )

        migration_plan = {
            "old_agent": old_agent,
            "new_agent": new_agent,
            "migration_possible": True,
            "total_commands_affected": len(migration_steps),
            "total_references_to_update": sum(
                step["references_to_update"] for step in migration_steps
            ),
            "estimated_total_time_minutes": total_time,
            "high_risk_migrations": high_risk_count,
            "recommended_approach": self._recommend_migration_approach(
                old_usage, migration_steps
            ),
            "migration_steps": migration_steps,
            "pre_migration_checklist": self._generate_pre_migration_checklist(
                old_usage
            ),
            "post_migration_validation": self._generate_post_migration_validation(),
            "rollback_plan": self._generate_rollback_plan(migration_steps),
            "generated_at": datetime.now().isoformat(),
        }

        return migration_plan

    def _assess_reference_strength(self, ref) -> str:
        """Assess the strength of an agent reference."""
        if ref.reference_type == "task_call":
            return "strong"  # Direct invocation
        elif ref.reference_type == "import":
            return "strong"  # Import dependency
        elif ref.reference_type == "config":
            return "moderate"  # Configuration reference
        else:
            return "weak"  # Mention in text

    def _calculate_dependency_strength(
        self, ref_count: int, strengths: List[str]
    ) -> str:
        """Calculate overall dependency strength."""
        if not strengths:
            return "weak"

        strong_count = strengths.count("strong")
        moderate_count = strengths.count("moderate")

        if strong_count > 0 or ref_count >= 3:
            return "strong"
        elif moderate_count > 0 or ref_count >= 2:
            return "moderate"
        else:
            return "weak"

    def _assess_breaking_change_risk(self, usage_patterns: List[str]) -> str:
        """Assess risk of breaking changes."""
        if "invoke" in usage_patterns or "delegate" in usage_patterns:
            return "high"
        elif "configure" in usage_patterns:
            return "medium"
        else:
            return "low"

    def _assess_migration_complexity(
        self, usage_patterns: List[str], ref_count: int
    ) -> str:
        """Assess complexity of migrating away from this agent."""
        if ref_count >= 5:
            return "complex"
        elif "invoke" in usage_patterns and ref_count >= 2:
            return "moderate"
        else:
            return "simple"

    def _assess_deletion_impact(self, total_refs: int, command_count: int) -> str:
        """Assess overall impact of deleting this agent."""
        if total_refs == 0:
            return "low"
        elif total_refs <= 2 and command_count == 1:
            return "low"
        elif total_refs <= 5 and command_count <= 2:
            return "medium"
        elif total_refs <= 10 and command_count <= 5:
            return "high"
        else:
            return "critical"

    def _assess_overall_migration_effort(
        self, affected_commands: List[CommandAgentDependency]
    ) -> str:
        """Assess overall effort required to migrate away from agent."""
        if not affected_commands:
            return "minimal"

        complex_count = len(
            [dep for dep in affected_commands if dep.migration_complexity == "complex"]
        )
        high_risk_count = len(
            [dep for dep in affected_commands if dep.breaking_change_risk == "high"]
        )

        if complex_count > 0 or high_risk_count > 2:
            return "significant"
        elif len(affected_commands) > 5 or high_risk_count > 0:
            return "moderate"
        else:
            return "minimal"

    def _calculate_impact_score(self, usage_analysis: AgentUsageAnalysis) -> float:
        """Calculate numeric impact score (0-100)."""
        base_score = min(
            usage_analysis.total_references * 5, 30
        )  # Max 30 for references
        command_score = min(
            usage_analysis.command_count * 10, 40
        )  # Max 40 for command count

        # Add complexity penalty
        complexity_penalty = 0
        if usage_analysis.migration_effort == "significant":
            complexity_penalty = 30
        elif usage_analysis.migration_effort == "moderate":
            complexity_penalty = 15

        return min(base_score + command_score + complexity_penalty, 100)

    def _generate_deletion_recommendations(
        self, usage_analysis: AgentUsageAnalysis
    ) -> List[str]:
        """Generate recommendations for agent deletion."""
        recommendations = []

        if usage_analysis.total_references == 0:
            recommendations.append(
                "Agent appears safe to delete - no command references found"
            )
            return recommendations

        recommendations.append(
            f"Agent is referenced in {usage_analysis.command_count} commands"
        )

        if usage_analysis.deletion_impact in ["high", "critical"]:
            recommendations.append(
                "HIGH RISK: Thoroughly test affected commands before deletion"
            )
            recommendations.append("Create backups of all affected commands")

        if usage_analysis.migration_effort == "significant":
            recommendations.append("Consider deprecating instead of immediate deletion")
            recommendations.append("Plan migration over multiple phases")

        high_risk_commands = [
            dep.command_name
            for dep in usage_analysis.affected_commands
            if dep.breaking_change_risk == "high"
        ]
        if high_risk_commands:
            recommendations.append(
                f"Priority commands requiring updates: {', '.join(high_risk_commands)}"
            )

        return recommendations

    def _estimate_migration_time(
        self, affected_commands: List[CommandAgentDependency]
    ) -> int:
        """Estimate total migration time in minutes."""
        total_time = 0
        for dep in affected_commands:
            total_time += self._estimate_command_migration_time(dep)
        return total_time

    def _estimate_command_migration_time(
        self, command_dep: CommandAgentDependency
    ) -> int:
        """Estimate migration time for a single command in minutes."""
        base_time = 10  # Base time per command
        ref_time = command_dep.reference_count * 5  # Time per reference

        complexity_multiplier = 1
        if command_dep.migration_complexity == "moderate":
            complexity_multiplier = 1.5
        elif command_dep.migration_complexity == "complex":
            complexity_multiplier = 2

        risk_multiplier = 1
        if command_dep.breaking_change_risk == "medium":
            risk_multiplier = 1.3
        elif command_dep.breaking_change_risk == "high":
            risk_multiplier = 1.7

        return int((base_time + ref_time) * complexity_multiplier * risk_multiplier)

    def _recommend_migration_approach(
        self, usage_analysis: AgentUsageAnalysis, steps: List[Dict]
    ) -> str:
        """Recommend migration approach based on analysis."""
        if usage_analysis.migration_effort == "minimal":
            return "Direct replacement - update all references simultaneously"
        elif usage_analysis.migration_effort == "moderate":
            return "Phased approach - migrate low-risk commands first, then high-risk"
        else:
            return "Careful phased migration - deprecate old agent, migrate incrementally, extensive testing"

    def _generate_pre_migration_checklist(
        self, usage_analysis: AgentUsageAnalysis
    ) -> List[str]:
        """Generate pre-migration checklist."""
        return [
            "Backup all affected command files",
            "Verify new agent functionality matches requirements",
            "Create test plan for affected commands",
            "Notify stakeholders of migration timeline",
            "Prepare rollback procedures",
        ]

    def _generate_post_migration_validation(self) -> List[str]:
        """Generate post-migration validation steps."""
        return [
            "Test all migrated commands functionality",
            "Verify no broken references remain",
            "Check command execution performance",
            "Validate output quality matches expectations",
            "Monitor for any runtime errors",
        ]

    def _generate_rollback_plan(self, steps: List[Dict]) -> Dict[str, Any]:
        """Generate rollback plan for migration."""
        return {
            "rollback_triggers": [
                "Critical functionality broken",
                "Performance degradation > 50%",
                "Multiple command failures",
            ],
            "rollback_steps": [
                "Stop using new agent immediately",
                "Restore backed-up command files",
                "Verify old agent still available",
                "Test restored commands",
                "Document rollback reason",
            ],
            "estimated_rollback_time_minutes": max(5, len(steps) * 3),
        }
