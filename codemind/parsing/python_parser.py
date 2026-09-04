"""
Python AST parser for extracting classes, functions, methods, imports, calls, and docstrings.
"""

import ast
import logging
from typing import List, Optional, Any
from .base_parser import BaseParser, ParsedFile, Symbol, ImportStatement
from ..ingestion.models import SourceFile

logger = logging.getLogger(__name__)


class PythonParser(BaseParser):
    """Parses Python source code using the standard library `ast` module."""

    @property
    def supported_language(self) -> str:
        return "python"

    def parse(self, source_file: SourceFile) -> ParsedFile:
        """
        Parse a Python source file into structured symbols and metadata.
        Catches SyntaxError and other parsing errors gracefully.
        """
        file_path = source_file.file_path
        rel_path = source_file.relative_path

        try:
            tree = ast.parse(source_file.content, filename=file_path)
        except SyntaxError as e:
            logger.debug(f"Syntax error parsing {rel_path}: {e}")
            return ParsedFile(
                file_path=file_path,
                relative_path=rel_path,
                language="python",
                is_valid=False,
                error=f"SyntaxError at line {e.lineno}: {e.msg}",
            )
        except Exception as e:
            logger.debug(f"Error parsing {rel_path}: {e}")
            return ParsedFile(
                file_path=file_path,
                relative_path=rel_path,
                language="python",
                is_valid=False,
                error=f"{type(e).__name__}: {str(e)}",
            )

        module_docstring = ast.get_docstring(tree)
        imports: List[ImportStatement] = []
        classes: List[Symbol] = []
        functions: List[Symbol] = []
        all_symbols: List[Symbol] = []

        for node in tree.body:
            # 1. Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportStatement(
                            name=alias.name,
                            alias=alias.asname,
                            is_from=False,
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level > 0:
                    # Relative import dots
                    module = "." * node.level + module
                for alias in node.names:
                    imports.append(
                        ImportStatement(
                            module=module,
                            name=alias.name,
                            alias=alias.asname,
                            is_from=True,
                            line_number=node.lineno,
                        )
                    )

            # 2. Classes
            elif isinstance(node, ast.ClassDef):
                class_symbol = self._parse_class(node)
                classes.append(class_symbol)
                all_symbols.append(class_symbol)
                # Add child methods to all_symbols as well
                all_symbols.extend(class_symbol.methods)

            # 3. Top-level Functions (sync or async)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_symbol = self._parse_function(node, parent_name=None, symbol_type="function")
                functions.append(func_symbol)
                all_symbols.append(func_symbol)

        return ParsedFile(
            file_path=file_path,
            relative_path=rel_path,
            language="python",
            is_valid=True,
            error=None,
            docstring=module_docstring,
            classes=classes,
            functions=functions,
            imports=imports,
            symbols=all_symbols,
        )

    def _parse_class(self, node: ast.ClassDef) -> Symbol:
        """Extract a class symbol and all its methods."""
        bases = [self._node_to_string(b) for b in node.bases]
        decorators = [self._node_to_string(d) for d in node.decorator_list]
        docstring = ast.get_docstring(node)
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno

        methods: List[Symbol] = []
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_symbol = self._parse_function(
                    child, parent_name=node.name, symbol_type="method"
                )
                methods.append(method_symbol)

        return Symbol(
            name=node.name,
            symbol_type="class",
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            parent_name=None,
            is_async=False,
            bases=bases,
            decorators=decorators,
            methods=methods,
        )

    def _parse_function(
        self,
        node: Any,  # ast.FunctionDef or ast.AsyncFunctionDef
        parent_name: Optional[str] = None,
        symbol_type: str = "function",
    ) -> Symbol:
        """Extract function/method details, signature, docstring, and called functions."""
        name = node.name
        is_async = isinstance(node, ast.AsyncFunctionDef)
        start_line = node.lineno
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        docstring = ast.get_docstring(node)
        decorators = [self._node_to_string(d) for d in node.decorator_list]
        args = self._extract_arg_names(node.args)
        returns = self._node_to_string(node.returns) if node.returns else None
        calls = self._extract_calls(node)

        return Symbol(
            name=name,
            symbol_type=symbol_type,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            parent_name=parent_name,
            is_async=is_async,
            args=args,
            returns=returns,
            decorators=decorators,
            calls=calls,
        )

    def _extract_arg_names(self, args_node: ast.arguments) -> List[str]:
        """Extract argument names including positional, keyword, vararg, and kwarg."""
        arg_names: List[str] = []

        # Positional-only args (Python 3.8+)
        for arg in getattr(args_node, "posonlyargs", []):
            arg_names.append(arg.arg)

        # Standard args
        for arg in args_node.args:
            arg_names.append(arg.arg)

        # *vararg
        if args_node.vararg:
            arg_names.append(f"*{args_node.vararg.arg}")

        # Keyword-only args
        for arg in args_node.kwonlyargs:
            arg_names.append(arg.arg)

        # **kwarg
        if args_node.kwarg:
            arg_names.append(f"**{args_node.kwarg.arg}")

        return arg_names

    def _extract_calls(self, func_node: Any) -> List[str]:
        """Extract unique function/method calls inside a function body."""
        calls: List[str] = []
        seen = set()

        for sub_node in ast.walk(func_node):
            if isinstance(sub_node, ast.Call):
                call_name = self._node_to_string(sub_node.func)
                if call_name and call_name not in seen:
                    seen.add(call_name)
                    calls.append(call_name)

        return calls

    def _node_to_string(self, node: Optional[ast.AST]) -> str:
        """Convert an AST node into a clean string representation."""
        if node is None:
            return ""

        # Use ast.unparse if available (Python 3.9+)
        try:
            return ast.unparse(node).strip()
        except Exception:
            pass

        # Fallback manual extraction
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            val = self._node_to_string(node.value)
            return f"{val}.{node.attr}" if val else node.attr
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Subscript):
            val = self._node_to_string(node.value)
            slice_str = self._node_to_string(node.slice)
            return f"{val}[{slice_str}]"
        elif isinstance(node, ast.Call):
            func = self._node_to_string(node.func)
            return f"{func}(...)"

        return ""
