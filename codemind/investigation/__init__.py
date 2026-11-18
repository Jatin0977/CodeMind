"""
CodeMind Agentic Investigation Engine package (Phase 6).
Provides foundational models, standardized tool wrappers, intent classification,
and dynamic investigation planning for Milestones 1–3.
"""

from .models import (
    InvestigationIntent,
    InvestigationStatus,
    ToolStatus,
    ToolAvailability,
    ToolDefinition,
    PlanStep,
    InvestigationPlan,
    StepResult,
    InvestigationResult,
)
from .tools import (
    BaseTool,
    ToolResult,
    DeferredTool,
    ToolRegistry,
    SearchSymbolsTool,
    GetNodeDetailsTool,
    GetFileContentTool,
    GetCallersTool,
    GetCalleesTool,
    GetDependenciesTool,
    GetDependentsTool,
    TraceStructuralImpactTool,
    DetectCyclesTool,
    SemanticSearchTool,
    HybridSearchTool,
    create_deferred_tools,
    create_tool_registry,
)
from .intent import (
    ExtractedEntities,
    EntityExtractor,
    IntentClassificationResult,
    InvestigationIntentClassifier,
    classify_investigation_intent,
)
from .planner import InvestigationPlanner
from .resolver import (
    ReferenceResolver,
    resolve_step_parameters,
    ResolutionResult,
    ReferenceResolutionError,
    MalformedReferenceError,
    StepNotFoundError,
    StepNotSuccessfulError,
    FieldNotFoundError,
    AmbiguousSymbolError,
    UnavailableValueError,
)
from .collector import (
    EvidenceItem,
    EvidenceCollector,
)
from .orchestrator import InvestigationOrchestrator
from .synthesizer import (
    InvestigationCitation,
    InvestigationSynthesizer,
    SYNTHESIZER_SYSTEM_INSTRUCTION,
)
from .engine import (
    InvestigationEngine,
    create_investigation_engine,
)

__all__ = [
    # Models
    "InvestigationIntent",
    "InvestigationStatus",
    "ToolStatus",
    "ToolAvailability",
    "ToolDefinition",
    "PlanStep",
    "InvestigationPlan",
    "StepResult",
    "InvestigationResult",
    # Tools
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
    "create_deferred_tools",
    "create_tool_registry",
    # Intent & Planning
    "ExtractedEntities",
    "EntityExtractor",
    "IntentClassificationResult",
    "InvestigationIntentClassifier",
    "classify_investigation_intent",
    "InvestigationPlanner",
    # Resolver
    "ReferenceResolver",
    "resolve_step_parameters",
    "ResolutionResult",
    "ReferenceResolutionError",
    "MalformedReferenceError",
    "StepNotFoundError",
    "StepNotSuccessfulError",
    "FieldNotFoundError",
    "AmbiguousSymbolError",
    "UnavailableValueError",
    # Collector
    "EvidenceItem",
    "EvidenceCollector",
    # Orchestrator
    "InvestigationOrchestrator",
    # Synthesizer
    "InvestigationCitation",
    "InvestigationSynthesizer",
    "SYNTHESIZER_SYSTEM_INSTRUCTION",
    # Engine
    "InvestigationEngine",
    "create_investigation_engine",
]
