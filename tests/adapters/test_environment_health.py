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


BASE_TASKS = {
    "lint": "ruff check src/",
    "typecheck": "mypy src/",
    "test": "pytest tests/",
}
TIP = "Consider using ruff format instead of black"


class TestRuffFormatTip:
    def _recs(self, adapter, tmp_path, tasks, black_envs):
        with (
            patch.object(adapter, "_is_pixi_project", return_value=True),
            patch.object(adapter, "_get_available_tasks", return_value=tasks),
            patch.object(
                adapter, "_all_task_bodies", return_value=list(tasks.values())
            ),
            patch.object(adapter, "_get_tool_version", return_value=None),
            patch.object(
                adapter,
                "environments_providing_tool",
                side_effect=lambda tool, wd=None: black_envs if tool == "black" else [],
            ),
        ):
            info = adapter.detect_quality_environment(working_dir=str(tmp_path))
        return info.recommendations

    def test_no_black_no_tip(self, adapter, tmp_path):
        assert TIP not in self._recs(adapter, tmp_path, BASE_TASKS, [])

    def test_black_task_without_ruff_format_gives_tip(self, adapter, tmp_path):
        tasks = {**BASE_TASKS, "fmt": "black src/"}
        assert TIP in self._recs(adapter, tmp_path, tasks, [])

    def test_black_declared_and_ruff_format_task_no_tip(self, adapter, tmp_path):
        tasks = {**BASE_TASKS, "format": "ruff format src/"}
        assert TIP not in self._recs(adapter, tmp_path, tasks, ["dev"])

    def test_black_declared_only_gives_tip(self, adapter, tmp_path):
        assert TIP in self._recs(adapter, tmp_path, BASE_TASKS, ["dev"])

    def test_qa_shape_black_in_non_default_feature_with_ruff_format_check(
        self, adapter, tmp_path
    ):
        tasks = {**BASE_TASKS, "format-check": "ruff format --check src/ tests/"}
        assert TIP not in self._recs(adapter, tmp_path, tasks, ["dev"])


class TestRuffFormatTipTaskParsing:
    """Formatter use is read from parsed commands, across every definition."""

    def test_argv_list_ruff_format_suppresses_tip(self, adapter, tmp_path):
        tasks = {**BASE_TASKS, "format": ["ruff", "format", "src/"]}
        assert TIP not in TestRuffFormatTip._recs(
            None, adapter, tmp_path, tasks, ["dev"]
        )

    def test_argv_list_black_gives_tip(self, adapter, tmp_path):
        tasks = {**BASE_TASKS, "fmt": ["black", "src/"]}
        assert TIP in TestRuffFormatTip._recs(None, adapter, tmp_path, tasks, [])

    def test_incidental_black_text_is_not_black_in_use(self, adapter, tmp_path):
        tasks = {**BASE_TASKS, "note": "echo black is retired  # black"}
        assert TIP not in TestRuffFormatTip._recs(None, adapter, tmp_path, tasks, [])

    def test_incidental_ruff_format_text_does_not_suppress_tip(self, adapter, tmp_path):
        tasks = {**BASE_TASKS, "note": "echo ruff format is great"}
        assert TIP in TestRuffFormatTip._recs(None, adapter, tmp_path, tasks, ["dev"])

    def test_prefixed_and_chained_invocations_count(self, adapter, tmp_path):
        tasks = {
            **BASE_TASKS,
            "fmt": "pixi run -e dev python -m black src/ && echo done",
        }
        assert TIP in TestRuffFormatTip._recs(None, adapter, tmp_path, tasks, [])

    def test_duplicate_task_names_across_features_are_all_scanned(
        self, adapter, tmp_path
    ):
        (tmp_path / "pixi.toml").write_text(
            '[tasks]\nformat = "ruff format src/"\n'
            '[feature.a.tasks]\nformat = "echo overwritten"\n'
            '[feature.b.tasks]\nfmt = "black src/"\n'
        )
        with (
            patch.object(adapter, "_get_tool_version", return_value=None),
            patch.object(adapter, "environments_providing_tool", return_value=[]),
        ):
            info = adapter.detect_quality_environment(working_dir=str(tmp_path))
        # `format` is collapsed to the feature's echo by name, yet ruff format
        # is still seen, so the tip stays off although black runs in `fmt`.
        assert TIP not in info.recommendations

    def test_duplicate_black_definition_overwritten_by_name_still_seen(
        self, adapter, tmp_path
    ):
        (tmp_path / "pixi.toml").write_text(
            '[tasks]\nfmt = "black src/"\n[feature.a.tasks]\nfmt = "echo skip"\n'
        )
        with (
            patch.object(adapter, "_get_tool_version", return_value=None),
            patch.object(adapter, "environments_providing_tool", return_value=[]),
        ):
            info = adapter.detect_quality_environment(working_dir=str(tmp_path))
        assert TIP in info.recommendations


