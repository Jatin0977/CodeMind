"""
Investigation tools subpackage for CodeMind (Phase 6, Milestone 2).
Exports BaseTool, ToolResult, DeferredTool, ToolRegistry, concrete tools,
and a deterministic factory function to initialize and populate the registry.
"""

from typing import Optional, Any, Dict, List

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
from .impact_tools import MultiSignalImpactTool, GetTestCoverageTool
from .architecture_tools import (
    GetArchitectureOverviewTool,
    CheckArchitectureConformanceTool,
    DetectPackageCyclesTool,
    DetectMaintenanceHotspotsTool,
    GetEvidenceCoverageTool,
)
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
    impact_engine: Optional[Any] = None,
    impact_scorer: Optional[Any] = None,
    test_engine: Optional[Any] = None,
    enable_impact: bool = False,
    has_tests: bool = False,
    total_repo_commits: int = 0,
    discovery_engine: Optional[Any] = None,
    conformance_engine: Optional[Any] = None,
    hotspot_detector: Optional[Any] = None,
    enable_architecture: bool = False,
    modules: Optional[Any] = None,
    layers: Optional[Any] = None,
    quotient_graph: Optional[Any] = None,
    evidence_coverage: Optional[Any] = None,
    parsed_files: Optional[Dict[str, Any]] = None,
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
    5. Impact tools (Phase 8): multi_signal_impact, get_test_coverage (if Impact enabled)
    6. Architecture tools (Phase 9): get_architecture_overview, check_architecture_conformance,
                                    detect_package_cycles, detect_maintenance_hotspots, get_evidence_coverage (if Architecture enabled)
    7. Deferred tools (any uninitialized phases):
       - Phase 7: git_commit_history, git_code_churn (when Git uninitialized)
       - Phase 8: multi_signal_impact, get_test_coverage (when Impact uninitialized)
       - Phase 9: detect_maintenance_hotspots, check_architecture_conformance (when Architecture uninitialized)

    Returns:
        Populated ToolRegistry with deterministic ordering.
    """
    has_git = enable_git or any(
        x is not None for x in (git_miner, git_client, git_churn_analyzer, git_coupling_analyzer)
    )
    has_impact = enable_impact or any(
        x is not None for x in (impact_engine, impact_scorer, test_engine)
    )
    has_architecture = enable_architecture or any(
        x is not None for x in (discovery_engine, conformance_engine, hotspot_detector, modules, layers, quotient_graph)
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

    # 4. Git Temporal Tools (Phase 7 Active)
    if has_git:
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

    # 5. Impact Tools (Phase 8 Active)
    if has_impact:
        registry.register(
            MultiSignalImpactTool(
                query_engine=query_engine,
                impact_engine=impact_engine,
                scorer=impact_scorer,
                test_engine=test_engine,
                coupling_analyzer=git_coupling_analyzer,
                churn_analyzer=git_churn_analyzer,
                has_git=has_git,
                total_repo_commits=total_repo_commits,
                has_tests=has_tests,
            )
        )
        registry.register(
            GetTestCoverageTool(
                query_engine=query_engine,
                impact_engine=impact_engine,
                test_engine=test_engine,
                coupling_analyzer=git_coupling_analyzer,
            )
        )

    # 6. Architecture & Risk Tools (Phase 9 Active)
    if has_architecture:
        registry.register(
            GetArchitectureOverviewTool(
                discovery_engine=discovery_engine,
                modules=modules,
                layers=layers,
                repo=repo,
                parsed_files=parsed_files,
            )
        )
        registry.register(
            CheckArchitectureConformanceTool(
                conformance_engine=conformance_engine,
                discovery_engine=discovery_engine,
                parsed_files=parsed_files,
            )
        )
        registry.register(
            DetectPackageCyclesTool(
                conformance_engine=conformance_engine,
                quotient_graph=quotient_graph,
            )
        )
        registry.register(
            DetectMaintenanceHotspotsTool(
                hotspot_detector=hotspot_detector,
                modules=modules,
                quotient_graph=quotient_graph,
                churn_summary=getattr(git_churn_analyzer, "latest_summary", None) if git_churn_analyzer else None,
                total_source_files=len(repo.files) if repo else 0,
                valid_ast_files=len(parsed_files) if parsed_files else 0,
            )
        )
        registry.register(
            GetEvidenceCoverageTool(
                evidence_coverage=evidence_coverage,
                total_source_files=len(repo.files) if repo else 0,
                valid_ast_files=len(parsed_files) if parsed_files else 0,
                has_graph=bool(query_engine is not None),
                has_churn=has_git,
                eligible_commits_count=total_repo_commits,
                has_structural_coupling=bool(quotient_graph is not None and quotient_graph.number_of_edges() > 0),
            )
        )

    # 7. Deferred Tools (any uninitialized phases)
    deferred_tools = create_deferred_tools(
        include_git=not has_git,
        include_impact=not has_impact,
        include_architecture=not has_architecture,
    )
    for def_tool in deferred_tools:
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
    "MultiSignalImpactTool",
    "GetTestCoverageTool",
    "GetArchitectureOverviewTool",
    "CheckArchitectureConformanceTool",
    "DetectPackageCyclesTool",
    "DetectMaintenanceHotspotsTool",
    "GetEvidenceCoverageTool",
    "create_deferred_tools",
    "create_tool_registry",
]
