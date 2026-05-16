"""Specialist runtime — typed execution layer for the three-tier brain (§7.3).

The specialist executes ONE task spec against ONE technique.  It does NOT
reason about results — it validates input, calls the tool, validates output,
and returns a Finding or SpecialistError.  No LLM call occurs here.

Usage::

    from app.pipeline.specialist import execute_task
    from app.pipeline.catalogs.loader import load_catalog
    from pathlib import Path

    techniques = load_catalog(
        "technique",
        Path("app/pipeline/catalogs/registries/techniques"),
    )
    technique = techniques["web_search"]
    task = TaskSpec(
        technique_id="web_search",
        params_template={"query": "zhao lusi curling iron ad 2025"},
    )

    finding = execute_task(task, technique, mcp_invoke_fn=my_mcp_fn)

Retry policy: transport errors (network, timeout) are retried ONCE.
Schema violations and no_evidence are NOT retried — they are structural
failures that a retry won't fix.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.pipeline.catalogs.schemas import TaskSpec, Technique

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

_SCHEMA_VIOLATION = "schema_violation"
_TOOL_ERROR = "tool_error"
_NO_EVIDENCE = "no_evidence"
_TRANSPORT_ERROR = "transport_error"

# Errors that should trigger a retry
_RETRYABLE_KINDS = frozenset([_TRANSPORT_ERROR])


@dataclass
class Finding:
    """Successful specialist output.

    Attributes:
        technique_id: id of the technique that produced this finding.
        params:       actual params passed to the tool.
        raw_output:   raw dict returned by the tool (after output schema validation).
        ts:           Unix timestamp (float) of when the tool responded.
    """

    technique_id: str
    params: dict[str, Any]
    raw_output: dict[str, Any]
    ts: float = field(default_factory=time.time)


@dataclass
class SpecialistError:
    """Non-successful specialist outcome.

    Attributes:
        kind:    one of ``schema_violation``, ``tool_error``, ``no_evidence``,
                 ``transport_error``.
        details: human-readable description of the failure.
    """

    kind: str
    details: str


# ---------------------------------------------------------------------------
# Minimal JSON-schema validator (required fields + basic types)
# ---------------------------------------------------------------------------

_JSON_SCHEMA_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


def _validate_against_schema(
    data: Any,
    schema: dict[str, Any],
    path: str = "root",
) -> list[str]:
    """Minimal JSON-schema validator.

    Returns a list of error strings.  Empty list means valid.

    Supports: ``type``, ``required``, ``properties`` (recursively).
    Does NOT support: ``$ref``, ``allOf``, ``oneOf``, ``enum``, ``format``.
    """
    errors: list[str] = []

    if not isinstance(schema, dict):
        return errors  # no schema constraint — pass

    schema_type = schema.get("type")
    if schema_type:
        # Handles ["string", "null"] union style
        if isinstance(schema_type, list):
            allowed = tuple(
                _JSON_SCHEMA_TYPE_MAP[t] for t in schema_type if t in _JSON_SCHEMA_TYPE_MAP
            )
        else:
            py_type = _JSON_SCHEMA_TYPE_MAP.get(schema_type)
            allowed = (py_type,) if py_type else ()

        if allowed and not isinstance(data, allowed):
            errors.append(
                f"{path}: expected type {schema_type!r}, got {type(data).__name__!r}"
            )
            return errors  # no point checking children if root type is wrong

    required = schema.get("required", [])
    properties = schema.get("properties", {})

    if isinstance(data, dict):
        for req_key in required:
            if req_key not in data:
                errors.append(f"{path}: missing required field '{req_key}'")
        for prop_name, prop_schema in properties.items():
            if prop_name in data:
                child_errors = _validate_against_schema(
                    data[prop_name], prop_schema, path=f"{path}.{prop_name}"
                )
                errors.extend(child_errors)

    return errors


def _try_jsonschema(data: Any, schema: dict[str, Any]) -> list[str]:
    """Attempt full jsonschema validation; fall back to hand-rolled on ImportError."""
    try:
        import jsonschema  # type: ignore[import]

        validator_cls = jsonschema.Draft7Validator
        validator = validator_cls(schema)
        return [str(e.message) for e in validator.iter_errors(data)]
    except ImportError:
        return _validate_against_schema(data, schema)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_task(
    task: TaskSpec,
    technique: Technique,
    mcp_invoke_fn: Callable[[str, dict[str, Any]], Any],
) -> Finding | SpecialistError:
    """Execute a single specialist task.

    Args:
        task:           The TaskSpec emitted by a tactician.
        technique:      The validated Technique catalog entry for this task.
        mcp_invoke_fn:  Callable that invokes an MCP tool.
                        Signature: ``(tool_name: str, params: dict) -> Any``.
                        Must raise ``TimeoutError`` or ``ConnectionError``
                        (or subclasses) for transport failures so the retry
                        policy triggers correctly.  Any other exception is
                        treated as a tool_error (not retried).

    Returns:
        ``Finding`` on success, ``SpecialistError`` on any failure.
    """
    # Step 1: validate params_template against technique.input_schema
    input_errors = _try_jsonschema(task.params_template, technique.input_schema)
    if input_errors:
        return SpecialistError(
            kind=_SCHEMA_VIOLATION,
            details=f"Input schema violation: {'; '.join(input_errors)}",
        )

    params = dict(task.params_template)

    # Step 2: invoke — one retry only for transport errors
    max_attempts = 2
    last_error: SpecialistError | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            raw = mcp_invoke_fn(technique.tool_name, params)
        except (TimeoutError, ConnectionError, OSError) as exc:
            last_error = SpecialistError(
                kind=_TRANSPORT_ERROR,
                details=f"Transport error on attempt {attempt}: {exc}",
            )
            if attempt < max_attempts:
                log.warning(
                    "specialist: transport error on attempt %d/%d for tool %r: %s",
                    attempt,
                    max_attempts,
                    technique.tool_name,
                    exc,
                )
                continue
            # Exhausted retries
            return last_error
        except Exception as exc:  # noqa: BLE001
            # Non-transport errors — tool_error, not retried
            return SpecialistError(
                kind=_TOOL_ERROR,
                details=f"Tool raised unexpected error: {type(exc).__name__}: {exc}",
            )
        else:
            # Success path — break retry loop
            break

    # Step 3: coerce raw output to dict
    if not isinstance(raw, dict):
        return SpecialistError(
            kind=_SCHEMA_VIOLATION,
            details=f"Tool returned non-dict response: {type(raw).__name__!r}",
        )

    # Step 4: validate output against technique.output_schema
    output_errors = _try_jsonschema(raw, technique.output_schema)
    if output_errors:
        return SpecialistError(
            kind=_SCHEMA_VIOLATION,
            details=f"Output schema violation: {'; '.join(output_errors)}",
        )

    # Step 5: check for empty results (no_evidence)
    results = raw.get("results")
    if isinstance(results, list) and len(results) == 0:
        return SpecialistError(
            kind=_NO_EVIDENCE,
            details="Tool returned an empty results list",
        )

    return Finding(
        technique_id=technique.id,
        params=params,
        raw_output=raw,
        ts=time.time(),
    )
