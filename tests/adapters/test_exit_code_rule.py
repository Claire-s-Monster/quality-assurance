"""Unit tests for the shared "exit 1 means findings" rule."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from adapters.direct_pixi_execution import (  # noqa: E402
    is_execution_failure,
    tool_ran_and_found_issues,
)


@pytest.mark.parametrize(
    ("result", "found_issues", "failure"),
    [
        ({"exit_code": 0}, False, False),
        ({"exit_code": 1, "stdout": "[{...}]"}, True, False),
        ({"exit_code": 1, "error": "boom"}, False, True),
        ({"exit_code": 2}, False, True),
        ({"exit_code": 127}, False, True),
        ({"exit_code": 0, "error": "boom"}, False, True),
        ({}, False, True),
    ],
    ids=[
        "exit0",
        "exit1_findings",
        "exit1_error_key",
        "exit2",
        "exit127",
        "exit0_error_key",
        "no_exit_code",
    ],
)
def test_exit_code_rule(result, found_issues, failure):
    assert tool_ran_and_found_issues(result) is found_issues
    assert is_execution_failure(result) is failure
