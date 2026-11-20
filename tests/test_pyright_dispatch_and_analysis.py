"""
pyright is routed through the type-check dispatch of the comprehensive suite
and parsed/counted by QualityAnalysisAdapter (PR #10 review).
"""

import contextlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from adapters.quality_analysis import QualityAnalysisAdapter  # noqa: E402
from core.models import QualitySuiteConfiguration, QualityTool  # noqa: E402
from core.quality_service import QualityAssuranceService  # noqa: E402
from core.quality_orchestration_service import (  # noqa: E402
    QualityOrchestrationService,
)

PYRIGHT_OUTPUT = (
    "/abs/src/a.py\n"
    "  /abs/src/a.py:12:5 - error: Message text (reportFooBar)\n"
    "  /abs/src/a.py:20:1 - error: Other (reportUndefinedVariable)\n"
    "  /abs/src/b.py:3:1 - warning: Unused (reportUnusedImport)\n"
    "2 errors, 1 warning, 0 informations \n"
)


@pytest.mark.parametrize("parallel", [False, True])
def test_suite_dispatches_pyright_to_typecheck(parallel):
    service = QualityOrchestrationService(
        quality_executor=MagicMock(),
        quality_analyzer=MagicMock(),
        trend_analyzer=MagicMock(),
        logging=MagicMock(),
    )
    config = QualitySuiteConfiguration(
        included_tools=[QualityTool.PYRIGHT], parallel_execution=parallel
    )
    run = (
        service._execute_tools_parallel
        if parallel
        else service._execute_tools_sequential
    )

    _, failed, skipped = run(config)

    service.quality_executor.execute_typecheck_assessment.assert_called_once()
    assert (
        service.quality_executor.execute_typecheck_assessment.call_args.kwargs["tool"]
        == QualityTool.PYRIGHT
    )
    assert skipped == []
    assert failed == []


def test_quality_service_suite_dispatches_pyright_to_typecheck():
    service = QualityAssuranceService(quality_executor=MagicMock(), logging=MagicMock())
    service.execute_typecheck_assessment = MagicMock()
    config = QualitySuiteConfiguration(included_tools=[QualityTool.PYRIGHT])

    # Only the dispatch is under test; aggregating a mock result may raise.
    with contextlib.suppress(Exception):
        service.execute_comprehensive_suite(config)

    service.execute_typecheck_assessment.assert_called_once_with(
        tool=QualityTool.PYRIGHT
    )


class TestQualityAnalysisPyright:
    def test_parse_tool_output_builds_pyright_violations_and_type_errors(self):
        result = QualityAnalysisAdapter().parse_tool_output(
            QualityTool.PYRIGHT, PYRIGHT_OUTPUT, 1
        )

        assert len(result.violations) == 3
        assert {v.tool for v in result.violations} == {QualityTool.PYRIGHT}
        assert result.violations[0].rule_code == "reportFooBar"
        assert result.violations[0].line_number == 12
        assert result.parsed_metrics.type_errors == 2
        assert result.assessment_type.value == "typecheck"
