"""
Agent lifecycle adapter for managing agent creation, updates, and deprecation.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from core.ports import AgentLifecyclePort
from core.models import AgentOperation, AgentTemplate
from adapters.filesystem import FilesystemAdapter


class AgentLifecycleAdapter(AgentLifecyclePort):
    """Manages agent lifecycle operations."""

    def __init__(self, filesystem: FilesystemAdapter, templates=None, validation=None):
        self.filesystem = filesystem
        self.templates = templates
        self.validation = validation

    def create_agent(
        self,
        name: str,
        template: AgentTemplate,
        configuration: Dict[str, Any],
        target_directory: Optional[str] = None,
    ) -> AgentOperation:
        """Create a new agent from template."""
        try:
            # Determine target path
            if target_directory:
                agent_path = Path(target_directory) / f"{name}.md"
            else:
                # Default to local agents directory
                local_agents = Path("./claude/agents")
                local_agents.mkdir(parents=True, exist_ok=True)
                agent_path = local_agents / f"{name}.md"

            # Check if agent already exists
            if agent_path.exists():
                return AgentOperation(
                    success=False,
                    message=f"Agent already exists: {agent_path}",
                    agent_path=str(agent_path),
                    operation_type="create",
                )

            # Create agent content from template
            agent_content = self._render_template(template, configuration)

            # Write agent file
            self.filesystem.write_file(str(agent_path), agent_content)

            return AgentOperation(
                success=True,
                message=f"Agent created successfully: {name}",
                agent_path=str(agent_path),
                operation_type="create",
            )

        except Exception as e:
            return AgentOperation(
                success=False,
                message=f"Failed to create agent: {e}",
                agent_path=target_directory,
                operation_type="create",
            )

    def update_agent(
        self, agent_path: str, updates: Dict[str, Any], validate_before: bool = True
    ) -> AgentOperation:
        """Update an existing agent."""
        try:
            # Check if agent exists
            if not Path(agent_path).exists():
                return AgentOperation(
                    success=False,
                    message=f"Agent not found: {agent_path}",
                    agent_path=agent_path,
                    operation_type="update",
                )

            # Validate before update if requested
            if validate_before and self.validation:
                validation_result = self.validation.validate_agent(agent_path)
                if not validation_result.is_valid:
                    return AgentOperation(
                        success=False,
                        message=f"Agent validation failed before update",
                        agent_path=agent_path,
                        operation_type="update",
                    )

            # Create backup
            backup_path = f"{agent_path}.backup.{int(datetime.now().timestamp())}"
            shutil.copy2(agent_path, backup_path)

            # Read current content
            current_content = self.filesystem.read_file(agent_path)

            # Apply updates (basic frontmatter update)
            updated_content = self._apply_updates(current_content, updates)

            # Write updated content
            self.filesystem.write_file(agent_path, updated_content)

            return AgentOperation(
                success=True,
                message=f"Agent updated successfully",
                agent_path=agent_path,
                operation_type="update",
            )

        except Exception as e:
            return AgentOperation(
                success=False,
                message=f"Failed to update agent: {e}",
                agent_path=agent_path,
                operation_type="update",
            )

    def deprecate_agent(
        self, agent_path: str, reason: str, migration_path: Optional[str] = None
    ) -> AgentOperation:
        """Deprecate an agent."""
        try:
            if not Path(agent_path).exists():
                return AgentOperation(
                    success=False,
                    message=f"Agent not found: {agent_path}",
                    agent_path=agent_path,
                    operation_type="deprecate",
                )

            # Update agent frontmatter to mark as deprecated
            content = self.filesystem.read_file(agent_path)
            deprecated_content = self._mark_as_deprecated(
                content, reason, migration_path
            )
            self.filesystem.write_file(agent_path, deprecated_content)

            return AgentOperation(
                success=True,
                message=f"Agent deprecated successfully",
                agent_path=agent_path,
                operation_type="deprecate",
            )

        except Exception as e:
            return AgentOperation(
                success=False,
                message=f"Failed to deprecate agent: {e}",
                agent_path=agent_path,
                operation_type="deprecate",
            )

    def archive_agent(
        self, agent_path: str, backup_location: Optional[str] = None
    ) -> AgentOperation:
        """Archive an agent."""
        try:
            if not Path(agent_path).exists():
                return AgentOperation(
                    success=False,
                    message=f"Agent not found: {agent_path}",
                    agent_path=agent_path,
                    operation_type="archive",
                )

            # Determine archive location
            if backup_location:
                archive_dir = Path(backup_location)
            else:
                archive_dir = Path("./claude/archive")

            archive_dir.mkdir(parents=True, exist_ok=True)

            # Create timestamped archive filename
            agent_name = Path(agent_path).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = archive_dir / f"{agent_name}_{timestamp}.md"

            # Copy to archive
            shutil.copy2(agent_path, archive_path)

            return AgentOperation(
                success=True,
                message=f"Agent archived to: {archive_path}",
                agent_path=agent_path,
                operation_type="archive",
            )

        except Exception as e:
            return AgentOperation(
                success=False,
                message=f"Failed to archive agent: {e}",
                agent_path=agent_path,
                operation_type="archive",
            )

    def backup_agent(
        self, agent_path: str, backup_location: Optional[str] = None
    ) -> AgentOperation:
        """Backup an agent."""
        try:
            if not Path(agent_path).exists():
                return AgentOperation(
                    success=False,
                    message=f"Agent not found: {agent_path}",
                    agent_path=agent_path,
                    operation_type="backup",
                )

            # Determine backup location
            if backup_location:
                backup_path = backup_location
            else:
                backup_path = f"{agent_path}.backup.{int(datetime.now().timestamp())}"

            # Create backup
            shutil.copy2(agent_path, backup_path)

            return AgentOperation(
                success=True,
                message=f"Agent backed up to: {backup_path}",
                agent_path=agent_path,
                operation_type="backup",
            )

        except Exception as e:
            return AgentOperation(
                success=False,
                message=f"Failed to backup agent: {e}",
                agent_path=agent_path,
                operation_type="backup",
            )

    def _render_template(
        self, template: AgentTemplate, configuration: Dict[str, Any]
    ) -> str:
        """Render agent template with configuration."""
        # Basic template rendering
        content = f"""---
