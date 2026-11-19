"""
Deterministic Change Target Resolver for CodeMind Phase 8.
Resolves user input queries (canonical IDs, file paths, qualified symbols,
and unqualified names) to a verified ChangeTarget entity.
"""

import os
import difflib
from typing import Dict, Any, Optional, List
import networkx as nx

from .models import (
    ChangeTarget,
    TargetResolutionError,
    AmbiguousTargetError,
    TargetNotFoundError,
)
from ..graph.models import NodeType


class ChangeTargetResolver:
    """
    Resolves targets using a strict 5-stage deterministic hierarchy:
    1. Canonical Node ID Match
    2. File Path Match (relative or absolute)
    3. Qualified Symbol Match ('file.py::Symbol' or 'file.py::Class::method')
    4. Unqualified Symbol Lookup (single match -> resolved; >1 matches -> AmbiguousTargetError)
    5. Target Not Found (difflib suggestions -> TargetNotFoundError)
    """

    def __init__(self, graph: nx.DiGraph):
        self.graph = graph

    def resolve(self, query: str) -> ChangeTarget:
        """
        Deterministically resolve query to a ChangeTarget.

        Args:
            query: User input query (node ID, file path, qualified or unqualified symbol name).

        Returns:
            Resolved ChangeTarget dataclass instance.

        Raises:
            AmbiguousTargetError: If query matches multiple candidate symbols.
            TargetNotFoundError: If query cannot be resolved to any entity.
        """
        if not isinstance(query, str) or not query.strip():
            raise TargetNotFoundError(query=str(query), message="Target query cannot be empty.")

        q = query.strip()

        # Stage 1: Canonical Node ID Match
        if q in self.graph:
            node_data = self.graph.nodes[q]
            return self._build_target(q, node_data, resolution_method="canonical_id")

        # Stage 2: File Path Match
        file_target = self._resolve_file_path(q)
        if file_target:
            return file_target

        # Stage 3: Qualified Symbol Match ('path::Symbol' or 'path::Class::method')
        if "::" in q or (":" in q and not q.startswith(("function:", "class:", "method:", "file:"))):
            qualified_target = self._resolve_qualified_symbol(q)
            if qualified_target:
                return qualified_target

        # Stage 4: Unqualified Symbol Lookup
        unqualified_target = self._resolve_unqualified_symbol(q)
        if unqualified_target:
            return unqualified_target

        # Stage 5: Target Not Found with Suggestions
        all_candidate_names = self._collect_searchable_names()
        suggestions = difflib.get_close_matches(q, all_candidate_names, n=3, cutoff=0.5)
        raise TargetNotFoundError(query=q, suggestions=suggestions)

    def _resolve_file_path(self, query: str) -> Optional[ChangeTarget]:
        """Match query against known file paths."""
        norm_q = query.replace("\\", "/").strip("/")

        # Check file node id directly
        file_node_id = f"file:{norm_q}"
        if file_node_id in self.graph:
            return self._build_target(file_node_id, self.graph.nodes[file_node_id], resolution_method="file_path")

        for n, data in self.graph.nodes(data=True):
            if data.get("node_type") == NodeType.FILE:
                rel_path = (data.get("relative_path") or "").replace("\\", "/").strip("/")
                file_path = (data.get("file_path") or "").replace("\\", "/").strip("/")
                name = (data.get("name") or "").replace("\\", "/").strip("/")
                if norm_q in (rel_path, file_path, name) or rel_path.endswith(norm_q):
                    return self._build_target(n, data, resolution_method="file_path")

        return None

    def _resolve_qualified_symbol(self, query: str) -> Optional[ChangeTarget]:
        """
        Resolve syntax:
        - 'path/to/file.py::Symbol'
        - 'path/to/file.py::Class::method'
        - 'path/to/file.py:Symbol'
        """
        delimiter = "::" if "::" in query else ":"
        parts = query.split(delimiter)
        file_part = parts[0].replace("\\", "/").strip("/")
        symbol_parts = [p.strip() for p in parts[1:] if p.strip()]

        if not symbol_parts:
            return None

        primary_symbol = symbol_parts[-1]
        container_symbol = symbol_parts[0] if len(symbol_parts) > 1 else None

        candidates = []
        for n, data in self.graph.nodes(data=True):
            ntype = data.get("node_type")
            if ntype not in (NodeType.FUNCTION, NodeType.CLASS, NodeType.METHOD):
                continue

            rel_path = (data.get("relative_path") or "").replace("\\", "/").strip("/")
            file_path = (data.get("file_path") or "").replace("\\", "/").strip("/")
            name = data.get("name", "")

            # File matching
            file_matches = file_part in (rel_path, file_path) or rel_path.endswith(file_part)
            if not file_matches:
                continue

            # Symbol matching
            if name == primary_symbol:
                if container_symbol:
                    # Verify parent/class context if specified
                    node_id = str(n)
                    if container_symbol in node_id or data.get("metadata", {}).get("class_name") == container_symbol:
                        candidates.append((n, data))
                else:
                    candidates.append((n, data))

        if len(candidates) == 1:
            n, data = candidates[0]
            return self._build_target(n, data, resolution_method="qualified_symbol")
        elif len(candidates) > 1:
            candidate_dicts = [self._candidate_to_dict(n, d) for n, d in candidates]
            raise AmbiguousTargetError(query=query, candidates=candidate_dicts)

        return None

    def _resolve_unqualified_symbol(self, query: str) -> Optional[ChangeTarget]:
        """
        Lookup symbol by bare name across code entities.
        If unique -> resolve.
        If multiple -> raise AmbiguousTargetError.
        """
        candidates = []
        for n, data in self.graph.nodes(data=True):
            ntype = data.get("node_type")
            if ntype not in (NodeType.FUNCTION, NodeType.CLASS, NodeType.METHOD, NodeType.FILE):
                continue

            name = data.get("name", "")
            if name == query:
                candidates.append((n, data))

        if len(candidates) == 1:
            n, data = candidates[0]
            return self._build_target(n, data, resolution_method="unqualified_symbol")
        elif len(candidates) > 1:
            candidate_dicts = [self._candidate_to_dict(n, d) for n, d in candidates]
            raise AmbiguousTargetError(query=query, candidates=candidate_dicts)

        return None

    def _build_target(self, node_id: str, data: Dict[str, Any], resolution_method: str) -> ChangeTarget:
        """Construct a validated ChangeTarget instance from node attributes."""
        return ChangeTarget(
            node_id=str(node_id),
            name=data.get("name", str(node_id)),
            entity_type=data.get("node_type", "unknown"),
            file_path=data.get("file_path"),
            relative_path=data.get("relative_path"),
            start_line=data.get("start_line"),
            end_line=data.get("end_line"),
            resolution_method=resolution_method,
            metadata=dict(data.get("metadata", {})),
        )

    def _candidate_to_dict(self, node_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Format candidate node metadata for ambiguity reporting."""
        return {
            "node_id": str(node_id),
            "name": data.get("name", ""),
            "entity_type": data.get("node_type", "unknown"),
            "file_path": data.get("relative_path") or data.get("file_path") or "",
            "start_line": data.get("start_line"),
            "end_line": data.get("end_line"),
            "class_name": data.get("metadata", {}).get("class_name"),
        }

    def _collect_searchable_names(self) -> List[str]:
        """Collect all symbol names and file paths for suggestion generation."""
        names = set()
        for _, data in self.graph.nodes(data=True):
            if data.get("name"):
                names.add(data["name"])
            if data.get("relative_path"):
                names.add(data["relative_path"])
        return sorted(list(names))
