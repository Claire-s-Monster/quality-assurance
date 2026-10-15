"""
Unit tests for QualityAssuranceService.get_system_health.

Verifies that the health check genuinely probes the pixi executable and
does not fabricate performance metrics (the previous implementation always
reported healthy=True with hardcoded average_assessment_time_ms=500.0 and
cache_hit_rate=85.0, even when pixi could not be resolved).
"""

from unittest.mock import Mock

from core.quality_service import QualityAssuranceService


def _make_service(
    pixi_bin: str, working_dir: str = "/tmp/project"
) -> QualityAssuranceService:
    """Build a QualityAssuranceService with a fake quality_executor.pixi_executor."""
    pixi_executor = Mock()
    pixi_executor._pixi_bin = pixi_bin
    pixi_executor.working_dir = working_dir
    pixi_executor.task_exists = Mock(return_value={"exists": True})

    quality_executor = Mock()
    quality_executor.pixi_executor = pixi_executor

    logging_port = Mock()

    return QualityAssuranceService(
        quality_executor=quality_executor, logging=logging_port
    )


class TestGetSystemHealthPixiProbe:
    """Test suite for real pixi executable probing in get_system_health."""

    def test_unresolvable_pixi_reports_unhealthy_with_issue(self, tmp_path):
        """When the pixi binary cannot be resolved, healthy must be False
        and active_issues must name the problem, not silently report all-clear."""
        service = _make_service(
            pixi_bin="/nonexistent/path/to/pixi", working_dir=str(tmp_path)
        )

        health = service.get_system_health()

        assert health.pixi_environment_healthy is False
        assert health.healthy is False
        assert len(health.active_issues) > 0
        assert any("pixi" in issue.lower() for issue in health.active_issues)
        assert any(
            "/nonexistent/path/to/pixi" in issue for issue in health.active_issues
        )

    def test_resolvable_executable_pixi_reports_healthy(self, tmp_path):
        """When the pixi binary genuinely resolves to an executable file,
        pixi_environment_healthy must be True (a real, varying probe)."""
        fake_pixi = tmp_path / "pixi"
        fake_pixi.write_text("#!/bin/sh\necho fake pixi\n")
        fake_pixi.chmod(0o755)

        service = _make_service(pixi_bin=str(fake_pixi), working_dir=str(tmp_path))

        health = service.get_system_health()

        assert health.pixi_environment_healthy is True

    def test_performance_metrics_are_not_hardcoded_constants(self, tmp_path):
        """average_assessment_time_ms and cache_hit_rate must not be the
        fabricated 500.0 / 85.0 placeholders that existed regardless of
        actual conditions."""
        service = _make_service(pixi_bin="/nonexistent/pixi", working_dir=str(tmp_path))

        health = service.get_system_health()

        assert health.average_assessment_time_ms != 500.0
        assert health.cache_hit_rate != 85.0
        # No real metrics source is wired in, so None is the honest value.
        assert health.average_assessment_time_ms is None
        assert health.cache_hit_rate is None

    def test_quality_tools_available_reflects_real_task_probe(self, tmp_path):
        """quality_tools_available must come from a real task_exists probe,
        not a hardcoded True."""
        service = _make_service(pixi_bin="/nonexistent/pixi", working_dir=str(tmp_path))
        service.quality_executor.pixi_executor.task_exists = Mock(
            return_value={"exists": False}
        )

        health = service.get_system_health()

        assert health.quality_tools_available is False
        assert any(
            "missing expected pixi quality tasks" in issue.lower()
            for issue in health.active_issues
        )

    def test_alternate_task_naming_is_reported_healthy(self, tmp_path):
        """Regression test: a project defining security-scan,
        complexity-check, and dead-code-check (this repo's actual pixi
        task names) must be reported healthy, not flagged as missing
        expected tasks under the old hardcoded security/complexity/dead-code
        vocabulary."""
        fake_pixi = tmp_path / "pixi"
        fake_pixi.write_text("#!/bin/sh\necho fake pixi\n")
        fake_pixi.chmod(0o755)

        service = _make_service(pixi_bin=str(fake_pixi), working_dir=str(tmp_path))
        available_tasks = {
            "lint",
            "typecheck",
            "security-scan",
            "complexity-check",
            "dead-code-check",
        }
        service.quality_executor.pixi_executor.task_exists = Mock(
            side_effect=lambda name: {"exists": name in available_tasks}
        )

        health = service.get_system_health()

        assert health.healthy is True
        assert health.quality_tools_available is True
        assert not any(
            "missing expected pixi quality tasks" in issue.lower()
            for issue in health.active_issues
        )

    def test_missing_optional_task_does_not_set_unhealthy(self, tmp_path):
        """A missing optional quality task (e.g. dead-code-check/dead-code
        absent) must not flip healthy to False; it is informational only."""
        fake_pixi = tmp_path / "pixi"
        fake_pixi.write_text("#!/bin/sh\necho fake pixi\n")
        fake_pixi.chmod(0o755)

        service = _make_service(pixi_bin=str(fake_pixi), working_dir=str(tmp_path))
        available_tasks = {"lint", "typecheck", "security-scan", "complexity-check"}
        service.quality_executor.pixi_executor.task_exists = Mock(
            side_effect=lambda name: {"exists": name in available_tasks}
        )

        health = service.get_system_health()

        assert health.healthy is True
        assert health.quality_tools_available is True
        assert any("dead-code-check" in rec for rec in health.recommendations)
        assert not any("dead-code" in issue.lower() for issue in health.active_issues)
