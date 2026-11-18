"""
Core data models for CodeMind Agentic Investigation Engine (Phase 6).
Provides typed, validated, and serializable models for investigation planning,
tool definitions, step execution traces, and grounded results.
"""

import time
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Union, Set


class InvestigationIntent(str, Enum):
    """
    Classified developer investigation intents.
    Represents the five core investigation categories outlined in the
    CodeMind Project Master Documentation (Chapter 7 & Chapter 13).
    """
    UNDERSTAND = "understand"  # Explaining workflows, architecture, implementation
    STRUCTURE = "structure"    # Class hierarchies, callers, callees, dependencies
    IMPACT = "impact"          # Reverse dependency reachability, blast radius
    EVOLUTION = "evolution"    # Historical changes, Git commits, churn (Phase 7)
    INSIGHTS = "insights"      # Hotspots, maintainability risks, conformance (Phase 9)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.lower() == other.lower()
        if isinstance(other, InvestigationIntent):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value.lower())


class ToolStatus(str, Enum):
    """Execution status for investigation tools and step runs."""
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    UNAVAILABLE_DEFERRED = "UNAVAILABLE_DEFERRED"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, ToolStatus):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value.upper())


class StepStatus(str, Enum):
    """Execution status for individual plan steps within an investigation."""
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    UNAVAILABLE_DEFERRED = "UNAVAILABLE_DEFERRED"
    SKIPPED = "SKIPPED"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, (StepStatus, ToolStatus)):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value.upper())


# Retain ToolStatus.SKIPPED alias for backward-compatibility with step execution traces
ToolStatus.SKIPPED = StepStatus.SKIPPED


class InvestigationStatus(str, Enum):
    """Overall status of an orchestrated investigation execution."""
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"
    DEFERRED = "DEFERRED"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, InvestigationStatus):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value.upper())


class ToolAvailability(str, Enum):
    """Availability classification for investigation tools."""
    AVAILABLE = "AVAILABLE"    # Fully implemented in current phases
    DEFERRED = "DEFERRED"      # Scheduled for a future development phase (e.g., Phase 7, 8, 9)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.value.upper() == other.upper()
        if isinstance(other, ToolAvailability):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value.upper())


