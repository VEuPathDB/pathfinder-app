"""The orthology shape a message asks for, read from its words, and the check
that a tree states that shape."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from typing import Literal

from pydantic import ConfigDict
from veupathdb.domain.strategy import (
    StrategyStepNode,
    extract_output_organisms,
    walk,
)
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.organism_scope import organism_params_of
from pathfinder.domain.strategy.orthology import round_trip_wiring, stated_steps

OrthologyShape = Literal["transform", "round_trip"]

_ORTHOLOGS = r"(?:ortholog(?:ue)?s?|homolog(?:ue)?s?|counterparts?)"
_ORTHOLOGY_NOUN_RE = re.compile(rf"\b{_ORTHOLOGS}\b", re.IGNORECASE)
_CARRY_RE = re.compile(
    r"\b(?:carr(?:y|ies|ied|ying)|map(?:s|ped|ping)?|translat(?:e|es|ed|ing)"
    r"|mov(?:e|es|ed|ing))\b.*?\b(?:to|into|onto)\b(?P<rest>.*)",
    re.IGNORECASE | re.DOTALL,
)
_KEEP_RE = re.compile(
    r"(?:\b(?:have|has|having|with)\s+(?:an?\s+|any\s+)?(?:syntenic\s+)?"
    rf"{_ORTHOLOGS}\s+|\bconserved\s+)in\b(?P<rest>.*)",
    re.IGNORECASE | re.DOTALL,
)
# A period ends a clause only before a capital or the end, so "T. gondii" holds.
_CLAUSE_END_RE = re.compile(r"[,;!?]|\.(?=\s+[A-Z]|\s*$)")
_NAME_START_RE = re.compile(r"\b[A-Z]")
_NAME_END_RE = re.compile(
    rf"\s+(?:and|but|with|that|which|then|using|keeping|genes?|{_ORTHOLOGS})\b.*",
    re.IGNORECASE | re.DOTALL,
)
_TRANSFORM_NODE = (
    '{"kind": "transform", "criterionId": "<the transform>", "inputs": '
    "[<the source subtree>]}"
)


def _target(rest: str) -> str:
    """The organism name the words open with a capital, or empty when none does."""
    start = _NAME_START_RE.search(rest)
    if start is None:
        return ""
    return _NAME_END_RE.sub("", rest[start.start() :]).strip()


class OrthologyRequest(CamelModel):
    """The orthology shape a message asks for, and the organism it names.

    "carry", "map", "translate" and "move" to orthologs in X ask for one
    transform whose result is X's genes. A gene that has an ortholog in X, or
    is conserved in X, is kept by the round trip. ``target`` is empty when the
    words name no organism.
    """

    model_config = ConfigDict(frozen=True)

    shape: OrthologyShape
    target: str = ""

    @classmethod
    def read(cls, message: str) -> OrthologyRequest | None:
        """The one orthology request the message states, or None.

        A carry verb counts only in a clause that names orthologs. A message
        that states two requests names no single one.
        """
        found = [
            reading
            for clause in _CLAUSE_END_RE.split(message)
            for reading in _readings(clause)
        ]
        return found[0] if len(found) == 1 else None


def _readings(clause: str) -> Iterator[OrthologyRequest]:
    carried = _CARRY_RE.search(clause)
    if carried is not None and _ORTHOLOGY_NOUN_RE.search(clause):
        yield OrthologyRequest(shape="transform", target=_target(carried["rest"]))
    for kept in _KEEP_RE.finditer(clause):
        yield OrthologyRequest(shape="round_trip", target=_target(kept["rest"]))


def _round_trips(
    tree: StrategyStepNode, marked: Mapping[str, str]
) -> Iterator[tuple[StrategyStepNode, StrategyStepNode]]:
    """Each transform that maps another transform's genes back to the organism
    of that transform's input, with that transform."""
    for back in walk(tree):
        there = back.primary_input
        if there is None or back.secondary_input is not None:
            continue
        source = there.primary_input
        if source is None or there.secondary_input is not None:
            continue
        organisms = extract_output_organisms(source, marked)
        mapped = extract_output_organisms(there, marked)
        if (
            organisms
            and mapped
            and mapped != organisms
            and extract_output_organisms(back, marked) == organisms
        ):
            yield back, there


def _one_way(
    tree: StrategyStepNode, marked: Mapping[str, str]
) -> Iterator[StrategyStepNode]:
    """Each transform to another organism that no transform maps back."""
    legs = {step.id for trip in _round_trips(tree, marked) for step in trip}
    for step in walk(tree):
        into = step.primary_input
        if into is None or step.secondary_input is not None or step.id in legs:
            continue
        mapped = extract_output_organisms(step, marked)
        organisms = extract_output_organisms(into, marked)
        if mapped and organisms and mapped != organisms:
            yield step


def _named(node: StrategyStepNode, marked: Mapping[str, str]) -> str:
    return ", ".join(sorted(extract_output_organisms(node, marked) or ()))


def orthology_shape_refusal(
    request: OrthologyRequest, spec: OperationalSpec, *, held: frozenset[str]
) -> str | None:
    """Why the spec's tree answers another orthology shape than the message
    asks for, or None.

    A transform the strategy ``held`` before the message is not read, so the
    message decides only the transforms it adds.
    """
    tree = stated_steps(spec)
    if tree is None:
        return None
    marked = organism_params_of(spec.criteria)
    if request.shape == "transform":
        trips = [b for b, t in _round_trips(tree, marked) if not {b.id, t.id} & held]
        if not trips:
            return None
        target = request.target or "another organism"
        genes = request.target or "that organism"
        return (
            f"The message carries the genes to {target}, which asks for one "
            f"transform whose result is the genes of {genes}. {trips[0].id} maps "
            f"them back to {_named(trips[0], marked)}, a round trip that keeps "
            f"the source genes. State {_TRANSFORM_NODE} with the organism the "
            f"message names, and no transform back."
        )
    added = [step for step in _one_way(tree, marked) if step.id not in held]
    if not added:
        return None
    step = added[0]
    source, mapped = _named(step.inputs()[0], marked), _named(step, marked)
    return (
        f"The message keeps the genes that have an ortholog in "
        f"{request.target or mapped}, which asks for the round trip that keeps "
        f"the source genes. {step.id} returns the genes of {mapped} where the "
        f"source holds genes of {source}. State {round_trip_wiring(source, mapped)}"
    )
