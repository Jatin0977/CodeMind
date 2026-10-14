"""
Query engine and structural reachability analysis for CodeMind Software Knowledge Graph.
"""

from collections import deque
from typing import Dict, Any, Optional, List, Set, Tuple
import networkx as nx

from .models import NodeType, EdgeType, Node


class GraphQueryEngine:
    """
    Query engine providing callers, callees, dependency depth,
    cycle detection, and structural reachability impact analysis.
    """

    def __init__(self, graph: nx.DiGraph, nodes_by_id: Optional[Dict[str, Node]] = None):
        """
        Initialize the query engine.

        Args:
            graph: A NetworkX DiGraph instance representing the software knowledge graph.
            nodes_by_id: Optional lookup dictionary of node_id -> Node.
        """
        self.graph = graph
        self.nodes_by_id = nodes_by_id or {}

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve node attributes dictionary by node ID."""
        if node_id in self.nodes_by_id:
            return self.nodes_by_id[node_id].to_dict()
        if node_id in self.graph:
            return dict(self.graph.nodes[node_id])
        return None

    def search_nodes(
        self,
        query: str = "",
        node_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search for nodes matching a substring in their name, ID, or file path.

        Args:
            query: Case-insensitive search string.
            node_type: Optional NodeType filter (e.g., 'class', 'function', 'file').
            limit: Maximum number of nodes to return.

        Returns:
            List of matching node dictionaries.
        """
        q = query.lower().strip()
        matches = []

        for node_id, data in self.graph.nodes(data=True):
            if node_type and data.get("node_type") != node_type:
                continue

            name = data.get("name", "").lower()
            rel_path = data.get("relative_path", "").lower()
            n_id = node_id.lower()

            if not q or (q in name or q in rel_path or q in n_id):
                matches.append(dict(data))
                if len(matches) >= limit:
                    break

        return matches

    def get_callers(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Find all callers of the given function or method.
        (Nodes with an outgoing CALLS edge pointing to node_id).

        Args:
            node_id: Callee node ID.

        Returns:
            List of caller node dictionaries augmented with edge metadata.
        """
        if node_id not in self.graph:
            return []

        callers = []
        for pred in self.graph.predecessors(node_id):
            edge_data = self.graph.get_edge_data(pred, node_id) or {}
            if edge_data.get("edge_type") == EdgeType.CALLS:
                node_data = self.get_node(pred)
                if node_data:
                    res = dict(node_data)
                    res["call_metadata"] = edge_data.get("metadata", {})
                    callers.append(res)
        return callers

    def get_callees(self, node_id: str) -> List[Dict[str, Any]]:
        """
        Find all callees invoked by the given function or method.
        (Nodes targeted by an outgoing CALLS edge from node_id).

        Args:
            node_id: Caller node ID.

        Returns:
            List of callee node dictionaries augmented with edge metadata.
        """
        if node_id not in self.graph:
            return []

        callees = []
        for succ in self.graph.successors(node_id):
            edge_data = self.graph.get_edge_data(node_id, succ) or {}
            if edge_data.get("edge_type") == EdgeType.CALLS:
                node_data = self.get_node(succ)
                if node_data:
                    res = dict(node_data)
                    res["call_metadata"] = edge_data.get("metadata", {})
                    callees.append(res)
        return callees

    def get_dependencies(
        self,
        node_id: str,
        edge_types: Optional[List[str]] = None,
        direct_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get dependencies of a node (outgoing edges of specified types).
        Default types: [IMPORTS, CALLS, INHERITS].

        Args:
            node_id: Source node ID.
            edge_types: Allowed edge types (defaults to dependency relations).
            direct_only: If True, only immediate successors; if False, full transitive closure.

        Returns:
            List of dependency node dictionaries.
        """
        if node_id not in self.graph:
            return []

        valid_types = set(edge_types or [EdgeType.IMPORTS, EdgeType.CALLS, EdgeType.INHERITS])

        if direct_only:
            deps = []
            for succ in self.graph.successors(node_id):
                edge_data = self.graph.get_edge_data(node_id, succ) or {}
                if edge_data.get("edge_type") in valid_types:
                    node_data = self.get_node(succ)
                    if node_data:
                        res = dict(node_data)
                        res["relationship"] = edge_data.get("edge_type")
                        deps.append(res)
            return deps

        # Transitive closure using BFS
        visited: Set[str] = set()
        queue = deque([node_id])
        deps = []

        while queue:
            curr = queue.popleft()
            for succ in self.graph.successors(curr):
                if succ in visited or succ == node_id:
                    continue
                edge_data = self.graph.get_edge_data(curr, succ) or {}
                if edge_data.get("edge_type") in valid_types:
                    visited.add(succ)
                    queue.append(succ)
                    node_data = self.get_node(succ)
                    if node_data:
                        res = dict(node_data)
                        res["relationship"] = edge_data.get("edge_type")
                        deps.append(res)

        return deps

    def get_dependents(
        self,
        node_id: str,
        edge_types: Optional[List[str]] = None,
        direct_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get dependents of a node (nodes having outgoing dependency edges to node_id).
        Default types: [IMPORTS, CALLS, INHERITS].

        Args:
            node_id: Target node ID.
            edge_types: Allowed edge types.
            direct_only: If True, direct incoming; if False, transitive.

        Returns:
            List of dependent node dictionaries.
        """
        if node_id not in self.graph:
            return []

        valid_types = set(edge_types or [EdgeType.IMPORTS, EdgeType.CALLS, EdgeType.INHERITS])

        if direct_only:
            dependents = []
            for pred in self.graph.predecessors(node_id):
                edge_data = self.graph.get_edge_data(pred, node_id) or {}
                if edge_data.get("edge_type") in valid_types:
                    node_data = self.get_node(pred)
                    if node_data:
                        res = dict(node_data)
                        res["relationship"] = edge_data.get("edge_type")
                        dependents.append(res)
            return dependents

        # Transitive dependents via BFS on reverse edges
        visited: Set[str] = set()
        queue = deque([node_id])
        dependents = []

        while queue:
            curr = queue.popleft()
            for pred in self.graph.predecessors(curr):
                if pred in visited or pred == node_id:
                    continue
                edge_data = self.graph.get_edge_data(pred, curr) or {}
                if edge_data.get("edge_type") in valid_types:
                    visited.add(pred)
                    queue.append(pred)
                    node_data = self.get_node(pred)
                    if node_data:
                        res = dict(node_data)
                        res["relationship"] = edge_data.get("edge_type")
                        dependents.append(res)

        return dependents

    def get_dependency_depth(
        self,
        node_id: str,
        edge_types: Optional[List[str]] = None,
    ) -> int:
        """
        Calculate maximum dependency depth from node_id along outgoing dependency edges.
        Handles cycles safely by tracking visited nodes along paths.

        Args:
            node_id: Starting node ID.
            edge_types: Allowed dependency edge types (default: IMPORTS, CALLS, INHERITS).

        Returns:
            Integer representing maximum dependency path length (0 if no dependencies).
        """
        if node_id not in self.graph:
            return 0

        valid_types = set(edge_types or [EdgeType.IMPORTS, EdgeType.CALLS, EdgeType.INHERITS])

        # Find maximum length using DFS with recursion stack tracking for cycle avoidance
        max_depth = 0
        visited_on_path: Set[str] = set()

        def dfs(curr: str, current_depth: int):
            nonlocal max_depth
            if current_depth > max_depth:
                max_depth = current_depth

            visited_on_path.add(curr)
            for succ in self.graph.successors(curr):
                if succ in visited_on_path:
                    continue
                edge_data = self.graph.get_edge_data(curr, succ) or {}
                if edge_data.get("edge_type") in valid_types:
                    dfs(succ, current_depth + 1)
            visited_on_path.remove(curr)

        dfs(node_id, 0)
        return max_depth

    def detect_cycles(
        self,
        edge_types: Optional[List[str]] = None,
        max_cycles: int = 25,
    ) -> List[List[str]]:
        """
        Detect circular dependency cycles in the knowledge graph.

        Args:
            edge_types: Filter edges to consider (default: [IMPORTS, CALLS]).
            max_cycles: Maximum cycles to return to avoid combinatorial explosion.

        Returns:
            List of cycles, where each cycle is an ordered list of node IDs forming a loop.
        """
        valid_types = set(edge_types or [EdgeType.IMPORTS, EdgeType.CALLS])

        dep_edges = [
            (u, v) for u, v, d in self.graph.edges(data=True)
            if d.get("edge_type") in valid_types
        ]

        if not dep_edges:
            return []

        subgraph = self.graph.edge_subgraph(dep_edges)
        cycles = []
        try:
            for cycle in nx.simple_cycles(subgraph):
                cycles.append(cycle)
                if len(cycles) >= max_cycles:
                    break
        except Exception:
            pass

        return cycles

    def trace_impact(
        self,
        target_node_id: str,
        max_depth: int = 3,
        edge_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Perform structural reachability impact analysis for a changed or target node.

        Traverses reverse dependencies (incoming CALLS, INHERITS, IMPORTS edges)
        up to `max_depth` levels to identify all entities structurally reachable from the change.

        IMPORTANT:
        This analysis represents deterministic structural reachability based on AST static analysis,
        NOT an advanced predictive statistical impact score.

        Args:
            target_node_id: Node ID of the entity being inspected or changed.
            max_depth: Maximum traversal depth for reverse dependencies (default: 3).
            edge_types: Types of edges to follow in reverse (default: CALLS, INHERITS, IMPORTS).

        Returns:
            Detailed structural reachability impact report dictionary.
        """
        target_node = self.get_node(target_node_id)
        if not target_node:
            return {
                "target_node_id": target_node_id,
                "found": False,
                "error": f"Node '{target_node_id}' not found in knowledge graph",
            }

        valid_types = set(edge_types or [EdgeType.CALLS, EdgeType.INHERITS, EdgeType.IMPORTS])

        # BFS tracking node -> (depth, direct_relationship, path)
        visited: Dict[str, Dict[str, Any]] = {}
        queue: deque = deque([(target_node_id, 0, [target_node_id], None)])

        subgraph_nodes: Dict[str, Dict[str, Any]] = {target_node_id: target_node}
        subgraph_edges: List[Dict[str, Any]] = []

        while queue:
            curr_id, depth, path, rel = queue.popleft()

            if curr_id != target_node_id and curr_id not in visited:
                node_data = self.get_node(curr_id)
                if node_data:
                    visited[curr_id] = {
                        "node": node_data,
                        "depth": depth,
                        "path": path,
                        "relationship": rel,
                    }
                    subgraph_nodes[curr_id] = node_data

            if depth >= max_depth:
                continue

            # Traverse reverse dependency edges: predecessors of curr_id
            for pred_id in self.graph.predecessors(curr_id):
                edge_data = self.graph.get_edge_data(pred_id, curr_id) or {}
                edge_type = edge_data.get("edge_type")

                if edge_type in valid_types:
                    subgraph_edges.append({
                        "source": pred_id,
                        "target": curr_id,
                        "edge_type": edge_type,
                        "metadata": edge_data.get("metadata", {}),
                    })

                    if pred_id not in visited and pred_id != target_node_id:
                        new_path = path + [pred_id]
                        queue.append((pred_id, depth + 1, new_path, edge_type))

        # Categorize impacted entities
        impact_by_type: Dict[str, int] = {}
        impacted_list = list(visited.values())
        impacted_list.sort(key=lambda item: (item["depth"], item["node"].get("name", "")))

        for item in impacted_list:
            ntype = item["node"].get("node_type", "unknown")
            impact_by_type[ntype] = impact_by_type.get(ntype, 0) + 1

        return {
            "found": True,
            "target_node": target_node,
            "analysis_type": "Structural Reachability",
            "methodology": "Reverse dependency traversal (incoming CALLS, INHERITS, IMPORTS)",
            "disclaimer": (
                "Structural reachability traces deterministic static relationships in the AST graph. "
                "It does not represent runtime execution probability or predictive risk scoring."
            ),
            "max_depth": max_depth,
            "total_impacted": len(impacted_list),
            "impact_by_type": impact_by_type,
            "impacted_entities": impacted_list,
            "subgraph": {
                "nodes": list(subgraph_nodes.values()),
                "edges": subgraph_edges,
            },
        }