@dataclass
class ToolDefinition:
    """
    Formal schema and metadata specification for an investigation tool.
    Used by the InvestigationPlanner to match intents to valid capabilities.
    """
    tool_name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    availability: Union[ToolAvailability, str] = ToolAvailability.AVAILABLE
    target_phase: Optional[str] = None  # e.g., "Phase 7: Git Temporal Intelligence"
    required_capabilities: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.tool_name or not isinstance(self.tool_name, str):
            raise ValueError("ToolDefinition.tool_name must be a non-empty string.")
        if not self.description or not isinstance(self.description, str):
            raise ValueError("ToolDefinition.description must be a non-empty string.")

        # Normalize availability enum
        if isinstance(self.availability, str):
            try:
                self.availability = ToolAvailability(self.availability.upper())
            except ValueError:
                self.availability = ToolAvailability.AVAILABLE

        # Deferred tools must identify their planned milestone
        if self.availability == ToolAvailability.DEFERRED and not self.target_phase:
            raise ValueError("Deferred tools must specify target_phase.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert ToolDefinition to a JSON-serializable dictionary."""
        return {
            "tool_name": self.tool_name,
            "description": self.description,
            "input_schema": self.input_schema,
            "availability": str(self.availability.value if isinstance(self.availability, ToolAvailability) else self.availability),
            "target_phase": self.target_phase,
            "required_capabilities": list(self.required_capabilities),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolDefinition":
        """Instantiate ToolDefinition from dictionary data."""
        return cls(
            tool_name=data["tool_name"],
            description=data["description"],
            input_schema=data.get("input_schema", {}),
            availability=data.get("availability", ToolAvailability.AVAILABLE),
            target_phase=data.get("target_phase"),
            required_capabilities=data.get("required_capabilities", []),
        )


@dataclass
class PlanStep:
    """
    A single planned action within an InvestigationPlan.
    Supports parameterized arguments with future support for output variable references
    (e.g., `{"node_id": "$step_1.primary_node_id"}`).
    """
    step_id: str
    tool_name: str
    purpose: str = ""
    input_parameters: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)  # Prior step_ids required before execution
    is_required: bool = True  # If False, failure does not abort downstream steps

    def __post_init__(self):
        if not self.step_id or not isinstance(self.step_id, str):
            raise ValueError("PlanStep.step_id must be a non-empty string.")
        if not self.tool_name or not isinstance(self.tool_name, str):
            raise ValueError("PlanStep.tool_name must be a non-empty string.")

    def to_dict(self) -> Dict[str, Any]:
        """Convert PlanStep to dictionary."""
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "purpose": self.purpose,
            "input_parameters": self.input_parameters,
            "dependencies": list(self.dependencies),
            "is_required": self.is_required,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        """Instantiate PlanStep from dictionary data."""
        return cls(
            step_id=data["step_id"],
            tool_name=data["tool_name"],
            purpose=data.get("purpose", ""),
            input_parameters=data.get("input_parameters", {}),
            dependencies=data.get("dependencies", []),
            is_required=data.get("is_required", True),
        )


@dataclass
class InvestigationPlan:
    """
    Structured, ordered plan of analytical steps to address a developer question.
    Generated dynamically by the InvestigationPlanner based on intent and entities.
    """
    plan_id: str
    original_query: str
    intent: Union[InvestigationIntent, str]
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    steps: List[PlanStep] = field(default_factory=list)
    creation_metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.plan_id:
            raise ValueError("InvestigationPlan.plan_id must be a non-empty string.")
        if not self.original_query:
            raise ValueError("InvestigationPlan.original_query must be non-empty.")

        if isinstance(self.intent, str):
            try:
                self.intent = InvestigationIntent(self.intent.lower())
            except ValueError:
                pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert InvestigationPlan to dictionary."""
        intent_str = self.intent.value if isinstance(self.intent, InvestigationIntent) else str(self.intent)
        return {
            "plan_id": self.plan_id,
            "original_query": self.original_query,
            "intent": intent_str,
            "extracted_entities": self.extracted_entities,
            "steps": [s.to_dict() for s in self.steps],
            "creation_metadata": self.creation_metadata,
            "created_at": round(self.created_at, 4),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestigationPlan":
        """Instantiate InvestigationPlan from dictionary data."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            plan_id=data["plan_id"],
            original_query=data["original_query"],
            intent=data.get("intent", InvestigationIntent.UNDERSTAND),
            extracted_entities=data.get("extracted_entities", {}),
            steps=steps,
            creation_metadata=data.get("creation_metadata", {}),
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class StepResult:
    """
    Execution trace and result produced by executing a single PlanStep.
    Retains individual tool outputs as attributable evidence.
    """
    step_id: str
    tool_name: str
    status: Union[ToolStatus, str] = ToolStatus.SUCCESS
    output: Optional[Any] = None
    error_message: Optional[str] = None
    warning: Optional[str] = None
    execution_timing: Dict[str, float] = field(default_factory=dict)  # {"start_time": ..., "end_time": ..., "latency_ms": ...}

    def __post_init__(self):
        if isinstance(self.status, str):
            try:
                self.status = StepStatus(self.status.upper())
            except ValueError:
                try:
                    self.status = ToolStatus(self.status.upper())
                except ValueError:
                    pass

    @property
    def is_success(self) -> bool:
        """Check if step executed successfully."""
        return self.status == ToolStatus.SUCCESS

    @property
    def is_deferred(self) -> bool:
        """Check if step represented a deferred tool."""
        return self.status == ToolStatus.UNAVAILABLE_DEFERRED

    @property
    def is_error(self) -> bool:
        """Check if step experienced an error."""
        return self.status == ToolStatus.ERROR

    @property
    def is_skipped(self) -> bool:
        """Check if step was skipped."""
        return self.status == ToolStatus.SKIPPED or str(self.status).upper() == "SKIPPED"

    def to_dict(self) -> Dict[str, Any]:
        """Convert StepResult to dictionary."""
        status_str = self.status.value if hasattr(self.status, "value") else str(self.status)
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "status": status_str,
            "output": self.output,
            "error_message": self.error_message,
            "warning": self.warning,
            "execution_timing": self.execution_timing,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepResult":
        """Instantiate StepResult from dictionary data."""
        return cls(
            step_id=data["step_id"],
            tool_name=data["tool_name"],
            status=data.get("status", ToolStatus.SUCCESS),
            output=data.get("output"),
            error_message=data.get("error_message"),
            warning=data.get("warning"),
            execution_timing=data.get("execution_timing", {}),
        )


@dataclass
class InvestigationResult:
    """
    Comprehensive response model for an end-to-end codebase investigation.
    Combines query metadata, generated plan, execution traces, attributable evidence,
    and the final synthesized answer.
    """
    query: str
    intent: Optional[Union[InvestigationIntent, str]] = None
    plan: Optional[InvestigationPlan] = None
    step_results: List[StepResult] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    final_answer: Optional[str] = None
    overall_status: Union[InvestigationStatus, ToolStatus, str] = InvestigationStatus.SUCCESS
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.intent, str):
            try:
                self.intent = InvestigationIntent(self.intent.lower())
            except ValueError:
                pass
        if isinstance(self.overall_status, str):
            try:
                self.overall_status = InvestigationStatus(self.overall_status.upper())
            except ValueError:
                try:
                    self.overall_status = ToolStatus(self.overall_status.upper())
                except ValueError:
                    pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert InvestigationResult to dictionary."""
        intent_str = self.intent.value if isinstance(self.intent, InvestigationIntent) else (str(self.intent) if self.intent else None)
        if isinstance(self.overall_status, (InvestigationStatus, ToolStatus)):
            status_str = self.overall_status.value
        else:
            status_str = str(self.overall_status)
        return {
            "query": self.query,
            "intent": intent_str,
            "plan": self.plan.to_dict() if self.plan else None,
            "step_results": [r.to_dict() for r in self.step_results],
            "evidence": self.evidence,
            "final_answer": self.final_answer,
            "overall_status": status_str,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InvestigationResult":
        """Instantiate InvestigationResult from dictionary data."""
        plan = InvestigationPlan.from_dict(data["plan"]) if data.get("plan") else None
        step_results = [StepResult.from_dict(r) for r in data.get("step_results", [])]
        return cls(
            query=data["query"],
            intent=data.get("intent"),
            plan=plan,
            step_results=step_results,
            evidence=data.get("evidence", []),
            final_answer=data.get("final_answer"),
            overall_status=data.get("overall_status", InvestigationStatus.SUCCESS),
            metadata=data.get("metadata", {}),
        )
