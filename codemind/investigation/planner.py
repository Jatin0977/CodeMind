"""
Investigation Planner for CodeMind Agentic Investigation Engine (Phase 6, Milestone 3).
Converts natural-language queries and classified intents into ordered, validated,
dependency-aware investigation plans using registered tools.
"""

import hashlib
import time
from typing import Dict, Any, Optional, List, Set, Union

from .models import (
    InvestigationIntent,
    InvestigationPlan,
    PlanStep,
    ToolAvailability,
)
from .tools.registry import ToolRegistry
from .intent import (
    IntentClassificationResult,
    InvestigationIntentClassifier,
    ExtractedEntities,
)
from ..ingestion.models import IngestedRepository


class InvestigationPlanner:
    """
    Constructs deterministic, query-aware investigation plans tailored to developer intent.
    Enforces strict dependency acyclicity, validates tool registration, and accurately
    tags available vs. deferred analytical capabilities.
    """

    def __init__(self, classifier: Optional[InvestigationIntentClassifier] = None):
        self.classifier = classifier or InvestigationIntentClassifier()

    def plan(
        self,
        query: str,
        registry: ToolRegistry,
        intent_result: Optional[IntentClassificationResult] = None,
        repo: Optional[IngestedRepository] = None,
    ) -> InvestigationPlan:
        """
        Generate an ordered, validated InvestigationPlan for the given query.

        Args:
            query: Natural language developer query.
            registry: Central ToolRegistry containing registered tools.
            intent_result: Optional pre-computed IntentClassificationResult.
            repo: Optional IngestedRepository instance for context.

        Returns:
            Validated InvestigationPlan instance.
        """
        q_clean = query.strip() if query else ""

        # Step 1: Resolve intent classification
        if intent_result is None:
            intent_result = self.classifier.classify(q_clean)

        intent = intent_result.intent
        entities = intent_result.extracted_entities
        primary_entity = entities.primary_entity

        # Step 2: Assemble workflow steps based on intent
        raw_steps: List[Dict[str, Any]] = []

        if intent == InvestigationIntent.UNDERSTAND:
            raw_steps = self._plan_understand_workflow(q_clean, entities, primary_entity)
        elif intent == InvestigationIntent.STRUCTURE:
            raw_steps = self._plan_structure_workflow(q_clean, entities, primary_entity)
        elif intent == InvestigationIntent.IMPACT:
            raw_steps = self._plan_impact_workflow(q_clean, entities, primary_entity)
        elif intent == InvestigationIntent.EVOLUTION:
            raw_steps = self._plan_evolution_workflow(q_clean, entities, primary_entity)
        elif intent == InvestigationIntent.INSIGHTS:
            raw_steps = self._plan_insights_workflow(q_clean, entities, primary_entity)
        else:
            raw_steps = self._plan_understand_workflow(q_clean, entities, primary_entity)

        # Step 3: Validate, number, and bind steps against registry
        validated_steps: List[PlanStep] = []
        step_id_map: Dict[str, str] = {}  # temporary tag -> final step_id

        # Pass 1: Filter to tools that actually exist in the registry and assign step IDs
        valid_candidates: List[Dict[str, Any]] = []
        for step_data in raw_steps:
            tool_name = step_data["tool_name"]
            if not registry.has_tool(tool_name):
                # Omit tools not available in the given registry
                continue
            valid_candidates.append(step_data)

        for idx, step_data in enumerate(valid_candidates, start=1):
            temp_tag = step_data.get("tag", f"step_{idx}")
            final_step_id = f"step_{idx}"
            step_id_map[temp_tag] = final_step_id

        # Pass 2: Build PlanStep objects with resolved dependencies
        for idx, step_data in enumerate(valid_candidates, start=1):
            tool_name = step_data["tool_name"]
            final_step_id = f"step_{idx}"

            # Map dependencies from temp tags to final step IDs
            raw_deps = step_data.get("dependencies", [])
            mapped_deps: List[str] = []
            for d in raw_deps:
                mapped_id = step_id_map.get(d)
                if mapped_id and mapped_id != final_step_id:
                    # Validate dependency is strictly earlier
                    dep_idx = int(mapped_id.split("_")[1])
                    curr_idx = int(final_step_id.split("_")[1])
                    if dep_idx < curr_idx and mapped_id not in mapped_deps:
                        mapped_deps.append(mapped_id)

            # Map variable references in input parameters
            input_params = dict(step_data.get("input_parameters", {}))
            for k, v in list(input_params.items()):
                if isinstance(v, str) and v.startswith("$"):
                    for temp_tag, mapped_id in step_id_map.items():
                        if v.startswith(f"${temp_tag}"):
                            input_params[k] = v.replace(f"${temp_tag}", f"${mapped_id}")
                            break

            plan_step = PlanStep(
                step_id=final_step_id,
                tool_name=tool_name,
                purpose=step_data.get("purpose", ""),
                input_parameters=input_params,
                dependencies=mapped_deps,
                is_required=step_data.get("is_required", True),
            )
            validated_steps.append(plan_step)

        # Step 4: Validate plan integrity (acyclicity, unique step IDs)
        self._validate_plan_integrity(validated_steps)

        # Step 5: Deterministic Plan ID generation
        plan_hash = hashlib.sha256(f"{q_clean}:{intent.value}:{len(validated_steps)}".encode()).hexdigest()[:12]
        plan_id = f"plan_{plan_hash}"

        return InvestigationPlan(
            plan_id=plan_id,
            original_query=q_clean,
            intent=intent,
            extracted_entities=entities.to_dict(),
            steps=validated_steps,
            creation_metadata={
                "planner": "InvestigationPlanner",
                "version": "1.0",
                "intent_confidence": intent_result.confidence,
                "confidence_category": intent_result.confidence_category,
                "is_ambiguous": intent_result.is_ambiguous,
                "total_steps": len(validated_steps),
            },
        )

    # -------------------------------------------------------------------------
    # Intent Workflow Builders
    # -------------------------------------------------------------------------

    def _plan_understand_workflow(
        self,
        query: str,
        entities: ExtractedEntities,
        primary_entity: Optional[str],
    ) -> List[Dict[str, Any]]:
        """UNDERSTAND: search_symbols -> get_node_details -> hybrid_search -> get_callees"""
        steps = []
        target_search = primary_entity or query

        # 1. search_symbols
        steps.append({
            "tag": "search_step",
            "tool_name": "search_symbols",
            "purpose": f"Locate symbol definitions matching '{target_search}' in knowledge graph",
            "input_parameters": {"query": target_search, "limit": 5},
            "dependencies": [],
            "is_required": True,
        })

        # 2. get_node_details (conditional if code entity was identified)
        if primary_entity or entities.classes or entities.functions:
            steps.append({
                "tag": "node_details_step",
                "tool_name": "get_node_details",
                "purpose": "Retrieve detailed attributes, line ranges, and metadata for primary entity",
                "input_parameters": {"node_id": "$search_step.primary_node_id"},
                "dependencies": ["search_step"],
                "is_required": False,
            })

        # 3. hybrid_search for broader implementation context
        steps.append({
            "tag": "hybrid_step",
            "tool_name": "hybrid_search",
            "purpose": "Retrieve grounded implementation chunks and forward call expansions",
            "input_parameters": {"query": query, "top_k": 4, "intent": "flow"},
            "dependencies": [],
            "is_required": True,
        })

        # 4. get_callees (if query asks about execution flow, pipeline, calls, or methods)
        flow_keywords = {"flow", "calls", "how", "step", "pipeline", "execution", "under the hood"}
        if any(kw in query.lower() for kw in flow_keywords) and (primary_entity or entities.functions):
            steps.append({
                "tag": "callees_step",
                "tool_name": "get_callees",
                "purpose": "Inspect functions and methods invoked during execution flow",
                "input_parameters": {"node_id": "$search_step.primary_node_id"},
                "dependencies": ["search_step"],
                "is_required": False,
            })

        return steps

    def _plan_structure_workflow(
        self,
        query: str,
        entities: ExtractedEntities,
        primary_entity: Optional[str],
    ) -> List[Dict[str, Any]]:
        """STRUCTURE: search_symbols -> get_node_details -> get_dependencies/get_dependents -> get_callers/get_callees"""
        steps = []
        target_search = primary_entity or query
        q_lower = query.lower()

        # 1. search_symbols
        steps.append({
            "tag": "search_step",
            "tool_name": "search_symbols",
            "purpose": f"Locate target code entity '{target_search}' in knowledge graph",
            "input_parameters": {"query": target_search, "limit": 5},
            "dependencies": [],
            "is_required": True,
        })

        # 2. get_node_details
        steps.append({
            "tag": "node_details_step",
            "tool_name": "get_node_details",
            "purpose": "Retrieve node definition and structural attributes",
            "input_parameters": {"node_id": "$search_step.primary_node_id"},
            "dependencies": ["search_step"],
            "is_required": False,
        })

        # 3. Directional analysis: Dependents vs Dependencies
        is_reverse_query = any(k in q_lower for k in [
            "who depends", "which components depend", "components depend on",
            "depend on", "used by", "who calls", "callers", "who imports",
        ])

        if is_reverse_query:
            # Incoming dependents
            steps.append({
                "tag": "dependents_step",
                "tool_name": "get_dependents",
                "purpose": "Find incoming dependent components importing, calling, or subclassing entity",
                "input_parameters": {"node_id": "$search_step.primary_node_id", "direct_only": True},
                "dependencies": ["search_step"],
                "is_required": True,
            })
            if "call" in q_lower:
                steps.append({
                    "tag": "callers_step",
                    "tool_name": "get_callers",
                    "purpose": "Find functions and methods that invoke this entity",
                    "input_parameters": {"node_id": "$search_step.primary_node_id"},
                    "dependencies": ["search_step"],
                    "is_required": False,
                })
        else:
            # Outgoing dependencies
            steps.append({
                "tag": "dependencies_step",
                "tool_name": "get_dependencies",
                "purpose": "Find outgoing dependencies (modules imported, functions called, base classes)",
                "input_parameters": {"node_id": "$search_step.primary_node_id", "direct_only": True},
                "dependencies": ["search_step"],
                "is_required": True,
            })
            if "call" in q_lower:
                steps.append({
                    "tag": "callees_step",
                    "tool_name": "get_callees",
                    "purpose": "Find functions and methods invoked by this entity",
                    "input_parameters": {"node_id": "$search_step.primary_node_id"},
                    "dependencies": ["search_step"],
                    "is_required": False,
                })

        return steps

    def _plan_impact_workflow(
        self,
        query: str,
        entities: ExtractedEntities,
        primary_entity: Optional[str],
    ) -> List[Dict[str, Any]]:
        """IMPACT: search_symbols -> get_node_details -> trace_structural_impact -> get_dependents -> get_test_coverage (deferred)"""
        steps = []
        target_search = primary_entity or query

        # 1. search_symbols
        steps.append({
            "tag": "search_step",
            "tool_name": "search_symbols",
            "purpose": f"Identify target entity '{target_search}' for modification impact analysis",
            "input_parameters": {"query": target_search, "limit": 3},
            "dependencies": [],
            "is_required": True,
        })

        # 2. get_node_details
        steps.append({
            "tag": "node_details_step",
            "tool_name": "get_node_details",
            "purpose": "Inspect entity attributes and file location before modification",
            "input_parameters": {"node_id": "$search_step.primary_node_id"},
            "dependencies": ["search_step"],
            "is_required": False,
        })

        # 3. trace_structural_impact
        steps.append({
            "tag": "impact_step",
            "tool_name": "trace_structural_impact",
            "purpose": "Trace multi-hop reverse dependencies (structural reachability blast radius)",
            "input_parameters": {"target_node_id": "$search_step.primary_node_id", "max_depth": 3},
            "dependencies": ["search_step"],
            "is_required": True,
        })

        # 4. get_dependents (immediate direct dependents)
        steps.append({
            "tag": "dependents_step",
            "tool_name": "get_dependents",
            "purpose": "Identify direct incoming dependents for immediate impact breakdown",
            "input_parameters": {"node_id": "$search_step.primary_node_id", "direct_only": True},
            "dependencies": ["search_step"],
            "is_required": False,
        })

        # 5. get_test_coverage (Deferred Tool, Phase 8)
        # Schedule deferred test coverage tool when test intelligence is requested or for full impact evaluation
        steps.append({
            "tag": "test_coverage_step",
            "tool_name": "get_test_coverage",
            "purpose": "Identify automated test suites affected by entity modification (Deferred to Phase 8)",
            "input_parameters": {"node_id": "$search_step.primary_node_id"},
            "dependencies": ["search_step"],
            "is_required": False,
        })

        return steps

    def _plan_evolution_workflow(
        self,
        query: str,
        entities: ExtractedEntities,
        primary_entity: Optional[str],
    ) -> List[Dict[str, Any]]:
        """
        EVOLUTION: Query-dependent planning for Git temporal intelligence.
        Dispatches targeted tools based on sub-intent:
        - History queries -> git_commit_history
        - Churn queries -> git_code_churn
        - Coupling queries -> git_logical_coupling
        - General evolution -> composite plan (history + churn + coupling)
        """
        steps = []
        q_lower = query.lower()
        has_entity = bool(primary_entity or entities.file_paths)
        target_search = primary_entity or (entities.file_paths[0] if entities.file_paths else query)

        # 1. Sub-intent classification within EVOLUTION
        is_history_query = any(w in q_lower for w in [
            "commit", "history", "recent", "log", "who modified", "who wrote",
            "revision", "authored", "touched", "when was", "who changed",
        ])
        is_churn_query = any(w in q_lower for w in [
            "churn", "frequent", "addition", "deletion", "hotspot", "most edited", "most modified",
        ])
        is_coupling_query = any(w in q_lower for w in [
            "co-change", "cochange", "change together", "changed together",
            "coupling", "coupled", "co-occur",
        ])

        is_general_evolution = (
            (not is_history_query and not is_churn_query and not is_coupling_query)
            or any(w in q_lower for w in ["evolv", "over time", "historical", "changes over time"])
        )

        # 2. search_symbols if entity is referenced
        if has_entity:
            steps.append({
                "tag": "search_step",
                "tool_name": "search_symbols",
                "purpose": f"Locate current code entity '{target_search}' in repository snapshot",
                "input_parameters": {"query": target_search, "limit": 3},
                "dependencies": [],
                "is_required": False,
            })

        path_param = "$search_step.primary_relative_path" if has_entity else (entities.file_paths[0] if entities.file_paths else "")

        # 3. git_commit_history
        if is_history_query or is_general_evolution:
            steps.append({
                "tag": "git_history_step",
                "tool_name": "git_commit_history",
                "purpose": "Mine Git commit history for revisions and author tracking",
                "input_parameters": {"path": path_param, "limit": 20},
                "dependencies": ["search_step"] if has_entity else [],
                "is_required": False,
            })

        # 4. git_code_churn
        if is_churn_query or is_general_evolution:
            steps.append({
                "tag": "git_churn_step",
                "tool_name": "git_code_churn",
                "purpose": "Calculate historical file code churn metrics and revision frequency",
                "input_parameters": {"path": path_param, "limit": 20},
                "dependencies": ["search_step"] if has_entity else [],
                "is_required": False,
            })

        # 5. git_logical_coupling
        if is_coupling_query or (is_general_evolution and has_entity):
            steps.append({
                "tag": "git_coupling_step",
                "tool_name": "git_logical_coupling",
                "purpose": "Discover files that historically co-change with target",
                "input_parameters": {"file_path": path_param, "min_support": 3, "min_confidence": 0.5, "limit": 20},
                "dependencies": ["search_step"] if has_entity else [],
                "is_required": False,
            })

        # 6. get_file_content (Current snapshot fallback)
        if has_entity:
            steps.append({
                "tag": "file_content_step",
                "tool_name": "get_file_content",
                "purpose": "Inspect current file content and revision comments in repository snapshot",
                "input_parameters": {"relative_path": path_param},
                "dependencies": ["search_step"],
                "is_required": False,
            })

        return steps

    def _plan_insights_workflow(
        self,
        query: str,
        entities: ExtractedEntities,
        primary_entity: Optional[str],
    ) -> List[Dict[str, Any]]:
        """INSIGHTS: detect_cycles -> search_symbols -> detect_maintenance_hotspots -> check_architecture_conformance -> get_architecture_overview -> detect_package_cycles -> get_evidence_coverage"""
        steps = []
        q_lower = query.lower()

        is_architecture_query = any(w in q_lower for w in ["architecture", "overview", "hierarchy", "module", "layer", "quotient", "structure", "system", "component", "subsystem"])
        is_conformance_query = any(w in q_lower for w in ["conformance", "layer", "violation", "aci", "boundary", "leak", "forbidden", "strict"])
        is_package_cycle_query = any(w in q_lower for w in ["package cycle", "package-level cycle", "module cycle", "quotient cycle", "circular package", "scc"])
        is_cycle_query = any(w in q_lower for w in ["cycle", "circular", "loop", "health", "risk", "insight"])
        is_hotspot_query = any(w in q_lower for w in ["hotspot", "maintenance", "risk", "debt", "complexity", "archetype", "brain", "rrs"])
        is_coverage_query = any(w in q_lower for w in ["coverage", "evidence", "limitation", "confidence", "completeness", "temporal", "validity"])

        # 1. get_architecture_overview (Phase 9 active tool)
        if is_architecture_query or is_conformance_query:
            steps.append({
                "tag": "arch_overview_step",
                "tool_name": "get_architecture_overview",
                "purpose": "Analyze architectural module decomposition and layered hierarchy",
                "input_parameters": {},
                "dependencies": [],
                "is_required": False,
            })

        # 2. detect_cycles (code graph / AST cycles)
        if is_cycle_query:
            steps.append({
                "tag": "cycles_step",
                "tool_name": "detect_cycles",
                "purpose": "Detect circular dependency loops across imports and function calls",
                "input_parameters": {"max_cycles": 25},
                "dependencies": [],
                "is_required": False if is_architecture_query else True,
            })

        # 3. detect_package_cycles (Phase 9 active tool: Tarjan SCC on module quotient graph)
        if is_package_cycle_query or (is_cycle_query and any(w in q_lower for w in ["package", "module", "quotient", "scc"])):
            steps.append({
                "tag": "package_cycles_step",
                "tool_name": "detect_package_cycles",
                "purpose": "Detect package-level strongly connected component cycles in quotient graph",
                "input_parameters": {},
                "dependencies": [],
                "is_required": False,
            })

        # 4. search_symbols (if specific entity mentioned in insight query)
        if primary_entity:
            steps.append({
                "tag": "search_step",
                "tool_name": "search_symbols",
                "purpose": f"Locate entity '{primary_entity}' for structural insight analysis",
                "input_parameters": {"query": primary_entity, "limit": 5},
                "dependencies": [],
                "is_required": False,
            })

        # 5. detect_maintenance_hotspots (Active Phase 9 or Deferred Phase 6)
        if is_hotspot_query:
            hotspot_params = {"module": primary_entity} if primary_entity else {}
            steps.append({
                "tag": "hotspots_step",
                "tool_name": "detect_maintenance_hotspots",
                "purpose": "Identify maintenance hotspots combining churn, complexity, and centrality",
                "input_parameters": hotspot_params,
                "dependencies": [],
                "is_required": False,
            })

        # 6. check_architecture_conformance (Active Phase 9 or Deferred Phase 6)
        if is_conformance_query or any(w in q_lower for w in ["conformance", "layer", "architecture", "boundary"]):
            conformance_params = {"module": primary_entity} if primary_entity else {}
            steps.append({
                "tag": "conformance_step",
                "tool_name": "check_architecture_conformance",
                "purpose": "Validate architectural layering and dependency conformance",
                "input_parameters": conformance_params,
                "dependencies": [],
                "is_required": False,
            })

        # 7. get_evidence_coverage (Phase 9 active tool)
        if is_coverage_query:
            steps.append({
                "tag": "evidence_coverage_step",
                "tool_name": "get_evidence_coverage",
                "purpose": "Evaluate multi-signal evidence completeness and analysis limitations",
                "input_parameters": {},
                "dependencies": [],
                "is_required": False,
            })

        # Fallback if no specific insight keyword triggered
        if not steps:
            steps.append({
                "tag": "cycles_step",
                "tool_name": "detect_cycles",
                "purpose": "Inspect codebase for circular dependency structural risks",
                "input_parameters": {"max_cycles": 25},
                "dependencies": [],
                "is_required": True,
            })
            steps.append({
                "tag": "hotspots_step",
                "tool_name": "detect_maintenance_hotspots",
                "purpose": "Analyze codebase for maintenance hotspots",
                "input_parameters": {},
                "dependencies": [],
                "is_required": False,
            })

        return steps

    # -------------------------------------------------------------------------
    # Plan Integrity Validation
    # -------------------------------------------------------------------------

    def _validate_plan_integrity(self, steps: List[PlanStep]) -> None:
        """
        Validate that step IDs are unique, dependencies are acyclic and reference
        only earlier steps in the plan.
        """
        seen_ids: Set[str] = set()
        step_indices: Dict[str, int] = {}

        for idx, step in enumerate(steps):
            if step.step_id in seen_ids:
                raise ValueError(f"Duplicate step_id '{step.step_id}' found in plan.")
            seen_ids.add(step.step_id)
            step_indices[step.step_id] = idx

        for step in steps:
            curr_idx = step_indices[step.step_id]
            for dep in step.dependencies:
                if dep not in step_indices:
                    raise ValueError(
                        f"Step '{step.step_id}' references unknown dependency '{dep}'."
                    )
                dep_idx = step_indices[dep]
                if dep_idx >= curr_idx:
                    raise ValueError(
                        f"Step '{step.step_id}' references future or self dependency '{dep}' (Acyclic violation)."
                    )
