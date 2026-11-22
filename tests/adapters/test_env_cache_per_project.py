"""Environment detection must not leak between projects, and lint assessment
metadata must describe what was really scanned.

Regression: detect_quality_environment memoized one result in a single slot,
so for the TTL every project got the first-analysed project's tasks/tools.
"""

import os
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from adapters.quality_analysis import QualityAnalysisAdapter
from adapters.quality_tool_execution import QualityToolExecutionAdapter
from core.models import ExecutionStatus, QualityMetrics, QualityTool


@pytest.fixture
def adapter(tmp_path):
    return DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))


def _tasks_for(path_to_tasks):
    return lambda working_dir, *a, **k: path_to_tasks[str(working_dir)]


def _detect(adapter, working_dir, tasks_mock, version_mock):
    with (
        patch.object(adapter, "_is_pixi_project", return_value=True),
        patch.object(adapter, "_get_available_tasks", tasks_mock),
        patch.object(adapter, "_get_tool_version", version_mock),
        patch.object(adapter, "environments_providing_tool", return_value=[]),
    ):
        return adapter.detect_quality_environment(working_dir=str(working_dir))


class TestEnvCacheKeyedByProject:
    def test_two_projects_get_their_own_results(self, adapter, tmp_path):
        a, b = tmp_path / "a", tmp_path / "b"
        a.mkdir()
        b.mkdir()
        tasks = {
            str(a): {"lint": "ruff check src/", "security": "bandit -r src/"},
            str(b): {"lint": "ruff check lib/", "typecheck": "mypy lib/"},
        }
        tasks_mock = Mock(side_effect=_tasks_for(tasks))
        versions = {str(a): "ruff 0.12.9", str(b): "ruff 0.14.0"}
        version_mock = Mock(
            side_effect=lambda tool, wd: versions[str(wd)] if tool == "ruff" else None
        )

        info_a = _detect(adapter, a, tasks_mock, version_mock)
        info_b = _detect(adapter, b, tasks_mock, version_mock)

        assert "bandit" in info_a.available_tools
        assert "bandit" not in info_b.available_tools
        assert "mypy" in info_b.available_tools
        assert info_a.quality_tasks != info_b.quality_tasks
        assert info_a.tool_versions["ruff"] == "ruff 0.12.9"
        assert info_b.tool_versions["ruff"] == "ruff 0.14.0"

    def test_same_dir_within_ttl_is_served_from_cache(self, adapter, tmp_path):
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})
        version_mock = Mock(return_value="ruff 1")

        first = _detect(adapter, tmp_path, tasks_mock, version_mock)
        calls = (tasks_mock.call_count, version_mock.call_count)
        second = _detect(adapter, tmp_path, tasks_mock, version_mock)

        assert second is first
        assert (tasks_mock.call_count, version_mock.call_count) == calls
        assert tasks_mock.call_count == 1

    def test_equivalent_paths_share_one_entry(self, adapter, tmp_path):
        (tmp_path / "p").mkdir()
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})
        version_mock = Mock(return_value=None)

        _detect(adapter, tmp_path / "p", tasks_mock, version_mock)
        _detect(adapter, tmp_path / "p" / ".." / "p", tasks_mock, version_mock)

        assert tasks_mock.call_count == 1

    def test_entry_expires_after_ttl(self, adapter, tmp_path):
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})
        version_mock = Mock(return_value=None)

        _detect(adapter, tmp_path, tasks_mock, version_mock)
        adapter._cache_ttl = -1
        _detect(adapter, tmp_path, tasks_mock, version_mock)

        assert tasks_mock.call_count == 2

    def test_cache_is_bounded_and_evicts_oldest(self, adapter, tmp_path):
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})
        version_mock = Mock(return_value=None)
        dirs = []
        for i in range(20):
            d = tmp_path / f"p{i}"
            d.mkdir()
            dirs.append(d)
            _detect(adapter, d, tasks_mock, version_mock)

        assert len(adapter._quality_env_cache) <= 16
        assert str(dirs[0].resolve()) not in adapter._quality_env_cache
        assert str(dirs[-1].resolve()) in adapter._quality_env_cache

        before = tasks_mock.call_count
        _detect(adapter, dirs[-1], tasks_mock, version_mock)
        assert tasks_mock.call_count == before

    def test_resolve_failure_falls_back_to_abspath(self, adapter, tmp_path):
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})
        version_mock = Mock(return_value=None)

        with patch.object(Path, "resolve", side_effect=RuntimeError("loop")):
            info = _detect(adapter, tmp_path, tasks_mock, version_mock)

        assert "ruff" in info.available_tools
        assert os.path.abspath(str(tmp_path)) in adapter._quality_env_cache

    def test_newer_concurrent_entry_is_not_overwritten(self, adapter, tmp_path):
        key = str(tmp_path.resolve())
        newer = (Mock(name="newer_info"), time.time() + 1000)
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})

        def plant_newer(tool, wd):
            adapter._quality_env_cache[key] = newer

        _detect(adapter, tmp_path, tasks_mock, Mock(side_effect=plant_newer))

        assert adapter._quality_env_cache[key] is newer


