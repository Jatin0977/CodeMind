"""
Safe variable-reference resolution for CodeMind Agentic Investigation Engine (Phase 6, Milestone 4).
Resolves validated references (e.g. '$step_1.primary_node_id') between step outputs
strictly without eval, exec, dynamic imports, or arbitrary expression evaluation.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union, Tuple

from .models import StepResult, ToolStatus


class ReferenceResolutionError(Exception):
    """Base exception for all variable reference resolution errors."""
    pass


class MalformedReferenceError(ReferenceResolutionError):
    """Raised when a reference string does not conform to the allowed reference syntax."""
    pass


class StepNotFoundError(ReferenceResolutionError):
    """Raised when a referenced step has not been executed or does not exist."""
    pass


class StepNotSuccessfulError(ReferenceResolutionError):
    """Raised when a referenced step is not in SUCCESS status."""
    pass


class FieldNotFoundError(ReferenceResolutionError):
    """Raised when a requested field or index does not exist on the step output."""
    pass


class AmbiguousSymbolError(ReferenceResolutionError):
    """Raised when an entity reference targets an ambiguous search result with multiple candidates."""
    pass


class UnavailableValueError(ReferenceResolutionError):
    """Raised when a referenced field exists but its value is None, empty, or unavailable."""
    pass


@dataclass
class ResolutionResult:
    """
    Structured outcome of resolving step input parameters against completed steps.
    """
    resolved_parameters: Dict[str, Any] = field(default_factory=dict)
    is_success: bool = True
    is_ambiguous: bool = False
    is_missing: bool = False
    error_message: Optional[str] = None
    unresolved_references: List[str] = field(default_factory=list)
    ambiguous_step_id: Optional[str] = None
    missing_step_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resolved_parameters": self.resolved_parameters,
            "is_success": self.is_success,
            "is_ambiguous": self.is_ambiguous,
            "is_missing": self.is_missing,
            "error_message": self.error_message,
            "unresolved_references": list(self.unresolved_references),
            "ambiguous_step_id": self.ambiguous_step_id,
            "missing_step_id": self.missing_step_id,
        }


class ReferenceResolver:
    """
    Deterministic, secure reference resolver.
    Navigates structured JSON/dict outputs produced by upstream completed steps.
    Strictly forbids dynamic expression evaluation (no eval, exec, or arbitrary code).
    """

    # Matches '$<step_id><path>' where path consists of .field or [index] segments
    # Step ID must be alphanumeric/underscores (e.g. step_1, search_step)
    REF_PATTERN = re.compile(r"^\$([a-zA-Z0-9_]+)((?:\.[a-zA-Z0-9_]+|\[\d+\])+)$")

    # Matches individual path segments: either '.field_name' or '[123]'
    SEGMENT_PATTERN = re.compile(r"\.([a-zA-Z0-9_]+)|\[(\d+)\]")

    # Forbidden characters or substrings that signal injection or complex expressions
    FORBIDDEN_CHARS = set("();:{}'\"`!@#%^&*+=|\\/<>?,~")
    FORBIDDEN_KEYWORDS = {"eval", "exec", "import", "lambda", "__", "globals", "locals"}

    @classmethod
    def is_reference(cls, val: Any) -> bool:
        """Check if a value is a candidate reference string starting with '$'."""
        return isinstance(val, str) and val.startswith("$")

    @classmethod
    def parse_reference(cls, ref_str: str) -> Tuple[str, List[Union[str, int]]]:
        """
        Parse a reference string into a step_id and a list of navigation tokens.

        Example:
            '$step_1.matches[0].id' -> ('step_1', ['matches', 0, 'id'])

        Raises:
            MalformedReferenceError: If reference syntax is invalid or contains forbidden tokens.
        """
        if not isinstance(ref_str, str) or not ref_str.startswith("$"):
            raise MalformedReferenceError(f"Reference must start with '$': '{ref_str}'")

        # Security check: disallow arbitrary characters and dangerous keywords
        for char in cls.FORBIDDEN_CHARS:
            if char in ref_str:
                raise MalformedReferenceError(
                    f"Forbidden character '{char}' in reference '{ref_str}'."
                )

        lower_ref = ref_str.lower()
        for kw in cls.FORBIDDEN_KEYWORDS:
            if kw in lower_ref:
                raise MalformedReferenceError(
                    f"Forbidden keyword '{kw}' in reference '{ref_str}'."
                )

        match = cls.REF_PATTERN.match(ref_str)
        if not match:
            raise MalformedReferenceError(
                f"Malformed reference syntax: '{ref_str}'. "
                f"Expected format: '$<step_id>.<field>' or '$<step_id>.<field>[<index>].<subfield>'."
            )

        step_id = match.group(1)
        path_str = match.group(2)

        # Validate that the entire path string is covered by valid segments
        segments: List[Union[str, int]] = []
        last_end = 0
        for seg_match in cls.SEGMENT_PATTERN.finditer(path_str):
            if seg_match.start() != last_end:
                raise MalformedReferenceError(
                    f"Invalid syntax segment in '{ref_str}' at '{path_str[last_end:seg_match.start()]}'."
                )
            field_name, index_str = seg_match.groups()
            if field_name is not None:
                segments.append(field_name)
            elif index_str is not None:
                segments.append(int(index_str))
            last_end = seg_match.end()

        if last_end != len(path_str):
            raise MalformedReferenceError(
                f"Unparsed trailing characters in reference: '{path_str[last_end:]}'"
            )

        return step_id, segments

    def resolve_value(
        self,
        value: Any,
        completed_steps: Dict[str, StepResult],
    ) -> Any:
        """
        Recursively resolve references within an arbitrary Python value (str, dict, list).
        Preserves original object types (int, float, bool, dict, list) rather than coercing to str.

        Raises:
            ReferenceResolutionError subclasses if resolution fails.
        """
        if isinstance(value, str):
            if value.startswith("$"):
                return self._resolve_single_reference(value, completed_steps)
            return value

        if isinstance(value, dict):
            return {k: self.resolve_value(v, completed_steps) for k, v in value.items()}

        if isinstance(value, list):
            return [self.resolve_value(item, completed_steps) for item in value]

        return value

    def _resolve_single_reference(
        self,
        ref_str: str,
        completed_steps: Dict[str, StepResult],
    ) -> Any:
        """
        Resolve a single reference string against completed steps.
        """
        step_id, segments = self.parse_reference(ref_str)

        # 1. Verify step existence
        if step_id not in completed_steps:
            raise StepNotFoundError(
                f"Referenced step '{step_id}' has not been executed or does not exist."
            )

        step_result = completed_steps[step_id]

        # 2. Verify step status
        if step_result.status != ToolStatus.SUCCESS:
            raise StepNotSuccessfulError(
                f"Referenced step '{step_id}' did not complete successfully "
                f"(status: {step_result.status}, error: {step_result.error_message or step_result.warning})."
            )

        # 3. Verify step output presence
        output = step_result.output
        if output is None:
            raise UnavailableValueError(
                f"Referenced step '{step_id}' produced no output (output is None)."
            )

        # 4. Ambiguous symbol check for search_symbols tool
        if isinstance(output, dict):
            is_ambiguous = output.get("is_ambiguous", False)
            total_matches = output.get("total_matches", 0)

            # Check if this reference is attempting to bind a unique node/path
            first_seg = segments[0] if segments else None
            is_unique_binding_attempt = first_seg in (
                "primary_node_id",
                "primary_relative_path",
            ) or (first_seg == "matches" and len(segments) > 1 and segments[1] == 0)

            if is_ambiguous and is_unique_binding_attempt:
                raise AmbiguousSymbolError(
                    f"Symbol search in '{step_id}' is ambiguous ({total_matches} candidates found). "
                    f"Cannot automatically bind unique reference '{ref_str}'."
                )

            if total_matches == 0 and is_unique_binding_attempt:
                raise UnavailableValueError(
                    f"Symbol search in '{step_id}' returned zero matches. "
                    f"Target reference '{ref_str}' is unavailable."
                )

        # 5. Safe traversal along segments
        curr = output
        for seg in segments:
            if isinstance(seg, str):
                if isinstance(curr, dict):
                    if seg not in curr:
                        raise FieldNotFoundError(
                            f"Field '{seg}' not found in step '{step_id}' output. "
                            f"Available keys: {list(curr.keys())}."
                        )
                    curr = curr[seg]
                elif hasattr(curr, seg):
                    curr = getattr(curr, seg)
                else:
                    raise FieldNotFoundError(
                        f"Cannot access field '{seg}' on non-dictionary/non-object type: {type(curr).__name__}."
                    )
            elif isinstance(seg, int):
                if isinstance(curr, (list, tuple)):
                    if seg < 0 or seg >= len(curr):
                        raise FieldNotFoundError(
                            f"Index [{seg}] out of bounds for step '{step_id}' list of length {len(curr)}."
                        )
                    curr = curr[seg]
                else:
                    raise FieldNotFoundError(
                        f"Cannot apply list index [{seg}] to non-sequence type: {type(curr).__name__}."
                    )

        # 6. Verify resolved value is not None when accessing identifier fields
        if curr is None:
            raise UnavailableValueError(
                f"Reference '{ref_str}' resolved to None in step '{step_id}'."
            )

        return curr

    def resolve_step_parameters(
        self,
        parameters: Dict[str, Any],
        completed_steps: Dict[str, StepResult],
    ) -> ResolutionResult:
        """
        Resolve all references in a step's input parameters.
        Returns a ResolutionResult with status and error metadata.
        """
        resolved: Dict[str, Any] = {}
        unresolved: List[str] = []

        for param_key, param_value in parameters.items():
            try:
                resolved[param_key] = self.resolve_value(param_value, completed_steps)
            except AmbiguousSymbolError as e:
                unresolved.append(f"{param_key}: {str(e)}")
                # Extract step ID from param_value if string
                step_id = None
                if isinstance(param_value, str) and param_value.startswith("$"):
                    try:
                        step_id, _ = self.parse_reference(param_value)
                    except Exception:
                        pass
                return ResolutionResult(
                    resolved_parameters={},
                    is_success=False,
                    is_ambiguous=True,
                    is_missing=False,
                    error_message=str(e),
                    unresolved_references=unresolved,
                    ambiguous_step_id=step_id,
                )
            except StepNotFoundError as e:
                unresolved.append(f"{param_key}: {str(e)}")
                step_id = None
                if isinstance(param_value, str) and param_value.startswith("$"):
                    try:
                        step_id, _ = self.parse_reference(param_value)
                    except Exception:
                        pass
                return ResolutionResult(
                    resolved_parameters={},
                    is_success=False,
                    is_ambiguous=False,
                    is_missing=True,
                    error_message=str(e),
                    unresolved_references=unresolved,
                    missing_step_id=step_id,
                )
            except (UnavailableValueError, FieldNotFoundError) as e:
                unresolved.append(f"{param_key}: {str(e)}")
                return ResolutionResult(
                    resolved_parameters={},
                    is_success=False,
                    is_ambiguous=False,
                    is_missing=True,
                    error_message=str(e),
                    unresolved_references=unresolved,
                )
            except ReferenceResolutionError as e:
                unresolved.append(f"{param_key}: {str(e)}")
                return ResolutionResult(
                    resolved_parameters={},
                    is_success=False,
                    is_ambiguous=False,
                    is_missing=False,
                    error_message=str(e),
                    unresolved_references=unresolved,
                )
            except Exception as e:
                unresolved.append(f"{param_key}: Unexpected error: {str(e)}")
                return ResolutionResult(
                    resolved_parameters={},
                    is_success=False,
                    is_ambiguous=False,
                    is_missing=False,
                    error_message=f"Unexpected error resolving parameter '{param_key}': {str(e)}",
                    unresolved_references=unresolved,
                )

        return ResolutionResult(
            resolved_parameters=resolved,
            is_success=True,
            is_ambiguous=False,
            is_missing=False,
            unresolved_references=[],
        )


def resolve_step_parameters(
    parameters: Dict[str, Any],
    completed_steps: Dict[str, StepResult],
) -> ResolutionResult:
    """
    Convenience function to resolve input parameters using a default ReferenceResolver.
    """
    resolver = ReferenceResolver()
    return resolver.resolve_step_parameters(parameters, completed_steps)
