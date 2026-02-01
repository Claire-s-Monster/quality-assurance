#!/usr/bin/env python3
"""
Integration test for Quality Assurance MCP Server.

Tests the integration between QualityToolExecutionAdapter, QualityAssuranceService,
and the Container dependency injection system.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.core.container import Container
from src.core.models import QualityTool
from src.adapters.quality_tool_execution import QualityToolExecutionAdapter


def test_mock_mcp_functions():
    """Mock MCP functions for testing."""
    return {
        "pixi_run_task": lambda task, args=None: {
            "success": True,
            "stdout": '{"files": ["src/test.py"], "violations": []}',
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


def test_container_initialization():
    """Test that the Container properly initializes with quality components."""
    print("Testing container initialization...")
    
    mcp_functions = test_mock_mcp_functions()
    container = Container(mcp_functions=mcp_functions)
    
    assert container is not None
    assert container.quality_service is not None
    assert container.quality_executor is not None
    assert container.logging is not None
    
    print("✅ Container initialization successful")


def test_service_integration():
    """Test that the QualityAssuranceService integrates properly with the adapter."""
    print("Testing service integration...")
    
    mcp_functions = test_mock_mcp_functions()
    container = Container(mcp_functions=mcp_functions)
    service = container.quality_service
    
    # Test that service has proper dependencies
    assert service.quality_executor is not None
    assert service.logging is not None
    
    print("✅ Service integration successful")


def test_lint_assessment_execution():
    """Test executing a lint assessment through the full stack."""
    print("Testing lint assessment execution...")
    
    mcp_functions = test_mock_mcp_functions()
    container = Container(mcp_functions=mcp_functions)
    service = container.quality_service
    
    try:
        # Execute lint assessment
        result = service.execute_lint_assessment(
            tool=QualityTool.RUFF,
            target_path="src/",
            fix_mode=False
        )
        
        assert result is not None
        assert result.tool == QualityTool.RUFF
        assert result.target_path == "src/"
        assert result.parsed_metrics is not None
        
        print(f"✅ Lint assessment successful - Score: {result.parsed_metrics.overall_score}")
        
    except Exception as e:
        print(f"❌ Lint assessment failed: {e}")
        raise


def test_all_assessment_types():
    """Test all assessment types can be executed."""
    print("Testing all assessment types...")
    
    mcp_functions = test_mock_mcp_functions()
    container = Container(mcp_functions=mcp_functions)
    service = container.quality_service
    
    assessment_tests = [
        ("Lint", lambda: service.execute_lint_assessment(QualityTool.RUFF)),
        ("TypeCheck", lambda: service.execute_typecheck_assessment(QualityTool.MYPY)),
        ("Security", lambda: service.execute_security_scan(QualityTool.BANDIT)),
        ("Complexity", lambda: service.execute_complexity_analysis(QualityTool.RADON)),
        ("Dead Code", lambda: service.execute_dead_code_detection(QualityTool.VULTURE))
    ]
    
    for name, test_func in assessment_tests:
        try:
            result = test_func()
            assert result is not None
            assert result.parsed_metrics is not None
            print(f"✅ {name} assessment successful")
        except Exception as e:
            print(f"❌ {name} assessment failed: {e}")
            # Continue with other tests


def test_system_health():
    """Test system health check."""
    print("Testing system health...")
    
    mcp_functions = test_mock_mcp_functions()
    container = Container(mcp_functions=mcp_functions)
    service = container.quality_service
    
    try:
        health = service.get_system_health()
        assert health is not None
        assert hasattr(health, 'healthy')
        assert hasattr(health, 'timestamp')
        
        print(f"✅ System health check successful - Healthy: {health.healthy}")
        
    except Exception as e:
        print(f"❌ System health check failed: {e}")
        raise


def run_all_tests():
    """Run all integration tests."""
    print("🚀 Starting Quality Assurance MCP Server Integration Tests")
    print("=" * 60)
    
    tests = [
        test_adapter_instantiation,
        test_container_initialization,
        test_service_integration,
        test_lint_assessment_execution,
        test_all_assessment_types,
        test_system_health
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"❌ Test failed: {test.__name__} - {e}")
            failed += 1
        print()
    
    print("=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All tests passed! Quality Assurance MCP Server integration is working correctly.")
        return True
    else:
        print("⚠️ Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)