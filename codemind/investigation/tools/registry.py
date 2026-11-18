"""
Deterministic ToolRegistry for managing CodeMind investigation tools.
Maintains tool schemas, manages availability state, and enforces registration integrity.
"""

from collections import OrderedDict
from typing import Dict, List, Optional, Set, Iterator, Any

from .base import BaseTool
from ..models import ToolAvailability


class ToolRegistry:
    """
    Central, deterministic catalog of investigation tools.
    Ensures unique registrations, validates tool conformance, and partitions tools
    by availability (AVAILABLE vs DEFERRED).
    """

    def __init__(self):
        # Use OrderedDict to guarantee deterministic listing order across all platforms
        self._tools: OrderedDict[str, BaseTool] = OrderedDict()

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: An instance implementing BaseTool.

        Raises:
            TypeError: If the object does not implement BaseTool.
            ValueError: If tool name is empty, invalid, or already registered.
        """
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Registered object must inherit from BaseTool, got {type(tool).__name__}.")

        name = tool.name
        if not name or not isinstance(name, str):
            raise ValueError("Tool name must be a non-empty string.")

        if name in self._tools:
            raise ValueError(f"Tool with name '{name}' is already registered.")

        self._tools[name] = tool

    def get(self, tool_name: str) -> Optional[BaseTool]:
        """
        Retrieve a tool by name, returning None if not found.

        Args:
            tool_name: Name of tool to look up.
        """
        return self._tools.get(tool_name)

    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Convenience alias for get()."""
        return self.get(tool_name)

    def get_definition(self, tool_name: str) -> Optional[Any]:
        """Retrieve definition for a registered tool, returning None if not found."""
        tool = self.get(tool_name)
        return tool.definition if tool else None

    def get_or_raise(self, tool_name: str) -> BaseTool:
        """
        Retrieve a tool by name, raising KeyError if not found.

        Args:
            tool_name: Name of tool to look up.
        """
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' not found in registry.")
        return self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """Check if tool name is currently registered."""
        return tool_name in self._tools

    def list_tools(self) -> List[BaseTool]:
        """Return all registered tools in deterministic registration order."""
        return list(self._tools.values())

    def list_available(self) -> List[BaseTool]:
        """Return all currently implemented and available tools in registration order."""
        return [
            tool for tool in self._tools.values()
            if tool.availability == ToolAvailability.AVAILABLE
        ]

    def list_deferred(self) -> List[BaseTool]:
        """Return all deferred tools scheduled for future development phases."""
        return [
            tool for tool in self._tools.values()
            if tool.availability == ToolAvailability.DEFERRED
        ]

    def unregister(self, tool_name: str) -> bool:
        """Remove a tool from the registry. Returns True if removed, False if not found."""
        if tool_name in self._tools:
            del self._tools[tool_name]
            return True
        return False

    def clear(self) -> None:
        """Remove all tools from the registry."""
        self._tools.clear()

    def count(self) -> int:
        """Return total number of registered tools."""
        return len(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def __iter__(self) -> Iterator[BaseTool]:
        return iter(self._tools.values())
