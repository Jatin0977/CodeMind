"""
AST McCabe Cyclomatic Complexity Analyzer for CodeMind (Phase 9, Milestone 1).
Provides subtree-isolated cyclomatic complexity calculations for functions, closures,
class methods, and files, guaranteeing that nested scopes never pollute parent metrics.
"""

import ast
import logging
from typing import List, Dict, Optional, Tuple, Any

from .models import SymbolComplexity, ComplexityMetrics

logger = logging.getLogger(__name__)


class SubtreeComplexityVisitor(ast.NodeVisitor):
    """
    Computes McCabe cyclomatic complexity strictly for the current callable scope.
    Halts recursive traversal upon encountering nested functions or classes,
    enforcing clean subtree isolation.
    """

    def __init__(self, is_root: bool = True, base_complexity: int = 1):
        self.complexity = base_complexity
        self._is_root = is_root

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._is_root:
            self._is_root = False
            self.generic_visit(node)
        # Subtree boundary stop: do NOT recurse into nested function bodies

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._is_root:
            self._is_root = False
            self.generic_visit(node)
        # Subtree boundary stop: do NOT recurse into nested async functions

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._is_root:
            self._is_root = False
            self.generic_visit(node)
        # Subtree boundary stop: do NOT recurse into nested class bodies

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        # Boolean operator with k values introduces k - 1 short-circuit branches
        self.complexity += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_Match(self, node: Any) -> None:
        # ast.Match itself is the switch container (+0)
        self.generic_visit(node)

    def visit_match_case(self, node: Any) -> None:
        pattern = getattr(node, "pattern", None)
        guard = getattr(node, "guard", None)

        # Check for wildcard default case: 'case _:'
        is_wildcard = False
        if isinstance(pattern, ast.MatchAs) and pattern.pattern is None and (pattern.name is None or pattern.name == "_"):
            is_wildcard = True

        if is_wildcard and guard is None:
            # Default wildcard branch adds 0
            pass
        else:
            # Explicit pattern branch adds +1
            self.complexity += 1

        if guard is not None:
            # Pattern guard ('if guard:') adds +1 decision predicate
            self.complexity += 1

        self.generic_visit(node)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._count_comprehension(node.generators)
        self.generic_visit(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._count_comprehension(node.generators)
        self.generic_visit(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._count_comprehension(node.generators)
        self.generic_visit(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._count_comprehension(node.generators)
        self.generic_visit(node)

    def _count_comprehension(self, generators: List[ast.comprehension]) -> None:
        for gen in generators:
            self.complexity += 1  # Comprehension for-loop iteration
            self.complexity += len(gen.ifs)  # Comprehension if-filters


class ComplexityAnalyzer:
    """
    Analyzes Python source code to calculate subtree-isolated cyclomatic complexity
    for modules, classes, methods, functions, and nested closures.
    Supports in-memory caching for accelerated repeated analysis with explicit invalidation.
    """

    def __init__(self, enable_cache: bool = True):
        self.enable_cache = enable_cache
        self._cache: Dict[Tuple[str, int, int], ComplexityMetrics] = {}

    def clear_cache(self) -> None:
        """Clear cached complexity analysis results for safe cache invalidation."""
        self._cache.clear()

    def analyze_source(
        self,
        source_code: str,
        file_path: str = "<memory>",
        relative_path: str = "<memory>",
        use_cache: Optional[bool] = None,
    ) -> ComplexityMetrics:
        """
        Parse Python source code and compute comprehensive isolated complexity metrics.
        Catches SyntaxError and other parse failures gracefully.
        """
        active_cache = self.enable_cache if use_cache is None else use_cache
        cache_key = (file_path, len(source_code), hash(source_code))
        if active_cache and cache_key in self._cache:
            return self._cache[cache_key]

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError as e:
            return ComplexityMetrics(
                file_path=file_path,
                relative_path=relative_path,
                script_complexity=1,
                file_complexity=1,
                max_symbol_complexity=0,
                symbols=[],
                is_valid=False,
                error=f"SyntaxError at line {e.lineno}: {e.msg}",
            )
        except Exception as e:
            return ComplexityMetrics(
                file_path=file_path,
                relative_path=relative_path,
                script_complexity=1,
                file_complexity=1,
                max_symbol_complexity=0,
                symbols=[],
                is_valid=False,
                error=f"{type(e).__name__}: {str(e)}",
            )

        # 1. Module Top-Level Script Complexity (code outside any function/class)
        # Root visitor base is 1 (base control flow path of module execution)
        script_visitor = SubtreeComplexityVisitor(is_root=False, base_complexity=1)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                script_visitor.visit(node)
        script_complexity = script_visitor.complexity

        # 2. Extract and measure all symbols with strict isolation
        symbols: List[SymbolComplexity] = []
        total_class_body_branching = 0

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._collect_function_symbols(node, parent_name=None, symbols=symbols)
            elif isinstance(node, ast.ClassDef):
                class_body_branching = self._collect_class_symbols(node, parent_name=None, symbols=symbols)
                total_class_body_branching += class_body_branching

        # 3. File-level aggregate complexity formula:
        # V_file = V_script + sum(class_body_branching) + sum(V(f) for f in all_symbols)
        all_symbol_complexity_sum = sum(s.complexity for s in symbols)
        file_complexity = script_complexity + total_class_body_branching + all_symbol_complexity_sum
        max_symbol_complexity = max((s.complexity for s in symbols), default=0)

        metrics = ComplexityMetrics(
            file_path=file_path,
            relative_path=relative_path,
            script_complexity=script_complexity,
            file_complexity=file_complexity,
            max_symbol_complexity=max_symbol_complexity,
            symbols=symbols,
            is_valid=True,
            error=None,
        )
        if active_cache:
            self._cache[cache_key] = metrics
        return metrics

    def _collect_function_symbols(
        self,
        func_node: Any,  # ast.FunctionDef or ast.AsyncFunctionDef
        parent_name: Optional[str],
        symbols: List[SymbolComplexity],
        symbol_type: Optional[str] = None,
    ) -> None:
        """Measure isolated complexity of a function/method and discover nested closures."""
        func_name = func_node.name
        qualified_name = f"{parent_name}.{func_name}" if parent_name else func_name

        if symbol_type is None:
            symbol_type = "closure" if parent_name and ".<locals>" in parent_name else ("method" if parent_name else "function")

        # Isolated visit: halts at child functions/classes
        visitor = SubtreeComplexityVisitor(is_root=True, base_complexity=1)
        visitor.visit(func_node)
        complexity = visitor.complexity

        start_line = getattr(func_node, "lineno", 1)
        end_line = getattr(func_node, "end_lineno", start_line) or start_line

        symbols.append(
            SymbolComplexity(
                name=qualified_name,
                symbol_type=symbol_type,
                start_line=start_line,
                end_line=end_line,
                complexity=complexity,
                parent_name=parent_name,
            )
        )

        # Discover nested callable subtrees inside this function body
        closure_parent_scope = f"{qualified_name}.<locals>"
        for child in ast.iter_child_nodes(func_node):
            self._search_nested_callables(child, parent_scope=closure_parent_scope, symbols=symbols)

    def _collect_class_symbols(
        self,
        class_node: ast.ClassDef,
        parent_name: Optional[str],
        symbols: List[SymbolComplexity],
    ) -> int:
        """Measure methods inside a class, discover nested classes, and return class-body branching."""
        class_name = class_node.name
        qualified_class_name = f"{parent_name}.{class_name}" if parent_name else class_name

        # Measure executable branching directly in class body outside methods
        class_body_visitor = SubtreeComplexityVisitor(is_root=False, base_complexity=0)
        for child in class_node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                class_body_visitor.visit(child)
        class_body_branching = class_body_visitor.complexity

        # Measure methods and nested classes
        for child in class_node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._collect_function_symbols(
                    child,
                    parent_name=qualified_class_name,
                    symbols=symbols,
                    symbol_type="method",
                )
            elif isinstance(child, ast.ClassDef):
                nested_branching = self._collect_class_symbols(
                    child,
                    parent_name=qualified_class_name,
                    symbols=symbols,
                )
                class_body_branching += nested_branching

        return class_body_branching

    def _search_nested_callables(
        self,
        node: ast.AST,
        parent_scope: str,
        symbols: List[SymbolComplexity],
    ) -> None:
        """Recursively scan for nested functions, closures, or local classes inside a function body."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._collect_function_symbols(
                node,
                parent_name=parent_scope,
                symbols=symbols,
                symbol_type="closure",
            )
            # _collect_function_symbols handles inner scopes internally; do not double-traverse
            return
        elif isinstance(node, ast.ClassDef):
            self._collect_class_symbols(
                node,
                parent_name=parent_scope,
                symbols=symbols,
            )
            return

        for child in ast.iter_child_nodes(node):
            self._search_nested_callables(child, parent_scope=parent_scope, symbols=symbols)
