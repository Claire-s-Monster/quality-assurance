"""environments_providing_tool counts pixi target tables for this host only."""

from unittest.mock import Mock, patch

import pytest

from adapters.direct_pixi_execution import DirectPixiExecutionAdapter
from core import pixi_platform
from core.pixi_platform import current_pixi_platform, target_key_matches

MODULE = "adapters.direct_pixi_execution.current_pixi_platform"


def _providers(tmp_path, manifest, host, tool="pyright"):
    (tmp_path / "pixi.toml").write_text(manifest)
    adapter = DirectPixiExecutionAdapter(logging=Mock(), working_dir=str(tmp_path))
    with patch(MODULE, return_value=host):
        return adapter.environments_providing_tool(tool)


TOP = '[target.{key}.dependencies]\npyright = "*"\n'
FEATURE = (
    "[environments]\nqa = ['qa']\n\n"
    "[feature.qa.target.{key}.dependencies]\npyright = '*'\n"
)


class TestTargetScopes:
    def test_matching_top_level_target(self, tmp_path):
        assert _providers(tmp_path, TOP.format(key="linux-64"), "linux-64") == [
            "default"
        ]

    def test_non_matching_top_level_target(self, tmp_path):
        assert _providers(tmp_path, TOP.format(key="osx-arm64"), "linux-64") == []

    def test_matching_feature_target(self, tmp_path):
        assert _providers(tmp_path, FEATURE.format(key="linux-64"), "linux-64") == [
            "qa"
        ]

    def test_non_matching_feature_target(self, tmp_path):
        assert _providers(tmp_path, FEATURE.format(key="win-64"), "linux-64") == []

    @pytest.mark.parametrize(
        ("key", "host", "expected"),
        [
            ("unix", "linux-64", True),
            ("unix", "osx-arm64", True),
            ("unix", "win-64", False),
            ("linux", "linux-aarch64", True),
            ("linux", "osx-64", False),
            ("osx", "osx-arm64", True),
            ("win", "win-64", True),
            ("win", "linux-64", False),
            ("linux-64", "linux-aarch64", False),
        ],
    )
    def test_selector_semantics(self, tmp_path, key, host, expected):
        result = _providers(tmp_path, TOP.format(key=key), host)
        assert result == (["default"] if expected else [])
        assert target_key_matches(key, host) is expected

    def test_unix_selector_on_linux(self, tmp_path):
        assert _providers(tmp_path, TOP.format(key="unix"), "linux-64") == ["default"]

    def test_unknown_platform_is_permissive(self, tmp_path):
        assert _providers(tmp_path, TOP.format(key="osx-arm64"), None) == ["default"]

    def test_untargeted_dependency_always_counts(self, tmp_path):
        assert _providers(tmp_path, '[dependencies]\npyright = "*"\n', "win-64") == [
            "default"
        ]


class TestPlatformMapping:
    @pytest.mark.parametrize(
        ("system", "machine", "expected"),
        [
            ("Linux", "x86_64", "linux-64"),
            ("Linux", "aarch64", "linux-aarch64"),
            ("Linux", "ppc64le", "linux-ppc64le"),
            ("Darwin", "x86_64", "osx-64"),
            ("Darwin", "arm64", "osx-arm64"),
            ("Windows", "AMD64", "win-64"),
            ("Windows", "ARM64", "win-arm64"),
            ("FreeBSD", "amd64", None),
            ("Linux", "riscv64", None),
        ],
    )
    def test_mapping(self, system, machine, expected):
        with (
            patch.object(pixi_platform.platform, "system", return_value=system),
            patch.object(pixi_platform.platform, "machine", return_value=machine),
        ):
            assert current_pixi_platform() == expected
