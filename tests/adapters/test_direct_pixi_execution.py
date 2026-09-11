"""
Unit tests for DirectPixiExecutionAdapter.run_task command construction.

Verifies that the --environment flag is only emitted when an environment is
explicitly requested, and that it is placed immediately before the task name
as required by pixi's CLI argument order.
"""

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
            assert called_command == ["pixi", "run", "lint", "src/"]
            assert "--environment" not in called_command

    def test_run_task_with_environment_inserts_flag_before_task(self):
        """When environment is provided, --environment <env> must precede the task name."""
        adapter = self._make_adapter()

        with patch("adapters.direct_pixi_execution.subprocess.run") as mock_run:
            mock_run.return_value = self._fake_completed_process()

            adapter.run_task("lint", args=["src/"], environment="quality")

            called_command = mock_run.call_args[0][0]
            assert called_command == ["pixi", "run", "--environment", "quality", "lint", "src/"]

            flag_index = called_command.index("--environment")
            task_index = called_command.index("lint")
            assert called_command[flag_index + 1] == "quality"
            assert flag_index < task_index
