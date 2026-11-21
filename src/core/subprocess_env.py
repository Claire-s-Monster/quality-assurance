"""Environment for subprocesses that run against a target project.

The server itself runs under ``pixi run``, which exports variables pinning pixi
to the server's own workspace. Inherited by a child ``pixi`` call they override
the target project's manifest (or stand in for one it lacks).
"""

import os
from typing import Mapping

# Variables that make pixi resolve the server's workspace/environment.
# CONDA_PREFIX, CONDA_DEFAULT_ENV and PIXI_IN_SHELL are left alone: pixi
# rewrites them when it activates the target environment, and they do not
# select a manifest. PATH is never touched.
WORKSPACE_PINNING_VARS: tuple[str, ...] = (
    "PIXI_WORKSPACE_MANIFEST",
    "PIXI_PROJECT_MANIFEST",
    "PIXI_PROJECT_ROOT",
    "PIXI_PROJECT_NAME",
    "PIXI_ENVIRONMENT_NAME",
)


def target_project_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """Copy of os.environ without workspace-pinning vars, plus `overrides`."""
    env = {k: v for k, v in os.environ.items() if k not in WORKSPACE_PINNING_VARS}
    if overrides:
        env.update(overrides)
    return env
