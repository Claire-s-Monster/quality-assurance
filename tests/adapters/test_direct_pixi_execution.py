"""
Unit tests for DirectPixiExecutionAdapter.run_task command construction.

Verifies that the --environment flag is only emitted when an environment is
explicitly requested, and that it is placed immediately before the task name
as required by pixi's CLI argument order.
"""

import subprocess
import textwrap
from unittest.mock import Mock, patch

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter


class TestRunTaskCommandConstruction:
    """Test suite for pixi command construction in run_task."""

    def _make_adapter(self) -> DirectPixiExecutionAdapter:
        logging_port = Mock()
        adapter = DirectPixiExecutionAdapter(
            logging=logging_port, working_dir="/tmp/project"
        )
        adapter._is_pixi_project = Mock(return_value=True)
        adapter._get_available_tasks = Mock(return_value={"lint": "ruff check src/"})
        return adapter

    def _fake_completed_process(self):
        result = Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    def test_run_task_without_environment_omits_flag(self):
        """When environment is None, no --environment token is emitted."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()

            adapter.run_task("lint", args=["src/"])

            called_command = mock_run.call_args[0][0]
            assert called_command[0] == adapter._pixi_bin
            assert called_command[0].endswith("pixi")
            assert called_command[1:] == ["run", "lint", "src/"]
            assert "--environment" not in called_command

    def test_run_task_with_environment_inserts_flag_before_task(self):
        """When environment is provided, --environment <env> must precede the task name."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()

            adapter.run_task("lint", args=["src/"], environment="quality")

            called_command = mock_run.call_args[0][0]
            assert called_command[0] == adapter._pixi_bin
            assert called_command[0].endswith("pixi")
            assert called_command[1:] == [
                "run",
                "--environment",
                "quality",
                "lint",
                "src/",
            ]

            flag_index = called_command.index("--environment")
            task_index = called_command.index("lint")
            assert called_command[flag_index + 1] == "quality"
            assert flag_index < task_index


class TestRunQualityTaskEnvironmentForwarding:
    """Test suite verifying run_quality_task forwards `environment` to run_task.

    run_quality_task previously accepted no `environment` parameter and could
    not honor an environment override at all. These tests confirm the
    override reaches the underlying pixi subprocess command.
    """

    def _make_adapter(self) -> DirectPixiExecutionAdapter:
        logging_port = Mock()
        adapter = DirectPixiExecutionAdapter(
            logging=logging_port, working_dir="/tmp/project"
        )
        adapter._is_pixi_project = Mock(return_value=True)
        # Bare-tool body: appended tool args are valid. A full-command body is
        # covered in test_task_body_aware_args.py.
        adapter._get_available_tasks = Mock(return_value={"lint": "ruff"})
        env_info = Mock()
        env_info.available_tools = {"ruff"}
        env_info.tool_versions = {}
        env_info.environment_health = "optimal"
        env_info.performance_indicators = {}
        env_info.recommendations = []
        env_info.missing_tools = set()
        adapter.detect_quality_environment = Mock(return_value=env_info)
        return adapter

    def _fake_completed_process(self):
        result = Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    def test_run_quality_task_with_environment_inserts_flag_before_task(self):
        """environment="quality" must appear as --environment quality before
        the task name in the actual subprocess command."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()

            adapter.run_quality_task(
                task_name="lint",
                quality_tool="ruff",
                target_paths=["src/"],
                environment="quality",
            )

            called_command = mock_run.call_args[0][0]
            assert called_command[1:] == [
                "run",
                "--environment",
                "quality",
                "lint",
                "check",
                "src/",
            ]
            flag_index = called_command.index("--environment")
            task_index = called_command.index("lint")
            assert flag_index < task_index

    def test_run_quality_task_without_environment_omits_flag(self):
        """environment=None (default) must not emit any --environment token."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()

            adapter.run_quality_task(
                task_name="lint", quality_tool="ruff", target_paths=["src/"]
            )

            called_command = mock_run.call_args[0][0]
            assert "--environment" not in called_command


