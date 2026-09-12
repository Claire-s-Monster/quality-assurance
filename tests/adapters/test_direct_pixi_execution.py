"""
Unit tests for DirectPixiExecutionAdapter.run_task command construction.

Verifies that the --environment flag is only emitted when an environment is
explicitly requested, and that it is placed immediately before the task name
as required by pixi's CLI argument order.
"""

import textwrap
from unittest.mock import Mock, patch

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter


class TestRunTaskCommandConstruction:
    """Test suite for pixi command construction in run_task."""

    def _make_adapter(self) -> DirectPixiExecutionAdapter:
        logging_port = Mock()
        adapter = DirectPixiExecutionAdapter(logging=logging_port, working_dir="/tmp/project")
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
            assert called_command[1:] == ["run", "--environment", "quality", "lint", "src/"]

            flag_index = called_command.index("--environment")
            task_index = called_command.index("lint")
            assert called_command[flag_index + 1] == "quality"
            assert flag_index < task_index


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
        self._write_pyproject(tmp_path, """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            build = "echo build"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists("lint", working_dir=str(tmp_path), environment="quality")

        assert result["exists"] is True

    def test_feature_scoped_task_found_when_environment_is_none(self, tmp_path):
        """With no environment specified, the permissive union of all
        feature tasks is used so pixi -- not this pre-check -- is the final
        authority on task resolution/ambiguity."""
        self._write_pyproject(tmp_path, """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists("lint", working_dir=str(tmp_path), environment=None)

        assert result["exists"] is True

    def test_feature_scoped_task_not_found_for_excluding_environment(self, tmp_path):
        """A feature-scoped task must NOT be found when the requested
        environment activates a different feature set that excludes it."""
        self._write_pyproject(tmp_path, """
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
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists("lint", working_dir=str(tmp_path), environment="dev-only")

        assert result["exists"] is False

    def test_environment_entry_dict_form_parses_features(self, tmp_path):
        """[tool.pixi.environments] entries in dict form
        {features=[...], solve-group=...} are parsed correctly."""
        self._write_pyproject(tmp_path, """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"], solve-group = "default"}
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists("lint", working_dir=str(tmp_path), environment="quality")

        assert result["exists"] is True

    def test_environment_entry_bare_list_form_parses_features(self, tmp_path):
        """[tool.pixi.environments] entries in bare-list shorthand form
        (equivalent to {features=[...]}) are parsed correctly."""
        self._write_pyproject(tmp_path, """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = ["quality"]
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists("lint", working_dir=str(tmp_path), environment="quality")

        assert result["exists"] is True

    def test_top_level_task_still_found_no_regression(self, tmp_path):
        """Top-level [tool.pixi.tasks] entries remain discoverable alongside
        feature-scoped tasks, even when an environment filter is active."""
        self._write_pyproject(tmp_path, """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.tasks]
            build = "echo build"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists("build", working_dir=str(tmp_path), environment="quality")

        assert result["exists"] is True

    def test_unknown_environment_falls_back_to_permissive_union(self, tmp_path):
        """A pre-check must never be stricter than pixi itself: an
        unrecognized environment name falls back to the permissive union
        of all tasks rather than returning empty."""
        self._write_pyproject(tmp_path, """
            [project]
            name = "demo"
            version = "0.1.0"

            [tool.pixi.feature.quality.tasks]
            lint = "ruff check src/"

            [tool.pixi.environments]
            quality = {features = ["quality"]}
        """)
        adapter = self._make_adapter(tmp_path)

        result = adapter.task_exists(
            "lint", working_dir=str(tmp_path), environment="nonexistent-env"
        )

        assert result["exists"] is True
