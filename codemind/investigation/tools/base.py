"""
Base abstractions and standardized interfaces for CodeMind investigation tools.
Provides BaseTool, ToolResult, and DeferredTool implementations for Milestone 1.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union

from ..models import ToolStatus, ToolAvailability, ToolDefinition


@dataclass
class ToolResult:
    """
    Standardized, structured result produced by any investigation tool execution.
    Prevents raw exceptions from leaking into the orchestration layer.
    """
    status: Union[ToolStatus, str]
    data: Optional[Any] = None
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if isinstance(self.status, str):
            try:
                self.status = ToolStatus(self.status.upper())
            except ValueError:
                pass

    @property
    def is_success(self) -> bool:
        """Return True if tool executed successfully."""
        return self.status == ToolStatus.SUCCESS

    @property
    def is_deferred(self) -> bool:
        """Return True if tool represents an unavailable future-phase capability."""
        return self.status == ToolStatus.UNAVAILABLE_DEFERRED

    @property
    def is_error(self) -> bool:
        """Return True if tool execution failed or was given invalid arguments."""
        return self.status == ToolStatus.ERROR

    def to_dict(self) -> Dict[str, Any]:
        """Convert ToolResult to a JSON-serializable dictionary."""
        status_str = self.status.value if isinstance(self.status, ToolStatus) else str(self.status)
        return {
            "status": status_str,
            "data": self.data,
            "message": self.message,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolResult":
        """Instantiate ToolResult from dictionary data."""
        return cls(
            status=data.get("status", ToolStatus.SUCCESS),
            data=data.get("data"),
            message=data.get("message", ""),
            metadata=data.get("metadata", {}),
        )


class BaseTool(ABC):
    """
    Abstract base class for all investigation tools in CodeMind.
    Enforces a uniform interface, argument validation, and exception-safe execution.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier name of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable explanation of tool functionality."""
        pass

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Formal ToolDefinition schema containing input requirements and metadata."""
        pass

    @property
    def availability(self) -> ToolAvailability:
        """Tool availability status (default: AVAILABLE)."""
        return ToolAvailability.AVAILABLE

    def validate_arguments(self, arguments: Dict[str, Any]) -> Optional[str]:
        """
        Validate input arguments against definition.
        Returns None if valid, or an error string if invalid.
        Default implementation checks required fields defined in input_schema.
        """
        if not isinstance(arguments, dict):
            return "Arguments must be provided as a dictionary."

        schema = self.definition.input_schema if self.definition else {}
        required = schema.get("required", [])
        for field_name in required:
            if field_name not in arguments or arguments[field_name] is None:
                return f"Missing required parameter '{field_name}'."
        return None

    def execute(self, arguments: Optional[Dict[str, Any]] = None) -> ToolResult:
        """
        Exception-safe tool execution wrapper.
        Validates arguments, catches unhandled exceptions, and returns a structured ToolResult.
        """
        args = arguments if arguments is not None else {}

        # 1. Validate arguments
        validation_error = self.validate_arguments(args)
        if validation_error:
            args_keys = list(args.keys()) if isinstance(args, dict) else []
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message=f"Validation failed for tool '{self.name}': {validation_error}",
                metadata={"validation_error": validation_error, "arguments_received": args_keys},
            )

        # 2. Execute concrete tool logic
        try:
            return self._run(args)
        except Exception as e:
            return ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                message=f"Tool execution failed for '{self.name}': {str(e)}",
                metadata={"exception_type": type(e).__name__, "exception_details": str(e)},
            )

    @abstractmethod
    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Concrete execution logic implemented by subclasses.
        Must return a structured ToolResult.
        """
        pass


class DeferredTool(BaseTool):
    """
    Reusable implementation for future-phase analytical tools.
    Explicitly reports capability boundaries for Phase 7 (Git Temporal),
    Phase 8 (Multi-Signal Impact & Test Mapping), and Phase 9 (Hotspots & Architecture).

    Crucial Constraint:
    Never simulates, fabricates, or invents results for deferred capabilities.
    """

    def __init__(
        self,
        name: str,
        description: str,
        target_phase: str,
        required_capabilities: Optional[List[str]] = None,
        input_schema: Optional[Dict[str, Any]] = None,
    ):
        if not name or not isinstance(name, str):
            raise ValueError("DeferredTool requires a valid name.")
        if not target_phase or not isinstance(target_phase, str):
            raise ValueError("DeferredTool requires a target_phase specification.")

        self._name = name
        self._description = description
        self._target_phase = target_phase
        self._required_capabilities = required_capabilities or []
        self._input_schema = input_schema or {}

        self._definition = ToolDefinition(
            tool_name=self._name,
            description=self._description,
            input_schema=self._input_schema,
            availability=ToolAvailability.DEFERRED,
            target_phase=self._target_phase,
            required_capabilities=self._required_capabilities,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    @property
    def availability(self) -> ToolAvailability:
        return ToolAvailability.DEFERRED

    @property
    def target_phase(self) -> str:
        return self._target_phase

    def _run(self, arguments: Dict[str, Any]) -> ToolResult:
        """
        Returns UNAVAILABLE_DEFERRED with an informative, transparent message.
        Guarantees data is None and never fabricated.
        """
        return ToolResult(
            status=ToolStatus.UNAVAILABLE_DEFERRED,
            data=None,
            message=(
                f"Capability '{self.name}' is currently unavailable. "
                f"This analytical feature is scheduled for {self.target_phase}."
            ),
            metadata={
                "tool_name": self.name,
                "target_phase": self.target_phase,
                "required_capabilities": self._required_capabilities,
                "received_arguments": arguments,
            },
        )
