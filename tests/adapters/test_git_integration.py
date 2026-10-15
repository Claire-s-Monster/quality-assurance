"""
Unit tests for GitIntegrationAdapter.

Tests git metadata detection, repository validation, and graceful handling
of non-git projects with comprehensive mock scenarios.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from adapters.git_integration import GitIntegrationAdapter


class TestGitIntegrationAdapter:
    """Test suite for GitIntegrationAdapter."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_logging(self):
        """Create mock logging adapter."""
        logging = MagicMock()
        return logging

    @pytest.fixture
    def adapter(self, temp_dir, mock_logging):
        """Create GitIntegrationAdapter with temporary directory."""
        return GitIntegrationAdapter(working_dir=temp_dir, logging=mock_logging)

    def test_adapter_initialization(self, temp_dir, mock_logging):
        """Test adapter initialization."""
        adapter = GitIntegrationAdapter(working_dir=temp_dir, logging=mock_logging)

        assert adapter.working_dir == Path(temp_dir)
        assert adapter.logging == mock_logging
        assert adapter._cache_timeout == 30
        assert len(adapter._git_cache) == 0

    def test_adapter_default_initialization(self):
        """Test adapter initialization with defaults."""
        adapter = GitIntegrationAdapter()

        assert adapter.working_dir == Path.cwd()
        assert adapter.logging is None

    @patch("subprocess.run")
    def test_is_git_available_success(self, mock_run, adapter):
        """Test git availability detection when git is available."""
        mock_run.return_value = MagicMock(returncode=0)

        assert adapter._is_git_available() is True
        mock_run.assert_called_once_with(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=adapter.working_dir,
        )

    @patch("subprocess.run")
    def test_is_git_available_failure(self, mock_run, adapter):
        """Test git availability detection when git is not available."""
        mock_run.side_effect = FileNotFoundError()

        assert adapter._is_git_available() is False

    @patch("subprocess.run")
    def test_is_git_repository_success(self, mock_run, adapter):
        """Test git repository detection when in a git repo."""
        mock_run.return_value = MagicMock(returncode=0)

        assert adapter._is_git_repository() is True
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=adapter.working_dir,
        )

    @patch("subprocess.run")
    def test_is_git_repository_failure(self, mock_run, adapter):
        """Test git repository detection when not in a git repo."""
        mock_run.return_value = MagicMock(returncode=1)

        assert adapter._is_git_repository() is False

    @patch("subprocess.run")
    def test_get_current_commit_success(self, mock_run, adapter):
        """Test current commit hash retrieval."""
        # Mock git repository check
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=0, stdout="abc123def456789\n"),  # rev-parse HEAD
        ]

        commit_hash = adapter.get_current_commit()

        assert commit_hash == "abc123def456789"
        assert mock_run.call_count == 2

    @patch("subprocess.run")
    def test_get_current_commit_not_git_repo(self, mock_run, adapter):
        """Test current commit retrieval in non-git repository."""
        mock_run.return_value = MagicMock(returncode=1)  # Not a git repo

        commit_hash = adapter.get_current_commit()

        assert commit_hash is None

    @patch("subprocess.run")
    def test_get_current_branch_success(self, mock_run, adapter):
        """Test current branch name retrieval."""
        # Mock git repository check and branch command
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=0, stdout="main\n"),  # branch --show-current
        ]

        branch_name = adapter.get_current_branch()

        assert branch_name == "main"

    @patch("subprocess.run")
    def test_get_current_branch_detached_head(self, mock_run, adapter):
        """Test current branch retrieval in detached HEAD state."""
        # Mock git repository check and commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=0, stdout=""),  # branch --show-current (empty)
            MagicMock(returncode=0, stdout=""),  # symbolic-ref --short HEAD (empty)
            MagicMock(returncode=0, stdout="HEAD"),  # rev-parse --abbrev-ref HEAD
        ]

        branch_name = adapter.get_current_branch()

        assert branch_name == "HEAD (detached)"

    @patch("subprocess.run")
    def test_is_repository_clean_true(self, mock_run, adapter):
        """Test repository cleanliness check when repo is clean."""
        # Mock git repository check and status commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=0),  # diff --cached --quiet (no staged changes)
            MagicMock(returncode=0),  # diff --quiet (no unstaged changes)
            MagicMock(returncode=0, stdout=""),  # ls-files (no untracked files)
        ]

        is_clean = adapter.is_repository_clean()

        assert is_clean is True

    @patch("subprocess.run")
    def test_is_repository_clean_false_staged_changes(self, mock_run, adapter):
        """Test repository cleanliness check with staged changes."""
        # Mock git repository check and status commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=1),  # diff --cached --quiet (has staged changes)
        ]

        is_clean = adapter.is_repository_clean()

        assert is_clean is False

    @patch("subprocess.run")
    def test_is_repository_clean_false_untracked_files(self, mock_run, adapter):
        """Test repository cleanliness check with untracked files."""
        # Mock git repository check and status commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=0),  # diff --cached --quiet (no staged changes)
            MagicMock(returncode=0),  # diff --quiet (no unstaged changes)
            MagicMock(
                returncode=0, stdout="untracked.txt\n"
            ),  # ls-files (untracked files)
        ]

        is_clean = adapter.is_repository_clean()

        assert is_clean is False

    @patch("subprocess.run")
    def test_get_repository_url_success(self, mock_run, adapter):
        """Test repository URL retrieval."""
        # Mock git repository check and remote command
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(
                returncode=0, stdout="https://github.com/user/repo.git\n"
            ),  # remote get-url origin
        ]

        repo_url = adapter.get_repository_url()

        assert repo_url == "https://github.com/user/repo.git"

    @patch("subprocess.run")
    def test_get_repository_url_no_origin(self, mock_run, adapter):
        """Test repository URL retrieval when no origin exists."""
        # Mock git repository check and remote commands
        mock_run.side_effect = [
            MagicMock(returncode=0),  # is_git_repository check
            MagicMock(returncode=1, stdout=""),  # remote get-url origin (fails)
            MagicMock(
                returncode=0,
                stdout="upstream\thttps://github.com/upstream/repo.git (fetch)\n",
            ),  # remote -v
        ]

        repo_url = adapter.get_repository_url()

        assert repo_url == "https://github.com/upstream/repo.git"

    def test_get_git_metadata_non_git_repo(self, adapter):
        """Test git metadata collection for non-git repository."""
        with (
            patch.object(adapter, "_is_git_repository", return_value=False),
            patch.object(adapter, "_is_git_available", return_value=True),
        ):
            metadata = adapter.get_git_metadata()

            assert metadata["is_git_repo"] is False
            assert metadata["git_available"] is True
            assert "Not a git repository" in metadata["error"]
            assert "working_directory" in metadata
            assert "detection_timestamp" in metadata

    def test_get_git_metadata_git_not_available(self, adapter):
        """Test git metadata collection when git is not available."""
        with (
            patch.object(adapter, "_is_git_repository", return_value=False),
            patch.object(adapter, "_is_git_available", return_value=False),
        ):
            metadata = adapter.get_git_metadata()

            assert metadata["is_git_repo"] is False
            assert metadata["git_available"] is False

    def test_get_git_metadata_comprehensive(self, adapter):
        """Test comprehensive git metadata collection."""
        with (
            patch.object(adapter, "_is_git_repository", return_value=True),
            patch.object(adapter, "_get_commit_info") as mock_commit,
            patch.object(adapter, "_get_branch_info") as mock_branch,
            patch.object(adapter, "_get_status_info") as mock_status,
            patch.object(adapter, "_get_remote_info") as mock_remote,
            patch.object(adapter, "_get_config_info") as mock_config,
        ):
            # Set up mock return values
            mock_commit.return_value = {
                "commit_hash": "abc123def456",
                "commit_message": "Test commit",
            }
            mock_branch.return_value = {"current_branch": "main", "branch_count": 3}
            mock_status.return_value = {"is_clean": True, "has_changes": False}
            mock_remote.return_value = {
                "has_remotes": True,
                "origin_url": "https://github.com/user/repo.git",
            }
            mock_config.return_value = {
                "user_name": "Test User",
                "git_version": "git version 2.34.1",
            }

            metadata = adapter.get_git_metadata()

            assert metadata["is_git_repo"] is True
            assert metadata["commit_hash"] == "abc123def456"
            assert metadata["current_branch"] == "main"
            assert metadata["is_clean"] is True
            assert metadata["origin_url"] == "https://github.com/user/repo.git"
            assert metadata["user_name"] == "Test User"

    def test_get_git_metadata_caching(self, adapter):
        """Test git metadata caching functionality."""
        with (
            patch.object(adapter, "_is_git_repository", return_value=True),
            patch.object(adapter, "_get_commit_info") as mock_commit,
            patch.object(adapter, "_get_branch_info") as mock_branch,
            patch.object(adapter, "_get_status_info") as mock_status,
            patch.object(adapter, "_get_remote_info") as mock_remote,
            patch.object(adapter, "_get_config_info") as mock_config,
        ):
            # Set up mock return values
            mock_commit.return_value = {"commit_hash": "abc123"}
            mock_branch.return_value = {"current_branch": "main"}
            mock_status.return_value = {"is_clean": True}
            mock_remote.return_value = {"has_remotes": True}
            mock_config.return_value = {"user_name": "Test User"}

            # First call should populate cache
            metadata1 = adapter.get_git_metadata()

            # Second call within cache timeout should use cache
            metadata2 = adapter.get_git_metadata()

            assert metadata1 == metadata2

            # Verify mocks were only called once (for first call)
            mock_commit.assert_called_once()
            mock_branch.assert_called_once()
            mock_status.assert_called_once()
            mock_remote.assert_called_once()
            mock_config.assert_called_once()

    def test_validate_git_state_for_baseline_valid(self, adapter):
        """Test git state validation for baseline creation when state is valid."""
        mock_metadata = {
            "is_git_repo": True,
            "commit_hash": "abc123def456",
            "current_branch": "main",
            "is_clean": True,
        }

        with patch.object(adapter, "get_git_metadata", return_value=mock_metadata):
            validation = adapter.validate_git_state_for_baseline()

            assert validation["is_valid"] is True
            assert len(validation["warnings"]) == 0
            assert "git_metadata" in validation
            assert validation["git_metadata"]["is_git_repo"] is True

    def test_validate_git_state_for_baseline_not_git_repo(self, adapter):
        """Test git state validation when not in a git repository."""
        mock_metadata = {"is_git_repo": False, "git_available": True}

        with patch.object(adapter, "get_git_metadata", return_value=mock_metadata):
            validation = adapter.validate_git_state_for_baseline()

            assert validation["is_valid"] is True  # Still valid, just with warnings
            assert len(validation["warnings"]) > 0
            assert any(
                "Not a git repository" in warning for warning in validation["warnings"]
            )
            assert any(
                "Consider initializing git repository" in rec
                for rec in validation["recommendations"]
            )

    def test_validate_git_state_for_baseline_dirty_repo(self, adapter):
        """Test git state validation with uncommitted changes."""
        mock_metadata = {
            "is_git_repo": True,
            "commit_hash": "abc123def456",
            "current_branch": "main",
            "is_clean": False,
        }

        with patch.object(adapter, "get_git_metadata", return_value=mock_metadata):
            validation = adapter.validate_git_state_for_baseline()

            assert validation["is_valid"] is True
            assert any(
                "uncommitted changes" in warning for warning in validation["warnings"]
            )
            assert any(
                "committing changes" in rec for rec in validation["recommendations"]
            )

    def test_validate_git_state_for_baseline_no_commit(self, adapter):
        """Test git state validation with no valid commit."""
        mock_metadata = {
            "is_git_repo": True,
            "commit_hash": None,
            "current_branch": "main",
            "is_clean": True,
        }

        with patch.object(adapter, "get_git_metadata", return_value=mock_metadata):
            validation = adapter.validate_git_state_for_baseline()

            assert validation["is_valid"] is False
            assert any(
                "No valid commit" in warning for warning in validation["warnings"]
            )
            assert any(
                "Make at least one commit" in rec
                for rec in validation["recommendations"]
            )

    def test_validate_git_state_for_baseline_detached_head(self, adapter):
        """Test git state validation in detached HEAD state."""
        mock_metadata = {
            "is_git_repo": True,
            "commit_hash": "abc123def456",
            "current_branch": "HEAD (detached)",
            "is_clean": True,
        }

        with patch.object(adapter, "get_git_metadata", return_value=mock_metadata):
            validation = adapter.validate_git_state_for_baseline()

            assert validation["is_valid"] is True
            assert any("detached HEAD" in warning for warning in validation["warnings"])
            assert any(
                "checking out a branch" in rec for rec in validation["recommendations"]
            )

    def test_clear_cache(self, adapter):
        """Test cache clearing functionality."""
        # Populate cache first
        adapter._git_cache = {"test": "data"}
        adapter._last_cache_time = 12345

        adapter.clear_cache()

        assert len(adapter._git_cache) == 0
        assert adapter._last_cache_time == 0

    def test_private_helper_methods(self, adapter):
        """Test private helper method edge cases."""
        # Test _run_git_command with timeout
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(["git", "test"], 10)

            result = adapter._run_git_command(["test"])
            assert result is None

        # Test _run_git_command with success
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="success\n")

            result = adapter._run_git_command(["test"])
            assert result == "success\n"

        # Test _run_git_command with failure
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="error")

            result = adapter._run_git_command(["test"])
            assert result is None
