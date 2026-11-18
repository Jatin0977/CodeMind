"""
Investigation Orchestrator for CodeMind Agentic Investigation Engine (Phase 6, Milestone 4).
Executes dependency-aware investigation plans sequentially, resolves validated variable
references, isolates tool failures, identifies deferred future-phase tools without running them,
and collects attributable evidence with full execution provenance.
"""

import time
from typing import Dict, Any, Optional, List, Union

from .models import (
    InvestigationPlan,
    InvestigationResult,
    InvestigationStatus,
    PlanStep,
    StepResult,
    ToolStatus,
    ToolAvailability,
    ToolDefinition,
)
from .tools.registry import ToolRegistry
from .resolver import ReferenceResolver, ResolutionResult
from .collector import EvidenceCollector


class InvestigationOrchestrator:
    """
    Deterministic sequential executor for InvestigationPlan instances.
    Enforces strict dependency order, isolates tool execution, resolves references,
    and constructs grounded InvestigationResults.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        resolver: Optional[ReferenceResolver] = None,
        collector: Optional[EvidenceCollector] = None,
    ):
        self.default_registry = registry
        self.resolver = resolver or ReferenceResolver()
        self.collector = collector or EvidenceCollector()

    def orchestrate(
        self,
        plan: InvestigationPlan,
        registry: Optional[ToolRegistry] = None,
    ) -> InvestigationResult:
        """Alias for execute()."""
        return self.execute(plan, registry)

    def execute(
        self,
        plan: InvestigationPlan,
        registry: Optional[ToolRegistry] = None,
    ) -> InvestigationResult:
        """
        Execute an investigation plan sequentially step-by-step.

        Args:
            plan: Validated InvestigationPlan instance.
            registry: Optional ToolRegistry; falls back to self.default_registry.

        Returns:
            Structured InvestigationResult containing step traces and collected evidence.
        """
        active_registry = registry or self.default_registry
        if active_registry is None:
            raise ValueError(
                "InvestigationOrchestrator requires a valid ToolRegistry to execute."
            )

        start_time_total = time.time()
        step_results: List[StepResult] = []
        completed_steps: Dict[str, StepResult] = {}
        collector = EvidenceCollector()
        deferred_capabilities: List[Dict[str, str]] = []

        # Empty plan check
        if not plan or not plan.steps:
            return InvestigationResult(
                query=plan.original_query if plan else "",
                intent=plan.intent if plan else None,
                plan=plan,
                step_results=[],
                evidence=[],
                final_answer=None,
                overall_status=InvestigationStatus.SUCCESS,
                metadata={
                    "execution_summary": {
                        "total_steps": 0,
                        "successful_steps": 0,
                        "skipped_steps": 0,
                        "failed_steps": 0,
                        "deferred_steps": 0,
                        "total_evidence_items": 0,
                        "total_duration_ms": 0.0,
                    },
                    "deferred_capabilities": [],
                },
            )

        # Execute steps sequentially in declared plan order
        for step in plan.steps:
            step_res = self._execute_step(
                step=step,
                registry=active_registry,
                completed_steps=completed_steps,
                collector=collector,
                deferred_capabilities=deferred_capabilities,
            )
            step_results.append(step_res)
            completed_steps[step.step_id] = step_res

        total_duration_ms = round((time.time() - start_time_total) * 1000, 2)

        # Compute overall status
        overall_status = self._compute_overall_status(plan, step_results, collector)

        # Prepare execution summary metadata
        summary = {
            "total_steps": len(step_results),
            "successful_steps": sum(1 for r in step_results if r.status == ToolStatus.SUCCESS),
            "skipped_steps": sum(1 for r in step_results if r.status == ToolStatus.SKIPPED),
            "failed_steps": sum(1 for r in step_results if r.status == ToolStatus.ERROR),
            "deferred_steps": sum(1 for r in step_results if r.status == ToolStatus.UNAVAILABLE_DEFERRED),
            "total_evidence_items": len(collector),
            "evidence_by_category": collector.summary(),
            "total_duration_ms": total_duration_ms,
        }

        return InvestigationResult(
            query=plan.original_query,
            intent=plan.intent,
            plan=plan,
            step_results=step_results,
            evidence=collector.to_list(),
            final_answer=None,  # Answer synthesis deferred to Milestone 5
            overall_status=overall_status,
            metadata={
                "execution_summary": summary,
                "deferred_capabilities": deferred_capabilities,
            },
        )

    def _execute_step(
        self,
        step: PlanStep,
        registry: ToolRegistry,
        completed_steps: Dict[str, StepResult],
        collector: EvidenceCollector,
        deferred_capabilities: List[Dict[str, str]],
    ) -> StepResult:
        """
        Execute or safely skip a single plan step.
        """
        step_id = step.step_id
        tool_name = step.tool_name

        # 1. Verify tool registration
        if not registry.has_tool(tool_name):
            msg = f"Tool '{tool_name}' is not registered in the ToolRegistry."
            if step.is_required:
                return StepResult(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolStatus.ERROR,
                    error_message=msg,
                )
            return StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=ToolStatus.SKIPPED,
                warning=msg,
            )

        tool = registry.get(tool_name)
        tool_def = tool.definition if tool else None

        # 2. Check tool availability (Deferred vs Available)
        if tool_def and tool_def.availability == ToolAvailability.DEFERRED:
            target_phase = tool_def.target_phase or "Future Phase"
            deferred_capabilities.append({
                "tool_name": tool_name,
                "target_phase": target_phase,
                "step_id": step_id,
            })
            step_res = StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=ToolStatus.UNAVAILABLE_DEFERRED,
                output=None,
                warning=(
                    f"Tool '{tool_name}' is deferred to a future development milestone "
                    f"({target_phase}) and cannot be executed in Phase 6."
                ),
            )
            collector.collect_from_step(step_res, tool_def)
            return step_res

        # 3. Check dependencies
        for dep_id in step.dependencies:
            if dep_id not in completed_steps:
                return StepResult(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolStatus.SKIPPED,
                    warning=f"Skipped because dependency '{dep_id}' was not executed.",
                )
            dep_res = completed_steps[dep_id]
            if dep_res.status != ToolStatus.SUCCESS:
                return StepResult(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolStatus.SKIPPED,
                    warning=(
                        f"Skipped because required upstream dependency '{dep_id}' "
                        f"ended with status {dep_res.status} "
                        f"({dep_res.error_message or dep_res.warning or 'incomplete'})."
                    ),
                )

        # 4. Resolve variable references in input parameters
        res_outcome: ResolutionResult = self.resolver.resolve_step_parameters(
            step.input_parameters, completed_steps
        )

        if not res_outcome.is_success:
            if res_outcome.is_ambiguous:
                return StepResult(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolStatus.SKIPPED,
                    warning=(
                        f"Skipped: target symbol reference in step '{res_outcome.ambiguous_step_id}' "
                        f"is ambiguous. Candidate details preserved in evidence."
                    ),
                )
            elif res_outcome.is_missing:
                return StepResult(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolStatus.SKIPPED,
                    warning=f"Skipped: required reference unavailable ({res_outcome.error_message}).",
                )
            else:
                if step.is_required:
                    return StepResult(
                        step_id=step_id,
                        tool_name=tool_name,
                        status=ToolStatus.ERROR,
                        error_message=f"Failed to resolve input parameters: {res_outcome.error_message}",
                    )
                return StepResult(
                    step_id=step_id,
                    tool_name=tool_name,
                    status=ToolStatus.SKIPPED,
                    warning=f"Skipped: parameter resolution failed ({res_outcome.error_message}).",
                )

        resolved_parameters = res_outcome.resolved_parameters

        # 5. Execute available tool safely
        tool = registry.get_tool(tool_name)
        start_t = time.time()
        try:
            tool_res = tool.execute(resolved_parameters)
            end_t = time.time()
            latency_ms = round((end_t - start_t) * 1000, 2)
            timing = {
                "start_time": start_t,
                "end_time": end_t,
                "latency_ms": latency_ms,
            }

            step_res = StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=tool_res.status,
                output=tool_res.data,
                error_message=tool_res.message if tool_res.status == ToolStatus.ERROR else None,
                warning=tool_res.message if tool_res.status not in (ToolStatus.SUCCESS, ToolStatus.ERROR) else None,
                execution_timing=timing,
            )

        except Exception as exc:
            end_t = time.time()
            latency_ms = round((end_t - start_t) * 1000, 2)
            timing = {
                "start_time": start_t,
                "end_time": end_t,
                "latency_ms": latency_ms,
            }
            step_res = StepResult(
                step_id=step_id,
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                output=None,
                error_message=f"Unexpected exception during tool execution: {type(exc).__name__}: {str(exc)}",
                execution_timing=timing,
            )

        # 6. Collect evidence from completed step
        collector.collect_from_step(step_res, tool_def)
        return step_res

    def _compute_overall_status(
        self,
        plan: InvestigationPlan,
        step_results: List[StepResult],
        collector: EvidenceCollector,
    ) -> InvestigationStatus:
        """
        Determine the overall InvestigationStatus based on step results and evidence.
        """
        if not step_results:
            return InvestigationStatus.SUCCESS

        total_steps = len(step_results)
        success_count = sum(1 for r in step_results if r.status == ToolStatus.SUCCESS)
        deferred_count = sum(1 for r in step_results if r.status == ToolStatus.UNAVAILABLE_DEFERRED)
        error_count = sum(1 for r in step_results if r.status == ToolStatus.ERROR)
        skipped_count = sum(1 for r in step_results if r.status == ToolStatus.SKIPPED)

        # 1. All steps deferred
        if deferred_count == total_steps:
            return InvestigationStatus.DEFERRED

        # 2. Check required step compliance
        step_req_map = {s.step_id: s.is_required for s in plan.steps}
        has_failed_required = any(
            step_req_map.get(r.step_id, True) and r.status in (ToolStatus.ERROR, ToolStatus.SKIPPED)
            for r in step_results
        )

        # 3. No evidence produced and no successful steps
        if success_count == 0:
            if deferred_count > 0 and error_count == 0:
                return InvestigationStatus.DEFERRED
            return InvestigationStatus.FAILED

        # 4. Perfect success: all steps succeeded without skips, errors, or deferrals
        if success_count == total_steps:
            return InvestigationStatus.SUCCESS

        # 5. Some steps succeeded and produced evidence, but some steps failed, were skipped, or deferred
        # or a required step failed while other independent branches succeeded
        return InvestigationStatus.PARTIAL_SUCCESS
