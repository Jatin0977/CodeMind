"""
Unit and integration tests for CodeMind AST McCabe Cyclomatic Complexity Analyzer (Phase 9, Milestone 1).
Verifies subtree boundary isolation, closures, match/case, comprehensions, and file aggregation.
"""

import pytest
from codemind.architecture.complexity import ComplexityAnalyzer, SubtreeComplexityVisitor


class TestComplexityAnalyzer:

    def setup_method(self):
        self.analyzer = ComplexityAnalyzer()

    def test_basic_branching_statements(self):
        """Verify standard branching control structures: If, For, While, Except, BoolOp."""
        code = """
def sample_function(x, y, items):
    # Base V = 1
    if x > 0:          # If (+1)
        pass
    elif x < -10:      # Elif is If (+1)
        pass
    else:
        pass

    for item in items: # For (+1)
        pass

    while y > 0:       # While (+1)
        y -= 1

    try:
        pass
    except ValueError: # Except (+1)
        pass
    except KeyError:   # Except (+1)
        pass

    # BoolOp: 3 operands -> 3 - 1 = 2 branches
    res = x > 0 and y > 0 and len(items) > 0 # BoolOp (+2)
    # IfExp: ternary (+1)
    val = 10 if x > 5 else 0                 # IfExp (+1)
    return val
"""
        metrics = self.analyzer.analyze_source(code)
        assert metrics.is_valid
        assert len(metrics.symbols) == 1
        sym = metrics.symbols[0]
        # Expected: 1 (base) + 1 (if) + 1 (elif) + 1 (for) + 1 (while) + 2 (excepts) + 2 (boolop) + 1 (ifexp) = 10
        assert sym.complexity == 10
        assert sym.name == "sample_function"
        assert sym.symbol_type == "function"

    def test_match_case_and_guards(self):
        """Verify Python 3.10+ match/case: patterns add +1, guards add +1, wildcard default adds 0."""
        code = """
def process_command(cmd, user):
    # Base V = 1
    match cmd:
        case "read":                     # Pattern (+1)
            return 1
        case "write" if user.is_admin:   # Pattern (+1) + Guard (+1) = +2
            return 2
        case "delete" if user.is_super:  # Pattern (+1) + Guard (+1) = +2
            return 3
        case _:                          # Wildcard default (+0)
            return 0
"""
        metrics = self.analyzer.analyze_source(code)
        assert metrics.is_valid
        assert len(metrics.symbols) == 1
        sym = metrics.symbols[0]
        # Expected: 1 (base) + 1 (read) + 2 (write+guard) + 2 (delete+guard) + 0 (wildcard) = 6
        assert sym.complexity == 6

    def test_comprehension_complexity(self):
        """Verify list/set/dict/generator comprehensions count each loop (+1) and each if-filter (+1)."""
        code = """
def build_lookups(data):
    # Base V = 1
    # 1 generator (+1) + 2 if-filters (+2) = +3
    list_comp = [x * 2 for x in data if x > 0 if x % 2 == 0]
    # 1 generator (+1) + 0 filters = +1
    dict_comp = {k: v for k, v in data.items()}
    return list_comp
"""
        metrics = self.analyzer.analyze_source(code)
        assert metrics.is_valid
        sym = metrics.symbols[0]
        # Expected: 1 (base) + 3 (listcomp) + 1 (dictcomp) = 5
        assert sym.complexity == 5

    def test_subtree_boundary_isolation_closures(self):
        """
        Critical invariant: Nested functions and closures must NOT inflate parent function complexity.
        The inner function must be recorded as an independent symbol.
        """
        code = """
def outer_orchestrator(records):
    # outer_orchestrator Base V = 1
    if not records: # If (+1)
        return []

    def inner_cleaner(r):
        # inner_cleaner Base V = 1 (ISOLATED from outer_orchestrator)
        if r is None:     # If (+1)
            return None
        for step in r:    # For (+1)
            if step < 0:  # If (+1)
                return None
        return r
        # inner_cleaner V = 1 + 1 + 1 + 1 = 4

    # outer_orchestrator comprehension: 1 generator (+1), 1 if-filter (+1) = +2
    return [inner_cleaner(r) for r in records if r is not None]
    # Total outer_orchestrator V = 1 (base) + 1 (if) + 2 (listcomp) = 4
    # (Must NOT be 4 + 4 = 8!)
"""
        metrics = self.analyzer.analyze_source(code)
        assert metrics.is_valid
        assert len(metrics.symbols) == 2

        sym_map = {s.name: s for s in metrics.symbols}
        outer = sym_map["outer_orchestrator"]
        inner = sym_map["outer_orchestrator.<locals>.inner_cleaner"]

        # Outer function is strictly isolated: V = 4
        assert outer.complexity == 4
        assert outer.symbol_type == "function"

        # Inner closure is independent: V = 4
        assert inner.complexity == 4
        assert inner.symbol_type == "closure"
        assert inner.parent_name == "outer_orchestrator.<locals>"

    def test_class_methods_and_executable_class_body_branching(self):
        """
        Verify class methods are evaluated independently and class body branching
        outside methods contributes strictly to class-body complexity.
        """
        code = """
import sys

class ConfigurableWorker:
    # Class body executable branching:
    if sys.platform == "win32": # Class body If (+1)
        TIMEOUT = 100
    else:
        TIMEOUT = 50

    def __init__(self, name):
        # __init__ Base V = 1
        self.name = name
        # V(__init__) = 1

    def execute(self, tasks):
        # execute Base V = 1
        for task in tasks:       # For (+1)
            if task.is_ready():  # If (+1)
                task.run()
        return True
        # V(execute) = 1 + 1 + 1 = 3
"""
        metrics = self.analyzer.analyze_source(code)
        assert metrics.is_valid
        assert len(metrics.symbols) == 2

        sym_map = {s.name: s for s in metrics.symbols}
        init_method = sym_map["ConfigurableWorker.__init__"]
        exec_method = sym_map["ConfigurableWorker.execute"]

        assert init_method.complexity == 1
        assert init_method.symbol_type == "method"

        assert exec_method.complexity == 3
        assert exec_method.symbol_type == "method"

        # Module script complexity = 1 (import sys has no branches)
        assert metrics.script_complexity == 1
        # Total file complexity:
        # V_script (1) + Delta V_class_body (1) + V(__init__) (1) + V(execute) (3) = 6
        assert metrics.file_complexity == 6

    def test_comprehensive_file_aggregation_no_omissions_or_double_counts(self):
        """Worked example from approved specification demonstrating complete disjoint accounting."""
        code = """
import sys

if sys.version_info < (3, 10):  # Top-level If (+1)
    raise RuntimeError("Python 3.10+ required")

def run_pipeline(records, mode):
    # Base V = 1
    if not records:  # If (+1)
        return []

    def sanitize(r):
        # Closure: Base V = 1
        if r is None or not r.is_valid:  # If (+1), or (+1) = +2
            return None
        return r.clean()
        # V(sanitize) = 1 + 2 = 3

    results = [sanitize(r) for r in records if r is not None]
    # ListComp: 1 gen (+1), 1 if (+1) = +2
    return results
    # Total V(run_pipeline) = 1 + 1 + 2 = 4

class PipelineReporter:
    if sys.platform == "win32":  # Class body If (+1)
        LOG_DIR = "C:\\\\logs"
    else:
        LOG_DIR = "/var/logs"

    def __init__(self, target):
        self.target = target
        # V(__init__) = 1

    def emit_report(self, items):
        # Base V = 1
        for item in items:  # For (+1)
            if item.score > 80 and not item.is_flagged:  # If (+1), and (+1) = +2
                print(item)
        return True
        # Total V(emit_report) = 1 + 1 + 2 = 4
"""
        metrics = self.analyzer.analyze_source(code)
        assert metrics.is_valid

        # 1. Script complexity: base 1 + top-level if (1) = 2
        assert metrics.script_complexity == 2

        # 2. Symbols: run_pipeline (4), sanitize (3), __init__ (1), emit_report (4)
        sym_map = {s.name: s for s in metrics.symbols}
        assert sym_map["run_pipeline"].complexity == 4
        assert sym_map["run_pipeline.<locals>.sanitize"].complexity == 3
        assert sym_map["PipelineReporter.__init__"].complexity == 1
        assert sym_map["PipelineReporter.emit_report"].complexity == 4

        # 3. File complexity = V_script (2) + V_class_body (1) + sum(V(f)) (4+3+1+4=12) = 15
        assert metrics.file_complexity == 15
        assert metrics.max_symbol_complexity == 4

    def test_syntax_error_graceful_handling(self):
        """Syntax errors must not raise exceptions; returns is_valid=False with captured error."""
        code = "def broken_code(x: return 123 {"
        metrics = self.analyzer.analyze_source(code, file_path="broken.py")
        assert not metrics.is_valid
        assert "SyntaxError" in metrics.error
        assert metrics.file_complexity == 1
        assert metrics.script_complexity == 1
        assert metrics.symbols == []
