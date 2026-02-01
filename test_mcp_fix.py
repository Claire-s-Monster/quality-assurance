#!/usr/bin/env python3
"""
Test the MCP server's automated fix function directly.
"""

import json
import sys
from pathlib import Path

# Add the MCP server location to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_mcp_automated_fix():
    """Test the MCP quality_apply_automated_fixes function."""
    print("🔧 Testing MCP Automated Fix Function")
    print("=" * 50)
    
    try:
        # Import the MCP server module
        from quality_assurance.server import quality_apply_automated_fixes
        
        print("✓ Successfully imported quality_apply_automated_fixes")
        
        # Test with basic parameters
        result = quality_apply_automated_fixes(
            fix_types=["imports", "formatting"],
            dry_run=True,
            backup_before_fix=True,
            validation_mode="strict"
        )
        
        print(f"✓ MCP function executed successfully")
        print(f"✓ Result type: {type(result)}")
        
        if isinstance(result, dict):
            print(f"✓ Result keys: {list(result.keys())}")
            
            # Check for expected result structure
            if "operation_summary" in result:
                print("✓ Operation summary present")
                summary = result["operation_summary"]
                print(f"  - Dry run: {summary.get('dry_run', 'N/A')}")
                print(f"  - Total changes: {summary.get('total_changes_applied', 'N/A')}")
                
            if "fix_results" in result:
                print("✓ Fix results present")
                fix_results = result["fix_results"]
                print(f"  - Successful fixes: {len(fix_results.get('successful_fixes', []))}")
                print(f"  - Failed fixes: {len(fix_results.get('failed_fixes', []))}")
                
            if "error" in result:
                print(f"⚠️ Function returned error: {result['error']}")
                if "message" in result:
                    print(f"⚠️ Error message: {result['message']}")
            else:
                print("✅ No errors in result")
        else:
            print(f"⚠️ Unexpected result type: {type(result)}")
            print(f"Result: {result}")
        
        return True
        
    except ImportError as e:
        print(f"❌ Failed to import MCP function: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_mcp_automated_fix()
    if success:
        print("\n🎉 MCP automated fix test completed!")
    else:
        print("\n💥 MCP automated fix test failed!")
        sys.exit(1)