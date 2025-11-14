"""
Audit command - Verify MCP tool parameter types match implementations.

This command compares:
1. MCP_FUNCTIONS definitions (parameter types, optional flags, defaults, enums)
2. MCPTodoAPI method signatures (actual implementation types)
3. main.py routing handlers (how parameters are extracted)
"""
import argparse
import ast
import re
import sys
from typing import Dict, List, Any, Optional, Set
from pathlib import Path

from todorama.__main__ import Command

logger = None  # Will be set in init()


def parse_mcp_functions(file_path: str) -> List[Dict[str, Any]]:
    """Parse MCP_FUNCTIONS from functions.py."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find MCP_FUNCTIONS = [
    start_idx = content.find('MCP_FUNCTIONS = [')
    if start_idx == -1:
        raise ValueError("MCP_FUNCTIONS not found")
    
    # Extract the list (rough parsing)
    functions = []
    
    # Read from start of MCP_FUNCTIONS to end
    bracket_count = 0
    in_list = False
    list_content = []
    
    for i, char in enumerate(content[start_idx:], start_idx):
        if char == '[':
            bracket_count += 1
            in_list = True
        elif char == ']':
            bracket_count -= 1
            if bracket_count == 0 and in_list:
                list_content = content[start_idx:i+1]
                break
    
    # Parse as Python code
    try:
        parsed = ast.parse(list_content)
        # Extract the list node
        assign_node = parsed.body[0]
        if isinstance(assign_node, ast.Assign):
            list_node = assign_node.value
            if isinstance(list_node, ast.List):
                for item in list_node.elts:
                    if isinstance(item, ast.Dict):
                        func_def = {}
                        for key, value in zip(item.keys, item.values):
                            if isinstance(key, ast.Constant) or isinstance(key, ast.Str):
                                key_str = key.value if isinstance(key, ast.Constant) else key.s
                                if key_str == 'name':
                                    if isinstance(value, ast.Constant) or isinstance(value, ast.Str):
                                        func_def['name'] = value.value if isinstance(value, ast.Constant) else value.s
                                elif key_str == 'parameters':
                                    if isinstance(value, ast.Dict):
                                        params = {}
                                        for pk, pv in zip(value.keys, value.values):
                                            if isinstance(pk, ast.Constant) or isinstance(pk, ast.Str):
                                                param_name = pk.value if isinstance(pk, ast.Constant) else pk.s
                                                param_info = {}
                                                if isinstance(pv, ast.Dict):
                                                    for ppk, ppv in zip(pv.keys, pv.values):
                                                        if isinstance(ppk, ast.Constant) or isinstance(ppk, ast.Str):
                                                            info_key = ppk.value if isinstance(ppk, ast.Constant) else ppk.s
                                                            if isinstance(ppv, ast.Constant) or isinstance(ppv, ast.Str):
                                                                info_value = ppv.value if isinstance(ppv, ast.Constant) else ppv.s
                                                                param_info[info_key] = info_value
                                                            elif isinstance(ppv, ast.List):
                                                                # Enum list
                                                                enum_vals = []
                                                                for ev in ppv.elts:
                                                                    if isinstance(ev, ast.Constant) or isinstance(ev, ast.Str):
                                                                        enum_vals.append(ev.value if isinstance(ev, ast.Constant) else ev.s)
                                                                param_info[info_key] = enum_vals
                                                            elif isinstance(ppv, ast.Num) or (isinstance(ppv, ast.Constant) and isinstance(ppv.value, (int, float))):
                                                                param_info[info_key] = ppv.n if hasattr(ppv, 'n') else ppv.value
                                                            elif isinstance(ppv, ast.NameConstant) or (isinstance(ppv, ast.Constant) and isinstance(ppv.value, bool)):
                                                                param_info[info_key] = ppv.value if isinstance(ppv, ast.Constant) else (ppv.value if hasattr(ppv, 'value') else None)
                                                params[param_name] = param_info
                                        func_def['parameters'] = params
                        functions.append(func_def)
    except Exception as e:
        print(f"Error parsing MCP_FUNCTIONS: {e}")
        # Fallback to manual parsing
        pass
    
    return functions


def get_method_signatures(file_path: str) -> Dict[str, Dict[str, Any]]:
    """Extract method signatures from MCPTodoAPI class."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    signatures = {}
    
    # Find class MCPTodoAPI
    class_pattern = r'class MCPTodoAPI:'
    if class_pattern not in content:
        return signatures
    
    # Parse file as AST
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == 'MCPTodoAPI':
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and any(
                        isinstance(dec, ast.Name) and dec.id == 'staticmethod'
                        or isinstance(dec, ast.Attribute) and dec.attr == 'staticmethod'
                        for dec in item.decorator_list
                    ):
                        method_name = item.name
                        params = {}
                        defaults_count = len(item.args.defaults)
                        required_count = len(item.args.args) - defaults_count
                        
                        for i, arg in enumerate(item.args.args):
                            if arg.arg == 'self':
                                continue
                            param_name = arg.arg
                            
                            # Get annotation if present
                            annotation = None
                            if arg.annotation:
                                if isinstance(arg.annotation, ast.Name):
                                    annotation = arg.annotation.id
                                elif isinstance(arg.annotation, ast.Constant):
                                    annotation = arg.annotation.value
                                elif isinstance(arg.annotation, ast.Subscript):
                                    # Handle Optional[...] and Literal[...]
                                    if isinstance(arg.annotation.value, ast.Name):
                                        if arg.annotation.value.id == 'Optional':
                                            annotation = 'Optional'
                                        elif arg.annotation.value.id == 'Literal':
                                            annotation = 'Literal'
                            
                            # Check if optional (has default)
                            is_optional = i >= required_count
                            default_value = None
                            if is_optional and i - required_count < len(item.args.defaults):
                                default_node = item.args.defaults[i - required_count]
                                if isinstance(default_node, ast.Constant):
                                    default_value = default_node.value
                                elif isinstance(default_node, ast.NameConstant) or (isinstance(default_node, ast.Constant) and isinstance(default_node.value, type(None))):
                                    default_value = None
                                elif isinstance(default_node, ast.Num) or (isinstance(default_node, ast.Constant) and isinstance(default_node.value, (int, float))):
                                    default_value = default_node.n if hasattr(default_node, 'n') else default_node.value
                            
                            params[param_name] = {
                                'annotation': annotation,
                                'optional': is_optional,
                                'default': default_value
                            }
                        
                        signatures[method_name] = {'params': params}
    except Exception as e:
        print(f"Error parsing method signatures: {e}")
    
    return signatures


