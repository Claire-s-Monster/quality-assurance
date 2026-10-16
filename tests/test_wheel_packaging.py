"""The built wheel must ship every top-level package the server imports."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip(
    "hatchling.build", reason="hatchling (build backend) not installed in test env"
)

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED_MEMBERS = [
    "quality_assurance/server.py",
    "core/container.py",
    "core/models.py",
    "adapters/direct_pixi_execution.py",
]


@pytest.fixture(scope="module")
def wheel_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("wheel")
    code = (
        "import sys; from hatchling.build import build_wheel; "
        "print(build_wheel(sys.argv[1]))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code, str(out_dir)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=110,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return out_dir / result.stdout.strip().splitlines()[-1]


@pytest.mark.slow
def test_wheel_contains_core_and_adapters(wheel_path: Path) -> None:
    with zipfile.ZipFile(wheel_path) as zf:
        names = set(zf.namelist())
    missing = [m for m in REQUIRED_MEMBERS if m not in names]
    assert not missing, f"wheel is missing: {missing}"


@pytest.mark.slow
def test_wheel_entry_modules_import_without_pythonpath(
    wheel_path: Path, tmp_path: Path
) -> None:
    target = tmp_path / "site"
    with zipfile.ZipFile(wheel_path) as zf:
        zf.extractall(target)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    code = (
        "import quality_assurance.server, quality_assurance.lean_server, "
        "quality_assurance.http_lean_server, core, adapters; "
        "from pathlib import Path; t = Path.cwd().resolve(); "
        "assert all(Path(m.__file__).resolve().is_relative_to(t) "
        "for m in (quality_assurance.server, core, adapters))"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        timeout=110,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-1500:]
