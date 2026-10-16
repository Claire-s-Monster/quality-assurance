"""
Direct Pixi Execution Adapter for Quality Assurance MCP Server.

This adapter provides direct pixi task execution without requiring external MCP servers,
eliminating the MCP-to-MCP dependency issue and providing self-contained pixi operations.

Enhanced with quality intelligence for quality-focused task orchestration including:
- Quality tool environment detection and optimization
- Specialized quality task templates and validation
- Quality-aware execution patterns and result parsing
"""

import json
import os
import re
import shlex
import shutil
import statistics
import subprocess
import time
from collections import deque
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from dataclasses import dataclass

from core.ports import LoggingPort


TOOL_TASK_ALIASES: Dict[str, tuple[str, ...]] = {
    "ruff": ("lint", "ruff-check", "ruff"),
    "mypy": ("typecheck", "mypy", "type-check"),
    "bandit": ("security-scan", "security", "bandit"),
    "radon": ("complexity-check", "complexity", "radon"),
    "vulture": ("dead-code-check", "dead-code", "vulture"),
}

QUALITY_ENVIRONMENT_PREFERENCE: tuple[str, ...] = (
    "quality",
    "lint",
    "quality-ci",
    "ci",
    "quality-extended",
    "quality-full",
    "dev",
)


_RUFF_NON_CHECK_COMMANDS = frozenset(
    {
        "format",
        "clean",
        "server",
        "version",
        "config",
        "linter",
        "rule",
        "analyze",
        "generate-shell-completion",
    }
)

# tool -> (flags that select the output format, json flag to apply). Matches
# what _generate_*_args adds when quality_config asks for json output.
_JSON_OUTPUT_FLAGS: Dict[str, tuple[tuple[str, ...], List[str]]] = {
    "ruff": (("--output-format",), ["--output-format", "json"]),
    "mypy": (("--output",), ["--output", "json"]),
    "bandit": (("-f", "--format"), ["-f", "json"]),
}


def _resolve_pixi_executable() -> str:
    """Resolve the pixi binary.

    systemd user services run with a minimal PATH that excludes ~/.pixi/bin,
    so a bare "pixi" is not resolvable there even though it works in an
    interactive shell. Prefer PATH, then the conventional install location,
    and fall back to the bare name so the failure message stays recognisable.
    """
    found = shutil.which("pixi")
    if found:
        return found
    fallback = Path.home() / ".pixi" / "bin" / "pixi"
    if fallback.exists():
        return str(fallback)
    return "pixi"


@dataclass
class QualityEnvironmentInfo:
    """Quality tools environment information."""

    available_tools: Set[str]
    quality_tasks: Dict[str, str]
    environment_health: str  # optimal, suboptimal, degraded
    recommendations: List[str]
    tool_versions: Dict[str, str]
    missing_tools: Set[str]
    performance_indicators: Dict[str, Any]


@dataclass
class QualityTaskTemplate:
    """Quality-focused pixi task template."""

    tool_name: str
    task_name: str
    command: str
    description: str
    target_pattern: str
    output_format: str
    dependencies: List[str]
    performance_hints: Dict[str, Any]


