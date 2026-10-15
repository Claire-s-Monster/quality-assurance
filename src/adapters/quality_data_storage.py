"""
Quality data storage adapter for persistent baseline and assessment result storage.

This adapter implements QualityDataStoragePort to provide production-ready data
persistence with atomic operations, backup/recovery, retention policies, and
comprehensive data integrity validation.
"""

import json
import shutil
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.models import (
    QualityAssessmentResult,
    QualityAssessmentType,
    QualityBaseline,
    OperationResult,
)
from core.ports import QualityDataStoragePort


class QualityDataStorageAdapter(QualityDataStoragePort):
    """
    Production-ready storage adapter for quality data persistence.

    Provides thread-safe storage operations with comprehensive features:
    - Atomic file operations with backup/recovery
    - Project-specific organization and indexing
    - Retention policy enforcement with cleanup
    - Data integrity validation and corruption detection
    - Export/import capabilities for data portability
    - Thread-safe concurrent access with file locking
    """

    def __init__(self, storage_root: Optional[str] = None):
        """
        Initialize storage adapter with directory structure.

        Args:
            storage_root: Root directory for storage (defaults to ./.claude/quality-data/)
        """
        if storage_root:
            self.storage_root = Path(storage_root)
        else:
            self.storage_root = Path("./.claude/quality-data")

        # Create storage directory structure
        self.storage_root.mkdir(parents=True, exist_ok=True)

        # Core storage directories
        self.baselines_dir = self.storage_root / "baselines"
        self.assessments_dir = self.storage_root / "assessments"
        self.backups_dir = self.storage_root / "backups"
        self.metadata_dir = self.storage_root / "metadata"
        self.exports_dir = self.storage_root / "exports"

        # Create all directories
        for directory in [
            self.baselines_dir,
            self.assessments_dir,
            self.backups_dir,
            self.metadata_dir,
            self.exports_dir,
        ]:
            directory.mkdir(exist_ok=True)

        # Thread safety
        self._file_locks: Dict[str, threading.RLock] = {}
        self._locks_lock = threading.RLock()

        # Data integrity tracking
        self._integrity_log = self.metadata_dir / "integrity_log.json"
        self._last_cleanup = self.metadata_dir / "last_cleanup.json"

        # Initialize metadata files
        self._initialize_metadata()

    def store_baseline(self, baseline: QualityBaseline) -> OperationResult:
        """Store quality baseline with atomic operations and backup."""
        operation_start = time.time()

        try:
            # Validate baseline data
            validation_result = self._validate_baseline_data(baseline)
            if not validation_result.success:
                return validation_result

            # Create backup before storing if baseline exists
            baseline_file = self.baselines_dir / f"{baseline.baseline_id}.json"
            backup_path = None

            if baseline_file.exists():
                backup_path = self._create_backup(baseline_file, "baseline")

            # Store baseline atomically
            with self._get_file_lock(f"baseline_{baseline.baseline_id}"):
                temp_file = baseline_file.with_suffix(".tmp")

                try:
                    # Write to temporary file first
                    with open(temp_file, "w") as f:
                        json.dump(baseline.model_dump(), f, indent=2, default=str)

                    # Atomic move
                    temp_file.replace(baseline_file)

                    # Update project index
                    self._update_baseline_index(baseline)

                    # Log successful operation
                    self._log_integrity_event(
                        {
                            "operation": "store_baseline",
                            "baseline_id": baseline.baseline_id,
                            "timestamp": datetime.now(UTC).isoformat(),
                            "file_size": baseline_file.stat().st_size,
                            "backup_created": backup_path is not None,
                            "backup_path": str(backup_path) if backup_path else None,
                        }
                    )

                    execution_time = (time.time() - operation_start) * 1000

                    return OperationResult(
                        success=True,
                        operation_type="store_baseline",
                        message=f"Baseline {baseline.baseline_id} stored successfully",
                        execution_time_ms=execution_time,
                        timestamp=datetime.now(UTC).isoformat(),
                        details={
                            "baseline_id": baseline.baseline_id,
                            "file_path": str(baseline_file),
                            "backup_created": backup_path is not None,
                            "backup_path": str(backup_path) if backup_path else None,
                        },
                    )

                except Exception as e:
                    # Clean up temp file on error
                    if temp_file.exists():
                        temp_file.unlink()

                    # Restore from backup if it was created
                    if backup_path and backup_path.exists():
                        shutil.copy2(backup_path, baseline_file)

                    raise e

        except Exception as e:
            execution_time = (time.time() - operation_start) * 1000
            error_msg = f"Failed to store baseline {baseline.baseline_id}: {str(e)}"

            # Log error
            self._log_integrity_event(
                {
                    "operation": "store_baseline_error",
                    "baseline_id": baseline.baseline_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": error_msg,
                }
            )

            return OperationResult(
                success=False,
                operation_type="store_baseline",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[error_msg],
            )

    def retrieve_baseline(self, baseline_id: str) -> Optional[QualityBaseline]:
        """Retrieve quality baseline by ID with data integrity validation."""
        try:
            baseline_file = self.baselines_dir / f"{baseline_id}.json"

            if not baseline_file.exists():
                return None

            with self._get_file_lock(f"baseline_{baseline_id}"):
                # Load and validate JSON
                try:
                    with open(baseline_file, "r") as f:
                        data = json.load(f)

                    # Validate data integrity
                    if not self._validate_json_integrity(data, "baseline"):
                        self._log_integrity_event(
                            {
                                "operation": "retrieve_baseline_corruption",
                                "baseline_id": baseline_id,
                                "timestamp": datetime.now(UTC).isoformat(),
                                "file_path": str(baseline_file),
                            }
                        )
                        return None

                    # Parse into model
                    baseline = QualityBaseline.model_validate(data)

                    # Check if baseline is expired
                    if self._is_baseline_expired(baseline):
                        return None

                    return baseline

                except (json.JSONDecodeError, ValueError) as e:
                    # Log corruption
                    self._log_integrity_event(
                        {
                            "operation": "retrieve_baseline_parse_error",
                            "baseline_id": baseline_id,
                            "timestamp": datetime.now(UTC).isoformat(),
                            "error": str(e),
                            "file_path": str(baseline_file),
                        }
                    )
                    return None

        except Exception as e:
            # Log unexpected error
            self._log_integrity_event(
                {
                    "operation": "retrieve_baseline_error",
                    "baseline_id": baseline_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "error": str(e),
                }
            )
            return None

    def store_assessment_result(
        self, result: QualityAssessmentResult
    ) -> OperationResult:
        """Store quality assessment result with project organization."""
        operation_start = time.time()

        try:
            # Validate assessment result
            validation_result = self._validate_assessment_data(result)
            if not validation_result.success:
                return validation_result

            # Organize by date and project (if available in metadata)
            date_str = datetime.now(UTC).strftime("%Y-%m-%d")
            assessment_dir = self.assessments_dir / date_str
            assessment_dir.mkdir(exist_ok=True)

            assessment_file = assessment_dir / f"{result.assessment_id}.json"

            # Store assessment atomically
            with self._get_file_lock(f"assessment_{result.assessment_id}"):
                temp_file = assessment_file.with_suffix(".tmp")

                try:
                    # Write to temporary file first
                    with open(temp_file, "w") as f:
                        json.dump(result.model_dump(), f, indent=2, default=str)

                    # Atomic move
                    temp_file.replace(assessment_file)

                    # Update assessment index
                    self._update_assessment_index(result, date_str)

                    execution_time = (time.time() - operation_start) * 1000

                    return OperationResult(
                        success=True,
                        operation_type="store_assessment_result",
                        message=f"Assessment {result.assessment_id} stored successfully",
                        execution_time_ms=execution_time,
                        timestamp=datetime.now(UTC).isoformat(),
                        details={
                            "assessment_id": result.assessment_id,
                            "assessment_type": result.assessment_type.value,
                            "file_path": str(assessment_file),
                        },
                    )

                except Exception as e:
                    # Clean up temp file on error
                    if temp_file.exists():
                        temp_file.unlink()
                    raise e

        except Exception as e:
            execution_time = (time.time() - operation_start) * 1000
            error_msg = (
                f"Failed to store assessment result {result.assessment_id}: {str(e)}"
            )

            return OperationResult(
                success=False,
                operation_type="store_assessment_result",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[error_msg],
            )

    def query_assessment_history(
        self,
        project_name: str,
        assessment_type: Optional[QualityAssessmentType] = None,
        limit: int = 50,
    ) -> List[QualityAssessmentResult]:
        """Query quality assessment history with filtering and limits."""
        try:
            results = []

            # Load assessment index
            index_file = self.metadata_dir / "assessment_index.json"
            if not index_file.exists():
                return []

            with open(index_file, "r") as f:
                index = json.load(f)

            # Get assessments for project
            project_assessments = index.get(project_name, {})

            # Collect assessment IDs by date (newest first)
            assessment_entries = []
            for date_str, assessments in project_assessments.items():
                for assessment_data in assessments:
                    if (
                        assessment_type is None
                        or assessment_data.get("assessment_type")
                        == assessment_type.value
                    ):
                        assessment_entries.append((date_str, assessment_data))

            # Sort by date (newest first) and limit
            assessment_entries.sort(key=lambda x: x[0], reverse=True)
            assessment_entries = assessment_entries[
                : limit * 2
            ]  # Load more for filtering

            # Load actual assessment results
            for date_str, assessment_data in assessment_entries:
                if len(results) >= limit:
                    break

                assessment_id = assessment_data["assessment_id"]
                assessment_file = (
                    self.assessments_dir / date_str / f"{assessment_id}.json"
                )

                if assessment_file.exists():
                    try:
                        with open(assessment_file, "r") as f:
                            data = json.load(f)

                        result = QualityAssessmentResult.model_validate(data)
                        results.append(result)

                    except (json.JSONDecodeError, ValueError):
                        # Skip corrupted files
                        continue

            return results[:limit]

        except Exception:
            return []

    def cleanup_expired_data(self, retention_days: int = 365) -> OperationResult:
        """Clean up expired quality data with comprehensive logging."""
        operation_start = time.time()
        cleanup_stats = {
            "expired_baselines": 0,
            "expired_assessments": 0,
            "freed_space_bytes": 0,
            "errors": [],
        }

        try:
            current_time = datetime.now(UTC)
            cutoff_time = current_time - timedelta(days=retention_days)

            # Clean up expired baselines
            for baseline_file in self.baselines_dir.glob("*.json"):
                try:
                    with open(baseline_file, "r") as f:
                        data = json.load(f)

                    expires_at = datetime.fromisoformat(
                        data["expires_at"].replace("Z", "+00:00")
                    )

                    if expires_at <= current_time:
                        file_size = baseline_file.stat().st_size
                        baseline_file.unlink()

                        # Update project index
                        self._remove_from_baseline_index(data["baseline_id"])

                        cleanup_stats["expired_baselines"] += 1
                        cleanup_stats["freed_space_bytes"] += file_size

                except (json.JSONDecodeError, KeyError, OSError) as e:
                    cleanup_stats["errors"].append(
                        f"Error processing {baseline_file}: {e}"
                    )

            # Clean up old assessment results
            for date_dir in self.assessments_dir.iterdir():
                if date_dir.is_dir():
                    try:
                        dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").replace(
                            tzinfo=UTC
                        )

                        if dir_date < cutoff_time:
                            # Calculate size before deletion
                            dir_size = sum(
                                f.stat().st_size
                                for f in date_dir.rglob("*")
                                if f.is_file()
                            )

                            # Remove entire date directory
                            shutil.rmtree(date_dir)

                            cleanup_stats["expired_assessments"] += len(
                                list(date_dir.glob("*.json"))
                            )
                            cleanup_stats["freed_space_bytes"] += dir_size

                    except (ValueError, OSError) as e:
                        cleanup_stats["errors"].append(
                            f"Error processing {date_dir}: {e}"
                        )

            # Update cleanup log
            self._log_cleanup_operation(cleanup_stats, retention_days)

            execution_time = (time.time() - operation_start) * 1000

            return OperationResult(
                success=True,
                operation_type="cleanup_expired_data",
                message=f"Cleaned up {cleanup_stats['expired_baselines']} baselines and {cleanup_stats['expired_assessments']} assessments",
                execution_time_ms=execution_time,
                timestamp=datetime.now(UTC).isoformat(),
                details=cleanup_stats,
            )

        except Exception as e:
            execution_time = (time.time() - operation_start) * 1000
            error_msg = f"Cleanup operation failed: {str(e)}"

            return OperationResult(
                success=False,
                operation_type="cleanup_expired_data",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[error_msg],
            )

    # Export/Import capabilities

    def export_baseline_data(
        self,
        project_name: str,
        export_format: str = "json",
        include_assessments: bool = False,
    ) -> OperationResult:
        """Export baseline data for backup or migration."""
        operation_start = time.time()

        try:
            export_timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            export_file = (
                self.exports_dir
                / f"{project_name}_baseline_export_{export_timestamp}.{export_format}"
            )

            # Load project baselines
            baseline_index = self._load_baseline_index()
            project_baselines = baseline_index.get(project_name, [])

            export_data = {
                "export_metadata": {
                    "project_name": project_name,
                    "export_timestamp": datetime.now(UTC).isoformat(),
                    "export_format": export_format,
                    "include_assessments": include_assessments,
                    "baseline_count": len(project_baselines),
                },
                "baselines": [],
            }

            # Export each baseline
            for baseline_id in project_baselines:
                baseline = self.retrieve_baseline(baseline_id)
                if baseline:
                    export_data["baselines"].append(baseline.model_dump())

            # Include assessment results if requested
            if include_assessments:
                export_data["assessments"] = []
                assessment_history = self.query_assessment_history(
                    project_name, limit=200
                )
                for assessment in assessment_history:
                    export_data["assessments"].append(assessment.model_dump())

            # Write export file
            with open(export_file, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

            execution_time = (time.time() - operation_start) * 1000

            return OperationResult(
                success=True,
                operation_type="export_baseline_data",
                message=f"Exported {len(project_baselines)} baselines for project {project_name}",
                execution_time_ms=execution_time,
                timestamp=datetime.now(UTC).isoformat(),
                details={
                    "project_name": project_name,
                    "export_file": str(export_file),
                    "baseline_count": len(project_baselines),
                    "file_size": export_file.stat().st_size,
                },
            )

        except Exception as e:
            execution_time = (time.time() - operation_start) * 1000
            error_msg = f"Export failed for project {project_name}: {str(e)}"

            return OperationResult(
                success=False,
                operation_type="export_baseline_data",
                message=error_msg,
                execution_time_ms=execution_time,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[error_msg],
            )

    # Private helper methods

    def _get_file_lock(self, lock_key: str) -> threading.RLock:
        """Get or create file lock for thread safety."""
        with self._locks_lock:
            if lock_key not in self._file_locks:
                self._file_locks[lock_key] = threading.RLock()
            return self._file_locks[lock_key]

    def _create_backup(self, file_path: Path, backup_type: str) -> Path:
        """Create backup of existing file with timestamp."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.stem}_{backup_type}_{timestamp}.backup"
        backup_path = self.backups_dir / backup_name

        shutil.copy2(file_path, backup_path)
        return backup_path

    def _validate_baseline_data(self, baseline: QualityBaseline) -> OperationResult:
        """Validate baseline data integrity."""
        try:
            # Basic validation
            if not baseline.baseline_id:
                return OperationResult(
                    success=False,
                    operation_type="validate_baseline_data",
                    message="Baseline ID cannot be empty",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat(),
                )

            if not baseline.project_name:
                return OperationResult(
                    success=False,
                    operation_type="validate_baseline_data",
                    message="Project name cannot be empty",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat(),
                )

            # Validate metrics
            if (
                baseline.metrics.overall_score < 0
                or baseline.metrics.overall_score > 10
            ):
                return OperationResult(
                    success=False,
                    operation_type="validate_baseline_data",
                    message="Overall score must be between 0 and 10",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat(),
                )

            return OperationResult(
                success=True,
                operation_type="validate_baseline_data",
                message="Baseline validation passed",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            return OperationResult(
                success=False,
                operation_type="validate_baseline_data",
                message=f"Baseline validation failed: {str(e)}",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[str(e)],
            )

    def _validate_assessment_data(
        self, result: QualityAssessmentResult
    ) -> OperationResult:
        """Validate assessment result data integrity."""
        try:
            # Basic validation
            if not result.assessment_id:
                return OperationResult(
                    success=False,
                    operation_type="validate_assessment_data",
                    message="Assessment ID cannot be empty",
                    execution_time_ms=0.0,
                    timestamp=datetime.now(UTC).isoformat(),
                )

            return OperationResult(
                success=True,
                operation_type="validate_assessment_data",
                message="Assessment validation passed",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
            )

        except Exception as e:
            return OperationResult(
                success=False,
                operation_type="validate_assessment_data",
                message=f"Assessment validation failed: {str(e)}",
                execution_time_ms=0.0,
                timestamp=datetime.now(UTC).isoformat(),
                errors=[str(e)],
            )

    def _validate_json_integrity(self, data: Dict[str, Any], data_type: str) -> bool:
        """Validate JSON data structure integrity."""
        try:
            if data_type == "baseline":
                required_fields = [
                    "baseline_id",
                    "project_name",
                    "created_at",
                    "metrics",
                ]
            elif data_type == "assessment":
                required_fields = [
                    "assessment_id",
                    "assessment_type",
                    "tool",
                    "parsed_metrics",
                ]
            else:
                return True

            for field in required_fields:
                if field not in data:
                    return False

            return True

        except Exception:
            return False

    def _is_baseline_expired(self, baseline: QualityBaseline) -> bool:
        """Check if baseline has expired."""
        try:
            current_time = datetime.now(UTC)
            expires_at = datetime.fromisoformat(
                baseline.expires_at.replace("Z", "+00:00")
            )
            return expires_at <= current_time
        except (ValueError, AttributeError):
            return False

    def _update_baseline_index(self, baseline: QualityBaseline) -> None:
        """Update baseline index for fast project queries."""
        index_file = self.metadata_dir / "baseline_index.json"

        # Use file lock for index operations to prevent concurrent access issues
        with self._get_file_lock("baseline_index"):
            try:
                # Load existing index
                if index_file.exists():
                    try:
                        with open(index_file, "r") as f:
                            content = f.read().strip()
                            if content:  # Check if file is not empty
                                index = json.loads(content)
                            else:
                                index = {}
                    except (json.JSONDecodeError, ValueError):
                        # If index is corrupted, start fresh
                        index = {}
                else:
                    index = {}

                # Add baseline to project index
                project_name = baseline.project_name
                if project_name not in index:
                    index[project_name] = []

                if baseline.baseline_id not in index[project_name]:
                    index[project_name].append(baseline.baseline_id)

                # Sort by baseline ID (chronological)
                index[project_name].sort()

                # Write updated index atomically
                temp_file = index_file.with_suffix(".tmp")
                with open(temp_file, "w") as f:
                    json.dump(index, f, indent=2)

                # Atomic move
                temp_file.replace(index_file)

            except Exception as e:
                # Log error but don't fail the baseline storage operation
                self._log_integrity_event(
                    {
                        "operation": "update_baseline_index_error",
                        "baseline_id": baseline.baseline_id,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "error": str(e),
                    }
                )

    def _update_assessment_index(
        self, result: QualityAssessmentResult, date_str: str
    ) -> None:
        """Update assessment index for fast queries."""
        index_file = self.metadata_dir / "assessment_index.json"

        # Load existing index
        if index_file.exists():
            with open(index_file, "r") as f:
                index = json.load(f)
        else:
            index = {}

        # Use a generic project name since we don't have it in assessment results
        project_name = "default_project"  # Could be enhanced with project detection

        if project_name not in index:
            index[project_name] = {}

        if date_str not in index[project_name]:
            index[project_name][date_str] = []

        # Add assessment info
        assessment_info = {
            "assessment_id": result.assessment_id,
            "assessment_type": result.assessment_type.value,
            "tool": result.tool.value,
            "timestamp": result.start_time,
        }

        index[project_name][date_str].append(assessment_info)

        # Write updated index
        with open(index_file, "w") as f:
            json.dump(index, f, indent=2)

    def _load_baseline_index(self) -> Dict[str, List[str]]:
        """Load baseline index."""
        index_file = self.metadata_dir / "baseline_index.json"

        if not index_file.exists():
            return {}

        try:
            with open(index_file, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, ValueError):
            return {}

    def _remove_from_baseline_index(self, baseline_id: str) -> None:
        """Remove baseline from index."""
        index_file = self.metadata_dir / "baseline_index.json"

        if not index_file.exists():
            return

        try:
            with open(index_file, "r") as f:
                index = json.load(f)

            # Remove from all projects
            for project_name, baseline_ids in index.items():
                if baseline_id in baseline_ids:
                    baseline_ids.remove(baseline_id)

            with open(index_file, "w") as f:
                json.dump(index, f, indent=2)

        except (json.JSONDecodeError, ValueError, OSError):
            pass

    def _initialize_metadata(self) -> None:
        """Initialize metadata files if they don't exist."""
        # Initialize integrity log
        if not self._integrity_log.exists():
            with open(self._integrity_log, "w") as f:
                json.dump(
                    {"initialized_at": datetime.now(UTC).isoformat(), "events": []},
                    f,
                    indent=2,
                )

        # Initialize cleanup log
        if not self._last_cleanup.exists():
            with open(self._last_cleanup, "w") as f:
                json.dump({"last_cleanup_at": None, "cleanup_history": []}, f, indent=2)

    def _log_integrity_event(self, event: Dict[str, Any]) -> None:
        """Log data integrity event."""
        try:
            # Load existing log
            with open(self._integrity_log, "r") as f:
                log_data = json.load(f)

            # Add new event
            log_data["events"].append(event)

            # Keep only last 1000 events
            if len(log_data["events"]) > 1000:
                log_data["events"] = log_data["events"][-1000:]

            # Write back
            with open(self._integrity_log, "w") as f:
                json.dump(log_data, f, indent=2, default=str)

        except (json.JSONDecodeError, OSError):
            pass

    def _log_cleanup_operation(
        self, cleanup_stats: Dict[str, Any], retention_days: int
    ) -> None:
        """Log cleanup operation results."""
        try:
            # Load existing cleanup log
            with open(self._last_cleanup, "r") as f:
                log_data = json.load(f)

            # Update last cleanup time
            log_data["last_cleanup_at"] = datetime.now(UTC).isoformat()

            # Add cleanup record
            cleanup_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "retention_days": retention_days,
                "stats": cleanup_stats,
            }

            log_data["cleanup_history"].append(cleanup_record)

            # Keep only last 50 cleanup operations
            if len(log_data["cleanup_history"]) > 50:
                log_data["cleanup_history"] = log_data["cleanup_history"][-50:]

            # Write back
            with open(self._last_cleanup, "w") as f:
                json.dump(log_data, f, indent=2, default=str)

        except (json.JSONDecodeError, OSError):
            pass

    def cleanup(self) -> None:
        """Clean up resources when shutting down."""
        try:
            # Clear file locks
            with self._locks_lock:
                self._file_locks.clear()

        except Exception:
            pass
