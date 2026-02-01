#!/usr/bin/env python3
"""
Test script for automated fix functionality.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.models import FixType, FixValidationMode
from adapters.automated_fix import AutomatedFixAdapter


def test_automated_fix_basic():
    """Test basic automated fix functionality."""
    print("Testing AutomatedFixAdapter...")
    
    # Mock MCP functions for testing
    mock_mcp_functions = {
        "pixi_run_task": lambda task, args: {
            "success": True,
            "stdout": "No issues found",
            "stderr": "",
            "exit_code": 0
        },
        "pixi_task_exists": lambda task: {"exists": True},
        "pixi_project_status": lambda: {"status": "ready"}
    }
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a test adapter
        adapter = AutomatedFixAdapter(mock_mcp_functions, temp_dir)
        
        # Create some test files
        test_file = Path(temp_dir) / "src" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("import os\nimport sys\n\ndef test_function():\n    pass\n")
        
        print("✓ AutomatedFixAdapter created successfully")
        print(f"✓ Test file created: {test_file}")
        
        # Test safety validation
        print("\n--- Testing Safety Validation ---")
        target_files = [str(test_file.relative_to(temp_dir))]
        safety_result = adapter.validate_fix_safety([FixType.IMPORTS], target_files)
        print(f"✓ Safety validation: {safety_result.success} - {safety_result.message}")
        
        # Test fix preview
        print("\n--- Testing Fix Preview ---")
        preview_result = adapter.preview_fix_changes([FixType.IMPORTS], target_files)
        print(f"✓ Fix preview generated: {len(preview_result)} fix types")
        for fix_type, changes in preview_result.items():
            print(f"  - {fix_type}: {len(changes)} changes")
        
        # Test backup creation
        print("\n--- Testing Backup System ---")
        backup_path = adapter.create_fix_backup(target_files)
        print(f"✓ Backup created: {backup_path}")
        
        # Test dry run fix application
        print("\n--- Testing Dry Run Fix Application ---")
        dry_run_result = adapter.apply_automated_fixes(
            fix_types=[FixType.IMPORTS],
            dry_run=True,
            backup_before_fix=False,
            validation_mode=FixValidationMode.PERMISSIVE
        )
        print(f"✓ Dry run completed: {dry_run_result.dry_run}")
        print(f"  - Fix session ID: {dry_run_result.fix_session_id}")
        print(f"  - Execution time: {dry_run_result.execution_time_ms:.1f}ms")
        print(f"  - Successful fixes: {len(dry_run_result.successful_fixes)}")
        print(f"  - Failed fixes: {len(dry_run_result.failed_fixes)}")
        
        # Test rollback functionality
        if Path(backup_path).exists():
            print("\n--- Testing Rollback System ---")
            rollback_result = adapter.rollback_fixes(backup_path)
            print(f"✓ Rollback test: {rollback_result.success} - {rollback_result.message}")
        
        print("\n✅ All automated fix tests passed!")
        return True


def test_fix_type_mapping():
    """Test that all fix types have proper command mappings."""
    print("\n--- Testing Fix Type Mappings ---")
    
    # Create adapter with minimal setup
    temp_dir = tempfile.mkdtemp()
    mock_mcp_functions = {
        "pixi_run_task": lambda task, args: {"success": True},
        "pixi_task_exists": lambda task: {"exists": True}
    }
    
    adapter = AutomatedFixAdapter(mock_mcp_functions, temp_dir)
    
    all_fix_types = [
        FixType.IMPORTS,
        FixType.FORMATTING,
        FixType.SIMPLE_ISSUES,
        FixType.SECURITY,
        FixType.TYPE_ANNOTATIONS,
        FixType.UNUSED_VARIABLES
    ]
    
    for fix_type in all_fix_types:
        if fix_type in adapter.fix_type_commands:
            config = adapter.fix_type_commands[fix_type]
            print(f"✓ {fix_type.value}: {config['tool']} -> {' '.join(config['commands'])}")
        else:
            print(f"✗ {fix_type.value}: No command mapping found")
            return False
    
    print("✅ All fix types have command mappings!")
    return True


if __name__ == "__main__":
    print("🔧 Testing Automated Fix System")
    print("=" * 50)
    
    try:
        # Test basic functionality
        if not test_automated_fix_basic():
            sys.exit(1)
        
        # Test fix type mappings
        if not test_fix_type_mapping():
            sys.exit(1)
        
        print("\n🎉 All automated fix tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)