"""environment_health must reflect the gates a project needs, not a count of
every tool the adapter knows how to detect.

Regression: the ratio was taken over all 11 known tools (pylint, flake8,
black, isort, ...), so a project with every gate it needs (ruff, mypy, bandit,
pytest) was reported "suboptimal"/"degraded"; and a tool declared only in a
non-default environment (bandit in quality-extended) counted as missing.
"""

from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter

CORE = {"ruff", "mypy", "bandit", "pytest"}
OPTIONAL = {"radon", "vulture", "safety", "pylint", "flake8", "black", "isort"}
TASKS = {"lint": "ruff check", "types": "mypy src", "test": "pytest"}


@pytest.fixture
def adapter(tmp_path):
    return DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))


class TestAssessEnvironmentHealth:
    def test_all_core_tools_with_optional_ones_absent_is_optimal(self, adapter):
        health = adapter._assess_environment_health(CORE, OPTIONAL, TASKS)
        assert health == "optimal"

    def test_core_tool_declared_in_another_environment_counts_as_present(self, adapter):
        health = adapter._assess_environment_health(
            {"ruff", "mypy", "pytest"},
            {"bandit"} | OPTIONAL,
            TASKS,
            declared_elsewhere={"bandit"},
        )
        assert health == "optimal"

    def test_core_tool_missing_everywhere_is_suboptimal(self, adapter):
        health = adapter._assess_environment_health(
            {"ruff", "mypy", "pytest"}, {"bandit"} | OPTIONAL, TASKS
        )
        assert health == "suboptimal"

    def test_no_core_tools_is_degraded(self, adapter):
        assert (
            adapter._assess_environment_health(set(), CORE | OPTIONAL, {}) == "degraded"
        )


class TestEnvironmentRecommendations:
    def test_names_exactly_the_core_tools_missing_everywhere(self, adapter):
        recs = adapter._generate_environment_recommendations(
            {"ruff", "mypy"},
            {"bandit", "pytest"} | OPTIONAL,
            TASKS,
            "suboptimal",
            declared_elsewhere={"pytest"},
        )
        joined = " ".join(recs)
        assert "bandit" in joined
        assert "pytest" not in joined

    def test_no_recommendation_when_everything_needed_is_present(self, adapter):
        recs = adapter._generate_environment_recommendations(
            CORE, OPTIONAL - {"black"}, TASKS, "optimal"
        )
        assert recs == []

    def test_task_shortfall_states_the_count(self, adapter):
        recs = adapter._generate_environment_recommendations(
            CORE, OPTIONAL, {"lint": "ruff check"}, "suboptimal"
        )
        assert any("1" in r and "quality task" in r for r in recs)


class TestDetectUsesAnyEnvironment:
    def test_tool_in_quality_extended_only_does_not_make_project_suboptimal(
        self, adapter, tmp_path
    ):
        tasks = {
            "lint": "ruff check src/",
            "typecheck": "mypy src/",
            "test": "pytest tests/",
        }

        def providers(tool, working_dir=None):
            return ["quality-extended"] if tool == "bandit" else []

        with (
            patch.object(adapter, "_is_pixi_project", return_value=True),
            patch.object(adapter, "_get_available_tasks", return_value=tasks),
            patch.object(adapter, "_get_tool_version", return_value=None),
            patch.object(adapter, "environments_providing_tool", side_effect=providers),
        ):
            info = adapter.detect_quality_environment(working_dir=str(tmp_path))

        assert "bandit" not in info.available_tools
        assert info.environment_health == "optimal"
        assert not any("bandit" in r for r in info.recommendations)