class TestEnvCacheManifestFingerprint:
    @staticmethod
    def _rewrite(path, text, mtime_ns):
        path.write_text(text)
        os.utime(path, ns=(mtime_ns, mtime_ns))

    def _prime(self, adapter, tmp_path):
        self._rewrite(tmp_path / "pixi.toml", "a = 1\n", 1_000_000_000)
        tasks_mock = Mock(return_value={"lint": "ruff check src/"})
        version_mock = Mock(return_value=None)
        _detect(adapter, tmp_path, tasks_mock, version_mock)
        return tasks_mock, version_mock

    def test_unchanged_manifest_still_hits(self, adapter, tmp_path):
        tasks_mock, version_mock = self._prime(adapter, tmp_path)
        _detect(adapter, tmp_path, tasks_mock, version_mock)
        assert tasks_mock.call_count == 1

    def test_size_change_invalidates(self, adapter, tmp_path):
        tasks_mock, version_mock = self._prime(adapter, tmp_path)
        self._rewrite(tmp_path / "pixi.toml", "a = 12345\n", 1_000_000_000)
        _detect(adapter, tmp_path, tasks_mock, version_mock)
        assert tasks_mock.call_count == 2

    def test_mtime_change_invalidates(self, adapter, tmp_path):
        tasks_mock, version_mock = self._prime(adapter, tmp_path)
        self._rewrite(tmp_path / "pixi.toml", "a = 1\n", 2_000_000_000)
        _detect(adapter, tmp_path, tasks_mock, version_mock)
        assert tasks_mock.call_count == 2

    def test_lockfile_change_invalidates(self, adapter, tmp_path):
        tasks_mock, version_mock = self._prime(adapter, tmp_path)
        self._rewrite(tmp_path / "pixi.lock", "version: 6\n", 3_000_000_000)
        _detect(adapter, tmp_path, tasks_mock, version_mock)
        assert tasks_mock.call_count == 2

    def test_pyproject_change_invalidates(self, adapter, tmp_path):
        tasks_mock, version_mock = self._prime(adapter, tmp_path)
        self._rewrite(tmp_path / "pyproject.toml", "[tool.x]\n", 3_000_000_000)
        _detect(adapter, tmp_path, tasks_mock, version_mock)
        assert tasks_mock.call_count == 2


def _lint_executor(tmp_path, body):
    executor = Mock()
    executor.working_dir = str(tmp_path)
    executor.resolve_task_name.return_value = "lint"
    executor.select_quality_environment.return_value = (None, "")
    executor._get_available_tasks.return_value = {"lint": body}
    executor.run_task.return_value = {"success": True, "stdout": "[]", "stderr": ""}
    return executor


def _lint_adapter(tmp_path, body):
    return QualityToolExecutionAdapter(_lint_executor(tmp_path, body))


class TestFilesAnalyzedAggregation:
    def test_none_is_skipped_and_counted_as_unknown(self):
        metrics = QualityMetrics(
            overall_score=10.0,
            total_violations=0,
            critical_violations=0,
            high_violations=0,
            medium_violations=0,
            low_violations=0,
            total_lines=0,
            code_lines=0,
            comment_lines=0,
            blank_lines=0,
        )

        def result(files):
            return Mock(
                status=ExecutionStatus.SUCCESS,
                tool=QualityTool.RUFF,
                parsed_metrics=metrics,
                violations=[],
                files_analyzed=files,
            )

        patterns = QualityAnalysisAdapter().detect_quality_patterns(
            [result(None), result(7), result(None), result(3)]
        )

        assert patterns["total_files"] == 10
        assert patterns["files_analyzed_unknown"] == 2


class TestLintAssessmentMetadata:
    def test_task_with_own_paths_does_not_report_src(self, tmp_path):
        (tmp_path / "lib").mkdir()
        adapter = _lint_adapter(tmp_path, "ruff check lib/")

        result = adapter.execute_lint_assessment(
            QualityTool.RUFF, project_path=str(tmp_path)
        )

        assert result.target_path == "src/"  # requested/default, unchanged
        assert result.effective_scope == "task-defined: ruff check lib/"

    def test_missing_default_src_is_not_claimed(self, tmp_path):
        adapter = _lint_adapter(tmp_path, "")

        result = adapter.execute_lint_assessment(
            QualityTool.RUFF, project_path=str(tmp_path)
        )

        assert result.target_path == "src/"
        assert (
            result.effective_scope == "src/ (default; directory does not exist "
            "in project)"
        )

    def test_explicit_target_path_is_echoed(self, tmp_path):
        adapter = _lint_adapter(tmp_path, "ruff check lib/")

        result = adapter.execute_lint_assessment(
            QualityTool.RUFF, target_path="pkg/", project_path=str(tmp_path)
        )

        assert result.target_path == "pkg/"
        assert result.effective_scope == "pkg/"

    def test_files_analyzed_is_not_the_line_based_fake(self, tmp_path):
        (tmp_path / "lib").mkdir()
        adapter = _lint_adapter(tmp_path, "ruff check lib/")
        lines = QualityMetrics(
            overall_score=10.0,
            total_violations=0,
            critical_violations=0,
            high_violations=0,
            medium_violations=0,
            low_violations=0,
            total_lines=500,
            code_lines=500,
            comment_lines=0,
            blank_lines=0,
        )

        with patch.object(adapter, "_parse_lint_output", return_value=([], lines)):
            result = adapter.execute_lint_assessment(
                QualityTool.RUFF, project_path=str(tmp_path)
            )

        assert result.files_analyzed is None
        assert result.estimated_files_analyzed == 10
