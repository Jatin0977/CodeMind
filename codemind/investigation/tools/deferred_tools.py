"""
Deferred future-phase tools for CodeMind Agentic Investigation Engine (Phase 6, Milestone 2).
Provides formal DeferredTool placeholders for Phase 7 (Git Temporal),
Phase 8 (Multi-Signal Impact & Test Mapping), and Phase 9 (Hotspots & Architecture).

Strict Architectural Rule:
All tools in this module return ToolStatus.UNAVAILABLE_DEFERRED with data=None.
Never simulate, mock, or fabricate results for unbuilt analytical capabilities.
"""

from typing import List
from .base import DeferredTool


def create_deferred_tools(include_git: bool = True) -> List[DeferredTool]:
    """
    Construct and return all formal DeferredTool instances for future/uninitialized phases.
    Preserves strict phase boundaries without fabricating analytical outputs.

    Args:
        include_git: If True, includes Phase 7 Git Temporal deferred placeholders
                     (for Phase 6 backward compatibility / non-git environments).
                     If False, only includes Phase 8 and Phase 9 deferred tools.
    """
    tools = []
    if include_git:
        tools.extend([
            DeferredTool(
                name="git_commit_history",
                description="Mine Git commit log to analyze chronological evolution and revision history of files or symbols.",
                target_phase="Phase 7: Git Temporal Intelligence",
                required_capabilities=["git_cli", "commit_graph"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Optional file path to filter commit history"},
                        "limit": {"type": "integer", "default": 20, "description": "Maximum commits to retrieve"},
                    },
                },
            ),
            DeferredTool(
                name="git_code_churn",
                description="Calculate historical file-level modification frequency, additions, and deletions from Git history.",
                target_phase="Phase 7: Git Temporal Intelligence",
                required_capabilities=["git_cli", "churn_analyzer"],
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Optional file or directory path"},
                    },
                },
            ),
        ])

    tools.extend([
        # Phase 8 — Change Impact and Test Intelligence
        DeferredTool(
            name="multi_signal_impact",
            description="Calculate explainable Multi-Signal Impact Score combining structural reach, churn, and logical coupling.",
            target_phase="Phase 8: Change Impact and Test Intelligence",
            required_capabilities=["coupling_miner", "centrality_scorer", "multi_signal_ranker"],
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {"type": "string", "description": "Target entity node ID"},
                },
            },
        ),
        DeferredTool(
            name="get_test_coverage",
            description="Map code entities to direct and heuristically inferred automated test suites and regression paths.",
            target_phase="Phase 8: Change Impact and Test Intelligence",
            required_capabilities=["test_mapper", "coverage_analyzer"],
            input_schema={
                "type": "object",
                "required": ["node_id"],
                "properties": {
                    "node_id": {"type": "string", "description": "Target entity node ID"},
                },
            },
        ),
        # Phase 9 — Advanced Architecture and Risk Insights
        DeferredTool(
            name="detect_maintenance_hotspots",
            description="Identify maintenance hotspots by cross-referencing code churn, cyclomatic complexity, and centrality.",
            target_phase="Phase 9: Advanced Architecture and Risk Insights",
            required_capabilities=["hotspot_detector", "complexity_analyzer", "churn_analyzer"],
            input_schema={"type": "object"},
        ),
        DeferredTool(
            name="check_architecture_conformance",
            description="Validate architectural layering and dependency conformance against configured architectural boundaries.",
            target_phase="Phase 9: Advanced Architecture and Risk Insights",
            required_capabilities=["conformance_engine", "layer_definitions"],
            input_schema={"type": "object"},
        ),
    ])
    return tools
