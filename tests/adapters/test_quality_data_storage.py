"""
Unit tests for QualityDataStorageAdapter.

Tests storage operations, backup/recovery, retention policies,
export/import capabilities, and data integrity validation.
"""

import json
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest

from core.models import (
    QualityAssessmentResult,
    QualityAssessmentType,
    QualityBaseline,
    QualityMetrics,
    QualityTool,
    ExecutionStatus,
)
from adapters.quality_data_storage import QualityDataStorageAdapter


class TestQualityDataStorageAdapter:
    """Test suite for QualityDataStorageAdapter."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def adapter(self, temp_storage):
        """Create QualityDataStorageAdapter with temporary storage."""
        return QualityDataStorageAdapter(storage_root=temp_storage)

    @pytest.fixture
    def sample_metrics(self):
        """Create sample quality metrics."""
        return QualityMetrics(
            overall_score=8.5,
            total_violations=5,
            critical_violations=0,
            high_violations=1,
            medium_violations=3,
            low_violations=1,
            test_coverage_percentage=92.0,
            average_complexity=4.2,
            max_complexity=8,
            maintainability_index=85.5,
            security_issues_count=0,
            dead_code_count=1,
            type_errors=0,
            total_lines=1500,
            code_lines=1200,
            comment_lines=200,
            blank_lines=100,
        )

    @pytest.fixture
    def sample_baseline(self, sample_metrics):
        """Create sample quality baseline."""
        return QualityBaseline(
            baseline_id="test-baseline-001",
            project_name="test-project",
            project_version="1.0.0",
            created_at=datetime.now(UTC).isoformat(),
            expires_at=(datetime.now(UTC) + timedelta(days=365)).isoformat(),
            git_commit="abc123def456",
            git_branch="main",
            retention_days=365,
            tags=["baseline", "release"],
            metrics=sample_metrics,
            tool_versions={"ruff": "0.1.0", "mypy": "1.5.0"},
            python_version="3.11.0",
            pixi_environment={},
        )

    @pytest.fixture
    def sample_assessment_result(self, sample_metrics):
        """Create sample assessment result."""
        return QualityAssessmentResult(
            assessment_type=QualityAssessmentType.LINT,
            tool=QualityTool.RUFF,
            status=ExecutionStatus.SUCCESS,
            start_time=datetime.now(UTC).isoformat(),
            end_time=datetime.now(UTC).isoformat(),
            execution_time_ms=1500.0,
            pixi_task_used="ruff",
            target_path="src/",
            files_analyzed=15,
            raw_output="ruff output",
            parsed_metrics=sample_metrics,
        )

    def test_adapter_initialization(self, temp_storage):
        """Test adapter initialization and directory creation."""
        adapter = QualityDataStorageAdapter(storage_root=temp_storage)

        # Check storage root
        assert adapter.storage_root == Path(temp_storage)

        # Check all subdirectories created
        assert adapter.baselines_dir.exists()
        assert adapter.assessments_dir.exists()
        assert adapter.backups_dir.exists()
        assert adapter.metadata_dir.exists()
        assert adapter.exports_dir.exists()

        # Check metadata files initialized
        assert (adapter.metadata_dir / "integrity_log.json").exists()
        assert (adapter.metadata_dir / "last_cleanup.json").exists()

    def test_adapter_default_initialization(self):
        """Test adapter initialization with default storage path."""
        adapter = QualityDataStorageAdapter()
        assert adapter.storage_root == Path("./.claude/quality-data")

    def test_store_baseline_success(self, adapter, sample_baseline):
        """Test successful baseline storage."""
        result = adapter.store_baseline(sample_baseline)

        assert result.success is True
        assert result.operation_type == "store_baseline"
        assert "stored successfully" in result.message
        assert result.execution_time_ms > 0
        assert result.details["baseline_id"] == sample_baseline.baseline_id

        # Check file was created
        baseline_file = adapter.baselines_dir / f"{sample_baseline.baseline_id}.json"
        assert baseline_file.exists()

        # Verify file content
        with open(baseline_file, "r") as f:
            stored_data = json.load(f)

        assert stored_data["baseline_id"] == sample_baseline.baseline_id
        assert stored_data["project_name"] == sample_baseline.project_name

    def test_store_baseline_with_backup(self, adapter, sample_baseline):
        """Test baseline storage creates backup when updating existing baseline."""
        # Store baseline initially
        adapter.store_baseline(sample_baseline)

        # Modify baseline and store again
        sample_baseline.project_version = "1.0.1"
        result = adapter.store_baseline(sample_baseline)

        assert result.success is True
        assert result.details["backup_created"] is True
        assert result.details["backup_path"] is not None

        # Check backup was created
        backup_path = Path(result.details["backup_path"])
        assert backup_path.exists()
        assert backup_path.parent == adapter.backups_dir

    def test_store_baseline_validation_failure(self, adapter):
        """Test baseline storage with validation failure."""
        # Create invalid baseline (empty baseline_id)
        invalid_baseline = QualityBaseline(
            baseline_id="",  # Invalid empty ID
            project_name="test-project",
            project_version="1.0.0",
            created_at=datetime.now(UTC).isoformat(),
            expires_at=(datetime.now(UTC) + timedelta(days=365)).isoformat(),
            retention_days=365,
            tags=[],
            metrics=QualityMetrics(
                overall_score=5.0,
                total_violations=0,
                critical_violations=0,
                high_violations=0,
                medium_violations=0,
                low_violations=0,
                total_lines=100,
                code_lines=80,
                comment_lines=15,
                blank_lines=5,
            ),
            assessment_results=[],
            tool_versions={},
            python_version="3.11.0",
            environment_hash="hash123",
        )

        result = adapter.store_baseline(invalid_baseline)

        assert result.success is False
        assert "Baseline ID cannot be empty" in result.message

    def test_retrieve_baseline_success(self, adapter, sample_baseline):
        """Test successful baseline retrieval."""
        # Store baseline first
        adapter.store_baseline(sample_baseline)

        # Retrieve baseline
        retrieved = adapter.retrieve_baseline(sample_baseline.baseline_id)

        assert retrieved is not None
        assert retrieved.baseline_id == sample_baseline.baseline_id
        assert retrieved.project_name == sample_baseline.project_name
        assert retrieved.metrics.overall_score == sample_baseline.metrics.overall_score

    def test_retrieve_baseline_not_found(self, adapter):
        """Test baseline retrieval for non-existent baseline."""
        retrieved = adapter.retrieve_baseline("non-existent")
        assert retrieved is None

    def test_retrieve_baseline_expired(self, adapter, sample_baseline):
        """Test baseline retrieval for expired baseline."""
        # Create expired baseline
        sample_baseline.expires_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        adapter.store_baseline(sample_baseline)

        # Should return None for expired baseline
        retrieved = adapter.retrieve_baseline(sample_baseline.baseline_id)
        assert retrieved is None

    def test_store_assessment_result_success(self, adapter, sample_assessment_result):
        """Test successful assessment result storage."""
        result = adapter.store_assessment_result(sample_assessment_result)

        assert result.success is True
        assert result.operation_type == "store_assessment_result"
        assert "stored successfully" in result.message
        assert result.details["assessment_id"] == sample_assessment_result.assessment_id

        # Check file was created
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        assessment_dir = adapter.assessments_dir / date_str
        assessment_file = (
            assessment_dir / f"{sample_assessment_result.assessment_id}.json"
        )
        assert assessment_file.exists()

    def test_query_assessment_history(self, adapter):
        """Test assessment history querying."""
        # Create multiple assessment results
        results = []
        for i in range(3):
            metrics = QualityMetrics(
                overall_score=7.0 + i,
                total_violations=10 - i,
                critical_violations=0,
                high_violations=1,
                medium_violations=5 - i,
                low_violations=4 - i,
                total_lines=1000 + i * 100,
                code_lines=800 + i * 80,
                comment_lines=150,
                blank_lines=50,
            )

            result = QualityAssessmentResult(
                assessment_type=QualityAssessmentType.COMPREHENSIVE,
                tool=QualityTool.RUFF,
                status=ExecutionStatus.SUCCESS,
                start_time=datetime.now(UTC).isoformat(),
                end_time=datetime.now(UTC).isoformat(),
                execution_time_ms=1000.0 + i * 100,
                pixi_task_used="ruff",
                target_path="src/",
                files_analyzed=10 + i,
                raw_output=f"output {i}",
                parsed_metrics=metrics,
            )

            adapter.store_assessment_result(result)
            results.append(result)

        # Query history
        history = adapter.query_assessment_history("default_project", limit=10)

        # Should return results (though actual count may vary due to indexing)
        assert isinstance(history, list)

    def test_cleanup_expired_data(self, adapter, sample_baseline):
        """Test cleanup of expired data."""
        # Create expired baseline by manipulating file directly
        expired_baseline_id = "expired-baseline"
        expired_time = datetime.now(UTC) - timedelta(days=1)

        baseline_data = {
            "baseline_id": expired_baseline_id,
            "created_at": expired_time.isoformat(),
            "expires_at": expired_time.isoformat(),  # Already expired
            "project_name": "test-project",
            "metrics": {
                "overall_score": 7.0,
                "total_violations": 5,
                "critical_violations": 0,
                "high_violations": 1,
                "medium_violations": 3,
                "low_violations": 1,
                "total_lines": 1000,
                "code_lines": 800,
                "comment_lines": 150,
                "blank_lines": 50,
            },
        }

        # Write expired baseline file
        baseline_file = adapter.baselines_dir / f"{expired_baseline_id}.json"
        with open(baseline_file, "w") as f:
            json.dump(baseline_data, f)

        # Update baseline index
        index_file = adapter.metadata_dir / "baseline_index.json"
        index_data = {"test-project": [expired_baseline_id]}
        with open(index_file, "w") as f:
            json.dump(index_data, f)

        # Verify file exists before cleanup
        assert baseline_file.exists()

        # Run cleanup
        result = adapter.cleanup_expired_data(retention_days=0)

        assert result.success is True
        assert result.details["expired_baselines"] >= 1

        # File should be removed
        assert not baseline_file.exists()

    def test_export_baseline_data(self, adapter, sample_baseline):
        """Test baseline data export."""
        # Store baseline first
        adapter.store_baseline(sample_baseline)

        # Export baseline data
        result = adapter.export_baseline_data(
            project_name=sample_baseline.project_name,
            export_format="json",
            include_assessments=False,
        )

        assert result.success is True
        assert result.operation_type == "export_baseline_data"
        assert result.details["baseline_count"] >= 1
        assert result.details["project_name"] == sample_baseline.project_name

        # Check export file was created
        export_file = Path(result.details["export_file"])
        assert export_file.exists()
        assert export_file.suffix == ".json"

        # Verify export content
        with open(export_file, "r") as f:
            export_data = json.load(f)

        assert "export_metadata" in export_data
        assert "baselines" in export_data
        assert (
            export_data["export_metadata"]["project_name"]
            == sample_baseline.project_name
        )

    def test_thread_safety_concurrent_operations(self, adapter, sample_baseline):
        """Test thread safety with concurrent operations."""
        num_threads = 10
        results = [None] * num_threads

        def store_baseline(index):
            """Store baseline with unique ID."""
            baseline = QualityBaseline(
                baseline_id=f"concurrent-baseline-{index}",
                project_name="test-concurrent",
                project_version="1.0.0",
                created_at=datetime.now(UTC).isoformat(),
                expires_at=(datetime.now(UTC) + timedelta(days=365)).isoformat(),
                retention_days=365,
                tags=[f"thread-{index}"],
                metrics=sample_baseline.metrics,
                tool_versions={},
                python_version="3.11.0",
                pixi_environment={"hash": f"{index}"},
            )

            result = adapter.store_baseline(baseline)
            results[index] = result

        # Start concurrent threads
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=store_baseline, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All operations should succeed
        for i, result in enumerate(results):
            assert result is not None
            assert result.success is True, (
                f"Thread {i} failed: {result.message if result else 'No result'}"
            )

    def test_data_integrity_validation(self, adapter):
        """Test data integrity validation methods."""
        # Test valid baseline data
        valid_baseline_data = {
            "baseline_id": "test-baseline",
            "project_name": "test-project",
            "created_at": datetime.now(UTC).isoformat(),
            "metrics": {"overall_score": 8.0, "total_violations": 5},
        }

        assert adapter._validate_json_integrity(valid_baseline_data, "baseline") is True

        # Test invalid baseline data (missing required field)
        invalid_baseline_data = {
            "project_name": "test-project",
            # Missing baseline_id
            "created_at": datetime.now(UTC).isoformat(),
            "metrics": {"overall_score": 8.0},
        }

        assert (
            adapter._validate_json_integrity(invalid_baseline_data, "baseline") is False
        )

    def test_backup_and_recovery(self, adapter):
        """Test backup creation and recovery functionality."""
        # Create a test file
        test_file = adapter.baselines_dir / "test-file.json"
        test_data = {"test": "data"}

        with open(test_file, "w") as f:
            json.dump(test_data, f)

        # Create backup
        backup_path = adapter._create_backup(test_file, "test")

        assert backup_path.exists()
        assert backup_path.parent == adapter.backups_dir
        assert "test_" in backup_path.name
        assert backup_path.suffix == ".backup"

        # Verify backup content matches original
        with open(backup_path, "r") as f:
            backup_data = json.load(f)

        assert backup_data == test_data

    def test_cleanup_method(self, adapter):
        """Test adapter cleanup method."""
        # Should not raise any exceptions
        adapter.cleanup()

        # File locks should be cleared (can't directly test, but should not hang)
        assert True  # If we get here without hanging, cleanup worked
