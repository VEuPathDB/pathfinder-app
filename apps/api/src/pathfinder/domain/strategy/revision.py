"""Fingerprint of what a strategy computes, ignoring what it happened to return.

A chat transcript reports counts that were true at the time of writing. Editing
the strategy afterwards leaves those numbers on screen with nothing marking
them historical. Stamping each assistant turn with the revision it observed,
and comparing that against the live one, is what lets the UI say "superseded"
without rewriting history.

Only inputs are hashed: search names, parameters, combine operators and tree
shape. Counts, WDK ids, validations and display labels are excluded so a
refresh never masquerades as an edit.
"""

from __future__ import annotations

import hashlib
import json

from veupathdb import JSONObject, get_logger
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

__all__ = [
    "parse_strategy_ast",
    "strategy_revision",
    "strategy_revision_of_raw",
    "without_wdk_ids",
    "without_wdk_readings",
]

logger = get_logger(__name__)

_INPUT_KEYS: tuple[str, ...] = (
    "searchName",
    "parameters",
    "operator",
    "colocationParams",
    "filters",
    "wdkWeight",
    "expandedStrategyId",
)

_REVISION_LENGTH = 16


def _node_inputs(node: StrategyStepNode) -> JSONObject:
    dumped = node.model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
        exclude={"primary_input", "secondary_input"},
    )
    inputs: JSONObject = {key: dumped[key] for key in _INPUT_KEYS if key in dumped}
    if node.primary_input is not None:
        inputs["primaryInput"] = _node_inputs(node.primary_input)
    if node.secondary_input is not None:
        inputs["secondaryInput"] = _node_inputs(node.secondary_input)
    return inputs


def strategy_revision(ast: StrategyAst | None) -> str:
    """Return a stable fingerprint of the strategy's inputs, ``""`` if absent."""
    if ast is None:
        return ""
    canonical = json.dumps(
        {
            "recordType": ast.record_type,
            "root": _node_inputs(ast.root),
            # A step added but not yet combined is still a change the agent
            # must not write over, so it has to move the fingerprint.
            "detachedRoots": [_node_inputs(n) for n in ast.detached_roots],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return digest[:_REVISION_LENGTH]


def parse_strategy_ast(raw: JSONObject | None) -> StrategyAst | None:
    """Read a persisted AST payload; ``None`` when it holds no tree."""
    if not raw or "root" not in raw:
        return None
    try:
        return StrategyAst.model_validate(raw)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning("Failed to parse plan payload", error=str(exc))
        return None


def strategy_revision_of_raw(raw: JSONObject | None) -> str:
    """Fingerprint a persisted AST payload; ``""`` when it holds no tree."""
    return strategy_revision(parse_strategy_ast(raw))


_READINGS = {
    "step_counts": None,
    "step_validations": None,
    "wdk_push_errors": None,
}

_READING_KEYS = frozenset(
    {
        "stepCounts",
        "step_counts",
        "stepValidations",
        "step_validations",
        "wdkPushErrors",
        "wdk_push_errors",
    },
)

_STEP_ID_KEYS = frozenset({"wdkStepIds", "wdk_step_ids"})


def _trimmed(
    raw: JSONObject,
    dropped: dict[str, None],
    keys: frozenset[str],
) -> JSONObject:
    """Drop through the model when the tree parses, by key when it does not.

    A stored AST that no longer validates must still lose its WDK state, or
    a thread that adopts it points at another thread's steps.
    """
    ast = parse_strategy_ast(raw)
    if ast is None:
        return {key: value for key, value in raw.items() if key not in keys}
    return ast.model_copy(update=dropped).model_dump(
        by_alias=True,
        exclude_none=True,
        mode="json",
    )


def without_wdk_readings(raw: JSONObject) -> JSONObject:
    """The AST without the WDK readings a stored snapshot cannot vouch for.

    Counts, validations and push errors were measured against a tree that has
    moved since. The step ids stay: the snapshot recorded them.
    """
    return _trimmed(raw, _READINGS, _READING_KEYS)


def without_wdk_ids(raw: JSONObject) -> JSONObject:
    """The AST as a plan alone: no WDK step ids and no WDK readings."""
    return _trimmed(
        raw,
        {**_READINGS, "wdk_step_ids": None},
        _READING_KEYS | _STEP_ID_KEYS,
    )
