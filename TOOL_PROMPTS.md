# Agent Ecosystem MCP Server - Tool Usage Prompts for Claude Code

This document provides clear usage guidance for Claude Code when using the Agent Ecosystem MCP Server functions. These prompts help Claude understand the purpose, parameters, and best practices for each tool.

## Core Principles for Tool Usage

### 🚨 **CRITICAL SAFETY RULE**
**ALWAYS run `analyze_agent_deletion_impact` before any agent deletion operations**
- This is MANDATORY, not optional
- Provides essential information about which commands will break
- Prevents ecosystem damage from unexpected dependencies

### 📋 **Systematic Approach**
1. **Discover first** - Use discovery functions to understand the ecosystem
2. **Analyze dependencies** - Check command-agent relationships 
3. **Validate impact** - Assess deletion/modification safety
4. **Execute carefully** - Make changes with full knowledge of consequences

## Agent Discovery Functions

### `discover_agents`
**Purpose**: Find all agents in the ecosystem with optional filtering
**When to use**: Starting point for any agent ecosystem operation
**Key parameters**:
- `scope: "both"` (default) - searches global (~/.claude/agents) and local (./claude/agents)
- `categories: ["meta", "focused", "micro"]` - filter by agent categories
- `access_level: "validator"` - filter by security access level

**Claude Code Usage Patterns**:
```
"Find all validator agents": discover_agents(categories=["focused", "concise"], access_level="validator")
"Get complete agent inventory": discover_agents(scope="both")
"Local agents only": discover_agents(scope="local")
```

### `search_agents`
**Purpose**: Text search across agent names, descriptions, and tags
**When to use**: Looking for specific functionality or agent by partial name
**Key parameters**:
- `query: "validation"` - search term
- `scope: "both"` - search scope

**Claude Code Usage Patterns**:
```
"Find agents that validate code": search_agents("validation")
"Agents for Python quality": search_agents("python quality")
"Reporter agents": search_agents("reporter")
```

### `get_agent_by_id`
**Purpose**: Get detailed information about a specific agent
**When to use**: Need complete metadata for a known agent
**Key parameters**:
- `agent_id: "focused-ciframework-validator_abc123"` - unique agent identifier

## Agent Validation Functions

### `validate_agent`
**Purpose**: Comprehensive validation of agent file integrity
**When to use**: Before using an agent, after modifications, or for quality assurance
**Key parameters**:
- `agent_path: "/home/user/.claude/agents/my-agent.md"` - absolute path to agent file
- `validation_level: "comprehensive"` - depth of validation ("basic", "security", "comprehensive")

**Claude Code Usage Patterns**:
```
"Quick validation check": validate_agent(path, "basic")
"Security audit": validate_agent(path, "security") 
"Full quality assessment": validate_agent(path, "comprehensive")
```

### `validate_agents_bulk`
**Purpose**: Validate multiple agents efficiently
**When to use**: Ecosystem-wide quality checks or CI/CD validation
**Key parameters**:
- `agent_paths: ["/path/1.md", "/path/2.md"]` - list of agent paths
- `validation_level: "basic"` - validation depth

## **🚨 CRITICAL: Command-Agent Dependency Functions**

### `analyze_agent_deletion_impact` ⚠️ **MANDATORY BEFORE DELETION**
**Purpose**: Analyze what breaks if an agent is deleted
**When to use**: **REQUIRED** before any agent deletion operation
**Key parameters**:
- `agent_name: "focused-ciframework-validator"` - agent to analyze

**Critical Return Information**:
- `safe_to_delete: true/false` - Can this agent be safely removed?
- `affected_commands: []` - List of commands that will break
- `total_references: N` - Number of places agent is used
- `recommendations: []` - Specific safety recommendations

**Claude Code MUST use this before deletion**:
```
Before: delete_agent("my-agent")
ALWAYS: analyze_agent_deletion_impact("my-agent") FIRST
Then: Only proceed with deletion if safe_to_delete: true
```

### `discover_commands`
**Purpose**: Find all Claude Code commands that might reference agents
**When to use**: Understanding the command ecosystem, dependency analysis
**Key parameters**:
- `scope: "both"` - search global (~/.claude/commands) and local (./claude/commands)
- `command_types: ["slash", "system_prompt", "hook"]` - filter by command type
- `include_agent_analysis: true` - analyze agent references (recommended)

**Claude Code Usage Patterns**:
```
"Find all commands": discover_commands(scope="both")
"System prompts only": discover_commands(command_types=["system_prompt"])
"Commands with agent analysis": discover_commands(include_agent_analysis=true)
```

### `find_commands_using_agent`
**Purpose**: Find specific commands that reference an agent
**When to use**: Before modifying/deleting an agent, dependency tracking
**Key parameters**:
- `agent_name: "my-validator-agent"` - agent to find references for
- `scope: "both"` - search scope

**Critical for Safe Operations**:
```
Before modifying agent "X": find_commands_using_agent("X")
Result shows which commands need updates if agent changes
```

### `analyze_agent_usage_in_commands`
**Purpose**: Comprehensive analysis of how an agent is used
**When to use**: Detailed impact assessment, migration planning
**Key parameters**:
- `agent_name: "agent-to-analyze"` - target agent

**Return Information**:
- `total_references: N` - How many times agent is referenced
- `command_count: N` - How many different commands use it
- `deletion_impact: "low/medium/high/critical"` - Impact level
- `migration_effort: "minimal/moderate/significant"` - Effort to replace