class TestFeatureScopedTaskDiscovery:
    """Test suite for feature-scoped pixi task discovery.

    The pre-check performed by `_get_available_tasks` / `task_exists` must
    never be stricter than pixi itself. It must find tasks defined under
    `[tool.pixi.feature.<name>.tasks]`, not just the top-level
    `[tool.pixi.tasks]` table, and must resolve which features are active
    for a given environment the same way pixi does.
    """

    def _make_adapter(self, tmp_path) -> DirectPixiExecutionAdapter:
        return DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))

    def _write_pyproject(self, tmp_path, content: str) -> None:
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent(content))

    def test_feature_scoped_task_found_with_matching_environment(self, tmp_path):
        """A task under [tool.pixi.feature.quality.tasks] is found when the
        requested environment activates the 'quality' feature."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            build = "echo build"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment="quality"
        )

        assert result["exists"] is True

    def test_feature_scoped_task_found_when_environment_is_none(self, tmp_path):
        """With no environment specified, the permissive union of all
        feature tasks is used so pixi -- not this pre-check -- is the final
        authority on task resolution/ambiguity."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment=None
        )

        assert result["exists"] is True

    def test_feature_scoped_task_not_found_for_excluding_environment(self, tmp_path):
        """A feature-scoped task must NOT be found when the requested
        environment activates a different feature set that excludes it."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.feature.dev.tasks]
            devtask = "echo dev"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
            dev-only = {features = ["dev"]}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment="dev-only"
        )

        assert result["exists"] is False

    def test_environment_entry_dict_form_parses_features(self, tmp_path):
        """[tool.pixi.environments] entries in dict form
        {features=[...], solve-group=...} are parsed correctly."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"], solve-group = "default"}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment="quality"
        )

        assert result["exists"] is True

    def test_environment_entry_bare_list_form_parses_features(self, tmp_path):
        """[tool.pixi.environments] entries in bare-list shorthand form
        (equivalent to {features=[...]}) are parsed correctly."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = ["quality"]
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment="quality"
        )

        assert result["exists"] is True

    def test_top_level_task_still_found_no_regression(self, tmp_path):
        """Top-level [tool.pixi.tasks] entries remain discoverable alongside
        feature-scoped tasks, even when an environment filter is active."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            build = "echo build"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "build", working_dir=str(tmp_path), environment="quality"
        )

        assert result["exists"] is True

    def test_unknown_environment_falls_back_to_permissive_union(self, tmp_path):
        """A pre-check must never be stricter than pixi itself: an
        unrecognized environment name falls back to the permissive union
        of all tasks rather than returning empty."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment="nonexistent-env"
        )

        assert result["exists"] is True


class TestResolveTaskName:
    """Test suite for DirectPixiExecutionAdapter.resolve_task_name.

    Task vocabulary varies per target project, so a hardcoded task name is
    the same category of bug as a hardcoded path. resolve_task_name must
    pick the first alias candidate that actually exists in the target
    project's pixi manifest, be environment-aware, and return None (never
    guess) when no candidate exists.
    """

    def _make_adapter(self, tmp_path) -> DirectPixiExecutionAdapter:
        return DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))

    def _write_pyproject(self, tmp_path, content: str) -> None:
        (tmp_path / "pyproject.toml").write_text(textwrap.dedent(content))

    def test_picks_conventional_alias_when_only_it_exists(self, tmp_path):
        """A manifest defining 'lint' but not 'ruff-check' must resolve the
        'ruff' tool to 'lint' (first, most-conventional candidate)."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            lint = "ruff check src/"
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.resolve_task_name("ruff", working_dir=str(tmp_path))

        assert result == "lint"

    def test_falls_back_to_later_alias_when_conventional_name_absent(self, tmp_path):
        """When only 'ruff-check' exists (no 'lint'), that alias must be
        picked instead of returning None."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            ruff-check = "ruff check src/"
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.resolve_task_name("ruff", working_dir=str(tmp_path))

        assert result == "ruff-check"

    def test_returns_none_when_no_candidate_exists(self, tmp_path):
        """Neither 'lint', 'ruff-check', nor 'ruff' defined -> None, not a guess."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            build = "echo build"
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.resolve_task_name("ruff", working_dir=str(tmp_path))

        assert result is None

    def test_resolution_is_environment_aware(self, tmp_path):
        """A feature-scoped 'lint' task only resolves when the requested
        environment activates that feature; a differently-scoped
        environment must not see it."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.feature.dev.tasks]
            devtask = "echo dev"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
            dev-only = {features = ["dev"]}
        """,
        )
        adapter = self._make_adapter(tmp_path)

        found = adapter.resolve_task_name(
            "ruff", working_dir=str(tmp_path), environment="quality"
        )
        not_found = adapter.resolve_task_name(
            "ruff", working_dir=str(tmp_path), environment="dev-only"
        )

        assert found == "lint"
        assert not_found is None

    def test_explicit_candidate_list_is_honored(self, tmp_path):
        """Passing an explicit list (instead of a known tool name) tries
        those candidates in order rather than consulting TOOL_TASK_ALIASES."""
        self._write_pyproject(
            tmp_path,
            """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            security = "bandit -r src/"
        """,
        )
        adapter = self._make_adapter(tmp_path)

        result = adapter.resolve_task_name(
            ["security-scan", "security"], working_dir=str(tmp_path)
        )

        assert result == "security"


