"""
Command discovery adapter for finding and analyzing Claude Code commands.
Handles scanning command directories and parsing agent references.
"""

import re
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import time

from core.ports import CommandDiscoveryPort
from core.models import (
    Command,
    CommandDiscoveryResult,
    CommandType,
    CommandStatus,
    AgentReference,
    SecurityViolation,
)
from adapters.filesystem import FilesystemAdapter


class CommandDiscoveryAdapter(CommandDiscoveryPort):
    """Discovers and catalogs Claude Code commands from filesystem."""

    def __init__(self, filesystem: FilesystemAdapter):
        self.filesystem = filesystem
        self.global_commands_dir = Path.home() / ".claude" / "commands"
        self.local_commands_dir = Path("./claude/commands")

        # Patterns for detecting agent references in commands
        self.agent_reference_patterns = {
            # Task delegation patterns
            "task_call": [
                r'Task\(\s*subagent_type\s*=\s*["\']([^"\']+)["\']',  # Task(subagent_type="agent-name")
                r"@(\w+[-_]\w+)",  # @agent-name shorthand
                r'task\s*\(\s*["\']([^"\']+)["\']',  # task("agent-name")
            ],
            # Direct mentions in text
            "direct_mention": [
                r"use\s+the\s+([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)\s+agent",  # "use the agent-name agent"
                r"invoke\s+([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)",  # "invoke agent-name"
                r"run\s+([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)",  # "run agent-name"
                r"launch\s+([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)",  # "launch agent-name"
            ],
            # Import-style references
            "import": [
                r"from\s+agents\s+import\s+([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)",  # from agents import agent-name
                r"import\s+([a-z][a-z0-9-]*(?:-[a-z0-9]+)*)",  # import agent-name
            ],
            # Configuration references
            "config": [
                r'agent["\']?\s*:\s*["\']([^"\']+)["\']',  # agent: "agent-name" in YAML/JSON
                r'subagent_type["\']?\s*:\s*["\']([^"\']+)["\']',  # subagent_type: "agent-name"
            ],
        }

        # Compiled patterns for efficiency
        self.compiled_patterns = {}
        for ref_type, patterns in self.agent_reference_patterns.items():
            self.compiled_patterns[ref_type] = [
                re.compile(pattern, re.IGNORECASE | re.MULTILINE)
                for pattern in patterns
            ]

    def discover_commands(
        self,
        scope: str = "both",
        command_types: Optional[List[str]] = None,
        include_agent_analysis: bool = True,
    ) -> CommandDiscoveryResult:
        """Discover commands from specified scope with optional filtering."""
        start_time = time.time()
        discovered_commands = []
        errors = []
        scan_paths = []

        # Determine directories to scan
        scan_dirs = []
        if scope in ["global", "both"]:
            if self.global_commands_dir.exists():
                scan_dirs.append(("global", self.global_commands_dir))
                scan_paths.append(str(self.global_commands_dir))

        if scope in ["local", "both"]:
            if self.local_commands_dir.exists():
                scan_dirs.append(("local", self.local_commands_dir))
                scan_paths.append(str(self.local_commands_dir))

        # Scan each directory
        for source, base_dir in scan_dirs:
            try:
                commands_in_dir = self._scan_directory(
                    base_dir, source, command_types, include_agent_analysis
                )
                discovered_commands.extend(commands_in_dir)
            except Exception as e:
                errors.append(f"Error scanning {source} directory {base_dir}: {e}")

        # Calculate statistics
        stats = self._calculate_discovery_stats(discovered_commands)
        execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds

        return CommandDiscoveryResult(
            commands=discovered_commands,
            total_count=len(discovered_commands),
            by_type=stats["by_type"],
            by_status=stats["by_status"],
            by_source=stats["by_source"],
            total_agent_references=stats["total_agent_references"],
            unique_agents_referenced=stats["unique_agents_referenced"],
            most_referenced_agents=stats["most_referenced_agents"],
            scan_paths=scan_paths,
            errors=errors,
            scan_time=datetime.now().isoformat(),
            execution_time_ms=execution_time,
        )

    def _scan_directory(
        self,
        base_dir: Path,
        source: str,
        command_types: Optional[List[str]] = None,
        include_agent_analysis: bool = True,
    ) -> List[Command]:
        """Scan a directory for command files."""
        commands = []

        try:
            # Find command files recursively
            command_extensions = {".md", ".txt", ".sh", ".py", ".js", ".yml", ".yaml"}

            for command_file in base_dir.rglob("*"):
                if (
                    command_file.is_file()
                    and command_file.suffix.lower() in command_extensions
                ):
                    try:
                        command = self._parse_command_file(
                            command_file, source, base_dir, include_agent_analysis
                        )
                        if command:
                            # Apply command type filter if specified
                            if (
                                command_types is None
                                or command.command_type.value in command_types
                            ):
                                commands.append(command)
                    except Exception as e:
                        # Log error but continue discovery
                        continue

        except PermissionError:
            raise SecurityViolation(f"Permission denied scanning directory: {base_dir}")

        return commands

    def _parse_command_file(
        self,
        file_path: Path,
        source: str,
        base_dir: Path,
        include_agent_analysis: bool = True,
    ) -> Optional[Command]:
        """Parse a command file and extract metadata."""
        try:
            content = self.filesystem.read_file(str(file_path))

            # Calculate file metadata
            file_metadata = self.filesystem.get_file_metadata(str(file_path))
            file_hash = self.filesystem.calculate_file_hash(str(file_path))

            # Determine command type
            command_type = self._determine_command_type(file_path, content)

            # Generate relative path
            relative_path = str(file_path.relative_to(base_dir))

            # Analyze agent references if requested
            agent_references = []
            agent_count = 0
            if include_agent_analysis:
                agent_references = self.analyze_command_agent_dependencies(
                    str(file_path)
                )
                agent_count = len(set(ref.agent_name for ref in agent_references))

            # Extract metadata from content
            metadata = self._extract_command_metadata(content)

            # Create command object
            command = Command(
                id=self._generate_command_id(file_path, source),
                name=file_path.stem,
                path=str(file_path),
                command_type=command_type,
                status=CommandStatus.ACTIVE,  # Default to active, could be determined from content
                content_hash=file_hash,
                content_size=file_metadata.size if file_metadata else 0,
                last_modified=file_metadata.modified_time.isoformat()
                if file_metadata
                else "",
                agent_references=agent_references,
                agent_count=agent_count,
                description=metadata.get("description"),
                author=metadata.get("author"),
                version=metadata.get("version"),
                tags=metadata.get("tags", []),
                source=source,
                relative_path=relative_path,
            )

            return command

        except Exception as e:
            # Return None for unparseable files
            return None

    def _determine_command_type(self, file_path: Path, content: str) -> CommandType:
        """Determine the type of command based on file and content analysis."""
        filename = file_path.name.lower()
        content_lower = content.lower()

        # Check for CLAUDE.md or system prompts
        if filename == "claude.md" or "claude.md" in filename:
            return CommandType.SYSTEM_PROMPT

        # Check for hook scripts
        if (
            "hook" in filename
            or file_path.suffix in [".sh", ".py"]
            and ("hook" in content_lower or "pre-commit" in content_lower)
        ):
            return CommandType.HOOK_SCRIPT

        # Check for slash commands (content that looks like Claude Code commands)
        if (
            content.startswith("/")
            or "slash_command" in content_lower
            or "command:" in content_lower
        ):
            return CommandType.SLASH_COMMAND

        # Default to custom command
        return CommandType.CUSTOM_COMMAND

    def _extract_command_metadata(self, content: str) -> Dict[str, Any]:
        """Extract metadata from command content."""
        metadata = {}

        # Look for YAML frontmatter
        if content.startswith("---"):
            try:
                import yaml

                end_marker = content.find("\n---\n", 3)
                if end_marker != -1:
                    frontmatter_text = content[3:end_marker]
                    frontmatter = yaml.safe_load(frontmatter_text)
                    if isinstance(frontmatter, dict):
                        metadata.update(frontmatter)
            except:
                pass

        # Look for common metadata patterns in content
        patterns = {
            "description": r"(?:description|desc):\s*([^\n]+)",
            "author": r"(?:author|by):\s*([^\n]+)",
            "version": r"version:\s*([^\n]+)",
            "tags": r"tags:\s*\[([^\]]+)\]",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if key == "tags":
                    # Parse tags list
                    metadata[key] = [
                        tag.strip().strip("\"'") for tag in value.split(",")
                    ]
                else:
                    metadata[key] = value

        return metadata

    def analyze_command_agent_dependencies(
        self, command_path: str
    ) -> List[AgentReference]:
        """Analyze agent dependencies within a command file."""
        try:
            content = self.filesystem.read_file(command_path)
            agent_references = []

            # Search for each type of agent reference
            for ref_type, compiled_patterns in self.compiled_patterns.items():
                for pattern in compiled_patterns:
                    for match in pattern.finditer(content):
                        agent_name = match.group(1).strip()
                        line_number = content[: match.start()].count("\n") + 1

                        # Extract surrounding context (50 chars before and after)
                        start_context = max(0, match.start() - 50)
                        end_context = min(len(content), match.end() + 50)
                        context = content[start_context:end_context].replace("\n", " ")

                        # Determine usage pattern based on context
                        usage_pattern = self._determine_usage_pattern(context, ref_type)

                        agent_ref = AgentReference(
                            agent_name=agent_name,
                            reference_type=ref_type,
                            line_number=line_number,
                            context=context,
                            usage_pattern=usage_pattern,
                        )

                        agent_references.append(agent_ref)

            # Remove duplicates while preserving order
            seen = set()
            unique_references = []
            for ref in agent_references:
                ref_key = (ref.agent_name, ref.reference_type, ref.line_number)
                if ref_key not in seen:
                    seen.add(ref_key)
                    unique_references.append(ref)

            return unique_references

        except Exception as e:
            return []

    def _determine_usage_pattern(self, context: str, reference_type: str) -> str:
        """Determine how the agent is being used based on context."""
        context_lower = context.lower()

        if reference_type == "task_call":
            if "task(" in context_lower or "invoke" in context_lower:
                return "invoke"
            elif "delegate" in context_lower:
                return "delegate"
        elif reference_type == "direct_mention":
            if "use" in context_lower or "run" in context_lower:
                return "invoke"
            elif "mention" in context_lower or "refer" in context_lower:
                return "mention"
        elif reference_type == "import":
            return "import"
        elif reference_type == "config":
            return "configure"

        return "mention"  # Default

    def search_commands(
        self, query: str, scope: str = "both", search_content: bool = False
    ) -> List[Command]:
        """Search commands by name, description, or content."""
        # First discover all commands
        discovery_result = self.discover_commands(scope=scope)
        query_lower = query.lower()

        matching_commands = []
        for command in discovery_result.commands:
            # Check name
            if query_lower in command.name.lower():
                matching_commands.append(command)
                continue

            # Check description
            if command.description and query_lower in command.description.lower():
                matching_commands.append(command)
                continue

            # Check tags
            if any(query_lower in tag.lower() for tag in command.tags):
                matching_commands.append(command)
                continue

            # Check relative path
            if query_lower in command.relative_path.lower():
                matching_commands.append(command)
                continue

            # Search content if requested (expensive operation)
            if search_content:
                try:
                    content = self.filesystem.read_file(command.path)
                    if query_lower in content.lower():
                        matching_commands.append(command)
                        continue
                except:
                    pass

        return matching_commands

    def get_command_by_id(self, command_id: str) -> Optional[Command]:
        """Get specific command by ID."""
        # Extract the name part from ID (before hash)
        name_part = command_id.split("_")[0] if "_" in command_id else command_id

        # Search in both global and local directories
        for scope in ["global", "local"]:
            result = self.discover_commands(scope=scope)
            for command in result.commands:
                if command.id == command_id or command.name == name_part:
                    return command

        return None

    def _generate_command_id(self, file_path: Path, source: str) -> str:
        """Generate unique command ID from path and source."""
        # Use relative path from commands root + source
        relative_path = file_path.stem
        id_string = f"{source}:{relative_path}"

        # Create short hash for uniqueness
        hash_digest = hashlib.md5(id_string.encode()).hexdigest()[:8]

        return f"{relative_path}_{hash_digest}"

    def _calculate_discovery_stats(self, commands: List[Command]) -> Dict[str, Any]:
        """Calculate discovery statistics."""
        stats = {
            "by_type": {},
            "by_status": {},
            "by_source": {},
            "total_agent_references": 0,
            "unique_agents_referenced": 0,
            "most_referenced_agents": {},
        }

        agent_reference_counts = {}
        unique_agents = set()

        for command in commands:
            # By command type
            cmd_type = command.command_type.value
            stats["by_type"][cmd_type] = stats["by_type"].get(cmd_type, 0) + 1

            # By status
            status = command.status.value
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # By source
            source = command.source
            stats["by_source"][source] = stats["by_source"].get(source, 0) + 1

            # Agent reference statistics
            stats["total_agent_references"] += len(command.agent_references)
            for ref in command.agent_references:
                unique_agents.add(ref.agent_name)
                agent_reference_counts[ref.agent_name] = (
                    agent_reference_counts.get(ref.agent_name, 0) + 1
                )

        stats["unique_agents_referenced"] = len(unique_agents)

        # Get top 10 most referenced agents
        sorted_agents = sorted(
            agent_reference_counts.items(), key=lambda x: x[1], reverse=True
        )
        stats["most_referenced_agents"] = dict(sorted_agents[:10])

        return stats
