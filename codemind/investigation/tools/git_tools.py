"""
Active Git investigation tools for CodeMind Agentic Investigation Engine (Phase 7, Milestone 5).
Wraps GitMiner, CodeChurnAnalyzer, LogicalCouplingAnalyzer, and GraphQueryEngine
into standardized BaseTool implementations for commit history, churn, and logical coupling.
"""

from typing import Dict, Any, Optional, List
from .base import BaseTool, ToolResult
from ..models import ToolStatus, ToolAvailability, ToolDefinition
from ...git.client import GitClient
from ...git.miner import GitMiner
from ...git.churn import CodeChurnAnalyzer
from ...git.coupling import LogicalCouplingAnalyzer
from ...graph.query import GraphQueryEngine


class GitCommitHistoryTool(BaseTool):
    """
    Mine Git commit log to analyze chronological evolution and revision history of files or symbols.
    """

    def __init__(
        self,
        git_miner: Optional[GitMiner] = None,
        git_client: Optional[GitClient] = None,
        query_engine: Optional[GraphQueryEngine] = None,
    ):
        self.git_miner = git_miner
        self.git_client = git_client
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="git_commit_history",
            description="Mine Git commit log to analyze chronological evolution and revision history of files or symbols.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional file path to filter commit history"},
                    "limit": {"type": "integer", "default": 50, "description": "Maximum commits to retrieve"},
                    "since": {"type": "string", "description": "Optional ISO date or Git date filter"},
                    "author": {"type": "string", "description": "Optional author name or email filter"},
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["git_cli", "commit_graph"],
        )

    @property
    def name(self) -> str:
        return "git_commit_history"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        path = arguments.get("path") or None
        if path == "":
            path = None
        limit = int(arguments.get("limit", 50))
        since = arguments.get("since") or None
        author = arguments.get("author") or None

        miner = self.git_miner
        if miner is None and self.git_client is not None:
            miner = GitMiner(self.git_client)

        if miner is not None:
            try:
                commits = miner.mine_commits(
                    max_commits=limit,
                    path=path,
                    since=since,
                    author=author,
                )
                serialized = [c.to_dict() for c in commits]
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    data={"commits": serialized, "total_commits": len(serialized), "filtered_path": path},
                    message=f"Retrieved {len(serialized)} commit records.",
                )
            except Exception as e:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    data=None,
                    message=f"Error mining commit history: {str(e)}",
                )

        # Fallback to temporal graph in query_engine if available
        if self.query_engine is not None and path:
            try:
                commits = self.query_engine.get_file_commits(path, limit=limit)
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    data={"commits": commits, "total_commits": len(commits), "filtered_path": path},
                    message=f"Retrieved {len(commits)} commits from temporal knowledge graph.",
                )
            except Exception as e:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    data=None,
                    message=f"Error querying temporal graph commits: {str(e)}",
                )

        return ToolResult(
            status=ToolStatus.ERROR,
            data=None,
            message="Git subsystem is not initialized or repository is not a Git repository.",
        )


class GitCodeChurnTool(BaseTool):
    """
    Calculate historical file-level modification frequency, additions, and deletions from Git history.
    """

    def __init__(
        self,
        churn_analyzer: Optional[CodeChurnAnalyzer] = None,
        git_miner: Optional[GitMiner] = None,
    ):
        self.churn_analyzer = churn_analyzer
        self.git_miner = git_miner
        self._definition = ToolDefinition(
            tool_name="git_code_churn",
            description="Calculate historical file-level modification frequency, additions, and deletions from Git history.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Optional file or directory path filter"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum hotspot files to return"},
                    "min_changes": {"type": "integer", "default": 1, "description": "Minimum commits required"},
                    "sort_by": {
                        "type": "string",
                        "enum": ["commits", "additions", "deletions", "total_churn", "authors"],
                        "default": "commits",
                        "description": "Metric to rank churn hotspots",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["git_cli", "churn_analyzer"],
        )

    @property
    def name(self) -> str:
        return "git_code_churn"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        path = arguments.get("path") or None
        if path == "":
            path = None
        limit = int(arguments.get("limit", 20))
        min_changes = int(arguments.get("min_changes", 1))
        sort_by = str(arguments.get("sort_by", "commits"))

        analyzer = self.churn_analyzer
        if analyzer is None and self.git_miner is not None:
            try:
                commits = self.git_miner.mine_commits(max_commits=1000)
                analyzer = CodeChurnAnalyzer()
                analyzer.analyze(commits)
            except Exception as e:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    data=None,
                    message=f"Error computing code churn: {str(e)}",
                )

        if analyzer is not None:
            try:
                hotspots = analyzer.get_top_churn_files(
                    limit=limit if not path else 1000,
                    sort_by=sort_by,
                    min_changes=min_changes,
                )
                if path:
                    norm_path = path.replace("\\", "/").lower()
                    hotspots = [h for h in hotspots if norm_path in h.path.lower()]
                    hotspots = hotspots[:limit]

                summary = analyzer.summary.to_dict() if analyzer.summary else {}
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    data={
                        "summary": summary,
                        "hotspots": [h.to_dict() for h in hotspots],
                        "total_returned": len(hotspots),
                        "filtered_path": path,
                    },
                    message=f"Calculated code churn metrics for {len(hotspots)} files.",
                )
            except Exception as e:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    data=None,
                    message=f"Error retrieving churn hotspots: {str(e)}",
                )

        return ToolResult(
            status=ToolStatus.ERROR,
            data=None,
            message="Code churn analyzer is not initialized or repository is not a Git repository.",
        )


