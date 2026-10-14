"""
Data models and type definitions for CodeMind Software Knowledge Graph.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List


class NodeType:
    """Standardized node types in the Software Knowledge Graph."""
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"


class EdgeType:
    """Standardized directed edge types in the Software Knowledge Graph."""
    CONTAINS = "CONTAINS"    # Container contains child (File -> Class/Function, Class -> Method)
    CALLS = "CALLS"          # Invocation relationship (Caller -> Callee)
    IMPORTS = "IMPORTS"      # Module/File import relationship (Importer -> Imported)
    INHERITS = "INHERITS"    # Object-oriented inheritance (Derived -> Base)


@dataclass
class Node:
    """Represents an entity node in the code graph."""
    id: str
    name: str
    node_type: str
    file_path: Optional[str] = None
    relative_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    language: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Node to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "node_type": self.node_type,
            "file_path": self.file_path,
            "relative_path": self.relative_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "language": self.language,
            "metadata": self.metadata,
        }


@dataclass
class Edge:
    """Represents a directed relationship edge between two nodes in the code graph."""
    source: str
    target: str
    edge_type: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Edge to dictionary representation."""
        return {
            "source": self.source,
            "target": self.target,
            "edge_type": self.edge_type,
            "metadata": self.metadata,
        }


@dataclass
class GraphSummary:
    """Summary metrics of the constructed Software Knowledge Graph."""
    total_nodes: int
    total_edges: int
    node_type_counts: Dict[str, int]
    edge_type_counts: Dict[str, int]
    has_cycles: bool = False
    cycle_count: int = 0
    cycles: List[List[str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert GraphSummary to dictionary."""
        return asdict(self)
