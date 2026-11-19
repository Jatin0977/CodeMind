"""
Unified Investigation Engine for CodeMind (Phase 6, Milestone 5).
Acts as the central coordination facade linking intent classification, entity extraction,
dynamic planning, deterministic tool orchestration, evidence collection, and answer synthesis.
"""

import time
import logging
from typing import Optional, Dict, Any

from .models import (
    InvestigationResult,
    InvestigationStatus,
    InvestigationPlan,
)
from .intent import InvestigationIntentClassifier, IntentClassificationResult
from .planner import InvestigationPlanner
from .orchestrator import InvestigationOrchestrator
from .synthesizer import InvestigationSynthesizer
from .tools.registry import ToolRegistry
from .tools import create_tool_registry
from ..ingestion.models import IngestedRepository
from ..graph.query import GraphQueryEngine
from ..retrieval.retriever import SemanticRetriever
from ..retrieval.hybrid_retriever import HybridGraphRetriever
from ..rag.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class InvestigationEngine:
    """
    Unified developer-facing investigation engine.
    Orchestrates the entire investigation lifecycle in a clean, stateless, and grounded manner.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        classifier: Optional[InvestigationIntentClassifier] = None,
        planner: Optional[InvestigationPlanner] = None,
        orchestrator: Optional[InvestigationOrchestrator] = None,
        synthesizer: Optional[InvestigationSynthesizer] = None,
        llm_provider: Optional[BaseLLMProvider] = None,
        repo: Optional[IngestedRepository] = None,
        query_engine: Optional[GraphQueryEngine] = None,
        retriever: Optional[SemanticRetriever] = None,
        hybrid_retriever: Optional[HybridGraphRetriever] = None,
        git_miner: Optional[Any] = None,
        git_client: Optional[Any] = None,
        git_churn_analyzer: Optional[Any] = None,
        git_coupling_analyzer: Optional[Any] = None,
        impact_engine: Optional[Any] = None,
        impact_scorer: Optional[Any] = None,
        test_engine: Optional[Any] = None,
        enable_impact: bool = False,
    ):
        """
        Initialize the investigation engine with explicit dependencies.
        Supports full dependency injection for testing and specialized setups.
        """
        self.repo = repo
        self.query_engine = query_engine
        self.retriever = retriever
        self.hybrid_retriever = hybrid_retriever
        self.git_miner = git_miner
        self.git_client = git_client
        self.git_churn_analyzer = git_churn_analyzer
        self.git_coupling_analyzer = git_coupling_analyzer
        self.impact_engine = impact_engine
        self.impact_scorer = impact_scorer
        self.test_engine = test_engine

        # 1. Tool registry
        if registry is not None:
            self.registry = registry
        else:
            self.registry = create_tool_registry(
                repo=repo,
                query_engine=query_engine,
                retriever=retriever,
                hybrid_retriever=hybrid_retriever,
                git_miner=git_miner,
                git_client=git_client,
                git_churn_analyzer=git_churn_analyzer,
                git_coupling_analyzer=git_coupling_analyzer,
                impact_engine=impact_engine,
                impact_scorer=impact_scorer,
                test_engine=test_engine,
                enable_impact=enable_impact,
            )

        # 2. Intent classifier
        self.classifier = classifier or InvestigationIntentClassifier()

        # 3. Dynamic planner
        self.planner = planner or InvestigationPlanner(classifier=self.classifier)

        # 4. Tool execution orchestrator
        self.orchestrator = orchestrator or InvestigationOrchestrator(registry=self.registry)

        # 5. Evidence synthesizer
        self.synthesizer = synthesizer or InvestigationSynthesizer(llm_provider=llm_provider)

    def investigate(self, query: str) -> InvestigationResult:
        """
        Execute an end-to-end investigation for a developer query.

        Coordinates:
        1. Query validation
        2. Intent classification and entity extraction
        3. Dynamic plan construction
        4. Dependency-aware tool execution
        5. Grounded evidence aggregation
        6. Structured developer answer synthesis

        Args:
            query: Natural language developer question.

        Returns:
            Fully populated InvestigationResult instance.
        """
        start_time = time.time()

        # Step 1: Query validation
        if not query or not isinstance(query, str) or not query.strip():
            return InvestigationResult(
                query=query if isinstance(query, str) else "",
                intent=None,
                plan=None,
                step_results=[],
                evidence=[],
                final_answer="Query cannot be empty or non-string.",
                overall_status=InvestigationStatus.FAILED,
                metadata={
                    "error": "empty_query",
                    "message": "Query string is empty or contains only whitespace.",
                    "total_duration_ms": 0.0,
                },
            )

        q_clean = query.strip()

        try:
            # Step 2: Intent classification & entity extraction
            intent_res: IntentClassificationResult = self.classifier.classify(q_clean)

            # Step 3: Investigation planning
            plan: InvestigationPlan = self.planner.plan(
                query=q_clean,
                registry=self.registry,
                intent_result=intent_res,
                repo=self.repo,
            )

            # Step 4 & 5: Tool orchestration & evidence collection
            exec_result: InvestigationResult = self.orchestrator.execute(
                plan=plan,
                registry=self.registry,
            )

            # Step 6: Evidence-grounded answer synthesis
            self.synthesizer.synthesize(exec_result)

            # Step 7: Final metadata enhancement
            total_duration_ms = round((time.time() - start_time) * 1000, 2)
            exec_result.metadata["engine"] = {
                "version": "1.0",
                "classification": intent_res.to_dict(),
                "total_duration_ms": total_duration_ms,
            }

            return exec_result

        except Exception as exc:
            total_duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error(f"Investigation pipeline encountered fatal exception: {exc}", exc_info=True)
            return InvestigationResult(
                query=q_clean,
                intent=locals().get("intent_res", None).intent if "intent_res" in locals() and locals().get("intent_res") else None,
                plan=locals().get("plan", None),
                step_results=[],
                evidence=[],
                final_answer=f"Investigation failed due to unexpected internal error: {type(exc).__name__}: {str(exc)}",
                overall_status=InvestigationStatus.FAILED,
                metadata={
                    "error": "pipeline_exception",
                    "exception_type": type(exc).__name__,
                    "exception_message": str(exc),
                    "total_duration_ms": total_duration_ms,
                },
            )


def create_investigation_engine(
    repo: Optional[IngestedRepository] = None,
    query_engine: Optional[GraphQueryEngine] = None,
    retriever: Optional[SemanticRetriever] = None,
    hybrid_retriever: Optional[HybridGraphRetriever] = None,
    llm_provider: Optional[BaseLLMProvider] = None,
) -> InvestigationEngine:
    """
    Convenience factory to construct a fully configured InvestigationEngine.
    """
    return InvestigationEngine(
        repo=repo,
        query_engine=query_engine,
        retriever=retriever,
        hybrid_retriever=hybrid_retriever,
        llm_provider=llm_provider,
    )