name: {configuration.get("name", "New Agent")}
description: {configuration.get("description", "Agent description")}
version: {configuration.get("version", "1.0.0")}
author: {configuration.get("author", "unknown")}
created_date: {datetime.now().isoformat()}
status: active
tags: {configuration.get("tags", [])}
tools: {configuration.get("tools", [])}
---

# {configuration.get("name", "New Agent")}

{configuration.get("description", "Agent description")}

## Usage

Add usage instructions here.

## Examples

Add examples here.
"""
        return content

    def _apply_updates(self, content: str, updates: Dict[str, Any]) -> str:
        """Apply updates to agent content."""
        # Basic frontmatter updates
        lines = content.split("\n")
        if lines[0] == "---":
            # Find end of frontmatter
            end_idx = 1
            while end_idx < len(lines) and lines[end_idx] != "---":
                end_idx += 1

            # Update frontmatter fields
            for i in range(1, end_idx):
                line = lines[i]
                for key, value in updates.items():
                    if line.startswith(f"{key}:"):
                        lines[i] = f"{key}: {value}"

        return "\n".join(lines)

    def _mark_as_deprecated(
        self, content: str, reason: str, migration_path: Optional[str]
    ) -> str:
        """Mark agent as deprecated in frontmatter."""
        lines = content.split("\n")
        if lines[0] == "---":
            # Find end of frontmatter
            end_idx = 1
            while end_idx < len(lines) and lines[end_idx] != "---":
                end_idx += 1

            # Add deprecation info
            deprecation_lines = [
                f"status: deprecated",
                f"deprecated_date: {datetime.now().isoformat()}",
                f"deprecation_reason: {reason}",
            ]

            if migration_path:
                deprecation_lines.append(f"migration_path: {migration_path}")

            # Insert before closing ---
            for line in reversed(deprecation_lines):
                lines.insert(end_idx, line)

        return "\n".join(lines)
