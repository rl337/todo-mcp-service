"""
Verify command - Check that all MCP_FUNCTIONS have corresponding handlers in main.py.
"""
import argparse
import re
import ast
import sys
from pathlib import Path

from todorama.__main__ import Command

logger = None  # Will be set in init()


def extract_mcp_functions(functions_path: str) -> list:
    """Extract function names from MCP_FUNCTIONS."""
    with open(functions_path, 'r') as f:
        content = f.read()
    
    # Find MCP_FUNCTIONS = [
    start_idx = content.find('MCP_FUNCTIONS = [')
    if start_idx == -1:
        raise ValueError("MCP_FUNCTIONS not found")
    
    # Extract function names
    function_names = []
    pattern = r'"name":\s*"([^"]+)"'
    matches = re.findall(pattern, content[start_idx:])
    
    return matches


def extract_handlers(request_handlers_path: str) -> list:
    """Extract tool_name handlers from request_handlers.py."""
    with open(request_handlers_path, 'r') as f:
        content = f.read()
    
    # Find tool_map dictionary
    start_idx = content.find('tool_map = {')
    if start_idx == -1:
        raise ValueError("tool_map not found in request_handlers.py")
    
    # Extract tool names from tool_map
    # Pattern: "tool_name": lambda: ...
    pattern = r'"([^"]+)":\s*lambda'
    matches = re.findall(pattern, content[start_idx:])
    
    return matches


def verify_routing(functions_path: str, request_handlers_path: str) -> int:
    """Verify MCP function routing."""
    print("Verifying MCP function routing...")
    print("=" * 60)
    
    # Get functions from MCP_FUNCTIONS
    mcp_functions = extract_mcp_functions(functions_path)
    print(f"\nFound {len(mcp_functions)} functions in MCP_FUNCTIONS:")
    for func in sorted(mcp_functions):
        print(f"  - {func}")
    
    # Get handlers from request_handlers.py
    handlers = extract_handlers(request_handlers_path)
    print(f"\nFound {len(handlers)} handlers in request_handlers.py:")
    for handler in sorted(handlers):
        print(f"  - {handler}")
    
    # Compare
    print("\n" + "=" * 60)
    mcp_set = set(mcp_functions)
    handlers_set = set(handlers)
    
    missing_handlers = mcp_set - handlers_set
    extra_handlers = handlers_set - mcp_set
    
    if missing_handlers:
        print(f"\n✗ MISSING HANDLERS ({len(missing_handlers)}):")
        for func in sorted(missing_handlers):
            print(f"  - {func} (defined in MCP_FUNCTIONS but no handler in request_handlers.py)")
    else:
        print("\n✓ All MCP_FUNCTIONS have handlers")
    
    if extra_handlers:
        print(f"\n⚠️  EXTRA HANDLERS ({len(extra_handlers)}):")
        for handler in sorted(extra_handlers):
            print(f"  - {handler} (handler exists but not in MCP_FUNCTIONS)")
    else:
        print("\n✓ No extra handlers found")
    
    if not missing_handlers and not extra_handlers:
        print("\n✓ VERIFICATION PASSED: All functions are properly routed!")
        return 0
    else:
        print("\n✗ VERIFICATION FAILED: Routing issues found")
        return 1


class VerifyCommand(Command):
    """Command to verify MCP function routing."""
    
    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Add verify command arguments."""
        parser.add_argument(
            "--functions",
            default="todorama/mcp/functions.py",
            help="Path to functions.py file (default: todorama/mcp/functions.py)"
        )
        parser.add_argument(
            "--request-handlers",
            default="todorama/mcp/request_handlers.py",
            help="Path to request_handlers.py file (default: todorama/mcp/request_handlers.py)"
        )
    
    def init(self):
        """Initialize the verify command."""
        global logger
        import logging
        logger = logging.getLogger(__name__)
        super().init()
    
    def run(self) -> int:
        """Run the verify command."""
        base_path = Path(__file__).parent.parent.parent
        functions_path = base_path / self.args.functions
        request_handlers_path = base_path / self.args.request_handlers
        
        if not functions_path.exists():
            print(f"Error: Functions file not found: {functions_path}", file=sys.stderr)
            return 1
        
        if not request_handlers_path.exists():
            print(f"Error: Request handlers file not found: {request_handlers_path}", file=sys.stderr)
            return 1
        
        return verify_routing(str(functions_path), str(request_handlers_path))