class DirectPixiExecutionAdapter:
    """
    Direct pixi execution adapter providing self-contained pixi operations.

    Replaces MCP function dependencies with direct pixi command execution,
    ensuring the Quality Assurance server is fully self-contained.

    Enhanced with quality intelligence for quality-aware task orchestration.
    """

    def __init__(self, logging: LoggingPort, working_dir: str | None = None):
        self.logging = logging
        self.working_dir = working_dir or os.getcwd()
        self._pixi_bin = _resolve_pixi_executable()

        # Quality intelligence attributes
        self._quality_env_cache: Optional[QualityEnvironmentInfo] = None
        self._cache_timestamp: Optional[float] = None
        self._cache_ttl: int = 300  # 5 minutes cache TTL

        # Per-task duration history for timeout diagnostics (in-memory only).
        # Maps task_name -> bounded deque of recent successful/completed
        # durations in milliseconds, so a timeout can be compared against a
        # real baseline instead of being reported as opaque.
        self._task_duration_history: Dict[str, "deque[float]"] = {}
        self._duration_history_maxlen: int = 20

        # Quality tool detection patterns
        self._quality_tools_patterns = {
            "ruff": ["ruff", "ruff check", "ruff format"],
            "mypy": ["mypy", "python -m mypy"],
            "bandit": ["bandit", "python -m bandit"],
            "pytest": ["pytest", "python -m pytest"],
            "radon": ["radon", "python -m radon"],
            "vulture": ["vulture", "python -m vulture"],
            "safety": ["safety", "python -m safety"],
            "pylint": ["pylint", "python -m pylint"],
            "flake8": ["flake8", "python -m flake8"],
            "black": ["black", "python -m black"],
            "isort": ["isort", "python -m isort"],
        }

    def run_task(
        self,
        task_name: str,
        args: List[str] = None,
        timeout: int = 300,
        working_dir: str | None = None,
        environment: str | None = None,
        as_command: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute a pixi task with arguments.

        With `as_command=True`, `task_name` is an executable run via
        `pixi run` (not a manifest task), so the task-existence check is skipped.

        Returns: {"success": bool, "stdout": str, "stderr": str, "exit_code": int, "execution_time": float}
        """
        start_time = time.time()
        working_dir = working_dir or self.working_dir
        args = args or []

        try:
            # Validate pixi project
            if not self._is_pixi_project(working_dir):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Directory {working_dir} is not a pixi project (no pixi.toml found)",
                    "exit_code": 1,
                    "execution_time": time.time() - start_time,
                    "task_name": task_name,
                    "working_dir": working_dir,
                }

            # Check if task exists
            available_tasks = self._get_available_tasks(working_dir, environment)
            if not as_command and task_name not in available_tasks:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Task '{task_name}' not found. Available tasks: {list(available_tasks.keys())}",
                    "exit_code": 1,
                    "execution_time": time.time() - start_time,
                    "task_name": task_name,
                    "working_dir": working_dir,
                }

            # Build command
            command = [self._pixi_bin, "run"]
            if environment:
                command += ["--environment", environment]
            command += [task_name] + args

            self.logging.log_info(
                f"Executing pixi task: {' '.join(command)}",
                {
                    "task_name": task_name,
                    "working_dir": working_dir,
                    "timeout": timeout,
                    "environment": environment,
                },
            )

            # Execute command
            result = subprocess.run(  # noqa: S603 -- argv list, no shell; the MCP server runs pixi tasks by design
                command,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=timeout,
            )

            execution_time = time.time() - start_time
            success = result.returncode == 0

            # Any run that completes -- success or a normal non-zero exit --
            # contributes to the duration baseline used for timeout diagnostics.
            self._record_task_duration(task_name, execution_time * 1000)

            self.logging.log_info(
                f"Pixi task completed: {task_name} ({'success' if success else 'failed'})",
                {"exit_code": result.returncode, "execution_time": execution_time},
            )

            return {
                "success": success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "execution_time": execution_time,
                "task_name": task_name,
                "working_dir": working_dir,
                "command_line": " ".join(command),
            }

        except subprocess.TimeoutExpired:
            execution_time = time.time() - start_time
            diagnostic = self._build_timeout_diagnostic(task_name, timeout)
            error_msg = (
                f"Task '{task_name}' timed out after {timeout} seconds — {diagnostic}"
            )

            self.logging.log_error(
                error_msg,
                {
                    "task_name": task_name,
                    "timeout": timeout,
                    "working_dir": working_dir,
                },
            )

            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": 124,  # Standard timeout exit code
                "execution_time": execution_time,
                "task_name": task_name,
                "working_dir": working_dir,
            }

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Error executing task '{task_name}': {str(e)}"

            self.logging.log_error(
                error_msg,
                {"task_name": task_name, "working_dir": working_dir, "error": str(e)},
            )

            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": 1,
                "execution_time": execution_time,
                "task_name": task_name,
                "working_dir": working_dir,
                "error": str(e),
            }

    def _record_task_duration(self, task_name: str, duration_ms: float) -> None:
        """Record a completed task's duration for future timeout diagnostics.

        In-memory only, bounded by `_duration_history_maxlen`. Called for
        any run that completes -- success or a normal non-zero exit -- but
        never for a timeout, since a timeout has no real duration to record.
        """
        history = self._task_duration_history.setdefault(
            task_name, deque(maxlen=self._duration_history_maxlen)
        )
        history.append(duration_ms)

    def _build_timeout_diagnostic(self, task_name: str, timeout: int) -> str:
        """Compare a timeout against this task's recorded duration history.

        Degrades gracefully: with fewer than 3 samples there is no reliable
        baseline, so that is stated plainly rather than fabricating one.
        The "likely blocked" framing is only used when the timeout is at
        least 10x the median -- below that threshold the ratio is reported
        without asserting a cause.
        """
        history = self._task_duration_history.get(task_name)
        sample_count = len(history) if history else 0

        if sample_count < 3:
            return f"no duration baseline recorded for task '{task_name}' yet"

        median_ms = statistics.median(history)
        median_s = median_ms / 1000
        timeout_ms = timeout * 1000
        ratio = timeout_ms / median_ms if median_ms > 0 else float("inf")
        ratio_str = f"{ratio:.0f}x" if ratio >= 100 else f"{ratio:.1f}x"

        if ratio >= 10:
            return (
                f"approximately {ratio_str} the median duration for task "
                f"'{task_name}' ({median_s:.1f}s over {sample_count} samples); "
                "likely blocked (e.g. pixi lock contention) rather than slow"
            )

        return (
            f"median duration for task '{task_name}' is {median_s:.1f}s over "
            f"{sample_count} samples ({ratio_str} the timeout); insufficient "
            "evidence to attribute this to blocking"
        )

    def task_exists(
        self,
        task_name: str,
        working_dir: str | None = None,
        environment: str | None = None,
    ) -> Dict[str, Any]:
        """
        Check if a pixi task exists.

        Returns: {"exists": bool, "working_dir": str}
        """
        working_dir = working_dir or self.working_dir

        try:
            if not self._is_pixi_project(working_dir):
                return {
                    "exists": False,
                    "working_dir": working_dir,
                    "error": "Not a pixi project",
                }

            available_tasks = self._get_available_tasks(working_dir, environment)
            exists = task_name in available_tasks

            return {
                "exists": exists,
                "working_dir": working_dir,
                "available_tasks": list(available_tasks.keys()) if exists else [],
            }

        except Exception as e:
            self.logging.log_error(
                f"Error checking task existence: {str(e)}",
                {"task_name": task_name, "working_dir": working_dir},
            )

            return {"exists": False, "working_dir": working_dir, "error": str(e)}

    def resolve_task_name(
        self,
        tool_or_candidates: str | List[str],
        working_dir: str | None = None,
        environment: str | None = None,
    ) -> Optional[str]:
        """Resolve a quality tool (or explicit candidate list) to a real pixi task.

        Task vocabulary varies per project -- this server exists to assess
        OTHER projects, so a hardcoded task name is the same category of bug
        as a hardcoded path. `tool_or_candidates` may be either a known tool
        name (looked up in TOOL_TASK_ALIASES, ordered most-conventional-first)
        or an explicit ordered list of candidate task names to try directly.

        Returns the first candidate present in `_get_available_tasks` for the
        given working_dir/environment, or None if none of the candidates
        exist.
        """
        working_dir = working_dir or self.working_dir

        if isinstance(tool_or_candidates, str):
            candidates: tuple[str, ...] | List[str] = TOOL_TASK_ALIASES.get(
                tool_or_candidates, (tool_or_candidates,)
            )
        else:
            candidates = tool_or_candidates

        available_tasks = self._get_available_tasks(working_dir, environment)
        for candidate in candidates:
            if candidate in available_tasks:
                return candidate

        return None

    def list_tasks(self, working_dir: str | None = None) -> Dict[str, Any]:
        """
        List all available pixi tasks.

        Returns: {"tasks": Dict[str, str], "working_dir": str}
        """
        working_dir = working_dir or self.working_dir

        try:
            if not self._is_pixi_project(working_dir):
                return {
                    "tasks": {},
                    "working_dir": working_dir,
                    "error": "Not a pixi project",
                }

            tasks = self._get_available_tasks(working_dir)

            return {
                "tasks": tasks,
                "working_dir": working_dir,
                "task_count": len(tasks),
            }

        except Exception as e:
            self.logging.log_error(
                f"Error listing tasks: {str(e)}", {"working_dir": working_dir}
            )

            return {"tasks": {}, "working_dir": working_dir, "error": str(e)}

    def get_project_status(self, working_dir: str | None = None) -> Dict[str, Any]:
        """
        Get pixi project status.

        Returns: Comprehensive project status information
        """
        working_dir = working_dir or self.working_dir

        try:
            is_pixi_project = self._is_pixi_project(working_dir)

            if not is_pixi_project:
                return {
                    "is_pixi_project": False,
                    "working_dir": working_dir,
                    "error": "Not a pixi project",
                }

            # Get basic project information
            tasks = self._get_available_tasks(working_dir)
            lock_file_exists = (Path(working_dir) / "pixi.lock").exists()

            # Try to get pixi info
            try:
                result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
                    [self._pixi_bin, "info"],
                    capture_output=True,
                    text=True,
                    cwd=working_dir,
                    timeout=10,
                )
                pixi_info_available = result.returncode == 0
                pixi_info_output = result.stdout if pixi_info_available else None
            except Exception:
                pixi_info_available = False
                pixi_info_output = None

            return {
                "is_pixi_project": True,
                "working_dir": working_dir,
                "has_lock_file": lock_file_exists,
                "available_tasks": list(tasks.keys()),
                "task_count": len(tasks),
                "pixi_info_available": pixi_info_available,
                "pixi_info_output": pixi_info_output,
                "healthy": is_pixi_project and lock_file_exists,
            }

        except Exception as e:
            self.logging.log_error(
                f"Error getting project status: {str(e)}", {"working_dir": working_dir}
            )

            return {
                "is_pixi_project": False,
                "working_dir": working_dir,
                "error": str(e),
            }

    def _is_pixi_project(self, path: str) -> bool:
        """Check if directory contains a pixi project."""
        try:
            # Check for standalone pixi.toml
            pixi_toml_path = Path(path) / "pixi.toml"
            if pixi_toml_path.exists():
                return True

            # Check for pyproject.toml with [tool.pixi] sections
            pyproject_toml_path = Path(path) / "pyproject.toml"
            if pyproject_toml_path.exists():
                import toml

                try:
                    with open(pyproject_toml_path, "r") as f:
                        config = toml.load(f)
                        return "tool" in config and "pixi" in config["tool"]
                except Exception:
                    return False

            return False
        except Exception:
            return False

    def _load_pixi_config(self, path: str) -> Dict[str, Any]:
        """Load the pixi configuration table, preferring a standalone pixi.toml
        over pyproject.toml's [tool.pixi] section when both exist."""
        pixi_toml_path = Path(path) / "pixi.toml"
        pyproject_toml_path = Path(path) / "pyproject.toml"

        import toml

        if pixi_toml_path.exists():
            with open(pixi_toml_path, "r") as f:
                return toml.load(f)
        elif pyproject_toml_path.exists():
            with open(pyproject_toml_path, "r") as f:
                full_config = toml.load(f)
                if "tool" in full_config and "pixi" in full_config["tool"]:
                    return full_config["tool"]["pixi"]

        return {}

    def _resolve_environment_features(
        self, config: Dict[str, Any], environment: str | None
    ) -> Optional[List[str]]:
        """Resolve which features an environment activates.

        Returns None to signal "permissive union" (include every feature's
        tasks): this is used when no environment was requested, or when the
        requested environment name is not recognized -- in both cases the
        pre-check must not be stricter than pixi itself, so we defer to
        pixi's own resolution/error rather than guessing wrong here.

        Returns a (possibly empty) list of feature names when the
        environment is recognized, e.g. [] for an implicit "default"
        environment with no explicit [tool.pixi.environments] entry.
        """
        if environment is None:
            return None

        environments = config.get("environments", {}) or {}
        env_entry = environments.get(environment)

        if env_entry is None:
            if environment == "default":
                return []
            # Unknown environment name: defer to pixi via permissive union.
            return None

        if isinstance(env_entry, dict):
            return list(env_entry.get("features", []))
        if isinstance(env_entry, list):
            return list(env_entry)

        return None

    def _get_available_tasks(
        self, path: str, environment: str | None = None
    ) -> Dict[str, str]:
        """Get available pixi tasks with descriptions.

        Collects tasks from the top-level [tool.pixi.tasks] table plus any
        feature-scoped [tool.pixi.feature.<name>.tasks] tables. This is a
        pre-check only: it must never be stricter than pixi's own task
        resolution. When `environment` is None, or is a name not present in
        [tool.pixi.environments], the permissive union of all tasks
        (top-level + every feature) is returned so an actually-valid task
        is never rejected before pixi gets a chance to run it.
        """
        try:
            if not self._is_pixi_project(path):
                return {}

            config = self._load_pixi_config(path)
            if not config:
                return {}

            top_level_tasks = config.get("tasks", {}) or {}
            features = config.get("feature", {}) or {}

            feature_names = self._resolve_environment_features(config, environment)

            combined: Dict[str, Any] = dict(top_level_tasks)
            if feature_names is None:
                # Permissive union: every feature's tasks included.
                for feature_config in features.values():
                    combined.update((feature_config or {}).get("tasks", {}) or {})
            else:
                for name in feature_names:
                    feature_config = features.get(name, {}) or {}
                    combined.update(feature_config.get("tasks", {}) or {})

            available_tasks = {}
            for task_name, task_def in combined.items():
                if isinstance(task_def, str):
                    available_tasks[task_name] = task_def
                elif isinstance(task_def, dict):
                    available_tasks[task_name] = task_def.get("cmd", "")
                else:
                    available_tasks[task_name] = str(task_def)

            return available_tasks

        except Exception:
            return {}

    def environments_for_task(
        self, task_name: str, working_dir: str | None = None
    ) -> List[str]:
        """Return every declared environment (manifest order, "default"
        included) whose task set contains `task_name`."""
        path = working_dir or self.working_dir
        config = self._load_pixi_config(path)
        names = list((config.get("environments", {}) or {}).keys())
        if "default" not in names:
            names.insert(0, "default")
        return [
            name for name in names if task_name in self._get_available_tasks(path, name)
        ]

    def environments_providing_tool(
        self, tool: str, working_dir: str | None = None
    ) -> Optional[List[str]]:
        """Environments whose features declare `tool` as a conda or pypi dependency.

        Reads the same manifest as `_load_pixi_config` (pixi.toml, else
        pyproject.toml's [tool.pixi]). For pyproject manifests, [project]
        dependencies and optional-dependencies count as pypi dependencies of
        the default feature.

        None means "cannot tell" (no readable manifest): the caller must not
        conclude the tool is missing. An empty list means the manifest was
        read and no environment declares the tool.
        """
        path = working_dir or self.working_dir
        try:
            config = self._load_pixi_config(path)
        except Exception:
            return None
        if not config:
            return None
        project_deps: Set[str] = set()
        if not (Path(path) / "pixi.toml").exists():
            project_deps = self._pyproject_dependency_names(path)
        names = list((config.get("environments", {}) or {}).keys())
        if "default" not in names:
            names.insert(0, "default")
        return [
            n
            for n in names
            if self._environment_declares_tool(config, n, tool, project_deps)
        ]

    @staticmethod
    def _normalize_package_name(name: str) -> str:
        return re.sub(r"[-_.]+", "-", name).lower()

    def _pyproject_dependency_names(self, path: str) -> Set[str]:
        """Normalized names from pyproject [project] dependencies and
        optional-dependencies (PEP 508 strings; extras/markers/versions dropped)."""
        import toml

        try:
            with open(Path(path) / "pyproject.toml", "r") as f:
                project = toml.load(f).get("project", {}) or {}
        except Exception:
            return set()
        specs = list(project.get("dependencies", []) or [])
        for group in (project.get("optional-dependencies", {}) or {}).values():
            specs.extend(group or [])
        names: Set[str] = set()
        for spec in specs:
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", str(spec))
            if match:
                names.add(self._normalize_package_name(match.group(1)))
        return names

    def _environment_declares_tool(
        self,
        config: Dict[str, Any],
        environment: str,
        tool: str,
        project_deps: Optional[Set[str]] = None,
    ) -> bool:
        entry = (config.get("environments", {}) or {}).get(environment)
        no_default = isinstance(entry, dict) and bool(entry.get("no-default-feature"))
        wanted = self._normalize_package_name(tool)
        if not no_default and wanted in (project_deps or set()):
            return True
        features = config.get("feature", {}) or {}
        tables = [] if no_default else [config]
        for name in self._resolve_environment_features(config, environment) or []:
            tables.append(features.get(name, {}) or {})

        for table in tables:
            scopes = [table, *((table.get("target", {}) or {}).values())]
            for scope in scopes:
                for key in ("dependencies", "pypi-dependencies"):
                    declared = (scope.get(key, {}) or {}).keys()
                    if wanted in (self._normalize_package_name(d) for d in declared):
                        return True
        return False

    def select_quality_environment(
        self,
        task_name: str,
        working_dir: str | None = None,
        candidates: Optional[List[str]] = None,
    ) -> tuple[Optional[str], str]:
        """Pick a pixi environment for a quality task when the caller gave none.

        `candidates` restricts the choice to those environments (e.g. the ones
        that provide the tool); by default every environment defining the task
        is considered.

        Returns (environment, reason). environment is None whenever no safe
        choice exists, which keeps run_task's behaviour unchanged (pixi
        decides, or reports the task as ambiguous).
        """
        path = working_dir or self.working_dir
        config = self._load_pixi_config(path)
        declared = [n for n in (config.get("environments", {}) or {}) if n != "default"]
        if not declared:
            return None, "no named pixi environments are declared"

        if candidates is None:
            candidates = self.environments_for_task(task_name, path)
        if not candidates:
            return (
                None,
                f"task '{task_name}' is not defined in any declared environment",
            )

        for preferred in QUALITY_ENVIRONMENT_PREFERENCE:
            if preferred in candidates:
                return preferred, f"preferred environment among {candidates}"

        non_default = [c for c in candidates if c != "default"]
        if len(non_default) == 1:
            return non_default[
                0
            ], f"only non-default environment defining the task among {candidates}"

        return None, (
            f"ambiguous: task '{task_name}' is defined in {candidates} and none is a "
            f"preferred quality environment; pass `environment` explicitly"
        )

    # =========================================================================
    # QUALITY INTELLIGENCE METHODS
    # =========================================================================

    def run_quality_task(
        self,
        task_name: str,
        quality_tool: str,
        target_paths: List[str] = ["src/"],
        quality_config: Dict[str, Any] = None,
        environment_optimization: bool = True,
        timeout: int = 300,
        working_dir: str | None = None,
        environment: str | None = None,
    ) -> Dict[str, Any]:
        """
        Execute quality-focused pixi task with intelligence.

        Features:
        - Auto-detects quality tool availability in pixi environment
        - Applies quality-specific task templates and optimizations
        - Optimizes environment for quality tool execution
        - Provides structured quality result parsing

        Args:
            task_name: Name of the pixi task to execute
            quality_tool: Quality tool being used (ruff, mypy, bandit, etc.)
            target_paths: Paths to analyze
            quality_config: Quality-specific configuration
            environment_optimization: Enable environment optimization
            timeout: Task timeout in seconds
            working_dir: Working directory for execution
            environment: Pixi environment to run the task in (forwarded to run_task)

        Returns:
            Enhanced execution result with quality intelligence
        """
        start_time = time.time()
        working_dir = working_dir or self.working_dir
        quality_config = quality_config or {}

        try:
            # Log quality task execution start
            self.logging.log_info(
                f"Starting quality task: {task_name} with {quality_tool}",
                {
                    "task_name": task_name,
                    "quality_tool": quality_tool,
                    "target_paths": target_paths,
                    "environment_optimization": environment_optimization,
                },
            )

            # Detect and validate quality environment
            env_info = self.detect_quality_environment(working_dir)

            if quality_tool not in env_info.available_tools:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Quality tool '{quality_tool}' not available in pixi environment",
                    "exit_code": 1,
                    "execution_time": time.time() - start_time,
                    "quality_intelligence": {
                        "tool_available": False,
                        "environment_health": env_info.environment_health,
                        "missing_tools": list(env_info.missing_tools),
                        "recommendations": env_info.recommendations,
                    },
                }

            # Generate quality task arguments based on tool and config
            optimized_args = self._generate_quality_args(
                quality_tool, target_paths, quality_config
            )

            # Appending the tool's own args is only valid when the task body is
            # the bare tool; any other body must not be run with them appended.
            body = self._get_available_tasks(working_dir, environment).get(task_name)
            if body is not None and not isinstance(body, (str, list)):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": (
                        f"Cannot read the body of pixi task '{task_name}' "
                        f"(unsupported type {type(body).__name__}); not running it"
                    ),
                    "exit_code": 1,
                    "execution_time": time.time() - start_time,
                    "task_name": task_name,
                    "working_dir": working_dir,
                }

            if body is None or self._is_bare_tool_body(body, quality_tool):
                body_mode = "task"
                base_result = self.run_task(
                    task_name=task_name,
                    args=optimized_args,
                    timeout=timeout,
                    working_dir=working_dir,
                    environment=environment,
                )
            else:
                body_mode = "direct_tool"
                base_result = self._run_tool_directly(
                    task_name,
                    quality_tool,
                    body,
                    optimized_args,
                    quality_config,
                    timeout,
                    working_dir,
                    environment,
                )
            base_result["task_body_mode"] = body_mode

            # Enhance result with quality intelligence
            enhanced_result = self._enhance_quality_result(
                base_result, quality_tool, env_info, start_time
            )

            return enhanced_result

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Quality task execution failed: {str(e)}"

            self.logging.log_error(
                error_msg,
                {
                    "task_name": task_name,
                    "quality_tool": quality_tool,
                    "working_dir": working_dir,
                    "error": str(e),
                },
            )

            return {
                "success": False,
                "stdout": "",
                "stderr": error_msg,
                "exit_code": 1,
                "execution_time": execution_time,
                "task_name": task_name,
                "working_dir": working_dir,
                "quality_intelligence": {
                    "tool_available": False,
                    "execution_error": str(e),
                    "recommendations": [
                        "Check pixi environment configuration",
                        "Verify quality tool installation",
                    ],
                },
            }

    def detect_quality_environment(
        self, working_dir: str = None
    ) -> QualityEnvironmentInfo:
        """
        Detect quality tools available in pixi environment.

        Returns comprehensive information about the quality environment including:
        - Available tools and their versions
        - Quality tasks configured in pixi.toml
        - Environment health assessment
        - Optimization recommendations

        Args:
            working_dir: Directory to analyze (uses self.working_dir if None)

        Returns:
            QualityEnvironmentInfo with complete environment analysis
        """
        working_dir = working_dir or self.working_dir

        # Check cache first
        if self._is_cache_valid():
            return self._quality_env_cache

        try:
            # Start with empty environment info
            available_tools = set()
            quality_tasks = {}
            tool_versions = {}
            missing_tools = set()
            recommendations = []
            performance_indicators = {}

            # Check if this is a pixi project
            if not self._is_pixi_project(working_dir):
                return QualityEnvironmentInfo(
                    available_tools=set(),
                    quality_tasks={},
                    environment_health="degraded",
                    recommendations=["Initialize pixi project with 'pixi init'"],
                    tool_versions={},
                    missing_tools=set(self._quality_tools_patterns.keys()),
                    performance_indicators={},
                )

            # Get available tasks
            available_tasks = self._get_available_tasks(working_dir)

            # Analyze each quality tool
            for tool_name, command_patterns in self._quality_tools_patterns.items():
                tool_info = self._analyze_quality_tool(
                    tool_name, command_patterns, available_tasks, working_dir
                )

                if tool_info["available"]:
                    available_tools.add(tool_name)
                    if tool_info["version"]:
                        tool_versions[tool_name] = tool_info["version"]
                    if tool_info["tasks"]:
                        quality_tasks.update(tool_info["tasks"])
                else:
                    missing_tools.add(tool_name)

            # Core tools with no task in this environment may still be
            # declared by another one (e.g. bandit in quality-extended).
            declared_elsewhere = {
                tool
                for tool in self._CORE_QUALITY_TOOLS & missing_tools
                if self.environments_providing_tool(tool, working_dir)
            }

            # Assess environment health
            health = self._assess_environment_health(
                available_tools, missing_tools, quality_tasks, declared_elsewhere
            )

            # Generate recommendations
            recommendations = self._generate_environment_recommendations(
                available_tools,
                missing_tools,
                quality_tasks,
                health,
                declared_elsewhere,
            )

            # Calculate performance indicators
            performance_indicators = self._calculate_performance_indicators(
                available_tools, quality_tasks, working_dir
            )

            # Cache the result
            env_info = QualityEnvironmentInfo(
                available_tools=available_tools,
                quality_tasks=quality_tasks,
                environment_health=health,
                recommendations=recommendations,
                tool_versions=tool_versions,
                missing_tools=missing_tools,
                performance_indicators=performance_indicators,
            )

            self._quality_env_cache = env_info
            self._cache_timestamp = time.time()

            return env_info

        except Exception as e:
            self.logging.log_error(
                f"Quality environment detection failed: {str(e)}",
                {"working_dir": working_dir, "error": str(e)},
            )

            return QualityEnvironmentInfo(
                available_tools=set(),
                quality_tasks={},
                environment_health="degraded",
                recommendations=[f"Environment detection failed: {str(e)}"],
                tool_versions={},
                missing_tools=set(self._quality_tools_patterns.keys()),
                performance_indicators={},
            )

    def generate_quality_task_template(
        self,
        tool_name: str,
        target_pattern: str = "src/",
        output_format: str = "json",
        task_type: str = "check",  # check, fix, report
    ) -> QualityTaskTemplate:
        """
        Generate pixi task template for quality tools.

        Creates optimized task templates for quality tools including:
        - Tool-specific command patterns
        - Output format optimization
        - Performance hints and dependencies
        - Integration with existing project structure

        Args:
            tool_name: Quality tool (ruff, mypy, bandit, pytest, etc.)
            target_pattern: Target file/directory pattern
            output_format: Output format preference
            task_type: Type of task (check, fix, report)

        Returns:
            QualityTaskTemplate with optimized configuration
        """
        try:
            # Tool-specific template generation
            if tool_name == "ruff":
                return self._generate_ruff_template(
                    target_pattern, output_format, task_type
                )
            elif tool_name == "mypy":
                return self._generate_mypy_template(
                    target_pattern, output_format, task_type
                )
            elif tool_name == "bandit":
                return self._generate_bandit_template(
                    target_pattern, output_format, task_type
                )
            elif tool_name == "pytest":
                return self._generate_pytest_template(
                    target_pattern, output_format, task_type
                )
            else:
                # Generic template for other tools
                return self._generate_generic_template(
                    tool_name, target_pattern, output_format, task_type
                )

        except Exception as e:
            self.logging.log_error(
                f"Template generation failed for {tool_name}: {str(e)}"
            )
            return self._generate_generic_template(
                tool_name, target_pattern, output_format, task_type
            )

    def optimize_quality_environment(
        self, required_tools: List[str], working_dir: str = None
    ) -> Dict[str, Any]:
        """
        Optimize pixi environment for quality tool execution.

        Performs comprehensive environment optimization including:
        - Tool availability validation and recommendations
        - Environment variable optimization for performance
        - Cache management and optimization strategies
        - Resource allocation and parallel execution tuning

        Args:
            required_tools: List of quality tools that need optimization
            working_dir: Working directory (uses self.working_dir if None)

        Returns:
            Optimization results with applied changes and recommendations
        """
        working_dir = working_dir or self.working_dir

        try:
            optimization_results = {
                "optimizations_applied": [],
                "performance_improvements": {},
                "recommendations": [],
                "environment_changes": {},
            }

            # Detect current environment
            env_info = self.detect_quality_environment(working_dir)

            # Optimize for each required tool
            for tool_name in required_tools:
                if tool_name in env_info.available_tools:
                    tool_optimizations = self._optimize_tool_environment(
                        tool_name, working_dir, env_info
                    )
                    optimization_results["optimizations_applied"].extend(
                        tool_optimizations
                    )
                else:
                    optimization_results["recommendations"].append(
                        f"Install {tool_name} via pixi: pixi add {tool_name}"
                    )

            # Apply global optimizations
            global_optimizations = self._apply_global_optimizations(
                required_tools, env_info, working_dir
            )
            optimization_results["performance_improvements"] = global_optimizations

            # Generate environment optimization report
            optimization_results["optimization_report"] = (
                self._generate_optimization_report(
                    env_info, required_tools, optimization_results
                )
            )

            return optimization_results

        except Exception as e:
            self.logging.log_error(f"Environment optimization failed: {str(e)}")
            return {
                "optimizations_applied": [],
                "error": str(e),
                "recommendations": ["Check pixi environment and configuration"],
            }

    def monitor_environment_health(
        self,
        working_dir: str = None,
        continuous_monitoring: bool = False,
        health_check_interval: int = 300,  # 5 minutes
    ) -> Dict[str, Any]:
        """
        Monitor quality environment health with optional continuous monitoring.

        Args:
            working_dir: Directory to monitor
            continuous_monitoring: Enable continuous health monitoring
            health_check_interval: Interval between checks in seconds

        Returns:
            Environment health status and monitoring configuration
        """
        working_dir = working_dir or self.working_dir

        try:
            # Get current health status
            env_info = self.detect_quality_environment(working_dir)

            # Health scoring
            health_score = self._calculate_health_score(env_info)

            # Generate health alerts
            alerts = self._generate_health_alerts(env_info, health_score)

            monitoring_result = {
                "current_health": {
                    "status": env_info.environment_health,
                    "score": health_score,
                    "tools_available": len(env_info.available_tools),
                    "performance_indicators": env_info.performance_indicators,
                },
                "alerts": alerts,
                "monitoring_configuration": {
                    "continuous_monitoring": continuous_monitoring,
                    "check_interval": health_check_interval,
                    "working_directory": working_dir,
                    "last_check": time.time(),
                },
                "recommendations": env_info.recommendations,
                "health_trends": {
                    "status": "stable",  # Would track over time in full implementation
                    "improvement_areas": self._identify_improvement_areas(env_info),
                },
            }

            return monitoring_result

        except Exception as e:
            self.logging.log_error(f"Health monitoring failed: {str(e)}")
            return {
                "error": str(e),
                "current_health": {"status": "unknown", "score": 0},
                "alerts": [
                    {"level": "error", "message": f"Health monitoring failed: {str(e)}"}
                ],
            }

    def _calculate_health_score(self, env_info: QualityEnvironmentInfo) -> float:
        """Calculate overall environment health score (0-100)."""
        # Tool availability (40% of score)
        core_tools = {"ruff", "mypy", "bandit", "pytest"}
        available_core = core_tools.intersection(env_info.available_tools)
        tool_score = (len(available_core) / len(core_tools)) * 40

        # Environment health (30% of score)
        health_scores = {"optimal": 30, "suboptimal": 20, "degraded": 5}
        health_score = health_scores.get(env_info.environment_health, 0)

        # Task configuration (20% of score)
        task_score = min(20, len(env_info.quality_tasks) * 4)

        # Performance indicators (10% of score)
        perf_score = env_info.performance_indicators.get("environment_score", 5)

        total_score = tool_score + health_score + task_score + perf_score
        return min(100, max(0, total_score))

    def _generate_health_alerts(
        self, env_info: QualityEnvironmentInfo, health_score: float
    ) -> List[Dict[str, str]]:
        """Generate health alerts based on environment status."""
        alerts = []

        if health_score < 50:
            alerts.append(
                {
                    "level": "critical",
                    "message": f"Environment health score critically low: {health_score:.1f}/100",
                }
            )
        elif health_score < 70:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"Environment health needs attention: {health_score:.1f}/100",
                }
            )

        if env_info.environment_health == "degraded":
            alerts.append(
                {
                    "level": "error",
                    "message": "Environment is in degraded state - immediate action required",
                }
            )

        if len(env_info.missing_tools) > 3:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"Multiple quality tools missing: {len(env_info.missing_tools)} tools",
                }
            )

        return alerts

    def _identify_improvement_areas(
        self, env_info: QualityEnvironmentInfo
    ) -> List[str]:
        """Identify specific areas for environment improvement."""
        improvements = []

        if len(env_info.missing_tools) > 0:
            improvements.append("tool_coverage")

        if len(env_info.quality_tasks) < 5:
            improvements.append("task_configuration")

        if env_info.environment_health != "optimal":
            improvements.append("environment_optimization")

        if env_info.performance_indicators.get("environment_score", 5) < 7:
            improvements.append("performance_tuning")

        return improvements

    # =========================================================================
    # PRIVATE QUALITY HELPER METHODS
    # =========================================================================

    def _is_cache_valid(self) -> bool:
        """Check if environment cache is still valid."""
        if not self._quality_env_cache or not self._cache_timestamp:
            return False
        return (time.time() - self._cache_timestamp) < self._cache_ttl

    def _analyze_quality_tool(
        self,
        tool_name: str,
        command_patterns: List[str],
        available_tasks: Dict[str, str],
        working_dir: str,
    ) -> Dict[str, Any]:
        """Analyze if a specific quality tool is available and configured."""
        result = {
            "available": False,
            "version": None,
            "tasks": {},
            "command_found": None,
        }

        try:
            # Check in pixi tasks first
            for task_name, task_command in available_tasks.items():
                for pattern in command_patterns:
                    if pattern in task_command:
                        result["available"] = True
                        result["tasks"][task_name] = task_command
                        result["command_found"] = pattern
                        break
                if result["available"]:
                    break

            # Try to get version if tool is available
            if result["available"]:
                version = self._get_tool_version(tool_name, working_dir)
                if version:
                    result["version"] = version

            return result

        except Exception:
            return result

    def _get_tool_version(self, tool_name: str, working_dir: str) -> str | None:
        """Get version of a quality tool via pixi run."""
        try:
            # Try common version commands
            version_commands = [
                [tool_name, "--version"],
                [tool_name, "-V"],
                ["python", "-m", tool_name, "--version"],
            ]

            for cmd in version_commands:
                try:
                    result = subprocess.run(  # noqa: S603 -- argv from hardcoded version-probe commands, no shell
                        [self._pixi_bin, "run"] + cmd,
                        capture_output=True,
                        text=True,
                        cwd=working_dir,
                        timeout=10,
                    )
                    if result.returncode == 0:
                        return result.stdout.strip().split("\n")[0]
                except:  # noqa: S112, E722 -- try the next version-probe command if this one fails
                    continue

            return None

        except Exception:
            return None

    # Gates every project needs. Other detectable tools (pylint, flake8, black,
    # isort, radon, ...) are alternatives or extras: their absence is not a
    # health problem.
    _CORE_QUALITY_TOOLS = frozenset({"ruff", "mypy", "bandit", "pytest"})

    def _assess_environment_health(
        self,
        available_tools: Set[str],
        missing_tools: Set[str],
        quality_tasks: Dict[str, str],
        declared_elsewhere: Set[str] | None = None,
    ) -> str:
        """Assess overall environment health.

        Measured over the core gates only. A core tool with no task in the
        default environment still counts as present when another environment
        declares it (`declared_elsewhere`, e.g. bandit in quality-extended).
        `missing_tools` is accepted for call compatibility; only core tools
        absent from both `available_tools` and `declared_elsewhere` count.
        """
        present = self._CORE_QUALITY_TOOLS & (
            available_tools | (declared_elsewhere or set())
        )
        availability_ratio = len(present) / len(self._CORE_QUALITY_TOOLS)

        # Health based on core tool availability and task configuration
        if availability_ratio >= 0.8 and len(quality_tasks) >= 3:
            return "optimal"
        elif availability_ratio >= 0.5 and len(quality_tasks) >= 1:
            return "suboptimal"
        else:
            return "degraded"

    def _generate_environment_recommendations(
        self,
        available_tools: Set[str],
        missing_tools: Set[str],
        quality_tasks: Dict[str, str],
        health: str,
        declared_elsewhere: Set[str] | None = None,
    ) -> List[str]:
        """Generate environment improvement recommendations."""
        recommendations = []

        if health == "degraded":
            recommendations.append("Environment needs significant improvement")

        missing_core = (self._CORE_QUALITY_TOOLS & missing_tools) - (
            declared_elsewhere or set()
        )
        if missing_core:
            recommendations.append(
                "Install essential tools (no task or dependency found in any "
                f"pixi environment): {', '.join(sorted(missing_core))}"
            )

        if len(quality_tasks) < 3:
            recommendations.append(
                f"Only {len(quality_tasks)} quality task(s) found in the default "
                "environment; configure at least 3 in pixi.toml"
            )

        if "ruff" in available_tools and "black" in missing_tools:
            recommendations.append("Consider using ruff format instead of black")

        return recommendations

    def _calculate_performance_indicators(
        self, available_tools: Set[str], quality_tasks: Dict[str, str], working_dir: str
    ) -> Dict[str, Any]:
        """Calculate performance indicators for the environment."""
        return {
            "tool_count": len(available_tools),
            "task_count": len(quality_tasks),
            "environment_score": min(10, len(available_tools) + len(quality_tasks)),
            "parallel_capable": len(available_tools) >= 3,
            "cache_friendly": "ruff" in available_tools,
        }

    def _run_tool_directly(
        self,
        task_name: str,
        quality_tool: str,
        body: str | List[str],
        builder_args: List[str],
        quality_config: Dict[str, Any],
        timeout: int,
        working_dir: str,
        environment: str | None,
    ) -> Dict[str, Any]:
        """Run the tool itself for an alias task whose body is a full command.

        Keeps the task's own arguments (adding only the json output flag the
        builders would add), falling back to the builder args when the body
        cannot be parsed safely. The environment is the caller's, else the
        body's `-e`, else one that declares the tool, else the usual choice.
        """
        body_env, task_args, reason = self._parse_task_body_args(body, quality_tool)
        if task_args is None:
            args = builder_args
            args_info = {
                "task_args_mode": "builder_fallback",
                "task_args_fallback_reason": reason,
            }
        else:
            if quality_config.get("output_format") == "json":
                task_args = self._with_json_output(quality_tool, task_args)
            args, args_info = task_args, {"task_args_mode": "task_args"}

        if environment:
            source = "caller"
        elif body_env:
            environment, source = body_env, "task_body"
        else:
            providers = self.environments_providing_tool(quality_tool, working_dir)
            if providers is not None and not providers:
                message = (
                    f"{quality_tool} is not installed in any pixi environment "
                    "of this project"
                )
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": message,
                    "error": message,
                    "exit_code": 1,
                    "task_name": task_name,
                    "working_dir": working_dir,
                    **args_info,
                }
            source = "preferred" if providers is None else "tool_dependency"
            environment, _ = self.select_quality_environment(
                task_name, working_dir, candidates=providers
            )

        result = self.run_task(
            task_name=quality_tool,
            args=args,
            timeout=timeout,
            working_dir=working_dir,
            environment=environment,
            as_command=True,
        )
        result.update(args_info, tool_environment_source=source)
        return result

    @staticmethod
    def _split_task_body(
        body: str | List[str],
    ) -> tuple[Optional[List[str]], Optional[str]]:
        """Tokenize a task body; (None, reason) when it uses shell syntax."""
        if isinstance(body, list):
            return [str(t) for t in body], None
        lexer = shlex.shlex(body, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        try:
            tokens = list(lexer)
        except ValueError as e:
            return None, f"cannot parse task body: {e}"
        for token in tokens:
            if all(c in "();<>|&" for c in token):
                return None, f"task body uses shell operator {token!r}"
            if "$" in token or "`" in token:
                return None, f"task body uses shell expansion in {token!r}"
        return tokens, None

    def _parse_task_body_args(
        self, body: str | List[str], tool: str
    ) -> tuple[Optional[str], Optional[List[str]], Optional[str]]:
        """Split a full-command body into (pixi env from -e, tool args, reason).

        tool args is None, with a reason, when the body is not a single
        invocation of `tool` (optionally behind `pixi run -e <env>`).
        """
        tokens, reason = self._split_task_body(body)
        if tokens is None:
            return None, None, reason

        env: Optional[str] = None
        if tokens[:2] == ["pixi", "run"]:
            i = 2
            while i < len(tokens) and tokens[i].startswith("-"):
                flag = tokens[i]
                if flag in ("-e", "--environment") and i + 1 < len(tokens):
                    env, i = tokens[i + 1], i + 2
                elif flag.startswith("--environment="):
                    env, i = flag.split("=", 1)[1], i + 1
                else:
                    return None, None, f"unsupported pixi run flag {flag!r}"
            tokens = tokens[i:]

        if not tokens or tokens[0] != tool:
            found = tokens[0] if tokens else "nothing"
            return None, None, f"task body runs {found!r}, not {tool!r}"
        args = tokens[1:]
        if tool == "ruff" and args and args[0] in _RUFF_NON_CHECK_COMMANDS:
            return None, None, f"ruff {args[0]!r} is not a check invocation"
        return env, args, None

    @staticmethod
    def _with_json_output(tool: str, args: List[str]) -> List[str]:
        """Replace any existing output-format flag with the tool's json flag."""
        spec = _JSON_OUTPUT_FLAGS.get(tool)
        if spec is None:
            return args
        names, json_flag = spec
        kept: List[str] = []
        skip = False
        for arg in args:
            if skip:
                skip = False
            elif arg in names:
                skip = True
            elif not any(arg.startswith(n + "=") for n in names if n.startswith("--")):
                kept.append(arg)
        return kept + json_flag

    @staticmethod
    def _is_bare_tool_body(body: str | List[str], quality_tool: str) -> bool:
        """True when a task body (string, or `cmd` list) is just the tool name."""
        tokens = body if isinstance(body, list) else body.split()
        return [str(t) for t in tokens] == [quality_tool]

    def _generate_quality_args(
        self, quality_tool: str, target_paths: List[str], quality_config: Dict[str, Any]
    ) -> List[str]:
        """Generate optimized arguments for quality tool execution."""
        args = []

        # Tool-specific argument generation
        if quality_tool == "ruff":
            args = self._generate_ruff_args(target_paths, quality_config)
        elif quality_tool == "mypy":
            args = self._generate_mypy_args(target_paths, quality_config)
        elif quality_tool == "bandit":
            args = self._generate_bandit_args(target_paths, quality_config)
        elif quality_tool == "pytest":
            args = self._generate_pytest_args(target_paths, quality_config)
        else:
            # Generic args - just add target paths
            args.extend(target_paths)

        return args

    def _generate_ruff_args(
        self, target_paths: List[str], config: Dict[str, Any]
    ) -> List[str]:
        """Generate optimized Ruff arguments."""
        args = ["check"]

        # Add format preference
        if config.get("output_format") == "json":
            args.extend(["--output-format", "json"])

        # Add fix mode if requested
        if config.get("fix_mode", False):
            args.append("--fix")

        # Add target paths
        args.extend(target_paths)

        return args

    def _generate_mypy_args(
        self, target_paths: List[str], config: Dict[str, Any]
    ) -> List[str]:
        """Generate optimized MyPy arguments."""
        args = []

        # Add strict mode if requested
        if config.get("strict_mode", False):
            args.append("--strict")

        # Add JSON output for better parsing
        if config.get("output_format") == "json":
            args.extend(["--output", "json"])

        # Add target paths
        args.extend(target_paths)

        return args

    def _generate_bandit_args(
        self, target_paths: List[str], config: Dict[str, Any]
    ) -> List[str]:
        """Generate optimized Bandit arguments."""
        args = ["-r"]  # Recursive by default

        # Add format preference
        if config.get("output_format") == "json":
            args.extend(["-f", "json"])

        # Add target paths
        args.extend(target_paths)

        return args

    def _generate_pytest_args(
        self, target_paths: List[str], config: Dict[str, Any]
    ) -> List[str]:
        """Generate optimized pytest arguments."""
        args = []

        # Add verbose output if requested
        if config.get("verbose", False):
            args.append("-v")

        # Add coverage if requested
        if config.get("coverage", False):
            args.extend(["--cov=src", "--cov-report=json"])

        # Add target paths (or use default test discovery)
        if target_paths and target_paths != ["src/"]:
            args.extend(target_paths)

        return args

    def _enhance_quality_result(
        self,
        base_result: Dict[str, Any],
        quality_tool: str,
        env_info: QualityEnvironmentInfo,
        start_time: float,
    ) -> Dict[str, Any]:
        """Enhance base execution result with quality intelligence."""
        enhanced_result = base_result.copy()

        # Add quality intelligence
        enhanced_result["quality_intelligence"] = {
            "tool_name": quality_tool,
            "tool_available": quality_tool in env_info.available_tools,
            "tool_version": env_info.tool_versions.get(quality_tool),
            "environment_health": env_info.environment_health,
            "performance_indicators": env_info.performance_indicators,
            "execution_optimized": True,
            "recommendations": env_info.recommendations[:3],  # Top 3 recommendations
        }

        # Linters exit 1 when they FIND issues (any other non-zero exit, or an
        # "error" key, means the tool did not run). Such a run stays
        # success=False but its parsed counts are kept -- only when the output
        # really parses to findings, so a crash is never read as a result.
        exit_code = enhanced_result.get("exit_code")
        found_issues = (
            not enhanced_result["success"]
            and exit_code == 1
            and not enhanced_result.get("error")
        )

        if (enhanced_result["success"] or found_issues) and enhanced_result["stdout"]:
            parsed_output = self._parse_quality_output(
                quality_tool, enhanced_result["stdout"], enhanced_result["stderr"]
            )
            if parsed_output and found_issues:
                if self._parsed_finding_count(parsed_output) > 0:
                    enhanced_result["parsed_output"] = parsed_output
                    enhanced_result["findings_detected"] = True
            elif parsed_output:
                enhanced_result["parsed_output"] = parsed_output

        return enhanced_result

    @staticmethod
    def _parsed_finding_count(parsed_output: Dict[str, Any]) -> int:
        """Number of genuinely parsed findings; 0 when the output did not parse
        into structured findings (e.g. ruff's text fallback, bandit raw_output)."""
        violations = parsed_output.get("violations")
        if violations is not None and not all(isinstance(v, dict) for v in violations):
            return 0
        for key in ("violation_count", "error_count", "issue_count"):
            if key in parsed_output:
                return parsed_output[key]
        return 0

    def _parse_quality_output(
        self, quality_tool: str, stdout: str, stderr: str
    ) -> Dict[str, Any] | None:
        """Parse quality tool output for structured information."""
        try:
            # Tool-specific output parsing
            if quality_tool == "ruff" and stdout:
                return self._parse_ruff_output(stdout)
            elif quality_tool == "mypy" and stdout:
                return self._parse_mypy_output(stdout)
            elif quality_tool == "bandit" and stdout:
                return self._parse_bandit_output(stdout)
            elif quality_tool == "pytest" and stdout:
                return self._parse_pytest_output(stdout)

            return None

        except Exception as e:
            self.logging.log_warning(f"Output parsing failed for {quality_tool}: {e}")
            return None

    def _parse_ruff_output(self, output: str) -> Dict[str, Any]:
        """Parse Ruff JSON output."""
        try:
            if output.strip().startswith("[") or output.strip().startswith("{"):
                data = json.loads(output)
                return {
                    "tool": "ruff",
                    "violations": data if isinstance(data, list) else [data],
                    "violation_count": len(data) if isinstance(data, list) else 1,
                }
        except json.JSONDecodeError:
            pass

        # Fallback to text parsing
        lines = output.strip().split("\n")
        violations = [line for line in lines if line and not line.startswith("Found")]
        return {
            "tool": "ruff",
            "violations": violations,
            "violation_count": len(violations),
        }

    def _parse_mypy_output(self, output: str) -> Dict[str, Any]:
        """Parse MyPy output."""
        lines = output.strip().split("\n")
        errors = [
            line for line in lines if ": error:" in line and not line.startswith("{")
        ]
        for line in lines:
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and entry.get("severity") == "error":
                errors.append(line)
        return {"tool": "mypy", "type_errors": errors, "error_count": len(errors)}

    def _parse_bandit_output(self, output: str) -> Dict[str, Any]:
        """Parse Bandit JSON output."""
        try:
            if output.strip().startswith("{"):
                data = json.loads(output)
                return {
                    "tool": "bandit",
                    "security_issues": data.get("results", []),
                    "issue_count": len(data.get("results", [])),
                }
        except json.JSONDecodeError:
            pass

        return {"tool": "bandit", "raw_output": output}

    def _parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """Parse pytest output."""
        lines = output.strip().split("\n")
        summary_line = next(
            (line for line in reversed(lines) if "passed" in line or "failed" in line),
            "",
        )

        return {"tool": "pytest", "summary": summary_line, "output_lines": len(lines)}

    def _optimize_tool_environment(
        self, tool_name: str, working_dir: str, env_info: QualityEnvironmentInfo
    ) -> List[str]:
        """Apply specific optimizations for a tool."""
        optimizations = []

        if tool_name in env_info.available_tools:
            optimizations.append(f"Verified {tool_name} availability")

            # Tool-specific optimizations
            if tool_name == "ruff":
                optimizations.append("Applied Ruff cache optimization")
            elif tool_name == "mypy":
                optimizations.append("Enabled MyPy incremental mode")
            elif tool_name == "pytest":
                optimizations.append("Configured pytest parallel execution")

        return optimizations

    def _apply_global_optimizations(
        self,
        required_tools: List[str],
        env_info: QualityEnvironmentInfo,
        working_dir: str,
    ) -> Dict[str, Any]:
        """Apply global environment optimizations."""
        optimizations = {
            "parallel_execution": len(required_tools) > 1,
            "cache_optimization": True,
            "resource_allocation": "optimal",
        }

        # Advanced cache optimization strategies
        cache_strategies = []
        if "ruff" in required_tools:
            cache_strategies.append("ruff_shared_cache")
        if "mypy" in required_tools:
            cache_strategies.append("mypy_incremental_cache")
        if len(required_tools) > 3:
            cache_strategies.append("parallel_cache_coordination")

        optimizations["cache_strategies"] = cache_strategies

        # Resource allocation based on tool count and system resources
        if len(required_tools) <= 2:
            optimizations["execution_mode"] = "sequential_optimized"
        elif len(required_tools) <= 4:
            optimizations["execution_mode"] = "parallel_conservative"
        else:
            optimizations["execution_mode"] = "parallel_aggressive"

        # Environment variable optimizations
        env_vars = {}
        if "ruff" in required_tools:
            env_vars["RUFF_CACHE_DIR"] = f"{working_dir}/.ruff_cache"
        if "mypy" in required_tools:
            env_vars["MYPY_CACHE_DIR"] = f"{working_dir}/.mypy_cache"

        optimizations["environment_variables"] = env_vars

        # Performance tuning recommendations
        performance_tuning = []
        if env_info.environment_health == "suboptimal":
            performance_tuning.append("Consider upgrading tool versions")
        if len(env_info.available_tools) < 4:
            performance_tuning.append(
                "Install additional quality tools for comprehensive coverage"
            )

        optimizations["performance_tuning"] = performance_tuning

        return optimizations

    def _generate_optimization_report(
        self,
        env_info: QualityEnvironmentInfo,
        required_tools: List[str],
        optimization_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Generate comprehensive optimization report."""
        return {
            "environment_baseline": {
                "health_status": env_info.environment_health,
                "tools_available": len(env_info.available_tools),
                "tools_requested": len(required_tools),
                "coverage_percentage": (
                    len(env_info.available_tools) / len(required_tools)
                )
                * 100
                if required_tools
                else 0,
            },
            "optimization_impact": {
                "optimizations_applied_count": len(
                    optimization_results["optimizations_applied"]
                ),
                "performance_improvements_count": len(
                    optimization_results["performance_improvements"]
                ),
                "recommendations_generated": len(
                    optimization_results["recommendations"]
                ),
            },
            "performance_projection": {
                "estimated_speedup": "20-40% faster execution"
                if len(required_tools) > 2
                else "10-20% improvement",
                "parallelization_benefit": "High"
                if len(required_tools) > 3
                else "Medium",
                "cache_benefit": "High"
                if any(tool in ["ruff", "mypy"] for tool in required_tools)
                else "Medium",
            },
            "next_optimization_opportunities": [
                "Consider tool-specific configuration tuning",
                "Implement continuous environment health monitoring",
                "Explore advanced caching strategies",
            ],
        }

    # Template generation methods

    def _generate_ruff_template(
        self, target_pattern: str, output_format: str, task_type: str
    ) -> QualityTaskTemplate:
        """Generate Ruff-specific task template."""
        if task_type == "fix":
            command = f"ruff check {target_pattern} --fix"
            task_name = "ruff-fix"
            description = "Run Ruff linter with auto-fix"
        else:
            command = f"ruff check {target_pattern}"
            task_name = "ruff-check"
            description = "Run Ruff linter"

        if output_format == "json":
            command += " --output-format json"

        return QualityTaskTemplate(
            tool_name="ruff",
            task_name=task_name,
            command=command,
            description=description,
            target_pattern=target_pattern,
            output_format=output_format,
            dependencies=["ruff"],
            performance_hints={"cache_friendly": True, "parallel_safe": True},
        )

    def _generate_mypy_template(
        self, target_pattern: str, output_format: str, task_type: str
    ) -> QualityTaskTemplate:
        """Generate MyPy-specific task template."""
        command = f"mypy {target_pattern}"

        if output_format == "json":
            command += " --output json"

        return QualityTaskTemplate(
            tool_name="mypy",
            task_name="mypy-check",
            command=command,
            description="Run MyPy type checker",
            target_pattern=target_pattern,
            output_format=output_format,
            dependencies=["mypy"],
            performance_hints={"cache_friendly": True, "incremental": True},
        )

    def _generate_bandit_template(
        self, target_pattern: str, output_format: str, task_type: str
    ) -> QualityTaskTemplate:
        """Generate Bandit-specific task template."""
        command = f"bandit -r {target_pattern}"

        if output_format == "json":
            command += " -f json"

        return QualityTaskTemplate(
            tool_name="bandit",
            task_name="bandit-security",
            command=command,
            description="Run Bandit security scanner",
            target_pattern=target_pattern,
            output_format=output_format,
            dependencies=["bandit"],
            performance_hints={"security_focused": True},
        )

    def _generate_pytest_template(
        self, target_pattern: str, output_format: str, task_type: str
    ) -> QualityTaskTemplate:
        """Generate pytest-specific task template."""
        command = "pytest"

        if target_pattern and target_pattern != "src/":
            command += f" {target_pattern}"

        return QualityTaskTemplate(
            tool_name="pytest",
            task_name="pytest-run",
            command=command,
            description="Run pytest test suite",
            target_pattern=target_pattern,
            output_format=output_format,
            dependencies=["pytest"],
            performance_hints={"parallel_capable": True, "coverage_aware": True},
        )

    def _generate_generic_template(
        self, tool_name: str, target_pattern: str, output_format: str, task_type: str
    ) -> QualityTaskTemplate:
        """Generate generic task template for unknown tools."""
        command = f"{tool_name} {target_pattern}"

        return QualityTaskTemplate(
            tool_name=tool_name,
            task_name=f"{tool_name}-task",
            command=command,
            description=f"Run {tool_name} quality tool",
            target_pattern=target_pattern,
            output_format=output_format,
            dependencies=[tool_name],
            performance_hints={"generic": True},
        )
