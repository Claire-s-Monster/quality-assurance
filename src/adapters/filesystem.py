"""
Filesystem adapter for agent ecosystem operations.
Handles secure file operations with validation and access control.
"""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading
import time
import json
import hashlib
from datetime import datetime

from core.ports import FileSystemPort
from core.models import Agent, FileMetadata, SecurityViolation


class FilesystemAdapter(FileSystemPort):
    """Secure filesystem operations for agent ecosystem management."""

    def __init__(self, allowed_roots: Optional[List[str]] = None):
        """Initialize filesystem adapter with security constraints."""
        self.allowed_roots = allowed_roots or [
            str(Path.home() / ".claude" / "agents"),
            "./claude/agents",
        ]
        self._file_locks: Dict[str, threading.RLock] = {}
        self._lock_manager = threading.RLock()

    def _validate_path(self, file_path: str) -> None:
        """Validate that path is within allowed directories."""
        abs_path = Path(file_path).resolve()

        allowed = False
        for root in self.allowed_roots:
            root_path = Path(root).resolve()
            try:
                abs_path.relative_to(root_path)
                allowed = True
                break
            except ValueError:
                continue

        if not allowed:
            raise SecurityViolation(
                f"Path {file_path} outside allowed roots: {self.allowed_roots}"
            )

        # Check for directory traversal attempts
        if (
            ".." in str(abs_path)
            or abs_path.parts
            and any("." in part for part in abs_path.parts[:-1])
        ):
            raise SecurityViolation(
                f"Directory traversal detected in path: {file_path}"
            )

    def _get_file_lock(self, file_path: str) -> threading.RLock:
        """Get or create file-specific lock."""
        with self._lock_manager:
            if file_path not in self._file_locks:
                self._file_locks[file_path] = threading.RLock()
            return self._file_locks[file_path]

    def read_file(self, file_path: str) -> str:
        """Read agent file with security validation."""
        self._validate_path(file_path)

        with self._get_file_lock(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Validate content size (max 10MB)
                if len(content) > 10 * 1024 * 1024:
                    raise SecurityViolation(
                        f"File {file_path} exceeds maximum size of 10MB"
                    )

                return content
            except FileNotFoundError:
                raise FileNotFoundError(f"Agent file not found: {file_path}")
            except PermissionError:
                raise SecurityViolation(f"Permission denied reading file: {file_path}")
            except UnicodeDecodeError:
                raise SecurityViolation(f"Invalid UTF-8 encoding in file: {file_path}")

    def file_exists(self, file_path: str) -> bool:
        """Check if file exists with security validation."""
        self._validate_path(file_path)

        try:
            return Path(file_path).exists()
        except (OSError, PermissionError):
            return False

    def write_file(
        self, file_path: str, content: str, create_backup: bool = True
    ) -> bool:
        """Write agent file with atomic operation and backup."""
        self._validate_path(file_path)

        # Validate content
        if len(content) > 10 * 1024 * 1024:
            raise SecurityViolation("Content exceeds maximum size of 10MB")

        # Ensure content is valid UTF-8
        try:
            content.encode("utf-8")
        except UnicodeEncodeError:
            raise SecurityViolation("Content contains invalid UTF-8 characters")

        with self._get_file_lock(file_path):
            file_path_obj = Path(file_path)

            # Create backup if file exists
            backup_path = None
            if create_backup and file_path_obj.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = file_path_obj.with_suffix(f".bak_{timestamp}")
                shutil.copy2(file_path, backup_path)

            try:
                # Ensure parent directory exists
                file_path_obj.parent.mkdir(parents=True, exist_ok=True)

                # Atomic write using temporary file
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=file_path_obj.parent, delete=False
                ) as temp_file:
                    temp_file.write(content)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())
                    temp_path = temp_file.name

                # Atomic move
                shutil.move(temp_path, file_path)
                return True

            except Exception as e:
                # Cleanup temp file if it exists
                temp_path_obj = Path(temp_path) if "temp_path" in locals() else None
                if temp_path_obj and temp_path_obj.exists():
                    temp_path_obj.unlink()

                # Restore backup if write failed
                if backup_path and Path(backup_path).exists():
                    shutil.move(backup_path, file_path)

                raise SecurityViolation(f"Failed to write file {file_path}: {e}")

    def delete_file(self, file_path: str, create_backup: bool = True) -> bool:
        """Delete agent file with optional backup."""
        self._validate_path(file_path)

        with self._get_file_lock(file_path):
            file_path_obj = Path(file_path)

            if not file_path_obj.exists():
                return False

            # Create backup before deletion
            if create_backup:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = file_path_obj.with_suffix(f".deleted_{timestamp}")
                shutil.copy2(file_path, backup_path)

            try:
                file_path_obj.unlink()
                return True
            except PermissionError:
                raise SecurityViolation(f"Permission denied deleting file: {file_path}")

    def move_file(self, source_path: str, destination_path: str) -> bool:
        """Move agent file with validation."""
        self._validate_path(source_path)
        self._validate_path(destination_path)

        source_obj = Path(source_path)
        dest_obj = Path(destination_path)

        if not source_obj.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        if dest_obj.exists():
            raise SecurityViolation(
                f"Destination file already exists: {destination_path}"
            )

        # Use file locks for both source and destination
        lock1 = self._get_file_lock(source_path)
        lock2 = self._get_file_lock(destination_path)

        # Acquire locks in deterministic order to prevent deadlock
        first_lock, second_lock = (
            (lock1, lock2) if source_path < destination_path else (lock2, lock1)
        )

        with first_lock:
            with second_lock:
                try:
                    # Ensure destination directory exists
                    dest_obj.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(source_path, destination_path)
                    return True
                except PermissionError:
                    raise SecurityViolation(
                        f"Permission denied moving file from {source_path} to {destination_path}"
                    )

    def list_directory(
        self, dir_path: str, pattern: Optional[str] = None
    ) -> List[FileMetadata]:
        """List files in directory with metadata."""
        self._validate_path(dir_path)

        dir_path_obj = Path(dir_path)
        if not dir_path_obj.exists():
            return []

        if not dir_path_obj.is_dir():
            raise SecurityViolation(f"Path is not a directory: {dir_path}")

        files = []
        try:
            for item in dir_path_obj.iterdir():
                if item.is_file():
                    # Apply pattern filter if specified
                    if pattern and not item.match(pattern):
                        continue

                    stat = item.stat()
                    files.append(
                        FileMetadata(
                            path=str(item),
                            name=item.name,
                            size=stat.st_size,
                            modified_time=datetime.fromtimestamp(stat.st_mtime),
                            created_time=datetime.fromtimestamp(stat.st_ctime),
                            is_directory=False,
                            permissions=oct(stat.st_mode)[-3:],
                        )
                    )
                elif item.is_dir():
                    stat = item.stat()
                    files.append(
                        FileMetadata(
                            path=str(item),
                            name=item.name,
                            size=0,
                            modified_time=datetime.fromtimestamp(stat.st_mtime),
                            created_time=datetime.fromtimestamp(stat.st_ctime),
                            is_directory=True,
                            permissions=oct(stat.st_mode)[-3:],
                        )
                    )

        except PermissionError:
            raise SecurityViolation(f"Permission denied listing directory: {dir_path}")

        return files

    def create_directory(self, dir_path: str) -> bool:
        """Create directory with parents."""
        self._validate_path(dir_path)

        try:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
            return True
        except PermissionError:
            raise SecurityViolation(f"Permission denied creating directory: {dir_path}")

    def get_file_metadata(self, file_path: str) -> Optional[FileMetadata]:
        """Get detailed file metadata."""
        self._validate_path(file_path)

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return None

        try:
            stat = file_path_obj.stat()
            return FileMetadata(
                path=str(file_path_obj),
                name=file_path_obj.name,
                size=stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime),
                created_time=datetime.fromtimestamp(stat.st_ctime),
                is_directory=file_path_obj.is_dir(),
                permissions=oct(stat.st_mode)[-3:],
            )
        except PermissionError:
            raise SecurityViolation(
                f"Permission denied accessing file metadata: {file_path}"
            )

    def calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file content."""
        self._validate_path(file_path)

        with self._get_file_lock(file_path):
            try:
                hasher = hashlib.sha256()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hasher.update(chunk)
                return hasher.hexdigest()
            except FileNotFoundError:
                raise FileNotFoundError(f"File not found: {file_path}")
            except PermissionError:
                raise SecurityViolation(
                    f"Permission denied reading file for hash: {file_path}"
                )

    def ensure_safe_operation(self, operation_type: str, target_path: str) -> bool:
        """Ensure operation is safe to perform."""
        self._validate_path(target_path)

        path_obj = Path(target_path)

        # Check if it's a system or hidden file (except .claude directory)
        if path_obj.name.startswith(".") and ".claude" not in str(path_obj):
            raise SecurityViolation(
                f"Cannot perform {operation_type} on hidden file: {target_path}"
            )

        # Check for dangerous file types
        dangerous_extensions = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".scr", ".vbs"}
        if path_obj.suffix.lower() in dangerous_extensions:
            raise SecurityViolation(
                f"Cannot perform {operation_type} on executable file: {target_path}"
            )

        # For write operations, check available space (at least 100MB)
        if operation_type in ["write", "move", "copy"]:
            available_space = shutil.disk_usage(path_obj.parent).free
            if available_space < 100 * 1024 * 1024:  # 100MB
                raise SecurityViolation(
                    f"Insufficient disk space for {operation_type} operation"
                )

        return True
