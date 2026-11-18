"""
Retrieval tools for CodeMind Agentic Investigation Engine (Phase 6, Milestone 2).
Provides standardized BaseTool wrappers for dense vector semantic search
and hybrid graph-aware retrieval using existing Phase 3 and Phase 5 components.
"""

from typing import Dict, Any, Optional, List

from .base import BaseTool, ToolResult
from ..models import ToolStatus, ToolAvailability, ToolDefinition
from ...retrieval.retriever import SemanticRetriever
from ...retrieval.hybrid_retriever import HybridGraphRetriever, HybridSearchResult
from ...vector_store.base import SearchResult


class SemanticSearchTool(BaseTool):
    """
    Execute dense vector semantic similarity search over code and documentation chunks.
    Wraps existing Phase 3 SemanticRetriever.
    """

    def __init__(self, retriever: Optional[SemanticRetriever] = None):
        self.retriever = retriever
        self._definition = ToolDefinition(
            tool_name="semantic_search",
            description="Execute dense vector semantic similarity search over repository chunks.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language query or code concept to search for",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of top matching chunks to retrieve",
                    },
                    "filter_dict": {
                        "type": "object",
                        "description": "Optional metadata key-value filter dictionary",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["vector_retrieval", "embeddings"],
        )

    @property
    def name(self) -> str:
        return "semantic_search"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.retriever is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Semantic retriever is not initialized.",
            )

        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'query' cannot be empty.")

        top_k = int(arguments.get("top_k", 5))
        if top_k <= 0:
            top_k = 5

        filter_dict = arguments.get("filter_dict")

        results: List[SearchResult] = self.retriever.search(
            query=query,
            top_k=top_k,
            filter_dict=filter_dict,
        )

        formatted_results: List[Dict[str, Any]] = []
        for r in results:
            item = r.to_dict()
            item["provenance"] = "vector_seed"
            item["relationship_type"] = None
            formatted_results.append(item)

        embedding_provider_name = (
            self.retriever.embedding_provider.model_name
            if hasattr(self.retriever, "embedding_provider") and self.retriever.embedding_provider
            else "unknown"
        )

        is_mock = "mock" in embedding_provider_name.lower()
        provider_disclaimer = (
            "Mock embedding provider in use; results demonstrate structural retrieval rather than production semantic relevance."
            if is_mock
            else None
        )

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "query": query,
                "top_k": top_k,
                "total_results": len(formatted_results),
                "results": formatted_results,
            },
            message=f"Semantic search retrieved {len(formatted_results)} chunk(s) for '{query}'.",
            metadata={
                "embedding_model": embedding_provider_name,
                "is_mock_provider": is_mock,
                "disclaimer": provider_disclaimer,
            },
        )


class HybridSearchTool(BaseTool):
    """
    Execute hybrid graph-aware retrieval combining dense vector search with topological BFS expansion.
    Wraps existing Phase 5 HybridGraphRetriever. Preserves graph provenance and scoring signals.
    """

    def __init__(self, hybrid_retriever: Optional[HybridGraphRetriever] = None):
        self.hybrid_retriever = hybrid_retriever
        self._definition = ToolDefinition(
            tool_name="hybrid_search",
            description="Execute hybrid graph-aware retrieval combining vector search with knowledge graph expansion.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Developer query or technical question",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Total evidence budget to retrieve",
                    },
                    "intent": {
                        "type": "string",
                        "enum": ["flow", "impact", "general"],
                        "description": "Optional explicit graph traversal intent override",
                    },
                    "use_graph": {
                        "type": "boolean",
                        "default": True,
                        "description": "If False, falls back cleanly to pure vector search",
                    },
                    "filter_dict": {
                        "type": "object",
                        "description": "Optional metadata key-value filter dictionary",
                    },
                },
            },
            availability=ToolAvailability.AVAILABLE,
            required_capabilities=["hybrid_retrieval", "knowledge_graph"],
        )

    @property
    def name(self) -> str:
        return "hybrid_search"

    @property
    def description(self) -> str:
        return self._definition.description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        if self.hybrid_retriever is None:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message="Hybrid graph retriever is not initialized.",
            )

        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(status=ToolStatus.ERROR, message="Parameter 'query' cannot be empty.")

        top_k = int(arguments.get("top_k", 5))
        if top_k <= 0:
            top_k = 5

        use_graph = bool(arguments.get("use_graph", True))
        intent = arguments.get("intent")
        filter_dict = arguments.get("filter_dict")

        results = self.hybrid_retriever.search(
            query=query,
            top_k=top_k,
            filter_dict=filter_dict,
            use_graph=use_graph,
            intent_override=intent,
        )

        formatted_results: List[Dict[str, Any]] = [r.to_dict() for r in results]

        seed_count = sum(
            1 for r in formatted_results
            if r.get("provenance", "vector_seed") == "vector_seed"
        )
        expanded_count = sum(
            1 for r in formatted_results
            if r.get("provenance") == "graph_expanded"
        )
        rels_used = list({
            r.get("relationship_type")
            for r in formatted_results
            if r.get("relationship_type")
        })

        return ToolResult(
            status=ToolStatus.SUCCESS,
            data={
                "query": query,
                "top_k": top_k,
                "retrieval_mode": "hybrid" if use_graph else "vector_only",
                "total_results": len(formatted_results),
                "seed_count": seed_count,
                "expanded_count": expanded_count,
                "relationships_used": rels_used,
                "results": formatted_results,
            },
            message=(
                f"Hybrid retrieval returned {len(formatted_results)} chunk(s) "
                f"({seed_count} seed(s), {expanded_count} graph-expanded)."
            ),
            metadata={
                "retrieval_mode": "hybrid" if use_graph else "vector_only",
                "intent": intent,
                "use_graph": use_graph,
            },
        )
