#!/usr/bin/env python3
"""
Test suite to verify lean server schema alignment with actual function implementations.

This test ensures that:
1. All tools in the lean server registry exist in the main server
2. Schema properties match function parameter names
3. FunctionTool objects can be properly invoked via .fn attribute
4. Server.py function calls match adapter signatures

Run with: pixi run python -m pytest tests/test_lean_server_schema_alignment.py -v
"""

import inspect
import sys
from pathlib import Path
from typing import Dict, Any, Set

import pytest

# Add source paths
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestLeanServerSchemaAlignment:
    """Test that lean server schemas match actual function signatures."""

    @pytest.fixture
    def lean_server_registry(self) -> Dict[str, Dict[str, Any]]:
        """Get the lean server tool registry."""
        from quality_assurance.lean_server import QualityAssuranceLeanMCP

        lean_mcp = QualityAssuranceLeanMCP(working_dir=".")
        return lean_mcp.tool_registry

    @pytest.fixture
    def main_server_module(self):
        """Get the main server module."""
        from quality_assurance import server as main_server

        return main_server

    def _get_function_parameters(self, func) -> Set[str]:
        """Extract parameter names from a function signature."""
        sig = inspect.signature(func)
        # Exclude 'self' for methods
        return {name for name in sig.parameters.keys() if name != "self"}

    def _get_schema_properties(self, schema: Dict[str, Any]) -> Set[str]:
        """Extract property names from a JSON schema."""
        if "properties" in schema:
            return set(schema["properties"].keys())
        return set()

    def test_pixi_aware_registry_description_mentions_gate_verdict(
        self, lean_server_registry
    ):
        """Clients discover the tool via the registry; it must point at gate_verdict."""
        entry = lean_server_registry["quality_execute_pixi_aware_assessment"]
        assert "gate_verdict" in entry["description"]

    def test_all_registry_tools_exist_in_server(
        self, lean_server_registry, main_server_module
    ):
        """Verify all tools in registry exist in main server."""
        missing_tools = []

        for tool_name in lean_server_registry.keys():
            if not hasattr(main_server_module, tool_name):
                missing_tools.append(tool_name)

        assert not missing_tools, f"Tools missing from main server: {missing_tools}"

    def test_all_tools_are_function_tools(
        self, lean_server_registry, main_server_module
    ):
        """Verify all tools are FunctionTool objects with .fn attribute."""
        from fastmcp.tools.tool import FunctionTool

        not_function_tools = []
        missing_fn_attr = []

        for tool_name in lean_server_registry.keys():
            if hasattr(main_server_module, tool_name):
                tool_obj = getattr(main_server_module, tool_name)

                if not isinstance(tool_obj, FunctionTool):
                    not_function_tools.append(tool_name)
                elif not hasattr(tool_obj, "fn"):
                    missing_fn_attr.append(tool_name)

        assert not not_function_tools, f"Not FunctionTool: {not_function_tools}"
        assert not missing_fn_attr, f"Missing .fn attribute: {missing_fn_attr}"

    def test_all_fn_attributes_are_callable(
        self, lean_server_registry, main_server_module
    ):
        """Verify all .fn attributes are callable."""
        not_callable = []

        for tool_name in lean_server_registry.keys():
            if hasattr(main_server_module, tool_name):
                tool_obj = getattr(main_server_module, tool_name)
                if hasattr(tool_obj, "fn"):
                    if not callable(tool_obj.fn):
                        not_callable.append(tool_name)

        assert not not_callable, f"Not callable: {not_callable}"

    def test_schema_properties_match_function_params(
        self, lean_server_registry, main_server_module
    ):
        """Verify schema properties match function parameter names."""
        mismatches = []

        for tool_name, tool_info in lean_server_registry.items():
            if not hasattr(main_server_module, tool_name):
                continue

            tool_obj = getattr(main_server_module, tool_name)
            if not hasattr(tool_obj, "fn"):
                continue

            # Get schema properties
            schema_props = self._get_schema_properties(tool_info.get("schema", {}))

            # Get function parameters
            func_params = self._get_function_parameters(tool_obj.fn)

            # Find mismatches
            in_schema_not_func = schema_props - func_params
            in_func_not_schema = func_params - schema_props

            if in_schema_not_func or in_func_not_schema:
                mismatches.append(
                    {
                        "tool": tool_name,
                        "in_schema_not_function": list(in_schema_not_func),
                        "in_function_not_schema": list(in_func_not_schema),
                        "schema_properties": list(schema_props),
                        "function_parameters": list(func_params),
                    }
                )

        if mismatches:
            report = "\n\nSchema/Function Parameter Mismatches:\n"
            report += "=" * 60 + "\n"
            for m in mismatches:
                report += f"\nTool: {m['tool']}\n"
                report += f"  Schema properties:    {m['schema_properties']}\n"
                report += f"  Function parameters:  {m['function_parameters']}\n"
                if m["in_schema_not_function"]:
                    report += f"  ❌ In schema but NOT in function: {m['in_schema_not_function']}\n"
                if m["in_function_not_schema"]:
                    report += f"  ⚠️  In function but NOT in schema: {m['in_function_not_schema']}\n"

            pytest.fail(report)

    def test_execute_tool_invocation_pattern(
        self, lean_server_registry, main_server_module
    ):
        """Test that the execute_tool invocation pattern works for all tools."""
        invocation_errors = []

        for tool_name in lean_server_registry.keys():
            if not hasattr(main_server_module, tool_name):
                invocation_errors.append(f"{tool_name}: Not found in server")
                continue

            tool_obj = getattr(main_server_module, tool_name)

            # Test the invocation pattern used in lean_server.py
            try:
                if hasattr(tool_obj, "fn"):
                    # This is the correct pattern - should not raise
                    assert callable(tool_obj.fn)
                else:
                    invocation_errors.append(f"{tool_name}: No .fn attribute")
            except Exception as e:
                invocation_errors.append(f"{tool_name}: {e}")

        assert not invocation_errors, "Invocation errors:\n" + "\n".join(
            invocation_errors
        )


