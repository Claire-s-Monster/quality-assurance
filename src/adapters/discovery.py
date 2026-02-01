"""
Agent discovery adapter for finding and cataloging agents in the ecosystem.
Handles parsing agent frontmatter and directory scanning.
"""

import re
import toml
import yaml
import sys
import os
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import hashlib

# Add parent directory to path to access core modules
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from core.ports import AgentDiscoveryPort
from core.models import (
    Agent, DiscoveryResult, AgentClassification, AccessLevel, 
    AgentFrontmatter, SecurityViolation
)
from adapters.filesystem import FilesystemAdapter


class AgentDiscoveryAdapter(AgentDiscoveryPort):
    """Discovers and catalogs agents from filesystem."""
    
    def __init__(self, filesystem: FilesystemAdapter):
        self.filesystem = filesystem
        self.global_agent_dir = Path.home() / ".claude" / "agents"
        self.local_agent_dir = Path("./claude/agents")
        
        # Regex patterns for agent frontmatter
        self.frontmatter_patterns = {
            'yaml': re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL),
            'toml': re.compile(r'^\+\+\+\s*\n(.*?)\n\+\+\+\s*\n', re.DOTALL),
            'json': re.compile(r'^```json\s*\n(.*?)\n```\s*\n', re.DOTALL)
        }
    
    def discover_agents(self, scope: str = "both", categories: Optional[List[str]] = None) -> DiscoveryResult:
        """Discover agents from specified scope with optional category filtering."""
        start_time = datetime.now()
        discovered_agents = []
        errors = []
        
        # Determine directories to scan
        scan_dirs = []
        if scope in ["global", "both"]:
            if self.global_agent_dir.exists():
                scan_dirs.append(("global", self.global_agent_dir))
        
        if scope in ["local", "both"]:
            if self.local_agent_dir.exists():
                scan_dirs.append(("local", self.local_agent_dir))
        
        # Scan each directory
        for source, base_dir in scan_dirs:
            try:
                agents_in_dir = self._scan_directory(base_dir, source, categories)
                discovered_agents.extend(agents_in_dir)
            except Exception as e:
                errors.append(f"Error scanning {source} directory {base_dir}: {e}")
        
        # Calculate statistics
        stats = self._calculate_discovery_stats(discovered_agents)
        
        # Calculate execution time
        end_time = datetime.now()
        execution_time = (end_time - start_time).total_seconds()
        
        return DiscoveryResult(
            agents=discovered_agents,
            total_count=len(discovered_agents),
            scope=scope,
            categories=list(stats["by_category"].keys()),
            execution_time=execution_time,
            timestamp=end_time.isoformat()
        )
    
    def _scan_directory(self, base_dir: Path, source: str, categories: Optional[List[str]] = None) -> List[Agent]:
        """Scan a directory for agent files."""
        agents = []
        
        try:
            # Find all .md files recursively
            for agent_file in base_dir.rglob("*.md"):
                try:
                    agent = self._parse_agent_file(agent_file, source)
                    if agent:
                        # Apply category filter if specified
                        if categories is None or agent.classification.category in categories:
                            agents.append(agent)
                except Exception as e:
                    # Log error but continue discovery
                    continue
        
        except PermissionError:
            raise SecurityViolation(f"Permission denied scanning directory: {base_dir}")
        
        return agents
    
    def _parse_agent_file(self, file_path: Path, source: str) -> Optional[Agent]:
        """Parse an agent file and extract metadata."""
        try:
            content = self.filesystem.read_file(str(file_path))
            
            # Extract frontmatter
            frontmatter = self._extract_frontmatter(content)
            if not frontmatter:
                return None
            
            # Calculate file metadata
            file_metadata = self.filesystem.get_file_metadata(str(file_path))
            file_hash = self.filesystem.calculate_file_hash(str(file_path))
            
            # Parse classification from frontmatter or filename
            classification = self._parse_classification(frontmatter, file_path.name)
            
            # Determine access level
            access_level = self._determine_access_level(classification, frontmatter)
            
            # Create agent object
            agent = Agent(
                id=self._generate_agent_id(file_path, source),
                name=frontmatter.get("name", file_path.stem),
                path=str(file_path),
                classification=classification,
                access_level=access_level,
                description=frontmatter.get("description", ""),
                version=frontmatter.get("version", "1.0.0"),
                author=frontmatter.get("author", "unknown"),
                created_date=frontmatter.get("created_date", file_metadata.created_time.isoformat() if file_metadata else ""),
                last_modified=file_metadata.modified_time.isoformat() if file_metadata else "",
                dependencies=frontmatter.get("dependencies", []),
                tools=frontmatter.get("tools", []),
                examples=frontmatter.get("examples", []),
                tags=frontmatter.get("tags", []),
                status=frontmatter.get("status", "active"),
                validation_rules=frontmatter.get("validation_rules", {}),
                source=source,
                file_size=file_metadata.size if file_metadata else 0,
                file_hash=file_hash,
                frontmatter=AgentFrontmatter(**frontmatter) if isinstance(frontmatter, dict) else frontmatter
            )
            
            return agent
            
        except Exception as e:
            # Return None for unparseable files
            return None
    
    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract and parse frontmatter from agent content."""
        # Try YAML frontmatter first (most common)
        yaml_match = self.frontmatter_patterns['yaml'].match(content)
        if yaml_match:
            try:
                return yaml.safe_load(yaml_match.group(1))
            except yaml.YAMLError:
                pass
        
        # Try TOML frontmatter
        toml_match = self.frontmatter_patterns['toml'].match(content)
        if toml_match:
            try:
                return toml.loads(toml_match.group(1))
            except toml.TomlDecodeError:
                pass
        
        # Try JSON frontmatter
        json_match = self.frontmatter_patterns['json'].match(content)
        if json_match:
            try:
                import json
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        return None
    
    def _parse_classification(self, frontmatter: Dict[str, Any], filename: str) -> AgentClassification:
        """Parse agent classification from frontmatter and filename patterns."""
        # Extract from frontmatter if available
        classification_data = frontmatter.get("classification", {})
        
        # Determine category from frontmatter or filename patterns
        category = classification_data.get("category")
        if not category:
            category = self._infer_category_from_filename(filename)
        
        # Determine type
        agent_type = classification_data.get("type")
        if not agent_type:
            agent_type = self._infer_type_from_content(frontmatter)
        
        # Determine scope
        scope = classification_data.get("scope", "general")
        
        # Determine complexity
        complexity = classification_data.get("complexity")
        if not complexity:
            complexity = self._infer_complexity(frontmatter)
        
        return AgentClassification(
            category=category,
            type=agent_type,
            scope=scope,
            complexity=complexity,
            domain=classification_data.get("domain", "general"),
            pattern=classification_data.get("pattern", "single")
        )
    
    def _infer_category_from_filename(self, filename: str) -> str:
        """Infer agent category from filename patterns."""
        name_lower = filename.lower()
        
        if name_lower.startswith("meta-"):
            return "meta"
        elif name_lower.startswith("focused-"):
            return "focused"
        elif name_lower.startswith("micro-"):
            return "micro"
        elif name_lower.startswith("concise-"):
            return "concise"
        elif name_lower.startswith("ultra-fast-"):
            return "ultra-fast"
        elif name_lower.startswith("rapid-"):
            return "rapid"
        elif "validator" in name_lower or "checker" in name_lower:
            return "validator"
        elif "reporter" in name_lower or "analyzer" in name_lower:
            return "reporter"
        elif "orchestrator" in name_lower or "manager" in name_lower:
            return "orchestrator"
        else:
            return "general"
    
    def _infer_type_from_content(self, frontmatter: Dict[str, Any]) -> str:
        """Infer agent type from frontmatter content."""
        tools = frontmatter.get("tools", [])
        description = frontmatter.get("description", "").lower()
        
        if "validate" in description or "check" in description:
            return "validator"
        elif "report" in description or "analyze" in description:
            return "reporter"
        elif "orchestrate" in description or "manage" in description:
            return "orchestrator"
        elif "create" in description or "generate" in description:
            return "creator"
        elif len(tools) > 5:
            return "comprehensive"
        else:
            return "specialized"
    
    def _infer_complexity(self, frontmatter: Dict[str, Any]) -> str:
        """Infer complexity from agent metadata."""
        tools = frontmatter.get("tools", [])
        dependencies = frontmatter.get("dependencies", [])
        
        tool_count = len(tools)
        dep_count = len(dependencies)
        
        if tool_count >= 10 or dep_count >= 5:
            return "high"
        elif tool_count >= 5 or dep_count >= 2:
            return "medium"
        else:
            return "low"
    
    def _determine_access_level(self, classification: AgentClassification, frontmatter: Dict[str, Any]) -> AccessLevel:
        """Determine access level based on classification and metadata."""
        # Check explicit access level in frontmatter
        explicit_level = frontmatter.get("access_level")
        if explicit_level and explicit_level in AccessLevel.__members__.values():
            return AccessLevel(explicit_level)
        
        # Infer from category
        if classification.category == "meta":
            return AccessLevel.META
        elif classification.category in ["focused", "concise"]:
            return AccessLevel.VALIDATOR
        elif classification.category in ["micro", "ultra-fast", "rapid"]:
            return AccessLevel.INFRASTRUCTURE
        else:
            return AccessLevel.DOMAIN
    
    def _generate_agent_id(self, file_path: Path, source: str) -> str:
        """Generate unique agent ID from path and source."""
        # Use relative path from agent root + source
        relative_path = file_path.stem
        id_string = f"{source}:{relative_path}"
        
        # Create short hash for uniqueness
        hash_digest = hashlib.md5(id_string.encode()).hexdigest()[:8]
        
        return f"{relative_path}_{hash_digest}"
    
    def _calculate_discovery_stats(self, agents: List[Agent]) -> Dict[str, Dict[str, int]]:
        """Calculate discovery statistics."""
        stats = {
            "by_classification": {},
            "by_access_level": {},
            "by_category": {}
        }
        
        for agent in agents:
            # By classification category
            category = agent.classification.category
            stats["by_category"][category] = stats["by_category"].get(category, 0) + 1
            
            # By access level
            level = agent.access_level.value
            stats["by_access_level"][level] = stats["by_access_level"].get(level, 0) + 1
            
            # By classification type
            agent_type = agent.classification.type
            stats["by_classification"][agent_type] = stats["by_classification"].get(agent_type, 0) + 1
        
        return stats
    
    def find_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Find a specific agent by its ID."""
        # Extract the name part from ID (before hash)
        name_part = agent_id.split('_')[0] if '_' in agent_id else agent_id
        
        # Search in both global and local directories
        for scope in ["global", "local"]:
            result = self.discover_agents(scope=scope)
            for agent in result.agents:
                if agent.id == agent_id or agent.name == name_part:
                    return agent
        
        return None
    
    def search_agents(self, query: str, scope: str = "both") -> List[Agent]:
        """Search agents by name, description, or tags."""
        result = self.discover_agents(scope=scope)
        query_lower = query.lower()
        
        matching_agents = []
        for agent in result.agents:
            # Check name
            if query_lower in agent.name.lower():
                matching_agents.append(agent)
                continue
            
            # Check description
            if query_lower in agent.description.lower():
                matching_agents.append(agent)
                continue
            
            # Check tags
            if any(query_lower in tag.lower() for tag in agent.tags):
                matching_agents.append(agent)
                continue
        
        return matching_agents
    
    # Abstract method implementations required by AgentDiscoveryPort
    
    def scan_directory(self, directory: str, recursive: bool = True) -> List[Agent]:
        """Scan a directory for agent files (public interface)."""
        base_dir = Path(directory)
        if not base_dir.exists():
            return []
        
        # Determine source from directory path
        source = "global" if ".claude" in str(base_dir) else "local"
        
        return self._scan_directory(base_dir, source)
    
    def parse_agent_file(self, file_path: str) -> Optional[Agent]:
        """Parse an agent markdown file and extract metadata (public interface)."""
        # Determine source from file path
        source = "global" if ".claude" in file_path else "local"
        
        return self._parse_agent_file(Path(file_path), source)
    
    def get_global_agents_path(self) -> str:
        """Get path to global agents directory."""
        return str(self.global_agent_dir)
    
    def get_local_agents_path(self) -> str:
        """Get path to local agents directory."""
        return str(self.local_agent_dir)