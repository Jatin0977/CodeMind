"""
Code tools for CodeMind Agentic Investigation Engine (Phase 6, Milestone 2).
Provides standardized BaseTool wrappers for symbol searching, node inspection,
and safe file content extraction from the ingested repository.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List

from .base import BaseTool, ToolResult
from ..models import ToolStatus, ToolAvailability, ToolDefinition
from ...ingestion.models import IngestedRepository, SourceFile
from ...graph.query import GraphQueryEngine


class SearchSymbolsTool(BaseTool):
    """
    Search for functions, classes, methods, and files across the software knowledge graph.
    Returns structured entity matches with file paths and line ranges.
    """

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="search_symbols",
            description="Search for functions, classes, methods, and files in the software knowledge graph.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Symbol name or substring to search for (case-insensitive)",
                    },
                    "node_type": {
                        "type": "string",
                        "enum": ["class", "function", "method", "file"],
                        "description": "Optional node type filter",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of matching symbols to return",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "search_symbols"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Search query cannot be empty.",
            )

        node_type = arguments.get("node_type")
        if node_type is not None:
            node_type = str(node_type).lower().strip() or None

        limit = int(arguments.get("limit", 20))
        if limit <= 0:
            limit = 20

        matches = self.query_engine.search_nodes(query=query, node_type=node_type, limit=limit)

        total_matches = len(matches)
        is_ambiguous = total_matches > 1
        primary_node_id = matches[0]["id"] if matches else None
        primary_relative_path = matches[0].get("relative_path") if matches else None

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "query": query,
                "node_type": node_type,
                "total_matches": total_matches,
                "is_ambiguous": is_ambiguous,
                "primary_node_id": primary_node_id,
                "primary_relative_path": primary_relative_path,
                "matches": matches,
            },
            message=f"Found {total_matches} symbol match(es) for '{query}'.",
            metadata={
                "query": query,
                "node_type": node_type,
                "limit": limit,
                "is_ambiguous": is_ambiguous,
            },
        )


class GetNodeDetailsTool(BaseTool):
    """
    Retrieve attributes, line ranges, and metadata for a specific knowledge graph node.
    Clearly reports missing entities.
    """

    def __init__(self, query_engine: Optional[GraphQueryEngine] = None):
        self.query_engine = query_engine
        self._definition = ToolDefinition(
            tool_name="get_node_details",
            description="Retrieve detailed attributes, line ranges, and metadata for a specific graph node.",
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "Canonical node identifier (e.g. 'class:codemind/auth.py:AuthService')",
                    }
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "get_node_details"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.query_engine is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Knowledge graph query engine is not initialized.",
            )

        node_id = str(arguments.get("node_id", "")).strip()
        if not node_id:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Parameter 'node_id' cannot be empty.",
            )

        node_data = self.query_engine.get_node(node_id)
        if not node_data:
            return ToolResult(
                status=ToolStatus.ERROR,
                data={"node_id": node_id, "found": False},
                message=f"Node '{node_id}' not found in knowledge graph.",
                metadata={"node_id": node_id, "found": False},
            )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data=node_data,
            message=f"Retrieved node details for '{node_id}'.",
            metadata={"node_id": node_id, "found": True},
        )


class GetFileContentTool(BaseTool):
    """
    Read verified source code lines from an ingested repository file.
    Enforces strict path traversal prevention and line range validation.
    Never fabricates file contents or line numbers.
    """

    def __init__(self, repo: Optional[IngestedRepository] = None):
        self.repo = repo
        self._definition = ToolDefinition(
            tool_name="get_file_content",
            description="Read verified source lines from a file belonging to the ingested repository.",
            input_schema={
                "type": "object",
                "required": ["relative_path"],
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Relative file path within the ingested repository",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Optional starting line number (1-based, inclusive)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Optional ending line number (1-based, inclusive)",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["repository_ingestion"],
        )

    @property
    def name(self) -> str:
        return "get_file_content"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.repo is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Repository is not ingested.",
            )

        raw_path = str(arguments.get("relative_path", "")).strip()
        if not raw_path:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Parameter 'relative_path' cannot be empty.",
            )

        # Path traversal and absolute path protection
        norm_path = raw_path.replace("\\", "/").strip()
        parts = [p for p in norm_path.split("/") if p and p != "."]
        if ".." in parts or Path(raw_path).is_absolute() or norm_path.startswith("/") or ":" in norm_path:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message=f"Access denied: path traversal or absolute path '{raw_path}' is prohibited.",
                metadata={"security_violation": "path_traversal", "path": raw_path},
            )

        source_file = self.repo.get_file_by_relative_path(norm_path)
        if not source_file:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message=f"File '{raw_path}' not found in ingested repository.",
                metadata={"relative_path": raw_path, "found": False},
            )

        lines = source_file.content.splitlines()
        total_lines = source_file.line_count if source_file.line_count > 0 else len(lines)

        # Validate line ranges
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")

        actual_start = 1
        if start_line is not None:
            try:
                actual_start = int(start_line)
            except (ValueError, TypeError):
                return ToolResult(status=ToolStatus.ERROR, message="Parameter 'start_line' must be an integer.")
            if actual_start < 1:
                return ToolResult(status=ToolStatus.ERROR, message="Parameter 'start_line' must be >= 1.")
            if total_lines > 0 and actual_start > total_lines:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    message=f"start_line ({actual_start}) exceeds total line count ({total_lines}).",
                )

        actual_end = total_lines if total_lines > 0 else len(lines)
        if end_line is not None:
            try:
                actual_end = int(end_line)
            except (ValueError, TypeError):
                return ToolResult(status=ToolStatus.ERROR, message="Parameter 'end_line' must be an integer.")
            if actual_end < actual_start:
                return ToolResult(
                    status=ToolStatus.ERROR,
                    message=f"end_line ({actual_end}) cannot be less than start_line ({actual_start}).",
                )
            if total_lines > 0 and actual_end > total_lines:
                actual_end = total_lines

        # Extract actual lines
        selected_lines = [
            {"line_number": i, "content": lines[i - 1]}
            for i in range(actual_start, actual_end + 1)
            if 0 <= i - 1 < len(lines)
        ]
        snippet = "\n".join(lines[actual_start - 1 : actual_end])

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "relative_path": source_file.relative_path,
                "file_name": source_file.file_name,
                "language": source_file.language,
                "total_lines": total_lines,
                "start_line": actual_start,
                "end_line": actual_end,
                "line_count_returned": len(selected_lines),
                "lines": selected_lines,
                "content": snippet,
            },
            message=f"Retrieved lines {actual_start}-{actual_end} from '{source_file.relative_path}'.",
            metadata={
                "relative_path": source_file.relative_path,
                "start_line": actual_start,
                "end_line": actual_end,
                "file_size": source_file.file_size,
            },
        )
