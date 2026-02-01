#!/usr/bin/env python3
"""
Minimal integration test for Quality Tool Execution Adapter.

Tests the core quality assessment functionality without dependencies
on other adapters that may have missing imports.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.adapters.quality_tool_execution import QualityToolExecutionAdapter
from src.core.models import QualityTool, QualityAssessmentType, ExecutionStatus


def test_mock_mcp_functions():
    """Mock MCP functions for testing."""
    return {
        "pixi_run_task": lambda task, args=None: {
            "success": True,
            "stdout": '[]',  # Empty JSON array for no violations
            "stderr": "",
            "exit_code": 0,
            "execution_time": 1.5
        },
        "pixi_task_exists": lambda task: {"exists": True, "working_dir": "/test"},
        "pixi_project_status": lambda: {"healthy": True, "pixi_active": True}
    }


def test_adapter_instantiation():
    """Test that the QualityToolExecutionAdapter can be instantiated."""
    print("Testing adapter instantiation...")
    
    mcp_functions = test_mock_mcp_functions()
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    assert adapter is not None
    assert adapter.pixi_run_task is not None
    assert adapter.pixi_task_exists is not None
    assert adapter.pixi_project_status is not None
    
    print("✅ Adapter instantiation successful")
    return True


def test_lint_assessment():
    """Test lint assessment execution."""
    print("Testing lint assessment...")
    
    mcp_functions = test_mock_mcp_functions()
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    try:
        result = adapter.execute_lint_assessment(
            tool=QualityTool.RUFF,
            target_path="src/",
            fix_mode=False
        )
        
        assert result is not None
        assert result.tool == QualityTool.RUFF
        assert result.assessment_type == QualityAssessmentType.LINT
        assert result.target_path == "src/"
        assert result.parsed_metrics is not None
        assert hasattr(result, 'recommendations')
        
        print(f"✅ Lint assessment successful - Status: {result.status}")
        print(f"   Tool: {result.tool.value}")
        print(f"   Score: {result.parsed_metrics.overall_score}")
        print(f"   Violations: {len(result.violations)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Lint assessment failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_typecheck_assessment():
    """Test typecheck assessment execution."""
    print("Testing typecheck assessment...")
    
    mcp_functions = test_mock_mcp_functions()
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    try:
        result = adapter.execute_typecheck_assessment(
            tool=QualityTool.MYPY,
            strict_mode=False
        )
        
        assert result is not None
        assert result.tool == QualityTool.MYPY
        assert result.assessment_type == QualityAssessmentType.TYPECHECK
        assert result.parsed_metrics is not None
        
        print(f"✅ Typecheck assessment successful - Status: {result.status}")
        print(f"   Tool: {result.tool.value}")
        print(f"   Type errors: {result.parsed_metrics.type_errors}")
        
        return True
        
    except Exception as e:
        print(f"❌ Typecheck assessment failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_security_scan():
    """Test security scan execution."""
    print("Testing security scan...")
    
    mcp_functions = test_mock_mcp_functions()
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    try:
        result = adapter.execute_security_scan(
            tool=QualityTool.BANDIT,
            scan_type="all"
        )
        
        assert result is not None
        assert result.tool == QualityTool.BANDIT
        assert result.assessment_type == QualityAssessmentType.SECURITY
        assert result.parsed_metrics is not None
        assert hasattr(result, 'security_issues')
        
        print(f"✅ Security scan successful - Status: {result.status}")
        print(f"   Tool: {result.tool.value}")
        print(f"   Security issues: {len(result.security_issues)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Security scan failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_complexity_analysis():
    """Test complexity analysis execution."""
    print("Testing complexity analysis...")
    
    mcp_functions = test_mock_mcp_functions()
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    try:
        result = adapter.execute_complexity_analysis(
            tool=QualityTool.RADON,
            complexity_threshold=10
        )
        
        assert result is not None
        assert result.tool == QualityTool.RADON
        assert result.assessment_type == QualityAssessmentType.COMPLEXITY
        assert result.parsed_metrics is not None
        assert hasattr(result, 'complexity_results')
        
        print(f"✅ Complexity analysis successful - Status: {result.status}")
        print(f"   Tool: {result.tool.value}")
        print(f"   Avg complexity: {result.parsed_metrics.average_complexity}")
        
        return True
        
    except Exception as e:
        print(f"❌ Complexity analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_dead_code_detection():
    """Test dead code detection execution."""
    print("Testing dead code detection...")
    
    mcp_functions = test_mock_mcp_functions()
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    try:
        result = adapter.execute_dead_code_detection(
            tool=QualityTool.VULTURE,
            confidence_threshold=80
        )
        
        assert result is not None
        assert result.tool == QualityTool.VULTURE
        assert result.assessment_type == QualityAssessmentType.DEAD_CODE
        assert result.parsed_metrics is not None
        assert hasattr(result, 'dead_code_results')
        
        print(f"✅ Dead code detection successful - Status: {result.status}")
        print(f"   Tool: {result.tool.value}")
        print(f"   Dead code count: {result.parsed_metrics.dead_code_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Dead code detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """Test error handling with invalid task."""
    print("Testing error handling...")
    
    # Mock function that simulates task not existing
    def mock_task_exists(task):
        return {"exists": False, "working_dir": "/test"}
    
    mcp_functions = test_mock_mcp_functions()
    mcp_functions["pixi_task_exists"] = mock_task_exists
    
    adapter = QualityToolExecutionAdapter(mcp_functions)
    
    try:
        result = adapter.execute_lint_assessment(tool=QualityTool.RUFF)
        
        # Should return error result
        assert result is not None
        assert result.status == ExecutionStatus.ERROR
        assert "not found" in result.raw_output
        
        print(f"✅ Error handling successful - Status: {result.status}")
        print(f"   Error message captured: {result.raw_output[:50]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all minimal integration tests."""
    print("🚀 Starting Quality Tool Execution Adapter Tests")
    print("=" * 60)
    
    tests = [
        test_adapter_instantiation,
        test_lint_assessment,
        test_typecheck_assessment,
        test_security_scan,
        test_complexity_analysis,
        test_dead_code_detection,
        test_error_handling
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            success = test()
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test failed: {test.__name__} - {e}")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Quality Tool Execution Adapter is working correctly.")
        return True
    else:
        print("⚠️ Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)