#\!/usr/bin/env python3
"""
Test server startup with automated fix integration.
"""

import os
import sys
import tempfile
from pathlib import Path

# Change to project directory
os.chdir(Path(__file__).parent)
sys.path.insert(0, "src")

def test_server_startup():
    """Test that the server can start with automated fix integration."""
    print("🚀 Testing Quality Assurance Server Startup")
    print("=" * 50)
    
    try:
        # Import required modules
        from core.container import Container
        from core.models import FixType, FixValidationMode
        
        print("✓ Successfully imported Container and models")
        
        # Create temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"✓ Created temp directory: {temp_dir}")
            
            # Mock MCP functions
            mock_mcp_functions = {
                "pixi_run_task": lambda task, args=None: {
                    "success": True,
                    "stdout": "Mock pixi task output",
                    "stderr": "",
                    "exit_code": 0
                },
                "pixi_task_exists": lambda task: {"exists": True},
                "pixi_project_status": lambda: {"status": "healthy"}
            }
            
            print("✓ Created mock MCP functions")
            
            # Initialize container
            try:
                container = Container(
                    working_dir=temp_dir,
                    mcp_functions=mock_mcp_functions
                )
                print("✓ Container initialized successfully")
                
                # Check if automated fix adapter is available
                if hasattr(container, 'automated_fix'):
                    automated_fix_adapter = container.automated_fix
                    print("✓ AutomatedFixAdapter is available in container")
                    print(f"  - Adapter type: {type(automated_fix_adapter).__name__}")
                    
                    # Test basic adapter functionality
                    fix_types = [FixType.IMPORTS, FixType.FORMATTING]
                    target_files = ["src/test.py"]
                    
                    # Test safety validation
                    safety_result = automated_fix_adapter.validate_fix_safety(fix_types, target_files)
                    print(f"✓ Safety validation works: {safety_result.success}")
                    
                    # Test preview functionality
                    preview_result = automated_fix_adapter.preview_fix_changes(fix_types, target_files)
                    print(f"✓ Preview functionality works: {len(preview_result)} fix types")
                    
                else:
                    print("❌ AutomatedFixAdapter not found in container")
                    return False
                
                # Check orchestration service has automated fix
                orchestration = container.orchestration_service
                if hasattr(orchestration, 'automated_fix') and orchestration.automated_fix:
                    print("✓ OrchestrationService has automated fix integration")
                else:
                    print("❌ OrchestrationService missing automated fix integration")
                    return False
                
                print("\n✅ All server startup tests passed\!")
                return True
                
            except Exception as e:
                print(f"❌ Container initialization failed: {e}")
                import traceback
                traceback.print_exc()
                return False
            
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_fix_types():
    """Test that all fix types are properly defined."""
    print("\n--- Testing Fix Types ---")
    
    try:
        from core.models import FixType, FixValidationMode
        
        expected_fix_types = [
            "imports", "formatting", "simple_issues", 
            "security", "type_annotations", "unused_variables"
        ]
        
        available_fix_types = [ft.value for ft in FixType]
        print(f"✓ Available fix types: {available_fix_types}")
        
        for expected in expected_fix_types:
            if expected in available_fix_types:
                print(f"  ✓ {expected}")
            else:
                print(f"  ❌ {expected} - MISSING")
                return False
        
        # Test validation modes
        validation_modes = [vm.value for vm in FixValidationMode]
        print(f"✓ Validation modes: {validation_modes}")
        
        return True
        
    except Exception as e:
        print(f"❌ Fix type test failed: {e}")
        return False


if __name__ == "__main__":
    print("🧪 Quality Assurance Server Test Suite")
    print("=" * 60)
    
    success = True
    
    # Test server startup
    if not test_server_startup():
        success = False
    
    # Test fix types
    if not test_fix_types():
        success = False
    
    if success:
        print("\n🎉 All tests passed\! Automated fix system is ready\!")
    else:
        print("\n💥 Some tests failed\!")
        sys.exit(1)
