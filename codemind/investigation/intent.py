"""
Intent classification and entity extraction for CodeMind Agentic Investigation Engine (Phase 6, Milestone 3).
Provides deterministic, multi-signal query understanding across the five canonical intents:
UNDERSTAND, STRUCTURE, IMPACT, EVOLUTION, and INSIGHTS.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Set, Tuple

from .models import InvestigationIntent


# Non-code English stop words that should not be extracted as PascalCase class entities
ENGLISH_PASCAL_STOP_WORDS: Set[str] = {
    "What", "How", "Which", "Explain", "Where", "When", "Who", "Show", "Find",
    "Check", "Does", "Is", "Are", "Will", "Would", "Could", "Should", "If", "Why",
    "Tell", "Describe", "Walk", "List", "Give", "Trace", "Inspect", "Identify",
    "Report", "Summarize", "Compare", "Analyze", "Verify", "Can", "Please", "About",
    "From", "With", "Under", "Over", "Before", "After", "Between", "Through",
    "Python", "CodeMind", "Git", "AST", "RAG", "API", "UI", "CLI", "JSON", "HTTP",
}


@dataclass
class ExtractedEntities:
    """
    Structured code entities and references extracted from a user query.
    Preserves original entity tokens, categorizes by candidate type, and tracks ambiguity.
    """
    raw_entities: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    file_paths: List[str] = field(default_factory=list)
    modules: List[str] = field(default_factory=list)
    primary_entity: Optional[str] = None
    is_ambiguous: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert ExtractedEntities to a dictionary."""
        return {
            "raw_entities": list(self.raw_entities),
            "classes": list(self.classes),
            "functions": list(self.functions),
            "methods": list(self.methods),
            "file_paths": list(self.file_paths),
            "modules": list(self.modules),
            "primary_entity": self.primary_entity,
            "is_ambiguous": self.is_ambiguous,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedEntities":
        """Instantiate ExtractedEntities from dictionary data."""
        return cls(
            raw_entities=data.get("raw_entities", []),
            classes=data.get("classes", []),
            functions=data.get("functions", []),
            methods=data.get("methods", []),
            file_paths=data.get("file_paths", []),
            modules=data.get("modules", []),
            primary_entity=data.get("primary_entity"),
            is_ambiguous=data.get("is_ambiguous", False),
        )


class EntityExtractor:
    """
    Extracts code entity candidates from natural-language queries.
    Identifies PascalCase classes, snake_case functions, Class.method patterns,
    and file paths while filtering English stop words. Never fabricates entities.
    """

    def extract(self, query: str) -> ExtractedEntities:
        if not query or not query.strip():
            return ExtractedEntities()

        text = query.strip()
        classes: List[str] = []
        functions: List[str] = []
        methods: List[str] = []
        file_paths: List[str] = []
        modules: List[str] = []
        raw_entities: List[str] = []

        # 1. Quoted terms (single, double, or backtick) e.g. "UserService", `file_filter.py`
        quoted_matches = re.findall(r"[\"'\`]([a-zA-Z0-9_\-\.\/\\]+)[\"'\`]", text)
        for q in quoted_matches:
            raw_entities.append(q)
            if q.endswith((".py", ".md", ".txt", ".json")) or "/" in q or "\\" in q:
                file_paths.append(q)
            elif "." in q and not q.endswith(".py"):
                methods.append(q)
            elif re.match(r"^[A-Z][a-zA-Z0-9]+$", q) and q not in ENGLISH_PASCAL_STOP_WORDS:
                classes.append(q)
            elif "_" in q or q.islower():
                functions.append(q)

        # 2. File paths (e.g. codemind/auth.py, file_filter.py, tests/test_rag.py)
        path_matches = re.findall(r"\b([a-zA-Z0-9_\-\.\/\\]+\.(?:py|md|txt|json))\b", text)
        for p in path_matches:
            clean_p = p.replace("\\", "/").strip("./")
            if clean_p and clean_p not in file_paths:
                file_paths.append(clean_p)
                raw_entities.append(clean_p)

        # 3. Class.method or module.symbol patterns (e.g. RepositoryLoader.load_repository)
        method_matches = re.findall(r"\b([A-Z][a-zA-Z0-9]+\.[a-zA-Z0-9_]+)\b", text)
        for m in method_matches:
            if m not in methods:
                methods.append(m)
                raw_entities.append(m)

        # 4. Explicit function calls ending with () e.g. parse_file(), should_ignore_dir()
        call_matches = re.findall(r"\b([a-zA-Z0-9_]+)\(\)", text)
        for c in call_matches:
            if c not in functions:
                functions.append(c)
                raw_entities.append(c)

        # 5. PascalCase class names (starts with capital, has internal lowercase or camel casing)
        pascal_matches = re.findall(r"\b([A-Z][a-z0-9]+(?:[A-Z0-9][a-z0-9]*)+)\b", text)
        for p in pascal_matches:
            if p not in ENGLISH_PASCAL_STOP_WORDS and p not in classes:
                classes.append(p)
                raw_entities.append(p)

        # 6. Snake_case function/variable identifiers (contains underscore and letters)
        snake_matches = re.findall(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", text)
        for s in snake_matches:
            # Skip common generic phrases
            if s not in {"under_the_hood", "inner_workings"} and s not in functions:
                functions.append(s)
                raw_entities.append(s)

        # 7. Module or component references e.g. "authentication module", "auth component"
        module_matches = re.findall(r"\b([a-zA-Z0-9_\-]+)\s+(?:module|component|package|subsystem)\b", text, re.IGNORECASE)
        for mod in module_matches:
            if mod.lower() not in {"the", "this", "that", "a", "an", "each", "all", "and", "or", "in", "of", "for", "with", "to", "from", "by", "our", "their", "its"} and mod not in ENGLISH_PASCAL_STOP_WORDS:
                if mod not in modules:
                    modules.append(mod)
                    raw_entities.append(mod)

        # Deduplicate while preserving discovery order
        def _dedup(seq: List[str]) -> List[str]:
            seen = set()
            out = []
            for item in seq:
                if item not in seen:
                    seen.add(item)
                    out.append(item)
            return out

        classes = _dedup(classes)
        functions = _dedup(functions)
        methods = _dedup(methods)
        file_paths = _dedup(file_paths)
        modules = _dedup(modules)
        raw_entities = _dedup(raw_entities)

        # Determine primary entity and ambiguity
        all_candidates = methods + classes + functions + file_paths + modules
        total_unique = len(all_candidates)
        primary = all_candidates[0] if total_unique > 0 else None
        is_ambiguous = total_unique > 1

        return ExtractedEntities(
            raw_entities=raw_entities,
            classes=classes,
            functions=functions,
            methods=methods,
            file_paths=file_paths,
            modules=modules,
            primary_entity=primary,
            is_ambiguous=is_ambiguous,
        )


@dataclass
class IntentClassificationResult:
    """
    Structured outcome of developer query intent classification.
    """
    intent: InvestigationIntent
    confidence: float  # Normalized score (0.0 to 1.0)
    confidence_category: str  # 'HIGH', 'MEDIUM', 'LOW'
    rationale: str
    extracted_entities: ExtractedEntities = field(default_factory=ExtractedEntities)
    signals: List[str] = field(default_factory=list)
    is_ambiguous: bool = False
    alternative_intents: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert IntentClassificationResult to a dictionary."""
        return {
            "intent": self.intent.value if isinstance(self.intent, InvestigationIntent) else str(self.intent),
            "confidence": round(self.confidence, 4),
            "confidence_category": self.confidence_category,
            "rationale": self.rationale,
            "extracted_entities": self.extracted_entities.to_dict(),
            "signals": list(self.signals),
            "is_ambiguous": self.is_ambiguous,
            "alternative_intents": self.alternative_intents,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntentClassificationResult":
        """Instantiate IntentClassificationResult from dictionary data."""
        entities = ExtractedEntities.from_dict(data.get("extracted_entities", {}))
        return cls(
            intent=InvestigationIntent(data["intent"]),
            confidence=data.get("confidence", 0.5),
            confidence_category=data.get("confidence_category", "MEDIUM"),
            rationale=data.get("rationale", ""),
            extracted_entities=entities,
            signals=data.get("signals", []),
            is_ambiguous=data.get("is_ambiguous", False),
            alternative_intents=data.get("alternative_intents", []),
        )


class InvestigationIntentClassifier:
    """
    Deterministic rule- and signal-based intent classifier.
    Categorizes natural-language developer queries into the five canonical intents:
    UNDERSTAND, STRUCTURE, IMPACT, EVOLUTION, and INSIGHTS.
    """

    def __init__(self):
        self.entity_extractor = EntityExtractor()

        # Weighted pattern definitions for each canonical intent
        self.intent_patterns: Dict[InvestigationIntent, List[Tuple[str, float]]] = {
            InvestigationIntent.EVOLUTION: [
                (r"\bchanged?\s+over\s+time\b", 3.0),
                (r"\bcommit\s+history\b", 3.0),
                (r"\bgit\s+history\b", 3.0),
                (r"\bgit\s+log\b", 3.0),
                (r"\brecent\s+commits?\b", 2.5),
                (r"\bcode\s+churn\b", 3.0),
                (r"\bwho\s+(?:modified|wrote|authored|touched|committed)\b", 2.5),
                (r"\bwhen\s+was\s+.*(?:created|modified|added|changed)\b", 2.5),
                (r"\bevolution\s+of\b", 2.5),
                (r"\bhistorical\s+changes?\b", 2.5),
                (r"\bhow\s+has\s+.*(?:changed|evolved)\b", 2.5),
                (r"\brevision\s+history\b", 2.5),
                (r"\bfrequently\s+changed\b", 2.0),
                (r"\bwho\s+last\s+changed\b", 2.5),
                (r"\bco-?chang(?:ed?|ing|es)?\b", 3.0),
                (r"\bchang(?:ed?|ing|es)?\s+together\b", 3.0),
                (r"\blogical\s+coupling\b", 3.0),
                (r"\bcoupled\s+with\b", 2.8),
                (r"\bcoupled\s+files\b", 2.8),
                (r"\bchurn\s+hotspots?\b", 2.5),
                (r"\bmost\s+(?:edited|modified|churned)\b", 2.5),
            ],
            InvestigationIntent.IMPACT: [
                (r"\b(?:affected|impacted)\s+if\b", 3.0),
                (r"\bif\s+.*(?:is|are)?\s*(?:modified|changed|refactored|deleted|updated)\b", 3.0),
                (r"\bwhat\s+breaks\s+if\b", 3.0),
                (r"\bwhat\s+(?:may|will|could)\s+be\s+(?:affected|impacted)\b", 2.8),
                (r"\bblast\s+radius\b", 3.0),
                (r"\bripple\s+effects?\b", 2.5),
                (r"\bimpact\s+of\s+(?:changing|modifying|updating)\b", 3.0),
                (r"\bconsequences?\s+of\s+(?:changing|modifying)\b", 2.5),
                (r"\bbreakage\b", 2.0),
                (r"\bchange\s+impact\b", 2.8),
                (r"\bwhat\s+breaks\b", 2.5),
                (r"\brisk\s+of\s+modifying\b", 2.5),
            ],
            InvestigationIntent.INSIGHTS: [
                (r"\barchitecture\s+of\b", 3.5),
                (r"\bexplain\s+.*architecture\b", 3.5),
                (r"\brepository\s+architecture\b", 3.0),
                (r"\barchitecture\s+layer\b", 3.0),
                (r"\bpackage\s+(?:dependency\s+)?cycles?\b", 3.5),
                (r"\bdependency\s+cycles?\b", 3.0),
                (r"\bhighest[- ]risk\b", 3.0),
                (r"\brisk\s+score\b", 3.0),
                (r"\bwhy\s+.*(?:risk\s+score|hotspot)\b", 3.5),
                (r"\bhigh\s+risk\s+score\b", 3.5),
                (r"\bmaintenance\s+risks?\b", 3.0),
                (r"\bhighest\s+(?:maintenance|risk)\b", 3.0),
                (r"\bmaintenance\s+hotspots?\b", 3.0),
                (r"\bcircular\s+dependenc(?:y|ies)\b", 3.0),
                (r"\bcycles?\s+in\b", 2.5),
                (r"\bcycle\s+issues?\b", 2.5),
                (r"\barchitectural\s+(?:risks?|concerns?|flaws?|debt)\b", 2.8),
                (r"\barchitecture\s+conformance\b", 3.0),
                (r"\btechnical\s+debt\b", 2.5),
                (r"\bcode\s+smells?\b", 2.5),
                (r"\bcode\s+health\b", 2.5),
                (r"\bhigh\s+complexity\b", 2.5),
                (r"\bhotspots?\b", 2.5),
                (r"\barchitectural\s+layering\b", 2.5),
                (r"\barchitecture\s+overview\b", 3.0),
                (r"\bmodule\s+hierarchy\b", 3.0),
                (r"\bpackage\s+cycles?\b", 3.0),
                (r"\bpackage\s+level\s+cycles?\b", 3.0),
                (r"\blayer\s+violations?\b", 3.0),
                (r"\blayer\s+conformance\b", 3.0),
                (r"\blayer\s+skipping\b", 3.0),
                (r"\bupward\s+layer\s+leaks?\b", 3.0),
                (r"\bforbidden\s+imports?\b", 3.0),
                (r"\bevidence\s+coverage\b", 3.0),
                (r"\banalysis\s+limitations?\b", 3.0),
                (r"\bconformance\s+index\b", 3.0),
                (r"\baci\b", 2.5),
                (r"\bvolatile\s+fragile\b", 3.0),
                (r"\bbrain\s+modules?\b", 3.0),
                (r"\bshotgun\s+surgery\b", 3.0),
                (r"\bgod\s+class\b", 3.0),
            ],
            InvestigationIntent.STRUCTURE: [
                (r"\bdepend(?:s|ed|ing)?\s+on\b", 2.5),
                (r"\bdepend(?:ent|ents|ency|encies)\s+of\b", 2.5),
                (r"\bwho\s+(?:calls|invokes|imports|uses)\b", 2.5),
                (r"\bwhat\s+(?:calls|invokes|imports|uses)\b", 2.5),
                (r"\bwhich\s+components?\s+depend\b", 2.8),
                (r"\bcallers?\s+of\b", 2.5),
                (r"\bcallees?\s+of\b", 2.5),
                (r"\b(?:are|is)\s+called\s+by\b", 3.0),
                (r"\bcalled\s+by\b", 3.0),
                (r"\bwhat\s+(?:functions?|methods?|classes?)\s+are\s+called\b", 3.0),
                (r"\b(?:invoked|imported|used)\s+by\b", 2.8),
                (r"\bwhat\s+does\s+.*(?:call|invoke|import)\b", 2.5),
                (r"\bwho\s+inherits\s+from\b", 2.8),
                (r"\binherit(?:s|ed|ing)?\s+from\b", 2.5),
                (r"\bbase\s+class(?:es)?\b", 2.5),
                (r"\bsubclass(?:es)?\b", 2.5),
                (r"\bclass\s+hierarchy\b", 2.5),
                (r"\bcode\s+structure\b", 2.0),
                (r"\bcomponent\s+hierarchy\b", 2.0),
                (r"\bwhere\s+is\s+.*(?:called|used|referenced|imported)\b", 2.5),
                (r"\bwhat\s+imports\b", 2.5),
                (r"\bimports\s+of\b", 2.2),
            ],
            InvestigationIntent.UNDERSTAND: [
                (r"\bhow\s+(?:does|do|can|is)\b.*\bwork\b", 3.0),
                (r"\bhow\s+(?:is|are)\s+.*implemented\b", 2.8),
                (r"\bwhat\s+(?:does|is)\s+.*do\b", 2.5),
                (r"\bexplain\b", 2.2),
                (r"\bwalk\s+me\s+through\b", 2.5),
                (r"\boverview\s+of\b", 2.2),
                (r"\bpurpose\s+of\b", 2.2),
                (r"\bhow\s+to\s+use\b", 2.0),
                (r"\binner\s+workings?\b", 2.5),
                (r"\bunder\s+the\s+hood\b", 2.5),
                (r"\bhow\s+does\b", 2.0),
                (r"\bworkflow\s+of\b", 2.2),
                (r"\bpipeline\s+of\b", 2.2),
                (r"\bimplementation\s+of\b", 2.2),
            ],
        }

    def classify(self, query: str) -> IntentClassificationResult:
        """
        Classify a natural-language query and extract relevant code entities.
        """
        if not query or not query.strip():
            return IntentClassificationResult(
                intent=InvestigationIntent.UNDERSTAND,
                confidence=0.1,
                confidence_category="LOW",
                rationale="Empty query provided; defaulted to UNDERSTAND with low confidence.",
                extracted_entities=ExtractedEntities(),
                signals=[],
                is_ambiguous=True,
            )

        q_clean = query.strip()
        q_lower = q_clean.lower()

        # Step 1: Extract entities
        entities = self.entity_extractor.extract(q_clean)

        # Step 2: Score intents using regex pattern matching
        scores: Dict[InvestigationIntent, float] = {intent: 0.0 for intent in InvestigationIntent}
        matched_signals: Dict[InvestigationIntent, List[str]] = {intent: [] for intent in InvestigationIntent}

        for intent, patterns in self.intent_patterns.items():
            for pat, weight in patterns:
                m = re.search(pat, q_lower)
                if m:
                    matched_str = m.group(0)
                    scores[intent] += weight
                    matched_signals[intent].append(matched_str)

        # Sort intents by score descending
        ranked_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        top_intent, top_score = ranked_intents[0]
        second_intent, second_score = ranked_intents[1]

        # Step 3: Determine confidence and ambiguity
        all_signals = matched_signals[top_intent]

        if top_score == 0.0:
            # No signals matched
            return IntentClassificationResult(
                intent=InvestigationIntent.UNDERSTAND,
                confidence=0.3,
                confidence_category="LOW",
                rationale="No strong intent keywords detected; defaulting to general comprehension workflow.",
                extracted_entities=entities,
                signals=[],
                is_ambiguous=True,
                alternative_intents=[],
            )

        # Check for ambiguity between top two candidates or multi-intent presence
        score_diff = top_score - second_score
        relative_ratio = (second_score / top_score) if top_score > 0 else 0.0
        is_ambiguous = second_score > 0.0 and (score_diff <= 1.5 or relative_ratio >= 0.35 or second_score >= 2.0)

        # Confidence categorization
        if is_ambiguous:
            confidence = 0.60
            category = "MEDIUM"
        elif top_score >= 3.0 and score_diff >= 1.5:
            confidence = min(0.95, 0.75 + (top_score * 0.05))
            category = "HIGH"
        elif top_score >= 2.0 and score_diff >= 0.8:
            confidence = 0.80
            category = "MEDIUM"
        else:
            confidence = 0.55
            category = "LOW"

        # Prepare alternative intents list if ambiguous
        alternatives = []
        if second_score > 0.0:
            for alt_intent, alt_score in ranked_intents[1:]:
                if alt_score > 0.0:
                    alternatives.append({
                        "intent": alt_intent.value,
                        "score": round(alt_score, 2),
                        "signals": matched_signals[alt_intent],
                    })

        rationale = (
            f"Classified as '{top_intent.value.upper()}' based on signals: {all_signals} "
            f"(Score: {top_score:.1f}"
            + (f", competing with '{second_intent.value.upper()}' at {second_score:.1f}" if is_ambiguous else "")
            + ")."
        )

        return IntentClassificationResult(
            intent=top_intent,
            confidence=confidence,
            confidence_category=category,
            rationale=rationale,
            extracted_entities=entities,
            signals=all_signals,
            is_ambiguous=is_ambiguous,
            alternative_intents=alternatives,
        )


def classify_investigation_intent(query: str) -> IntentClassificationResult:
    """Convenience helper to classify a query using InvestigationIntentClassifier."""
    classifier = InvestigationIntentClassifier()
    return classifier.classify(query)
