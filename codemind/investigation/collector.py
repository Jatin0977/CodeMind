"""
Evidence Collector for CodeMind Agentic Investigation Engine (Phase 6, Milestone 4).
Aggregates, categorizes, deduplicates, and formats attributable evidence
from successful tool execution traces while strictly maintaining provenance.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set, Tuple

from .models import StepResult, ToolStatus, ToolDefinition


@dataclass
class EvidenceItem:
    """
    Standardized, attributable evidence record produced during an investigation.
    Maintains exact provenance (source tool, step, lines, relationships).
    """
    category: str  # 'code', 'graph', 'retrieval', 'deferred'
    source_tool: str
    source_step_id: str
    content: Optional[str] = None
    relative_path: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    symbol_name: Optional[str] = None
    score: Optional[float] = None
    provenance: Optional[str] = None  # e.g., 'vector_seed', 'graph_expanded', 'symbol_search'
    relationship_type: Optional[str] = None  # e.g., 'CALLS', 'IMPORTS', 'DEPENDS_ON'
    graph_source: Optional[str] = None  # source node id
    graph_target: Optional[str] = None  # target node id
    target_phase: Optional[str] = None  # For deferred future capabilities
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence item to a JSON-serializable dictionary."""
        return {
            "category": self.category,
            "source_tool": self.source_tool,
            "source_step_id": self.source_step_id,
            "content": self.content,
            "relative_path": self.relative_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "symbol_name": self.symbol_name,
            "score": round(self.score, 4) if self.score is not None else None,
            "provenance": self.provenance,
            "relationship_type": self.relationship_type,
            "graph_source": self.graph_source,
            "graph_target": self.graph_target,
            "target_phase": self.target_phase,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceItem":
        """Instantiate EvidenceItem from dictionary data."""
        return cls(
            category=data["category"],
            source_tool=data["source_tool"],
            source_step_id=data["source_step_id"],
            content=data.get("content"),
            relative_path=data.get("relative_path"),
            start_line=data.get("start_line"),
            end_line=data.get("end_line"),
            symbol_name=data.get("symbol_name"),
            score=data.get("score"),
            provenance=data.get("provenance"),
            relationship_type=data.get("relationship_type"),
            graph_source=data.get("graph_source"),
            graph_target=data.get("graph_target"),
            target_phase=data.get("target_phase"),
            metadata=data.get("metadata", {}),
        )


class EvidenceCollector:
    """
    Gathers, validates, deduplicates, and manages evidence items collected
    across tool execution steps in an investigation.
    """

    def __init__(self):
        self._items: List[EvidenceItem] = []
        self._seen_keys: Set[Tuple[Any, ...]] = set()

    @property
    def items(self) -> List[EvidenceItem]:
        """Return list of collected EvidenceItems."""
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def clear(self) -> None:
        """Reset collector state."""
        self._items.clear()
        self._seen_keys.clear()

    def add_item(self, item: EvidenceItem) -> bool:
        """
        Add an EvidenceItem if it is not an exact duplicate.
        Returns True if added, False if deduplicated.
        """
        dedup_key = self._compute_dedup_key(item)
        if dedup_key in self._seen_keys:
            return False

        self._seen_keys.add(dedup_key)
        self._items.append(item)
        return True

    def _compute_dedup_key(self, item: EvidenceItem) -> Tuple[Any, ...]:
        """Compute a deterministic hashable key for deduplication."""
        cat = item.category.lower() if item.category else ""
        if cat == "code":
            return (
                cat,
                item.relative_path or "",
                item.start_line,
                item.end_line,
                item.symbol_name or "",
                item.content or "",
            )
        elif cat == "graph":
            return (
                cat,
                item.graph_source or "",
                item.graph_target or "",
                item.relationship_type or "",
            )
        elif cat == "retrieval":
            chunk_id = item.metadata.get("chunk_id") if item.metadata else None
            if chunk_id:
                return (cat, chunk_id)
            return (
                cat,
                item.relative_path or "",
                item.start_line,
                item.end_line,
                item.content or "",
            )
        elif cat == "architecture":
            return (
                cat,
                item.source_tool,
                item.symbol_name or "",
                item.relative_path or "",
                item.start_line,
                item.relationship_type or "",
                item.provenance or "",
            )
        elif cat == "deferred":
            return (cat, item.source_tool, item.target_phase or "")
        else:
            return (
                cat,
                item.source_tool,
                item.relative_path or "",
                item.symbol_name or "",
                item.content or "",
            )

    def collect_from_step(
        self,
        step_result: StepResult,
        tool_definition: Optional[ToolDefinition] = None,
    ) -> int:
        """
        Extract structured evidence items from a StepResult and add them to the collection.
        Returns the count of newly added items.

        Args:
            step_result: Execution result produced by a plan step.
            tool_definition: Optional ToolDefinition providing tool metadata.
        """
        initial_count = len(self._items)

        # 1. Handle deferred capabilities
        if step_result.status == ToolStatus.UNAVAILABLE_DEFERRED:
            target_phase = (
                tool_definition.target_phase
                if tool_definition and tool_definition.target_phase
                else "Future Phase"
            )
            item = EvidenceItem(
                category="deferred",
                source_tool=step_result.tool_name,
                source_step_id=step_result.step_id,
                target_phase=target_phase,
                provenance="deferred_placeholder",
                metadata={
                    "status": ToolStatus.UNAVAILABLE_DEFERRED.value,
                    "warning": step_result.warning,
                },
            )
            self.add_item(item)
            return len(self._items) - initial_count

        # 2. Skip failed steps without output
        if step_result.output is None or step_result.status != ToolStatus.SUCCESS:
            return 0

        data = step_result.output
        tool_name = step_result.tool_name
        step_id = step_result.step_id

        # 3. Code tools
        if tool_name == "search_symbols" and isinstance(data, dict):
            matches = data.get("matches", [])
            is_ambiguous = data.get("is_ambiguous", False)
            for m in matches:
                self.add_item(
                    EvidenceItem(
                        category="code",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=m.get("relative_path"),
                        start_line=m.get("start_line"),
                        end_line=m.get("end_line"),
                        symbol_name=m.get("name"),
                        provenance="symbol_search",
                        metadata={
                            "node_id": m.get("id"),
                            "node_type": m.get("node_type"),
                            "is_ambiguous": is_ambiguous,
                            "query": data.get("query"),
                        },
                    )
                )

        elif tool_name == "get_node_details" and isinstance(data, dict):
            if data.get("found", True):
                self.add_item(
                    EvidenceItem(
                        category="code",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=data.get("relative_path"),
                        start_line=data.get("start_line"),
                        end_line=data.get("end_line"),
                        symbol_name=data.get("name"),
                        provenance="node_details",
                        metadata={
                            "node_id": data.get("id"),
                            "node_type": data.get("node_type"),
                        },
                    )
                )

        elif tool_name == "get_file_content" and isinstance(data, dict):
            self.add_item(
                EvidenceItem(
                    category="code",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    content=data.get("content"),
                    relative_path=data.get("relative_path"),
                    start_line=data.get("start_line"),
                    end_line=data.get("end_line"),
                    provenance="file_content",
                    metadata={
                        "total_lines": data.get("total_lines"),
                        "line_count_returned": data.get("line_count_returned"),
                    },
                )
            )

        # 4. Graph tools
        elif tool_name == "get_callers" and isinstance(data, dict):
            target_node = data.get("node_id")
            for c in data.get("callers", []):
                self.add_item(
                    EvidenceItem(
                        category="graph",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        graph_source=c.get("id"),
                        graph_target=target_node,
                        relationship_type="CALLS",
                        symbol_name=c.get("name"),
                        relative_path=c.get("relative_path"),
                        start_line=c.get("start_line"),
                        end_line=c.get("end_line"),
                        provenance="graph_caller",
                        metadata={"caller_node_type": c.get("node_type")},
                    )
                )

        elif tool_name == "get_callees" and isinstance(data, dict):
            source_node = data.get("node_id")
            for c in data.get("callees", []):
                self.add_item(
                    EvidenceItem(
                        category="graph",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        graph_source=source_node,
                        graph_target=c.get("id"),
                        relationship_type="CALLS",
                        symbol_name=c.get("name"),
                        relative_path=c.get("relative_path"),
                        start_line=c.get("start_line"),
                        end_line=c.get("end_line"),
                        provenance="graph_callee",
                        metadata={"callee_node_type": c.get("node_type")},
                    )
                )

        elif tool_name == "get_dependencies" and isinstance(data, dict):
            source_node = data.get("node_id")
            for dep in data.get("dependencies", []):
                self.add_item(
                    EvidenceItem(
                        category="graph",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        graph_source=source_node,
                        graph_target=dep.get("id"),
                        relationship_type=dep.get("relationship", "DEPENDS_ON"),
                        symbol_name=dep.get("name"),
                        relative_path=dep.get("relative_path"),
                        provenance="graph_dependency",
                        metadata={"dependency_type": dep.get("node_type")},
                    )
                )

        elif tool_name == "get_dependents" and isinstance(data, dict):
            target_node = data.get("node_id")
            for dep in data.get("dependents", []):
                self.add_item(
                    EvidenceItem(
                        category="graph",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        graph_source=dep.get("id"),
                        graph_target=target_node,
                        relationship_type=dep.get("relationship", "DEPENDS_ON"),
                        symbol_name=dep.get("name"),
                        relative_path=dep.get("relative_path"),
                        provenance="graph_dependent",
                        metadata={"dependent_type": dep.get("node_type")},
                    )
                )

        elif tool_name == "trace_structural_impact" and isinstance(data, dict):
            # Graph edges
            for edge in data.get("impact_edges", []):
                self.add_item(
                    EvidenceItem(
                        category="graph",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        graph_source=edge.get("source"),
                        graph_target=edge.get("target"),
                        relationship_type=edge.get("type", "IMPACT"),
                        provenance="structural_impact",
                    )
                )
            # Affected nodes
            for node in data.get("affected_nodes", []):
                self.add_item(
                    EvidenceItem(
                        category="code",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        symbol_name=node.get("name"),
                        relative_path=node.get("relative_path"),
                        start_line=node.get("start_line"),
                        end_line=node.get("end_line"),
                        provenance="structural_impact_node",
                        metadata={
                            "node_id": node.get("id"),
                            "node_type": node.get("node_type"),
                        },
                    )
                )

        elif tool_name == "detect_cycles" and isinstance(data, dict):
            for cycle in data.get("cycles", []):
                self.add_item(
                    EvidenceItem(
                        category="graph",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relationship_type="CYCLE",
                        provenance="cycle_detection",
                        metadata={"cycle_nodes": cycle},
                    )
                )

        # 5. Retrieval tools
        elif tool_name in ("semantic_search", "hybrid_search") and isinstance(data, dict):
            results = data.get("results", [])
            for r in results:
                chunk = r.get("chunk") or {}
                rel_path = (
                    chunk.get("file_path")
                    or chunk.get("relative_path")
                    or r.get("relative_path")
                )
                start_l = chunk.get("start_line") or r.get("start_line")
                end_l = chunk.get("end_line") or r.get("end_line")
                content = chunk.get("content") or r.get("content")
                score = r.get("score")
                provenance = r.get("provenance") or (
                    "vector_seed" if tool_name == "semantic_search" else "hybrid"
                )
                rel_type = r.get("relationship_type")
                chunk_id = chunk.get("id") or r.get("chunk_id")

                self.add_item(
                    EvidenceItem(
                        category="retrieval",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        content=content,
                        relative_path=rel_path,
                        start_line=start_l,
                        end_line=end_l,
                        score=score,
                        provenance=provenance,
                        relationship_type=rel_type,
                        metadata={
                            "chunk_id": chunk_id,
                            "query": data.get("query"),
                        },
                    )
                )

        # 6. Git Temporal tools (Phase 7 Active)
        elif tool_name == "git_commit_history" and isinstance(data, dict):
            commits = data.get("commits", [])
            filtered_p = data.get("filtered_path")
            for c in commits:
                full_h = c.get("full_hash", "")
                short_h = c.get("short_hash", full_h[:7] if full_h else "")
                self.add_item(
                    EvidenceItem(
                        category="temporal",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=filtered_p or (c.get("files_changed", [{}])[0].get("path") if c.get("files_changed") else None),
                        symbol_name=short_h,
                        provenance="git_history",
                        metadata={
                            "full_hash": full_h,
                            "short_hash": short_h,
                            "author_name": c.get("author_name"),
                            "author_date": c.get("author_date"),
                            "subject": c.get("subject"),
                            "files_changed_count": c.get("files_changed_count", len(c.get("files_changed", []))),
                        },
                    )
                )

        elif tool_name == "git_code_churn" and isinstance(data, dict):
            hotspots = data.get("hotspots", [])
            for h in hotspots:
                self.add_item(
                    EvidenceItem(
                        category="temporal",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=h.get("path"),
                        provenance="git_churn",
                        metadata={
                            "commits_count": h.get("commits_count", 0),
                            "additions": h.get("additions", 0),
                            "deletions": h.get("deletions", 0),
                            "total_churn": h.get("total_churn", 0),
                            "unique_authors": h.get("unique_authors", 0),
                        },
                    )
                )

        elif tool_name == "git_logical_coupling" and isinstance(data, dict):
            couplings = data.get("couplings", [])
            focal = data.get("focal_file")
            for coup in couplings:
                src_f = focal or coup.get("source_file") or coup.get("canonical_file_a")
                tgt_f = coup.get("target_file") or coup.get("canonical_file_b")
                self.add_item(
                    EvidenceItem(
                        category="temporal",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=src_f,
                        relationship_type="CO_CHANGED_WITH",
                        provenance="git_coupling",
                        metadata={
                            "target_file": tgt_f,
                            "support_count": coup.get("support_count", 0),
                            "jaccard_similarity": coup.get("jaccard_similarity", 0.0),
                            "confidence": coup.get("confidence") or coup.get("confidence_to_target", 0.0),
                            "last_co_change_date": coup.get("last_co_change_date"),
                        },
                    )
                )

        # 7. Impact & Test Intelligence tools (Phase 8 Active)
        elif tool_name == "multi_signal_impact" and isinstance(data, dict):
            target_info = data.get("target") or {}
            comp_score = data.get("composite_score")
            risk_level = data.get("risk_level")
            self.add_item(
                EvidenceItem(
                    category="impact",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    relative_path=target_info.get("relative_path") or target_info.get("file_path"),
                    symbol_name=target_info.get("name"),
                    score=comp_score,
                    provenance="multi_signal_impact",
                    metadata={
                        "target_node_id": target_info.get("node_id"),
                        "risk_level": risk_level,
                        "confidence": data.get("confidence"),
                        "signals": data.get("signals", {}),
                        "total_impacted": (data.get("blast_radius") or {}).get("total_impacted", 0),
                    },
                )
            )
            br = data.get("blast_radius") or {}
            for inode in (br.get("impacted_nodes") or [])[:10]:
                self.add_item(
                    EvidenceItem(
                        category="impact",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=inode.get("file_path"),
                        symbol_name=inode.get("name"),
                        relationship_type=inode.get("direct_relationship"),
                        provenance="blast_radius_node",
                        metadata={
                            "node_id": inode.get("node_id"),
                            "depth": inode.get("depth"),
                            "tags": inode.get("tags", []),
                        },
                    )
                )

        elif tool_name == "get_test_coverage" and isinstance(data, dict):
            recs = data.get("recommendations", [])
            for rec in recs:
                self.add_item(
                    EvidenceItem(
                        category="test_intelligence",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=rec.get("test_file"),
                        symbol_name=rec.get("test_target"),
                        score=rec.get("rank_score"),
                        relationship_type=rec.get("evidence_type"),
                        provenance="test_recommendation",
                        metadata={
                            "tier": rec.get("tier"),
                            "associated_source_entity": rec.get("associated_source_entity"),
                            "description": rec.get("description"),
                        },
                    )
                )

        # 8. Phase 9 Architecture Intelligence tools
        elif tool_name == "get_architecture_overview" and isinstance(data, dict):
            q_info = data.get("quotient_graph") or data.get("quotient_graph_summary") or {}
            self.add_item(
                EvidenceItem(
                    category="architecture",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    symbol_name="ArchitectureHierarchy",
                    provenance="architecture_overview",
                    metadata={
                        "total_modules": data.get("total_modules", 0),
                        "total_layers": data.get("total_layers", 0),
                        "matched_modules": data.get("matched_modules_count", 0),
                        "cross_module_edges": q_info.get("edges_count", data.get("cross_module_edges", 0)),
                        "is_acyclic": q_info.get("is_acyclic", True),
                    },
                )
            )
            for mod in (data.get("modules") or [])[:15]:
                mod_name = mod.get("name") or mod.get("module_id") or "module"
                layer_name = mod.get("layer") or mod.get("layer_name") or "UNCLASSIFIED"
                self.add_item(
                    EvidenceItem(
                        category="architecture",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        symbol_name=mod_name,
                        score=mod.get("stability") or mod.get("confidence"),
                        provenance="module_stability",
                        metadata={
                            "layer": layer_name,
                            "files_count": mod.get("files_count", 0),
                            "fan_in": mod.get("fan_in", 0),
                            "fan_out": mod.get("fan_out", 0),
                            "complexity": mod.get("total_complexity", 0),
                        },
                    )
                )

        elif tool_name == "check_architecture_conformance" and isinstance(data, dict):
            tot_edges = data.get("total_evaluated_edges", data.get("total_cross_module_edges", 0))
            viols_cnt = data.get("violations_count", data.get("total_violations", len(data.get("violations", []))))
            self.add_item(
                EvidenceItem(
                    category="architecture",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    symbol_name="ArchitectureConformance",
                    score=data.get("conformance_index"),
                    provenance="architecture_conformance",
                    metadata={
                        "conformance_index": data.get("conformance_index"),
                        "total_cross_module_edges": tot_edges,
                        "violating_edges_count": data.get("violating_edges_count", 0),
                        "total_violations": viols_cnt,
                        "is_fully_conformant": data.get("is_compliant", data.get("is_fully_conformant", False)),
                    },
                )
            )
            for v in (data.get("violations") or [])[:25]:
                self.add_item(
                    EvidenceItem(
                        category="architecture",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        relative_path=v.get("source_file"),
                        start_line=v.get("line_number"),
                        end_line=v.get("line_number"),
                        symbol_name=f"{v.get('source_module')} -> {v.get('target_module')}",
                        relationship_type=v.get("violation_type"),
                        graph_source=v.get("source_module"),
                        graph_target=v.get("target_module"),
                        score=v.get("weight"),
                        provenance="layer_violation",
                        metadata={
                            "target_file": v.get("target_file"),
                            "rule_description": v.get("rule_description"),
                            "violation_type": v.get("violation_type"),
                            "severity": v.get("severity"),
                        },
                    )
                )

        elif tool_name == "detect_package_cycles" and isinstance(data, dict):
            cyc_cnt = data.get("total_cycles", data.get("package_cycles_count", len(data.get("cycles", []))))
            has_cyc = data.get("has_cycles", data.get("has_package_cycles", cyc_cnt > 0))
            self.add_item(
                EvidenceItem(
                    category="architecture",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    symbol_name="PackageCycles",
                    score=float(cyc_cnt),
                    provenance="package_cycle_analysis",
                    metadata={
                        "has_package_cycles": has_cyc,
                        "package_cycles_count": cyc_cnt,
                        "total_sccs": data.get("total_sccs", 0),
                    },
                )
            )
            for cyc in (data.get("cycles") or [])[:15]:
                mods = cyc.get("modules") or cyc.get("cycle_path") or []
                self.add_item(
                    EvidenceItem(
                        category="architecture",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        symbol_name=f"Cycle: {' -> '.join(str(m) for m in mods)}",
                        relationship_type="PACKAGE_CYCLE",
                        provenance="package_cycle",
                        metadata={
                            "cycle_id": cyc.get("cycle_id", "cycle"),
                            "modules": mods,
                            "length": cyc.get("length", len(mods)),
                        },
                    )
                )

        elif tool_name == "detect_maintenance_hotspots" and isinstance(data, dict):
            rrs_score = data.get("top_hotspot_mean", data.get("repository_risk_score"))
            hot_cnt = data.get("matched_hotspots_count", data.get("hotspots_count", len(data.get("hotspots", []))))
            tot_analyzed = data.get("total_analyzed", data.get("total_modules_analyzed", 0))
            self.add_item(
                EvidenceItem(
                    category="architecture",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    symbol_name="RepositoryRiskScore",
                    score=rrs_score,
                    provenance="repository_risk_score",
                    metadata={
                        "repository_risk_score": rrs_score,
                        "hotspots_count": hot_cnt,
                        "total_modules_analyzed": tot_analyzed,
                        "analysis_state": data.get("analysis_state"),
                        "evidence_coverage": data.get("evidence_coverage"),
                    },
                )
            )
            for h in (data.get("hotspots") or [])[:20]:
                h_name = h.get("entity_path") or h.get("module_id") or "hotspot"
                h_score = h.get("hotspot_score") if h.get("hotspot_score") is not None else h.get("risk_score")
                self.add_item(
                    EvidenceItem(
                        category="architecture",
                        source_tool=tool_name,
                        source_step_id=step_id,
                        symbol_name=h_name,
                        score=h_score,
                        provenance="maintenance_hotspot",
                        metadata={
                            "archetype": h.get("archetype"),
                            "active_signals": list(h.get("effective_weights", {}).keys()) or h.get("active_signals", []),
                            "interaction_multiplier": h.get("multiplier") or h.get("interaction_multiplier", 1.0),
                            "metrics": h.get("raw_metrics") or h.get("metrics", {}),
                        },
                    )
                )

        elif tool_name == "get_evidence_coverage" and isinstance(data, dict):
            cov_score = data.get("overall_coverage") if data.get("overall_coverage") is not None else data.get("coverage_score")
            self.add_item(
                EvidenceItem(
                    category="architecture",
                    source_tool=tool_name,
                    source_step_id=step_id,
                    symbol_name="EvidenceCoverage",
                    score=cov_score,
                    provenance="evidence_coverage",
                    metadata={
                        "coverage_score": cov_score,
                        "analysis_state": data.get("analysis_state"),
                        "missing_signals": data.get("missing_signals", []),
                        "limitations": data.get("limitations", []),
                        "dimensions": data.get("dimensions", {}),
                    },
                )
            )

        return len(self._items) - initial_count

    # Alias for convenience
    extract_from_step_result = collect_from_step

    def to_list(self) -> List[Dict[str, Any]]:
        """Return list of serialized dictionary representations of evidence items."""
        return [item.to_dict() for item in self._items]

    def filter_by_category(self, category: str) -> List[EvidenceItem]:
        """Return collected items matching a specific category."""
        target = category.lower().strip()
        return [item for item in self._items if item.category.lower() == target]

    def summary(self) -> Dict[str, int]:
        """Return a count of items by category."""
        counts: Dict[str, int] = {}
        for item in self._items:
            cat = item.category.lower()
            counts[cat] = counts.get(cat, 0) + 1
        return counts