### `generate_agent_migration_plan`
**Purpose**: Create step-by-step plan for replacing one agent with another
**When to use**: Systematic agent replacement, deprecation management
**Key parameters**:
- `old_agent: "deprecated-agent"` - agent to replace
- `new_agent: "replacement-agent"` - replacement agent

**Migration Workflow**:
1. Check migration is possible
2. Get step-by-step instructions  
3. Follow backup recommendations
4. Execute in recommended order
5. Validate success

## Ecosystem Health Functions

### `generate_ecosystem_health_report`
**Purpose**: Comprehensive health assessment of agents and commands
**When to use**: Regular health checks, troubleshooting, audit requirements
**Key parameters**:
- `include_commands: true` - include command analysis
- `include_agents: true` - include agent analysis  
- `deep_analysis: false` - thorough analysis (slower but comprehensive)

### `identify_broken_dependencies`
**Purpose**: Find broken references between commands and agents
**When to use**: Troubleshooting, after agent changes, regular maintenance
**No parameters needed**

**Claude Code Usage Pattern**:
```
"Check ecosystem health": identify_broken_dependencies()
Fix any issues found before making changes
```

## Agent Lifecycle Functions

### `create_agent`
**Purpose**: Create new agent from template with validation
**When to use**: Adding new capabilities to the ecosystem
**Key parameters**:
- `name: "my-new-agent"` - unique agent name
- `description: "Agent purpose"` - clear description
- `access_level: "validator"` - security access level
- `tools: ["Read", "Write", "Edit"]` - tools agent can use
- `template: "validator"` - template to use

### `update_agent`
**Purpose**: Modify existing agent metadata safely
**When to use**: Updating agent configuration, adding capabilities
**Key parameters**:
- `agent_id: "agent-id"` - target agent
- Optional updates: `name`, `description`, `tools`, `dependencies`, `tags`, `status`

### `delete_agent` ⚠️ **USE WITH EXTREME CAUTION**
**Purpose**: Remove agent from ecosystem
**When to use**: Only after confirming safety via `analyze_agent_deletion_impact`
**Key parameters**:
- `agent_id: "agent-to-delete"` - target agent
- `force: false` - skip dependency checks (DANGEROUS)

**MANDATORY Safety Protocol**:
```
1. ALWAYS run analyze_agent_deletion_impact(agent_name) FIRST
2. Check safe_to_delete status
3. Review affected_commands list
4. Only proceed if safe_to_delete: true
5. Never use force: true unless absolutely necessary
```

### `deprecate_agent`
**Purpose**: Mark agent as deprecated with migration guidance
**When to use**: Phasing out agents gradually instead of immediate deletion
**Key parameters**:
- `agent_id: "agent-to-deprecate"` - target agent
- `reason: "Migration to new-agent recommended"` - deprecation reason

## Advanced Analysis Functions

### `classify_agent_access_level`
**Purpose**: Determine appropriate security access level for agent
**When to use**: Security audits, access level validation
**Key parameters**:
- `agent_path: "/path/to/agent.md"` - agent to classify

### `get_agent_dependencies`
**Purpose**: Analyze dependency relationships between agents
**When to use**: Understanding agent interconnections
**Key parameters**:
- `agent_id: "target-agent"` - specific agent (optional, analyzes all if not provided)

## Cache and Performance Functions

### `clear_cache`
**Purpose**: Clear server cache for fresh data
**When to use**: After making changes, troubleshooting, performance issues
**Key parameters**:
- `pattern: "discovery:*"` - optional pattern to clear specific cache entries

### `get_cache_statistics`
**Purpose**: Monitor cache performance and health
**When to use**: Performance optimization, debugging
**No parameters needed**

## Health and Monitoring Functions

### `health_check`
**Purpose**: Verify all server components are functioning
**When to use**: Troubleshooting, system monitoring, startup validation
**No parameters needed**

### `get_server_info`
**Purpose**: Get server capabilities and configuration
**When to use**: Understanding available features, version checking
**No parameters needed**

## **Best Practices for Claude Code**

### 🔍 **Discovery Pattern**
```
1. discover_agents() or discover_commands() - Get the full picture
2. search_agents("criteria") - Find specific matches
3. get_agent_by_id() - Get detailed information
```

### ⚠️ **Safety Pattern for Agent Operations**
```
1. analyze_agent_deletion_impact(agent) - MANDATORY safety check
2. find_commands_using_agent(agent) - Understand dependencies  
3. Only proceed if safe_to_delete: true
4. Consider deprecate_agent() instead of delete_agent() for gradual migration
```

### 🔧 **Modification Pattern**
```
1. validate_agent(path) - Ensure agent is healthy before changes
2. find_commands_using_agent(agent) - Check impact
3. update_agent() - Make changes
4. validate_agent(path) - Verify changes don't break agent
5. identify_broken_dependencies() - Check ecosystem health
```

### 📊 **Health Monitoring Pattern**
```
1. generate_ecosystem_health_report() - Get comprehensive overview
2. identify_broken_dependencies() - Find specific issues
3. Fix issues found
4. Re-run health checks to verify fixes
```

## **Error Prevention Guidelines**

### ❌ **Never Do These**
- Delete agents without checking impact first
- Use `force: true` on deletions unless absolutely necessary
- Modify agents without validating them first
- Ignore broken dependencies in health reports

### ✅ **Always Do These**
- Run impact analysis before agent changes
- Validate agents after modifications
- Check ecosystem health regularly
- Use deprecation before deletion when possible

This guidance ensures Claude Code uses the Agent Ecosystem MCP Server safely and effectively, preventing accidental damage to the agent ecosystem while enabling powerful management capabilities.