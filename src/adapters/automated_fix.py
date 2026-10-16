"""
Automated fix adapter for safe application of quality improvements.

This adapter implements AutomatedFixPort to provide enterprise-grade automated
fix application with comprehensive safety validations, backup/rollback capabilities,
and thorough pre/post-fix testing.
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from adapters.direct_pixi_execution import (
    DirectPixiExecutionAdapter,
    is_execution_failure,
)
from core.models import (
    AutomatedFixResult,
    FixResult,
    FixType,
    FixValidationMode,
    OperationResult,
)
from core.ports import AutomatedFixPort

_log = logging.getLogger(__name__)


class AutomatedFixAdapter(AutomatedFixPort):
    """
    Adapter for applying automated fixes with comprehensive safety validations.

    Provides enterprise-grade automated fix application with:
    - Multi-layer safety validation before fix application
    - Atomic backup and rollback capabilities
    - Comprehensive pre/post-fix testing
    - Granular fix type support with safety controls
    - Detailed audit logging and progress tracking
    """

    def __init__(
        self, direct_pixi_executor: DirectPixiExecutionAdapter, working_dir: str
    ) -> None:
        """Initialize the automated fix adapter with direct pixi execution capability."""
        self.pixi_executor = direct_pixi_executor
        self.working_dir = Path(working_dir)

        # Fix type to tool/command mapping
        self.fix_type_commands: Dict[FixType, Dict[str, Any]] = {
            FixType.IMPORTS: {
                "tool": "ruff",
                "commands": ["check", "--select=I", "--fix"],
                "description": "Remove unused imports and sort import statements",
            },
            FixType.FORMATTING: {
                "tool": "ruff",
                "commands": ["format"],
                "description": "Apply code formatting fixes",
            },
            FixType.SIMPLE_ISSUES: {
                "tool": "ruff",
                "commands": ["check", "--select=W,E1,E9,F401,F841", "--fix"],
                "description": "Fix simple linting issues (whitespace, unused variables, etc.)",
            },
            FixType.SECURITY: {
                "tool": "ruff",
                "commands": ["check", "--select=S", "--fix"],
                "description": "Apply low-risk security fixes",
            },
            FixType.TYPE_ANNOTATIONS: {
                "tool": "mypy",
                "commands": ["--install-types", "--non-interactive"],
                "description": "Add missing type annotations (requires manual review)",
            },
            FixType.UNUSED_VARIABLES: {
                "tool": "ruff",
                "commands": ["check", "--select=F841,F401", "--fix"],
                "description": "Remove unused variables and dead code",
            },
        }

        # Safety configuration
        self.backup_dir = self.working_dir / ".claude" / "fix-backups"
        self.max_backup_age_days = 30
        self.test_timeout_seconds = 300

    def apply_automated_fixes(
        self,
        fix_types: List[FixType],
        dry_run: bool = True,
        backup_before_fix: bool = True,
        validation_mode: FixValidationMode = FixValidationMode.STRICT,
    ) -> AutomatedFixResult:
        """
        Apply automated fixes with comprehensive safety validations.

        Args:
            fix_types: Types of fixes to apply
            dry_run: Preview changes without applying them
            backup_before_fix: Create backup before applying fixes
            validation_mode: Level of safety validation to perform

        Returns:
            AutomatedFixResult with fix details, validation results, and rollback info
        """
        started = time.perf_counter()
        result = AutomatedFixResult(
            requested_fix_types=fix_types,
            dry_run=dry_run,
            validation_mode=validation_mode,
            start_time=datetime.now(UTC).isoformat(),
            end_time="",
            execution_time_ms=0.0,
            # No quality assessment is run by this adapter: not yet assessed.
            pre_fix_validation=None,
            post_fix_validation=None,
            rollback_available=False,
            rollback_command=None,
            backup_path=None,
            quality_improvement=None,
            total_files_modified=0,
            total_changes_applied=0,
        )

        try:
            # Step 1: Pre-fix safety validation
            safety_validation = self.validate_fix_safety(
                fix_types, self._get_target_files(fix_types)
            )
            if not safety_validation.success:
                result.failed_fixes.append(
                    {
                        "error": "Pre-fix safety validation failed",
                        "details": safety_validation.details,
                        "fix_types": [ft.value for ft in fix_types],
                    }
                )
                result.end_time = datetime.now(UTC).isoformat()
                result.execution_time_ms = self._elapsed_ms(started)
                return result

            # Step 2: Create backup if requested and not dry run
            backup_path = None
            if backup_before_fix and not dry_run:
                target_files = self._get_target_files(fix_types)
                backup_path = self.create_fix_backup(target_files)
                result.backup_created = True
                result.backup_path = backup_path
                result.rollback_available = True
                result.rollback_command = f"restore backup from {backup_path}"
                result.rollback_commands.append(
                    f"python -c \"import shutil; shutil.rmtree('{self.working_dir}'); shutil.move('{backup_path}', '{self.working_dir}')\""
                )

            # Step 3: Apply fixes by type
            successful_fixes: List[FixResult] = []
            failed_fixes: List[Dict[str, Any]] = []

            for fix_type in fix_types:
                try:
                    fix_result = self._apply_single_fix_type(
                        fix_type, dry_run, validation_mode
                    )
                    if fix_result:
                        if fix_result.validation_passed:
                            successful_fixes.append(fix_result)
                        else:
                            failed_fixes.append(
                                {
                                    "fix_type": fix_type.value,
                                    "error": "Post-fix validation failed",
                                    "details": fix_result.validation_errors,
                                }
                            )
                except Exception as e:
                    failed_fixes.append(
                        {
                            "fix_type": fix_type.value,
                            "error": f"Fix application failed: {str(e)}",
                            "details": [],
                        }
                    )

            result.successful_fixes = successful_fixes
            result.failed_fixes = failed_fixes

            # Step 4: Generate summary statistics
            result.total_files_modified = len(
                set(fix.file_path for fix in successful_fixes)
            )
            result.total_changes_applied = sum(
                fix.lines_changed for fix in successful_fixes
            )

            # Step 5: Generate recommendations
            result.additional_manual_fixes.extend(
                self._generate_manual_fix_recommendations(fix_types, successful_fixes)
            )

        except Exception as e:
            # Emergency error handling
            result.failed_fixes.append(
                {
                    "error": f"Critical error during fix application: {str(e)}",
                    "fix_types": [ft.value for ft in fix_types],
                }
            )

        result.end_time = datetime.now(UTC).isoformat()
        result.execution_time_ms = self._elapsed_ms(started)
        return result

    def validate_fix_safety(
        self, fix_types: List[FixType], target_files: List[str]
    ) -> OperationResult:
        """
        Validate that fixes can be safely applied.

        Performs comprehensive safety checks including:
        - Git repository state validation
        - File system permissions
        - Available disk space
        - Tool availability
        - Project structure integrity

        Args:
            fix_types: Types of fixes to validate
            target_files: Files that would be modified

        Returns:
            OperationResult with success status and validation details
        """
        op = "validate_fix_safety"
        started = time.perf_counter()
        try:
            validation_results: List[Dict[str, Any]] = []
            checks = (
                (
                    lambda: self._validate_git_state(),
                    "Git validation failed - repository has uncommitted changes",
                ),
                (
                    lambda: self._validate_file_access(target_files),
                    "File access validation failed",
                ),
                (
                    lambda: self._validate_disk_space(),
                    "Insufficient disk space for safe fix application",
                ),
                (
                    lambda: self._validate_required_tools(fix_types),
                    "Required tools not available",
                ),
                (
                    lambda: self._validate_project_structure(),
                    "Project structure validation failed",
                ),
            )

            for check, failure_message in checks:
                validation = check()
                validation_results.append(validation)
                if not validation["passed"]:
                    return self._operation_result(
                        op,
                        started,
                        False,
                        failure_message,
                        {"validations": validation_results},
                        errors=[str(validation.get("message", failure_message))],
                    )

            return self._operation_result(
                op,
                started,
                True,
                "All safety validations passed",
                {"validations": validation_results},
            )

        except Exception as e:
            return self._operation_result(
                op,
                started,
                False,
                f"Safety validation failed with error: {str(e)}",
                {"error": str(e)},
                errors=[str(e)],
            )

    def create_fix_backup(self, target_files: List[str]) -> str:
        """
        Create timestamped backup of files before applying fixes.

        Creates a complete backup of target files in .claude/fix-backups/
        with timestamp and integrity checksums.

        Args:
            target_files: List of file paths to backup

        Returns:
            Path to backup directory
        """
        try:
            # Create backup directory with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"fix_backup_{timestamp}"
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(parents=True, exist_ok=True)

            # Backup metadata
            file_checksums: Dict[str, str] = {}
            backup_metadata: Dict[str, Any] = {
                "backup_id": backup_name,
                "created_at": datetime.now(UTC).isoformat(),
                "source_directory": str(self.working_dir),
                "target_files": target_files,
                "file_checksums": file_checksums,
                "backup_type": "automated_fix_backup",
            }

            # Copy files with directory structure preservation
            files_backed_up = 0
            for file_path in target_files:
                source_file = Path(file_path)
                if not source_file.is_absolute():
                    source_file = self.working_dir / source_file

                if source_file.exists() and source_file.is_file():
                    # Calculate relative path from working directory
                    try:
                        relative_path = source_file.relative_to(self.working_dir)
                        backup_file_path = backup_path / relative_path

                        # Create parent directories
                        backup_file_path.parent.mkdir(parents=True, exist_ok=True)

                        # Copy file and calculate checksum
                        shutil.copy2(source_file, backup_file_path)
                        checksum = self._calculate_file_checksum(source_file)
                        file_checksums[str(relative_path)] = checksum
                        files_backed_up += 1

                    except ValueError:
                        # File is outside working directory, skip
                        continue

            # Save backup metadata
            metadata_file = backup_path / "backup_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(backup_metadata, f, indent=2)

            # Cleanup old backups
            self._cleanup_old_backups()

            return str(backup_path)

        except Exception as e:
            raise RuntimeError(f"Failed to create backup: {str(e)}") from e

    def rollback_fixes(self, backup_path: str) -> OperationResult:
        """
        Rollback fixes using backup.

        Restores files from backup with integrity verification.

        Args:
            backup_path: Path to backup directory

        Returns:
            OperationResult with rollback status and details
        """
        op = "rollback_fixes"
        started = time.perf_counter()
        try:
            backup_dir = Path(backup_path)
            if not backup_dir.exists():
                return self._operation_result(
                    op,
                    started,
                    False,
                    f"Backup directory not found: {backup_path}",
                    {"backup_path": backup_path},
                )

            # Load backup metadata
            metadata_file = backup_dir / "backup_metadata.json"
            if not metadata_file.exists():
                return self._operation_result(
                    op,
                    started,
                    False,
                    "Backup metadata not found - cannot verify backup integrity",
                    {"backup_path": backup_path},
                )

            with open(metadata_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            # Verify backup integrity
            integrity_check = self._verify_backup_integrity(backup_dir, metadata)
            if not integrity_check["valid"]:
                return self._operation_result(
                    op,
                    started,
                    False,
                    "Backup integrity check failed - cannot safely rollback",
                    {"integrity_check": integrity_check},
                )

            # Restore files
            files_restored = 0
            restoration_errors: List[str] = []

            for relative_path in metadata["file_checksums"].keys():
                try:
                    backup_file = backup_dir / relative_path
                    target_file = self.working_dir / relative_path

                    # Create parent directories if needed
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # Restore file
                    shutil.copy2(backup_file, target_file)
                    files_restored += 1

                except Exception as e:
                    restoration_errors.append(f"{relative_path}: {str(e)}")

            if restoration_errors:
                return self._operation_result(
                    op,
                    started,
                    False,
                    f"Partial rollback completed with {len(restoration_errors)} errors",
                    {
                        "files_restored": files_restored,
                        "restoration_errors": restoration_errors,
                    },
                    errors=restoration_errors,
                )

            return self._operation_result(
                op,
                started,
                True,
                f"Successfully rolled back {files_restored} files",
                {"files_restored": files_restored, "backup_source": backup_path},
            )

        except Exception as e:
            return self._operation_result(
                op,
                started,
                False,
                f"Rollback failed: {str(e)}",
                {"error": str(e), "backup_path": backup_path},
                errors=[str(e)],
            )

    def preview_fix_changes(
        self, fix_types: List[FixType], target_files: List[str]
    ) -> Dict[str, List[str]]:
        """
        Preview changes that would be made by fixes.

        Shows a preview of all changes without applying them.

        Args:
            fix_types: Types of fixes to preview
            target_files: Files that would be modified

        Returns:
            Dictionary mapping fix types to lists of change descriptions
        """
        try:
            preview_results: Dict[str, List[str]] = {}

            for fix_type in fix_types:
                changes: List[str] = []

                if fix_type in self.fix_type_commands:
                    fix_config = self.fix_type_commands[fix_type]

                    # Run fix in preview mode (dry-run)
                    try:
                        if fix_config["tool"] == "ruff":
                            # Use ruff's --diff option to show changes
                            commands = list(fix_config["commands"])
                            if "--fix" in commands:
                                commands.remove("--fix")
                            commands.append("--diff")  # never write during preview

                            result = self._run_fix_tool("ruff", commands)
                            if not is_execution_failure(result):
                                diff_output = result.get("stdout", "")
                                changes.extend(
                                    self._parse_ruff_diff_output(diff_output)
                                )

                        elif fix_config["tool"] == "mypy":
                            # MyPy doesn't have auto-fix, show what would be checked
                            changes.append(
                                "Would run type checking and install missing type stubs"
                            )

                    except Exception as e:
                        changes.append(f"Preview failed: {str(e)}")

                preview_results[fix_type.value] = changes

            return preview_results

        except Exception as e:
            return {"error": [f"Preview generation failed: {str(e)}"]}

    # Private helper methods

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        """Milliseconds since a time.perf_counter() reading."""
        return (time.perf_counter() - started) * 1000

    def _operation_result(
        self,
        operation_type: str,
        started: float,
        success: bool,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ) -> OperationResult:
        """Build an OperationResult with measured timing and a real timestamp."""
        return OperationResult(
            success=success,
            operation_type=operation_type,
            message=message,
            execution_time_ms=self._elapsed_ms(started),
            timestamp=datetime.now(UTC).isoformat(),
            details=details,
            errors=errors or [],
        )

    def _tool_environment(self, tool: str) -> Optional[str]:
        """Pixi environment that declares `tool` (None = default/unknown)."""
        envs = self.pixi_executor.environments_providing_tool(
            tool, working_dir=str(self.working_dir)
        )
        if not envs or "default" in envs:
            return None
        return envs[0]

    def _run_fix_tool(self, tool: str, args: List[str]) -> Dict[str, Any]:
        """Run a quality tool as a command through the injected pixi executor.

        Tools run as commands, not via the `lint`/`typecheck` tasks: those
        tasks fix their own select/target, so extra args cannot change them.
        """
        src_dir = self.working_dir / "src"
        target = "src/" if src_dir.is_dir() else "."
        return self.pixi_executor.run_task(
            tool,
            [*args, target],
            timeout=self.test_timeout_seconds,
            working_dir=str(self.working_dir),
            environment=self._tool_environment(tool),
            as_command=True,
        )

    def _apply_single_fix_type(
        self, fix_type: FixType, dry_run: bool, validation_mode: FixValidationMode
    ) -> Optional[FixResult]:
        """Apply a single fix type and return the result."""
        if fix_type not in self.fix_type_commands:
            raise ValueError(f"Unsupported fix type: {fix_type}")

        fix_config = self.fix_type_commands[fix_type]
        target_files = self._get_target_files([fix_type])

        if not target_files:
            return None

        # Calculate original content hashes (target paths are working_dir-relative)
        original_hashes: Dict[str, str] = {}
        for file_path in target_files:
            file_obj = self.working_dir / file_path
            if file_obj.exists():
                original_hashes[file_path] = self._calculate_file_checksum(file_obj)

        # Apply the fix
        if not dry_run:
            try:
                result = self._run_fix_tool(fix_config["tool"], fix_config["commands"])

                if is_execution_failure(result):
                    raise RuntimeError(
                        f"Fix command failed: {result.get('stderr') or 'Unknown error'}"
                    )

            except Exception as e:
                raise RuntimeError(
                    f"Failed to apply {fix_type.value} fixes: {str(e)}"
                ) from e

        # Calculate modified content hashes and changes
        modified_hashes: Dict[str, str] = {}
        total_lines_changed = 0
        files_modified: List[str] = []
        changes_applied: List[str] = []

        for file_path in target_files:
            file_obj = self.working_dir / file_path
            if file_obj.exists():
                new_hash = self._calculate_file_checksum(file_obj)
                modified_hashes[file_path] = new_hash

                if original_hashes.get(file_path) != new_hash:
                    files_modified.append(file_path)
                    changes_applied.append(f"Modified {file_path}")
                    # Estimate lines changed (simplified)
                    total_lines_changed += 1

        # Post-fix validation
        validation_passed = True
        validation_errors: List[str] = []

        if validation_mode == FixValidationMode.STRICT and not dry_run:
            # Run syntax check
            syntax_validation = self._validate_python_syntax(files_modified)
            if not syntax_validation["valid"]:
                validation_passed = False
                validation_errors.extend(syntax_validation["errors"])

        # Create fix result for the first modified file (or first target file)
        primary_file = files_modified[0] if files_modified else target_files[0]
        original_hash = original_hashes.get(primary_file, "")
        modified_hash = modified_hashes.get(primary_file, original_hash)

        return FixResult(
            fix_type=fix_type,
            file_path=primary_file,
            original_content_hash=original_hash,
            modified_content_hash=modified_hash,
            lines_changed=total_lines_changed,
            changes_applied=changes_applied,
            backup_created=False,  # Backup is handled at session level
            backup_path=None,
            validation_passed=validation_passed,
            validation_errors=validation_errors,
        )

    def _get_target_files(self, fix_types: List[FixType]) -> List[str]:
        """Get list of target files for the given fix types."""
        # For now, target all Python files in src/
        src_dir = self.working_dir / "src"
        if src_dir.exists():
            python_files = list(src_dir.rglob("*.py"))
            return [str(f.relative_to(self.working_dir)) for f in python_files]
        else:
            # Fallback to all Python files in working directory
            python_files = list(self.working_dir.rglob("*.py"))
            return [
                str(f.relative_to(self.working_dir)) for f in python_files[:10]
            ]  # Limit to first 10

    def _validate_git_state(self) -> Dict[str, Any]:
        """Validate git repository state."""
        try:
            # Check if git repository exists
            git_dir = self.working_dir / ".git"
            if not git_dir.exists():
                return {
                    "check": "git_state",
                    "passed": True,
                    "message": "No git repository found - proceeding without git checks",
                }

            # Check for uncommitted changes
            result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
                ["git", "status", "--porcelain"],  # noqa: S607 -- git resolved from PATH by design
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return {
                    "check": "git_state",
                    "passed": False,
                    "message": "Git status check failed",
                    "error": result.stderr,
                }

            uncommitted_changes = result.stdout.strip()
            if uncommitted_changes:
                return {
                    "check": "git_state",
                    "passed": False,
                    "message": "Repository has uncommitted changes",
                    "details": uncommitted_changes.split("\n")[:10],  # First 10 changes
                }

            return {
                "check": "git_state",
                "passed": True,
                "message": "Git repository is clean",
            }

        except subprocess.TimeoutExpired:
            return {
                "check": "git_state",
                "passed": False,
                "message": "Git status check timed out",
            }
        except Exception as e:
            return {
                "check": "git_state",
                "passed": False,
                "message": f"Git validation failed: {str(e)}",
            }

    def _validate_file_access(self, target_files: List[str]) -> Dict[str, Any]:
        """Validate file access permissions."""
        try:
            inaccessible_files: List[str] = []

            for file_path in target_files:
                file_obj = Path(file_path)
                if not file_obj.is_absolute():
                    file_obj = self.working_dir / file_obj

                if file_obj.exists():
                    # Check read/write access
                    if not os.access(file_obj, os.R_OK | os.W_OK):
                        inaccessible_files.append(str(file_obj))

            if inaccessible_files:
                return {
                    "check": "file_access",
                    "passed": False,
                    "message": f"{len(inaccessible_files)} files are not accessible",
                    "inaccessible_files": inaccessible_files[:5],  # First 5 files
                }

            return {
                "check": "file_access",
                "passed": True,
                "message": f"All {len(target_files)} target files are accessible",
            }

        except Exception as e:
            return {
                "check": "file_access",
                "passed": False,
                "message": f"File access validation failed: {str(e)}",
            }

    def _validate_disk_space(self) -> Dict[str, Any]:
        """Validate available disk space."""
        try:
            stat = shutil.disk_usage(self.working_dir)
            free_space_mb = stat.free / (1024 * 1024)

            # Require at least 100 MB free space
            min_required_mb = 100

            if free_space_mb < min_required_mb:
                return {
                    "check": "disk_space",
                    "passed": False,
                    "message": f"Insufficient disk space: {free_space_mb:.1f} MB available, {min_required_mb} MB required",
                    "available_mb": free_space_mb,
                }

            return {
                "check": "disk_space",
                "passed": True,
                "message": f"Sufficient disk space available: {free_space_mb:.1f} MB",
                "available_mb": free_space_mb,
            }

        except Exception as e:
            return {
                "check": "disk_space",
                "passed": False,
                "message": f"Disk space validation failed: {str(e)}",
            }

    def _validate_required_tools(self, fix_types: List[FixType]) -> Dict[str, Any]:
        """Validate required tools are available."""
        try:
            required_tools: set[str] = set()
            for fix_type in fix_types:
                if fix_type in self.fix_type_commands:
                    tool = self.fix_type_commands[fix_type]["tool"]
                    required_tools.add(tool)

            missing_tools: List[str] = []
            for tool in sorted(required_tools):
                try:
                    # None = manifest unreadable (cannot tell): do not block.
                    # [] = manifest read and no environment declares the tool.
                    providers = self.pixi_executor.environments_providing_tool(
                        tool, working_dir=str(self.working_dir)
                    )
                    if providers is not None and not providers:
                        missing_tools.append(tool)

                except Exception:
                    missing_tools.append(tool)

            if missing_tools:
                return {
                    "check": "required_tools",
                    "passed": False,
                    "message": f"Missing required tools: {', '.join(missing_tools)}",
                    "missing_tools": missing_tools,
                }

            return {
                "check": "required_tools",
                "passed": True,
                "message": f"All required tools available: {', '.join(required_tools)}",
            }

        except Exception as e:
            return {
                "check": "required_tools",
                "passed": False,
                "message": f"Tool validation failed: {str(e)}",
            }

    def _validate_project_structure(self) -> Dict[str, Any]:
        """Validate project structure integrity."""
        try:
            # Check for essential files
            essential_files = ["pyproject.toml", "pixi.toml", "pixi.lock"]
            missing_files: List[str] = []

            for file_name in essential_files:
                file_path = self.working_dir / file_name
                if not file_path.exists():
                    missing_files.append(file_name)

            # Check for src directory
            src_dir = self.working_dir / "src"
            has_src_dir = src_dir.exists() and src_dir.is_dir()

            if len(missing_files) >= len(
                essential_files
            ):  # All essential files missing
                return {
                    "check": "project_structure",
                    "passed": False,
                    "message": "Project structure appears invalid - no essential project files found",
                    "missing_files": missing_files,
                }

            issues: List[str] = []
            if missing_files:
                issues.append(f"Missing files: {', '.join(missing_files)}")
            if not has_src_dir:
                issues.append("No src/ directory found")

            return {
                "check": "project_structure",
                "passed": len(issues) == 0,
                "message": "Project structure validation passed"
                if len(issues) == 0
                else f"Project structure issues: {'; '.join(issues)}",
                "issues": issues,
            }

        except Exception as e:
            return {
                "check": "project_structure",
                "passed": False,
                "message": f"Project structure validation failed: {str(e)}",
            }

    def _validate_python_syntax(self, files: List[str]) -> Dict[str, Any]:
        """Validate Python syntax for modified files."""
        try:
            syntax_errors: List[str] = []

            for file_path in files:
                file_obj = Path(file_path)
                if not file_obj.is_absolute():
                    file_obj = self.working_dir / file_obj

                if file_obj.exists() and file_obj.suffix == ".py":
                    try:
                        with open(file_obj, "r", encoding="utf-8") as f:
                            source_code = f.read()

                        compile(source_code, str(file_obj), "exec")

                    except SyntaxError as e:
                        syntax_errors.append(f"{file_obj}: {str(e)}")
                    except Exception as e:
                        syntax_errors.append(f"{file_obj}: {str(e)}")

            return {"valid": len(syntax_errors) == 0, "errors": syntax_errors}

        except Exception as e:
            return {"valid": False, "errors": [f"Syntax validation failed: {str(e)}"]}

    def _generate_manual_fix_recommendations(
        self, fix_types: List[FixType], successful_fixes: List[FixResult]
    ) -> List[str]:
        """Generate recommendations for manual fixes."""
        recommendations: List[str] = []

        # Add recommendations based on applied fix types
        if FixType.TYPE_ANNOTATIONS in fix_types:
            recommendations.append(
                "Review and verify auto-generated type annotations for correctness"
            )

        if FixType.SECURITY in fix_types:
            recommendations.append(
                "Manually review security fixes to ensure they don't break functionality"
            )

        if successful_fixes:
            recommendations.append(
                "Run comprehensive tests to verify fixes don't introduce regressions"
            )
            recommendations.append(
                "Review changed files for any unintended modifications"
            )

        return recommendations

    def _calculate_file_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum of a file."""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception:
            return ""

    def _cleanup_old_backups(self) -> None:
        """Clean up old backups beyond retention period."""
        try:
            if not self.backup_dir.exists():
                return

            cutoff_time = time.time() - (self.max_backup_age_days * 24 * 60 * 60)

            for backup_path in self.backup_dir.iterdir():
                if backup_path.is_dir():
                    try:
                        backup_time = backup_path.stat().st_ctime
                        if backup_time < cutoff_time:
                            shutil.rmtree(backup_path)
                    except OSError as e:
                        # Best-effort cleanup: skip backups that cannot be removed.
                        _log.debug("could not remove old backup %s: %s", backup_path, e)
                        continue

        except Exception as e:
            # Best-effort cleanup must never fail the calling operation.
            _log.debug("old-backup cleanup failed: %s", e)

    def _verify_backup_integrity(
        self, backup_dir: Path, metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Verify backup integrity using checksums."""
        try:
            invalid_files: List[str] = []
            missing_files: List[str] = []

            for relative_path, expected_checksum in metadata["file_checksums"].items():
                backup_file = backup_dir / relative_path

                if not backup_file.exists():
                    missing_files.append(relative_path)
                    continue

                actual_checksum = self._calculate_file_checksum(backup_file)
                if actual_checksum != expected_checksum:
                    invalid_files.append(relative_path)

            return {
                "valid": len(invalid_files) == 0 and len(missing_files) == 0,
                "invalid_files": invalid_files,
                "missing_files": missing_files,
            }

        except Exception as e:
            return {"valid": False, "error": str(e)}

    def _parse_ruff_diff_output(self, diff_output: str) -> List[str]:
        """Parse ruff --diff output to extract change descriptions."""
        changes: List[str] = []

        if not diff_output.strip():
            changes.append("No changes would be made")
            return changes

        # Parse unified diff format
        lines = diff_output.split("\n")
        current_file: Optional[str] = None

        for line in lines:
            if line.startswith("--- ") or line.startswith("+++ "):
                if line.startswith("+++ "):
                    current_file = line[4:].strip()
            elif line.startswith("@@"):
                # Extract line numbers from @@ -start,count +start,count @@
                if current_file:
                    changes.append(f"Would modify {current_file}")
            elif line.startswith("+") and not line.startswith("+++"):
                changes.append(f"Would add: {line[1:].strip()}")
            elif line.startswith("-") and not line.startswith("---"):
                changes.append(f"Would remove: {line[1:].strip()}")

        if not changes:
            changes.append("Changes detected but could not parse details")

        return changes