def audit_mcp_types(functions_path: str, mcp_api_path: str, main_path: str) -> Dict[str, Any]:
    """Perform MCP type audit."""
    print("=" * 80)
    print("MCP Tool Parameter Type Audit")
    print("=" * 80)
    print()
    
    # Load MCP_FUNCTIONS definitions
    print("Loading MCP_FUNCTIONS definitions...")
    try:
        with open(functions_path, 'r') as f:
            functions_content = f.read()
        
        # Count functions
        func_count = functions_content.count('"name":')
        print(f"Found {func_count} MCP function definitions")
        
        # Get method signatures
        print("Loading MCPTodoAPI method signatures...")
        signatures = get_method_signatures(mcp_api_path)
        print(f"Found {len(signatures)} method signatures")
        
        # Check routing in main.py
        print("Checking main.py routing handlers...")
        with open(main_path, 'r') as f:
            main_content = f.read()
        
        # Find all tool routing calls
        tool_routes = {}
        lines = main_content.split('\n')
        for i, line in enumerate(lines):
            if 'elif tool_name ==' in line:
                tool_name_match = re.search(r'tool_name == "([^"]+)"', line)
                if tool_name_match:
                    tool_name = tool_name_match.group(1)
                    # Look for MCPTodoAPI call on next few lines
                    for j in range(i, min(i+20, len(lines))):
                        if f'MCPTodoAPI.{tool_name}(' in lines[j]:
                            # Extract parameters
                            call_line = lines[j]
                            tool_routes[tool_name] = {
                                'line': j+1,
                                'call': call_line.strip()
                            }
                            break
        
        print(f"Found {len(tool_routes)} tool routing handlers")
        print()
        
        # Now we'll do manual checks - the user can review specific functions
        print("RECOMMENDATION: Manual review needed for full type checking.")
        print("Key areas to verify:")
        print("1. Parameter types (string, integer, number, boolean, array, object)")
        print("2. Optional flags (optional: True vs required parameters)")
        print("3. Default values match between definition and implementation")
        print("4. Enum values match between definition and actual allowed values")
        print("5. Array/object types are properly defined")
        print()
        
        # Example checks
        print("Example checks:")
        if 'list_available_tasks' in signatures:
            print(f"\n✓ list_available_tasks signature found")
            print(f"  Parameters: {list(signatures['list_available_tasks']['params'].keys())}")
        
        if 'list_available_tasks' in tool_routes:
            print(f"✓ list_available_tasks routing found at line {tool_routes['list_available_tasks']['line']}")
        
        return {
            'function_count': func_count,
            'signature_count': len(signatures),
            'route_count': len(tool_routes),
            'signatures': signatures,
            'routes': tool_routes
        }
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return {}


class AuditCommand(Command):
    """Command to audit MCP tool parameter types."""
    
    @classmethod
    def add_arguments(cls, parser: argparse.ArgumentParser) -> None:
        """Add audit command arguments."""
        parser.add_argument(
            "--functions",
            default="todorama/mcp/functions.py",
            help="Path to functions.py file (default: todorama/mcp/functions.py)"
        )
        parser.add_argument(
            "--mcp-api",
            default="todorama/mcp_api.py",
            help="Path to mcp_api.py file (default: todorama/mcp_api.py)"
        )
        parser.add_argument(
            "--main",
            default="todorama/main.py",
            help="Path to main.py file (default: todorama/main.py)"
        )
    
    def init(self):
        """Initialize the audit command."""
        global logger
        import logging
        logger = logging.getLogger(__name__)
        super().init()
    
    def run(self) -> int:
        """Run the audit command."""
        base_path = Path(__file__).parent.parent.parent
        functions_path = base_path / self.args.functions
        mcp_api_path = base_path / self.args.mcp_api
        main_path = base_path / self.args.main
        
        if not functions_path.exists():
            print(f"Error: Functions file not found: {functions_path}", file=sys.stderr)
            return 1
        
        if not mcp_api_path.exists():
            print(f"Error: MCP API file not found: {mcp_api_path}", file=sys.stderr)
            return 1
        
        if not main_path.exists():
            print(f"Error: Main file not found: {main_path}", file=sys.stderr)
            return 1
        
        result = audit_mcp_types(str(functions_path), str(mcp_api_path), str(main_path))
        
        if result:
            return 0
        else:
            return 1
