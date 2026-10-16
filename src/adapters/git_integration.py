"""
Git integration adapter for automatic git metadata detection and project information.

This adapter provides git repository information for quality baselines including
commit hashes, branch names, repository status, and other git-related metadata
with graceful handling of non-git projects.
"""

import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

from core.ports import LoggingPort


class GitIntegrationAdapter:
    """
    Git integration adapter for automatic metadata detection.

    Provides comprehensive git information for quality baselines:
    - Current commit hash and branch detection
    - Repository status and clean state validation
    - Remote repository information
    - Git configuration and user information
    - Graceful handling of non-git projects
    """

    def __init__(
        self, working_dir: Optional[str] = None, logging: Optional[LoggingPort] = None
    ):
        """
        Initialize git integration adapter.

        Args:
            working_dir: Working directory for git operations (defaults to current)
            logging: Optional logging port for operation logging
        """
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.logging = logging

        # Cache git information for performance
        self._git_cache = {}
        self._cache_timeout = 30  # seconds
        self._last_cache_time = 0

    def get_git_metadata(self) -> Dict[str, Any]:
        """
        Get comprehensive git metadata for current project.

        Returns:
            Dictionary with git information including commit, branch, status, remotes
        """
        try:
            # Check cache first
            current_time = time.time()
            if (
                current_time - self._last_cache_time
            ) < self._cache_timeout and self._git_cache:
                if self.logging:
                    self.logging.log_info("Using cached git metadata")
                return self._git_cache.copy()

            # Check if we're in a git repository
            if not self._is_git_repository():
                metadata = {
                    "is_git_repo": False,
                    "git_available": self._is_git_available(),
                    "working_directory": str(self.working_dir),
                    "detection_timestamp": datetime.now(UTC).isoformat(),
                    "error": "Not a git repository",
                }

                if self.logging:
                    self.logging.log_info(
                        "No git repository detected",
                        {"working_dir": str(self.working_dir)},
                    )

                return metadata

            # Gather git information
            metadata = {
                "is_git_repo": True,
                "git_available": True,
                "working_directory": str(self.working_dir),
                "detection_timestamp": datetime.now(UTC).isoformat(),
            }

            # Get current commit information
            commit_info = self._get_commit_info()
            metadata.update(commit_info)

            # Get branch information
            branch_info = self._get_branch_info()
            metadata.update(branch_info)

            # Get repository status
            status_info = self._get_status_info()
            metadata.update(status_info)

            # Get remote information
            remote_info = self._get_remote_info()
            metadata.update(remote_info)

            # Get git configuration
            config_info = self._get_config_info()
            metadata.update(config_info)

            # Cache the results
            self._git_cache = metadata.copy()
            self._last_cache_time = current_time

            if self.logging:
                self.logging.log_info(
                    "Git metadata collected successfully",
                    {
                        "commit": metadata.get("commit_hash", "unknown")[:8],
                        "branch": metadata.get("current_branch", "unknown"),
                        "clean": metadata.get("is_clean", False),
                    },
                )

            return metadata

        except Exception as e:
            error_metadata = {
                "is_git_repo": False,
                "git_available": self._is_git_available(),
                "working_directory": str(self.working_dir),
                "detection_timestamp": datetime.now(UTC).isoformat(),
                "error": f"Git metadata collection failed: {str(e)}",
            }

            if self.logging:
                self.logging.log_error(
                    f"get_git_metadata failed: {e}",
                    {
                        "operation": "get_git_metadata",
                        "working_dir": str(self.working_dir),
                    },
                )

            return error_metadata

    def get_current_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            if not self._is_git_repository():
                return None

            result = self._run_git_command(["rev-parse", "HEAD"])
            if result and result.strip():
                return result.strip()

            return None

        except Exception:
            return None

    def get_current_branch(self) -> Optional[str]:
        """Get current git branch name."""
        try:
            if not self._is_git_repository():
                return None

            # Try to get branch name
            result = self._run_git_command(["branch", "--show-current"])
            if result and result.strip():
                return result.strip()

            # Fallback: try symbolic-ref
            result = self._run_git_command(["symbolic-ref", "--short", "HEAD"])
            if result and result.strip():
                return result.strip()

            # Fallback: check if we're in detached HEAD
            result = self._run_git_command(["rev-parse", "--abbrev-ref", "HEAD"])
            if result and result.strip() == "HEAD":
                return "HEAD (detached)"

            return result.strip() if result else None

        except Exception:
            return None

    def is_repository_clean(self) -> bool:
        """Check if git repository has uncommitted changes."""
        try:
            if not self._is_git_repository():
                return True  # Non-git projects are considered "clean"

            # Check for staged changes
            result = self._run_git_command(["diff", "--cached", "--quiet"])
            if result is None:  # Command failed (has staged changes)
                return False

            # Check for unstaged changes
            result = self._run_git_command(["diff", "--quiet"])
            if result is None:  # Command failed (has unstaged changes)
                return False

            # Check for untracked files
            result = self._run_git_command(
                ["ls-files", "--others", "--exclude-standard"]
            )
            if result and result.strip():
                return False

            return True

        except Exception:
            return True  # Default to clean if we can't determine

    def get_repository_url(self) -> Optional[str]:
        """Get remote repository URL."""
        try:
            if not self._is_git_repository():
                return None

            # Try to get origin URL
            result = self._run_git_command(["remote", "get-url", "origin"])
            if result and result.strip():
                return result.strip()

            # Try to get any remote URL
            result = self._run_git_command(["remote", "-v"])
            if result and result.strip():
                lines = result.strip().split("\n")
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]

            return None

        except Exception:
            return None

    def validate_git_state_for_baseline(self) -> Dict[str, Any]:
        """
        Validate git state is suitable for creating a quality baseline.

        Returns:
            Validation result with recommendations
        """
        try:
            validation = {
                "is_valid": True,
                "warnings": [],
                "recommendations": [],
                "git_metadata": self.get_git_metadata(),
                "validation_timestamp": datetime.now(UTC).isoformat(),
            }

            if not validation["git_metadata"]["is_git_repo"]:
                validation["warnings"].append(
                    "Not a git repository - baseline will have limited traceability"
                )
                validation["recommendations"].append(
                    "Consider initializing git repository for better baseline tracking"
                )
                return validation

            # Check if repository is clean
            if not validation["git_metadata"].get("is_clean", False):
                validation["warnings"].append("Repository has uncommitted changes")
                validation["recommendations"].append(
                    "Consider committing changes before establishing baseline"
                )

            # Check if we have a valid commit
            if not validation["git_metadata"].get("commit_hash"):
                validation["is_valid"] = False
                validation["warnings"].append("No valid commit found")
                validation["recommendations"].append(
                    "Make at least one commit before establishing baseline"
                )

            # Check if we're on a branch
            current_branch = validation["git_metadata"].get("current_branch")
            if not current_branch or current_branch.startswith("HEAD"):
                validation["warnings"].append("In detached HEAD state")
                validation["recommendations"].append(
                    "Consider checking out a branch for better baseline organization"
                )

            return validation

        except Exception as e:
            return {
                "is_valid": False,
                "warnings": [f"Git validation failed: {str(e)}"],
                "recommendations": ["Check git installation and repository status"],
                "git_metadata": {},
                "validation_timestamp": datetime.now(UTC).isoformat(),
            }

    # Private helper methods

    def _is_git_available(self) -> bool:
        """Check if git command is available."""
        try:
            result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
                ["git", "--version"],  # noqa: S607 -- git resolved from PATH by design
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self.working_dir,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _is_git_repository(self) -> bool:
        """Check if current directory is a git repository."""
        try:
            result = subprocess.run(  # noqa: S603 -- fixed argv, no shell
                ["git", "rev-parse", "--git-dir"],  # noqa: S607 -- git resolved from PATH by design
                capture_output=True,
                text=True,
                timeout=5,
                cwd=self.working_dir,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _run_git_command(self, args: list, timeout: int = 10) -> Optional[str]:
        """Run git command and return output."""
        try:
            result = subprocess.run(  # noqa: S603 -- private helper; all callers pass literal argv, no shell
                ["git"] + args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.working_dir,
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return None

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def _get_commit_info(self) -> Dict[str, Any]:
        """Get current commit information."""
        info = {}

        try:
            # Current commit hash
            commit_hash = self._run_git_command(["rev-parse", "HEAD"])
            if commit_hash:
                info["commit_hash"] = commit_hash.strip()
                info["commit_hash_short"] = commit_hash.strip()[:8]

            # Commit message
            commit_message = self._run_git_command(["log", "-1", "--pretty=format:%s"])
            if commit_message:
                info["commit_message"] = commit_message.strip()

            # Commit author
            commit_author = self._run_git_command(
                ["log", "-1", "--pretty=format:%an <%ae>"]
            )
            if commit_author:
                info["commit_author"] = commit_author.strip()

            # Commit date
            commit_date = self._run_git_command(["log", "-1", "--pretty=format:%ci"])
            if commit_date:
                info["commit_date"] = commit_date.strip()

            # Commit count
            commit_count = self._run_git_command(["rev-list", "--count", "HEAD"])
            if commit_count and commit_count.strip().isdigit():
                info["commit_count"] = int(commit_count.strip())

        except Exception as e:
            info["commit_info_error"] = str(e)

        return info

    def _get_branch_info(self) -> Dict[str, Any]:
        """Get branch information."""
        info = {}

        try:
            # Current branch
            current_branch = self.get_current_branch()
            if current_branch:
                info["current_branch"] = current_branch

            # All branches
            branches = self._run_git_command(["branch", "-a"])
            if branches:
                branch_list = [
                    b.strip().lstrip("*").strip()
                    for b in branches.split("\n")
                    if b.strip()
                ]
                info["all_branches"] = branch_list
                info["branch_count"] = len(branch_list)

            # Check if current branch has upstream
            upstream = self._run_git_command(
                ["rev-parse", "--abbrev-ref", "@{upstream}"]
            )
            if upstream and upstream.strip():
                info["upstream_branch"] = upstream.strip()

                # Check if branch is ahead/behind
                ahead_behind = self._run_git_command(
                    ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"]
                )
                if ahead_behind and ahead_behind.strip():
                    parts = ahead_behind.strip().split()
                    if len(parts) == 2:
                        info["commits_ahead"] = int(parts[0])
                        info["commits_behind"] = int(parts[1])

        except Exception as e:
            info["branch_info_error"] = str(e)

        return info

    def _get_status_info(self) -> Dict[str, Any]:
        """Get repository status information."""
        info = {}

        try:
            # Repository cleanliness
            info["is_clean"] = self.is_repository_clean()

            # Detailed status
            status = self._run_git_command(["status", "--porcelain"])
            if status:
                status_lines = [line for line in status.split("\n") if line.strip()]
                info["status_lines"] = status_lines
                info["has_changes"] = len(status_lines) > 0

                # Count different types of changes
                staged = [
                    line for line in status_lines if line[0] != " " and line[0] != "?"
                ]
                unstaged = [
                    line for line in status_lines if line[1] != " " and line[0] != "?"
                ]
                untracked = [line for line in status_lines if line.startswith("??")]

                info["staged_changes"] = len(staged)
                info["unstaged_changes"] = len(unstaged)
                info["untracked_files"] = len(untracked)
            else:
                info["has_changes"] = False
                info["staged_changes"] = 0
                info["unstaged_changes"] = 0
                info["untracked_files"] = 0

        except Exception as e:
            info["status_info_error"] = str(e)

        return info

    def _get_remote_info(self) -> Dict[str, Any]:
        """Get remote repository information."""
        info = {}

        try:
            # List remotes
            remotes = self._run_git_command(["remote", "-v"])
            if remotes:
                remote_lines = [line for line in remotes.split("\n") if line.strip()]
                remote_dict = {}

                for line in remote_lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        remote_name = parts[0]
                        remote_url = parts[1]
                        if remote_name not in remote_dict:
                            remote_dict[remote_name] = remote_url

                info["remotes"] = remote_dict
                info["has_remotes"] = len(remote_dict) > 0

                # Get origin URL specifically
                if "origin" in remote_dict:
                    info["origin_url"] = remote_dict["origin"]
            else:
                info["has_remotes"] = False

        except Exception as e:
            info["remote_info_error"] = str(e)

        return info

    def _get_config_info(self) -> Dict[str, Any]:
        """Get git configuration information."""
        info = {}

        try:
            # User name and email
            user_name = self._run_git_command(["config", "user.name"])
            if user_name:
                info["user_name"] = user_name.strip()

            user_email = self._run_git_command(["config", "user.email"])
            if user_email:
                info["user_email"] = user_email.strip()

            # Git version
            git_version = self._run_git_command(["--version"])
            if git_version:
                info["git_version"] = git_version.strip()

        except Exception as e:
            info["config_info_error"] = str(e)

        return info

    def clear_cache(self) -> None:
        """Clear git metadata cache."""
        self._git_cache.clear()
        self._last_cache_time = 0

        if self.logging:
            self.logging.log_info("Git metadata cache cleared")