PYRIGHT_TASKS = {
    "lint": "ruff check src/",
    "typecheck": "pyright src/",
    "test": "pytest tests/",
    "security": "bandit -r src/",
}


class TestPyrightCoversMypy:
    @staticmethod
    def _no_bandit(tool, working_dir=None):
        return [] if tool == "bandit" else ["x"]

    def _detect(self, adapter, tmp_path, tasks, providers=None):
        with (
            patch.object(adapter, "_is_pixi_project", return_value=True),
            patch.object(adapter, "_get_available_tasks", return_value=tasks),
            patch.object(
                adapter, "_all_task_bodies", return_value=list(tasks.values())
            ),
            patch.object(adapter, "_get_tool_version", return_value=None),
            patch.object(
                adapter,
                "environments_providing_tool",
                side_effect=providers or (lambda tool, working_dir=None: ["x"]),
            ),
        ):
            return adapter.detect_quality_environment(working_dir=str(tmp_path))

    def test_pyright_task_without_mypy_is_optimal(self, adapter, tmp_path):
        info = self._detect(adapter, tmp_path, PYRIGHT_TASKS)
        assert "mypy" not in info.available_tools
        assert info.environment_health == "optimal"

    def test_missing_bandit_is_still_suboptimal(self, adapter, tmp_path):
        tasks = {k: v for k, v in PYRIGHT_TASKS.items() if k != "security"}
        info = self._detect(adapter, tmp_path, tasks, self._no_bandit)
        assert info.environment_health == "suboptimal"

    def test_health_score_same_for_pyright_and_mypy(self, adapter, tmp_path):
        mypy_tasks = {**PYRIGHT_TASKS, "typecheck": "mypy src/"}
        pyright = self._detect(adapter, tmp_path, PYRIGHT_TASKS)
        mypy = self._detect(adapter, tmp_path, mypy_tasks)
        assert adapter._calculate_health_score(pyright) == pytest.approx(
            adapter._calculate_health_score(mypy)
        )

    def test_health_score_honours_declared_elsewhere(self, adapter, tmp_path):
        tasks = {k: v for k, v in PYRIGHT_TASKS.items() if k != "security"}
        elsewhere = self._detect(adapter, tmp_path, tasks)
        other = tmp_path / "other"  # detection results are cached per directory
        other.mkdir()
        nowhere = self._detect(adapter, other, tasks, self._no_bandit)
        assert adapter._calculate_health_score(
            elsewhere
        ) > adapter._calculate_health_score(nowhere)

    def test_real_manifest_with_pyright_typecheck_task(self, adapter, tmp_path):
        (tmp_path / "pixi.toml").write_text(
            "[dependencies]\nruff = '*'\nbandit = '*'\npytest = '*'\npyright = '*'\n"
            "[tasks]\n"
            'lint = "ruff check src/"\n'
            'typecheck = "pyright src/"\n'
            'test = "pytest tests/"\n'
            'security = "bandit -r src/"\n'
        )
        with patch.object(adapter, "_get_tool_version", return_value=None):
            info = adapter.detect_quality_environment(working_dir=str(tmp_path))
        assert info.environment_health == "optimal"
        assert info.recommendations == []


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
