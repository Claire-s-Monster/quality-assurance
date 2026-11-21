"""Pixi subprocesses for a target project must not inherit the server's own
workspace pins (PIXI_WORKSPACE_MANIFEST etc., set because the server runs under
`pixi run`)."""

from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from core.subprocess_env import WORKSPACE_PINNING_VARS, target_project_env

RUN = "adapters.direct_pixi_execution.subprocess.run"


@pytest.fixture
def adapter(tmp_path):
    (tmp_path / "pixi.toml").write_text('[workspace]\nname = "t"\n')
    return DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))


@pytest.fixture
def pinned(monkeypatch):
    for var in WORKSPACE_PINNING_VARS:
        monkeypatch.setenv(var, "/qa/pyproject.toml")
    monkeypatch.setenv("CONDA_PREFIX", "/qa/.pixi/envs/default")
    monkeypatch.setenv("PATH", "/qa/bin:/usr/bin")


def _ok():
    return Mock(returncode=0, stdout="v1\n", stderr="")


def _captured_env(run_mock):
    env = run_mock.call_args.kwargs["env"]
    assert env is not None
    return env


def _assert_clean(env):
    for var in WORKSPACE_PINNING_VARS:
        assert var not in env
    assert env["PATH"] == "/qa/bin:/usr/bin"
    assert env["CONDA_PREFIX"] == "/qa/.pixi/envs/default"


class TestHelper:
    def test_strips_pins_keeps_rest_and_overrides(self, pinned):
        env = target_project_env({"RUFF_CACHE_DIR": "/tmp/rc"})
        _assert_clean(env)
        assert env["RUFF_CACHE_DIR"] == "/tmp/rc"

    def test_override_wins_even_for_pinning_var(self, pinned):
        env = target_project_env({"PIXI_PROJECT_ROOT": "/x"})
        assert env["PIXI_PROJECT_ROOT"] == "/x"


class TestSpawnSites:
    def test_run_task(self, adapter, pinned):
        with (
            patch.object(adapter, "_get_available_tasks", return_value={"t": "x"}),
            patch(RUN, return_value=_ok()) as run,
        ):
            adapter.run_task("t")
        _assert_clean(_captured_env(run))

    def test_project_status_pixi_info(self, adapter, pinned):
        with (
            patch.object(adapter, "_get_available_tasks", return_value={}),
            patch(RUN, return_value=_ok()) as run,
        ):
            adapter.get_project_status()
        _assert_clean(_captured_env(run))

    def test_tool_version_probe(self, adapter, pinned, tmp_path):
        with patch(RUN, return_value=_ok()) as run:
            adapter._get_tool_version("ruff", str(tmp_path))
        _assert_clean(_captured_env(run))
