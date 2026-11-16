"""Environment detection must not leak between projects, and lint assessment
metadata must describe what was really scanned.

Regression: detect_quality_environment memoized one result in a single slot,
so for the TTL every project got the first-analysed project's tasks/tools.
"""

from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from adapters.quality_tool_execution import QualityToolExecutionAdapter
from core.models import QualityMetrics, QualityTool


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


class TestLintAssessmentMetadata:
    def test_task_with_own_paths_does_not_report_src(self, tmp_path):
        (tmp_path / "lib").mkdir()
        adapter = _lint_adapter(tmp_path, "ruff check lib/")

        result = adapter.execute_lint_assessment(
            QualityTool.RUFF, project_path=str(tmp_path)
        )

        assert result.target_path != "src/"
        assert "lib/" in result.target_path

    def test_missing_default_src_is_not_claimed(self, tmp_path):
        adapter = _lint_adapter(tmp_path, "")

        result = adapter.execute_lint_assessment(
            QualityTool.RUFF, project_path=str(tmp_path)
        )

        assert result.target_path != "src/"
        assert "src/" in result.target_path  # explains that it does not exist

    def test_explicit_target_path_is_echoed(self, tmp_path):
        adapter = _lint_adapter(tmp_path, "ruff check lib/")

        result = adapter.execute_lint_assessment(
            QualityTool.RUFF, target_path="pkg/", project_path=str(tmp_path)
        )

        assert result.target_path == "pkg/"

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