class TestTimeoutDurationDiagnostics:
    """Test suite for timeout diagnostics based on recorded task durations.

    A timeout with no duration context is indistinguishable from a hang or
    genuinely slow work. These tests verify the diagnostic text compares a
    timeout against real recorded history, and never fabricates a baseline.
    """

    def _make_adapter(self) -> DirectPixiExecutionAdapter:
        logging_port = Mock()
        adapter = DirectPixiExecutionAdapter(
            logging=logging_port, working_dir="/tmp/project"
        )
        adapter._is_pixi_project = Mock(return_value=True)
        adapter._get_available_tasks = Mock(return_value={"lint": "ruff check src/"})
        return adapter

    def _fake_completed_process(self, returncode: int = 0):
        result = Mock()
        result.returncode = returncode
        result.stdout = ""
        result.stderr = ""
        return result

    def test_timeout_without_history_reports_no_baseline_and_no_contention_claim(self):
        """No recorded samples -> message states no baseline was recorded and
        must not assert that the task was blocked."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="pixi run lint", timeout=300
            )

            result = adapter.run_task("lint", args=["src/"], timeout=300)

            assert result["success"] is False
            assert (
                "no duration baseline recorded for task 'lint' yet" in result["stderr"]
            )
            assert "likely blocked" not in result["stderr"]

    def test_timeout_with_fast_history_reports_median_ratio_and_blocked_claim(self):
        """Ten ~300ms samples then a 300s timeout -> ratio is ~1000x, so the
        message must include the median, the ratio, and the 'likely blocked'
        wording (ratio >= 10x threshold)."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()
            for _ in range(10):
                with patch(
                    "adapters.direct_pixi_execution.time.time", side_effect=[0.0, 0.3]
                ):
                    adapter.run_task("lint", args=["src/"], timeout=300)

            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="pixi run lint", timeout=300
            )
            mock_run.return_value = None
            result = adapter.run_task("lint", args=["src/"], timeout=300)

            assert result["success"] is False
            assert "0.3s over 10 samples" in result["stderr"]
            assert "1000x" in result["stderr"]
            assert "likely blocked" in result["stderr"]
            assert "pixi lock contention" in result["stderr"]

    def test_timeout_with_close_median_reports_ratio_without_blocked_claim(self):
        """History whose median is close to the timeout (ratio < 10x) ->
        median and ratio are reported but no 'likely blocked' assertion is
        made, since there isn't enough evidence to attribute a cause."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()
            for _ in range(5):
                with patch(
                    "adapters.direct_pixi_execution.time.time", side_effect=[0.0, 25.0]
                ):
                    adapter.run_task("lint", args=["src/"], timeout=30)

            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd="pixi run lint", timeout=30
            )
            mock_run.return_value = None
            result = adapter.run_task("lint", args=["src/"], timeout=30)

            assert result["success"] is False
            assert "25.0s over 5 samples" in result["stderr"]
            assert "1.2x" in result["stderr"]
            assert "likely blocked" not in result["stderr"]

    def test_duration_recorded_on_non_zero_exit_run(self):
        """A completed run that exits non-zero (e.g. lint found violations)
        must still contribute a duration sample -- only timeouts are excluded."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process(returncode=1)
            with patch(
                "adapters.direct_pixi_execution.time.time", side_effect=[0.0, 0.5]
            ):
                adapter.run_task("lint", args=["src/"], timeout=300)

            assert len(adapter._task_duration_history["lint"]) == 1
            assert adapter._task_duration_history["lint"][0] == 500.0

    def test_duration_history_deque_is_bounded(self):
        """More completed runs than the configured maxlen must not grow the
        per-task history without limit."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()
            maxlen = adapter._duration_history_maxlen
            for _ in range(maxlen + 15):
                with patch(
                    "adapters.direct_pixi_execution.time.time", side_effect=[0.0, 0.1]
                ):
                    adapter.run_task("lint", args=["src/"], timeout=300)

            assert len(adapter._task_duration_history["lint"]) == maxlen