class TestSchemaAlignmentReport:
    """Generate a detailed alignment report."""

    def test_generate_alignment_report(self, capsys):
        """Generate and print a complete alignment report."""
        from quality_assurance.lean_server import QualityAssuranceLeanMCP
        from quality_assurance import server as main_server

        lean_mcp = QualityAssuranceLeanMCP(working_dir=".")
        registry = lean_mcp.tool_registry

        print("\n" + "=" * 80)
        print("LEAN SERVER SCHEMA ALIGNMENT REPORT")
        print("=" * 80)

        all_passed = True

        for tool_name, tool_info in sorted(registry.items()):
            schema_props = set(tool_info.get("schema", {}).get("properties", {}).keys())

            if not hasattr(main_server, tool_name):
                print(f"\n❌ {tool_name}")
                print("   ERROR: Tool not found in main server!")
                all_passed = False
                continue

            tool_obj = getattr(main_server, tool_name)

            if not hasattr(tool_obj, "fn"):
                print(f"\n❌ {tool_name}")
                print("   ERROR: Not a FunctionTool (no .fn attribute)")
                all_passed = False
                continue

            sig = inspect.signature(tool_obj.fn)
            func_params = {n for n in sig.parameters.keys() if n != "self"}

            in_schema_not_func = schema_props - func_params
            in_func_not_schema = func_params - schema_props

            if in_schema_not_func or in_func_not_schema:
                print(f"\n❌ {tool_name}")
                print(f"   Schema:   {sorted(schema_props)}")
                print(f"   Function: {sorted(func_params)}")
                if in_schema_not_func:
                    print(
                        f"   ⛔ Schema declares but function doesn't accept: {in_schema_not_func}"
                    )
                if in_func_not_schema:
                    print(
                        f"   ⚠️  Function accepts but schema doesn't declare: {in_func_not_schema}"
                    )
                all_passed = False
            else:
                print(f"\n✅ {tool_name}")
                print(f"   Parameters: {sorted(schema_props)}")

        print("\n" + "=" * 80)
        if all_passed:
            print("✅ ALL TOOLS ALIGNED")
        else:
            print("❌ SOME TOOLS HAVE MISMATCHES - FIX REQUIRED")
        print("=" * 80 + "\n")

        # This test always passes - it's for reporting only
        # The actual assertions are in other tests


class TestAdapterAlignment:
    """Test that server.py function calls match adapter signatures."""

    # Map server function names to adapter method names
    SERVER_TO_ADAPTER_MAP = {
        "quality_execute_lint_assessment": "execute_lint_assessment",
        "quality_execute_typecheck_assessment": "execute_typecheck_assessment",
        "quality_execute_security_scan": "execute_security_scan",
        "quality_execute_complexity_analysis": "execute_complexity_analysis",
    }

    def test_adapter_methods_exist(self):
        """Verify all mapped adapter methods exist."""
        from adapters.quality_tool_execution import QualityToolExecutionAdapter

        missing = []
        for server_func, adapter_method in self.SERVER_TO_ADAPTER_MAP.items():
            if not hasattr(QualityToolExecutionAdapter, adapter_method):
                missing.append(f"{server_func} -> {adapter_method}")

        assert not missing, f"Missing adapter methods: {missing}"

    def test_adapter_signatures_accept_required_params(self):
        """Verify adapter methods accept all params that server.py passes."""
        from adapters.quality_tool_execution import QualityToolExecutionAdapter
        from quality_assurance import server as main_server

        mismatches = []

        for server_func_name, adapter_method_name in self.SERVER_TO_ADAPTER_MAP.items():
            # Get server function params
            if not hasattr(main_server, server_func_name):
                continue

            tool_obj = getattr(main_server, server_func_name)
            if not hasattr(tool_obj, "fn"):
                continue

            # Get adapter method params
            adapter_method = getattr(QualityToolExecutionAdapter, adapter_method_name)
            adapter_sig = inspect.signature(adapter_method)
            adapter_params = {n for n in adapter_sig.parameters.keys() if n != "self"}

            # Check key params that server passes are accepted by adapter
            # Note: adapter may have additional params with defaults
            critical_server_params = {"tool", "target_path"}
            missing_in_adapter = critical_server_params - adapter_params

            if missing_in_adapter:
                mismatches.append(
                    {
                        "server_func": server_func_name,
                        "adapter_method": adapter_method_name,
                        "missing": missing_in_adapter,
                    }
                )

        if mismatches:
            msg = "\nAdapter signature mismatches:\n"
            for m in mismatches:
                msg += f"  {m['server_func']} -> {m['adapter_method']}: missing {m['missing']}\n"
            pytest.fail(msg)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