class GitLogicalCouplingTool(BaseTool):
    """
    Discover hidden architectural dependencies and co-change clusters mined from historical commit co-occurrences.
    """

    def __init__(
        self,
        coupling_analyzer: Optional[LogicalCouplingAnalyzer] = None,
        git_miner: Optional[GitMiner] = None,
        query_engine: Optional[GraphQueryEngine] = None,
    ):
        self.coupling_analyzer = coupling_analyzer
        self.git_miner = git_miner
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="git_logical_coupling",
            description="Discover hidden architectural dependencies and co-change clusters mined from historical commit co-occurrences.",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Optional file path to inspect coupling for"},
                    "min_support": {"type": "integer", "default": 3, "description": "Minimum co-change commits"},
                    "min_confidence": {"type": "number", "default": 0.5, "description": "Minimum directional confidence"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum couplings to return"},
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["git_cli", "coupling_miner"],
        )

    @property
    def name(self) -> str:
        return "git_logical_coupling"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        file_path = arguments.get("file_path") or arguments.get("path") or None
        if file_path == "":
            file_path = None
        min_support = int(arguments.get("min_support", 3))
        min_confidence = float(arguments.get("min_confidence", 0.5))
        limit = int(arguments.get("limit", 20))

        # Check graph query engine first if file_path is specified and graph has temporal edges
        if file_path and self.query_engine is not None:
            try:
                graph_couplings = self.query_engine.get_logically_coupled_files(file_path, limit=limit)
                if graph_couplings:
                    return ToolResult(
                        status=ToolStatus.SUCCESS,
                        data={
                            "focal_file": file_path,
                            "couplings": graph_couplings,
                            "total_couplings": len(graph_couplings),
                        },
                        message=f"Discovered {len(graph_couplings)} logically coupled files from temporal graph.",
                    )
            except Exception:
                pass

        analyzer = self.coupling_analyzer
        if analyzer is None and self.git_miner is not None:
            try:
                commits = self.git_miner.mine_commits(max_commits=1000)
                analyzer = LogicalCouplingAnalyzer(min_support=min_support, min_confidence=min_confidence)
                analyzer.analyze(commits)
            except Exception as e:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    data=None,
                    message=f"Error computing logical coupling: {str(e)}",
                )

        if analyzer is not None:
            try:
                if file_path:
                    oriented = analyzer.get_couplings_for_file(
                        file_path,
                        min_support=min_support,
                        min_confidence=min_confidence,
                    )
                    oriented = oriented[:limit]
                    return ToolResult(
                        status=ToolStatus.SUCCESS,
                        data={
                            "focal_file": file_path,
                            "couplings": oriented,
                            "total_couplings": len(oriented),
                        },
                        message=f"Found {len(oriented)} files logically coupled with '{file_path}'.",
                    )
                else:
                    top_couplings = analyzer.get_top_couplings(limit=limit)
                    serialized = [c.to_dict() for c in top_couplings]
                    return ToolResult(
                        status=ToolStatus.SUCCESS,
                        data={
                            "focal_file": None,
                            "couplings": serialized,
                            "total_couplings": len(serialized),
                        },
                        message=f"Found {len(serialized)} repository logical couplings.",
                    )
            except Exception as e:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    data=None,
                    message=f"Error retrieving logical couplings: {str(e)}",
                )

        return ToolResult(
            status=ToolStatus.ERROR,
            data=None,
            message="Logical coupling analyzer is not initialized or repository is not a Git repository.",
        )
