"""
Investigation tools subpackage for CodeMind (Phase 6, Milestone 2).
Exports BaseTool, ToolResult, DeferredTool, ToolRegistry, concrete tools,
and a deterministic factory function to initialize and populate the registry.
"""

from typing import Optional, Any

from .base import BaseTool, ToolResult, DeferredTool
from .registry import ToolRegistry
from .code_tools import SearchSymbolsTool, GetNodeDetailsTool, GetFileContentTool
from .graph_tools import (
    GetCallersTool,
    GetCalleesTool,
    GetDependenciesTool,
    GetDependentsTool,
    TraceStructuralImpactTool,
    DetectCyclesTool,
)
from .retrieval_tools import SemanticSearchTool, HybridSearchTool
from .git_tools import GitCommitHistoryTool, GitCodeChurnTool, GitLogicalCouplingTool
from .deferred_tools import create_deferred_tools

from ...ingestion.models import IngestedRepository
from ...graph.query import GraphQueryEngine
from ...retrieval.retriever import SemanticRetriever
from ...retrieval.hybrid_retriever import HybridGraphRetriever


def create_tool_registry(
    repo: Optional[IngestedRepository] = None,
    query_engine: Optional[GraphQueryEngine] = None,
    retriever: Optional[SemanticRetriever] = None,
    hybrid_retriever: Optional[HybridGraphRetriever] = None,
    git_miner: Optional[Any] = None,
    git_client: Optional[Any] = None,
    git_churn_analyzer: Optional[Any] = None,
    git_coupling_analyzer: Optional[Any] = None,
    enable_git: bool = False,
) -> ToolRegistry:
    """
    Construct and return a deterministic ToolRegistry populated with all
    standardized CodeMind investigation tools (both available and deferred).

    Registration Order:
    1. Code tools: search_symbols, get_node_details, get_file_content
    2. Graph tools: get_callers, get_callees, get_dependencies, get_dependents,
                   trace_structural_impact, detect_cycles
    3. Retrieval tools: semantic_search, hybrid_search
    4. Git Temporal tools (Phase 7): git_commit_history, git_code_churn, git_logical_coupling (if Git enabled)
    5. Deferred tools (Phases 8, 9, or Phases 7-9 when Git uninitialized/disabled):
       - Phase 7: git_commit_history, git_code_churn (when Git uninitialized)
       - Phase 8: multi_signal_impact, get_test_coverage
       - Phase 9: detect_maintenance_hotspots, check_architecture_conformance

    Args:
        repo: Optional IngestedRepository instance for file reading.
        query_engine: Optional GraphQueryEngine instance for AST graph queries.
        retriever: Optional SemanticRetriever instance for vector search.
        hybrid_retriever: Optional HybridGraphRetriever instance for hybrid search.
        git_miner: Optional GitMiner instance for commit history & mining.
        git_client: Optional GitClient instance.
        git_churn_analyzer: Optional CodeChurnAnalyzer instance for churn analytics.
        git_coupling_analyzer: Optional LogicalCouplingAnalyzer instance.
        enable_git: Explicit flag to force active Git tool registration even if analyzers are not yet passed.

    Returns:
        Populated ToolRegistry with deterministic ordering.
    """
    has_git = enable_git or any(
        x is not None for x in (git_miner, git_client, git_churn_analyzer, git_coupling_analyzer)
    )
    registry = ToolRegistry()

    # 1. Code Tools (Phase 1 & 2 & Graph)
    registry.register(SearchSymbolsTool(query_engine=query_engine))
    registry.register(GetNodeDetailsTool(query_engine=query_engine))
    registry.register(GetFileContentTool(repo=repo))

    # 2. Graph Tools (Phase 4)
    registry.register(GetCallersTool(query_engine=query_engine))
    registry.register(GetCalleesTool(query_engine=query_engine))
    registry.register(GetDependenciesTool(query_engine=query_engine))
    registry.register(GetDependentsTool(query_engine=query_engine))
    registry.register(TraceStructuralImpactTool(query_engine=query_engine))
    registry.register(DetectCyclesTool(query_engine=query_engine))

    # 3. Retrieval Tools (Phase 3 & 5)
    registry.register(SemanticSearchTool(retriever=retriever))
    registry.register(HybridSearchTool(hybrid_retriever=hybrid_retriever))

    if has_git:
        # 4. Git Temporal Tools (Phase 7 Active)
        registry.register(
            GitCommitHistoryTool(
                git_miner=git_miner,
                git_client=git_client,
                query_engine=query_engine,
            )
        )
        registry.register(
            GitCodeChurnTool(
                churn_analyzer=git_churn_analyzer,
                git_miner=git_miner,
            )
        )
        registry.register(
            GitLogicalCouplingTool(
                coupling_analyzer=git_coupling_analyzer,
                git_miner=git_miner,
                query_engine=query_engine,
            )
        )

        # 5. Deferred Tools (Phases 8, 9 only)
        for def_tool in create_deferred_tools(include_git=False):
            registry.register(def_tool)
    else:
        # 5. Deferred Tools (Phases 7, 8, 9 for uninitialized / non-git mode)
        for def_tool in create_deferred_tools(include_git=True):
            registry.register(def_tool)

    return registry


__all__ = [
    "BaseTool",
    "ToolResult",
    "DeferredTool",
    "ToolRegistry",
    "SearchSymbolsTool",
    "GetNodeDetailsTool",
    "GetFileContentTool",
    "GetCallersTool",
    "GetCalleesTool",
    "GetDependenciesTool",
    "GetDependentsTool",
    "TraceStructuralImpactTool",
    "DetectCyclesTool",
    "SemanticSearchTool",
    "HybridSearchTool",
    "GitCommitHistoryTool",
    "GitCodeChurnTool",
    "GitLogicalCouplingTool",
    "create_deferred_tools",
    "create_tool_registry",
]
