"""A separation run's result as the report PathFinder shows and the offer it builds.

The spec is the measured tree itself: each leaf is a criterion bound to the
candidate's own search and wire parameters, and each carries the counts its
step returned as its reason.
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from pydantic import TypeAdapter
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.separation import (
    MeasuredCandidate,
    SeparationNode,
    SeparationResult,
    SkipReason,
)

from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.separation import (
    SKIPPED_EXAMPLES,
    MeasuredCriterion,
    OfferedLeaf,
    SeparationOffer,
    SeparationReport,
    SkippedCriterion,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.step_rationale import ControlsRationale, ControlsSource
from pathfinder.services.evidence.control_enrichment import control_enrichment

_RECORD_TYPE = "transcript"
# A catalog or thread candidate's basis names where it came from, not what it finds.
_NAMED_BY_ITS_SEARCH = frozenset({"catalog", "thread"})
_SOURCE: TypeAdapter[ControlsSource] = TypeAdapter(ControlsSource)


def _controls(measured: MeasuredCandidate) -> ControlTestEvidence:
    return ControlTestEvidence(
        tested_label=measured.candidate.display_name,
        positive=ControlSetEvidence(
            returned=measured.positive.recovered_ids,
            not_returned=measured.positive.missed_ids,
        ),
        negative=ControlSetEvidence(
            returned=measured.negative.admitted_ids,
            not_returned=measured.negative.excluded_ids,
        ),
    )


def _rationale(measured: MeasuredCandidate, task_id: UUID) -> ControlsRationale:
    candidate = measured.candidate
    return ControlsRationale(
        task_id=str(task_id),
        search_name=candidate.search_name,
        source=_SOURCE.validate_python(candidate.source.value),
        basis=candidate.basis,
        sources=[] if candidate.reference is None else [candidate.reference],
        informs=measured.informs,
        recovered=measured.positive.intersection_count,
        positives=measured.positive.controls_count,
        admitted=measured.negative.intersection_count,
        negatives=measured.negative.controls_count,
        result_size=measured.result_size,
    )


def _criterion(
    measured: MeasuredCandidate, role: CriterionRole, task_id: UUID
) -> Criterion:
    candidate = measured.candidate
    text = (
        candidate.display_name
        if candidate.source.value in _NAMED_BY_ITS_SEARCH
        else f"{candidate.display_name}: {candidate.basis}"
    )
    return Criterion(
        id=candidate.id,
        text=text,
        search_name=candidate.search_name,
        search_display_name=candidate.display_name,
        role=role,
        resolved_params=dict(candidate.parameters),
        confidence=1.0,
        rationale=_rationale(measured, task_id),
    )


def _roles(node: SeparationNode, role: CriterionRole) -> dict[str, CriterionRole]:
    """Each leaf's role: the tree's first leaf seeds, a right input takes its operator's."""
    if node.kind == "leaf":
        return {str(node.candidate_id): role}
    left, right = node.inputs
    right_role: CriterionRole
    match node.operator:
        case CombineOp.INTERSECT:
            right_role = "filter"
        case CombineOp.MINUS:
            right_role = "exclude"
        case _:
            right_role = "seed"
    return _roles(left, role) | _roles(right, right_role)


def _structure(node: SeparationNode) -> StructureNode:
    if node.kind == "leaf":
        return StructureNode(kind="leaf", criterion_id=node.candidate_id)
    return StructureNode(
        kind="combine",
        operator=node.operator,
        inputs=[_structure(child) for child in node.inputs],
    )


def _offer(result: SeparationResult, task_id: UUID) -> SeparationOffer | None:
    tree, positive, negative = result.tree, result.positive, result.negative
    if tree is None or positive is None or negative is None:
        return None
    by_id = {m.candidate.id: m for m in result.measured}
    roles = _roles(tree, "seed")
    criteria = [_criterion(by_id[cid], role, task_id) for cid, role in roles.items()]
    read_positive = ControlSetEvidence(
        returned=positive.recovered_ids, not_returned=positive.missed_ids
    )
    read_negative = ControlSetEvidence(
        returned=negative.admitted_ids, not_returned=negative.excluded_ids
    )
    return SeparationOffer(
        task_id=str(task_id),
        site_id=result.site_id,
        mode=result.mode,
        spec=OperationalSpec(
            goal=(
                f"Separate {len(result.positives)} positive genes from "
                f"{len(result.negatives)} negative genes"
            ),
            record_type=_RECORD_TYPE,
            organism_scope=", ".join(result.organisms) or None,
            criteria=criteria,
            structure=SpecStructure(root=_structure(tree)),
        ),
        positive=read_positive,
        negative=read_negative,
        enrichment=control_enrichment(read_positive, read_negative),
        result_size=result.result_size,
        separates=result.separates,
        predicted_matches_read=result.predicted_matches_read,
        leaves=[
            OfferedLeaf(
                criterion_id=cid,
                display_name=by_id[cid].candidate.display_name,
                controls=_controls(by_id[cid]),
            )
            for cid in roles
        ],
    )


def _measured(measured: MeasuredCandidate) -> MeasuredCriterion:
    candidate = measured.candidate
    return MeasuredCriterion(
        candidate_id=candidate.id,
        search_name=candidate.search_name,
        display_name=candidate.display_name,
        source=_SOURCE.validate_python(candidate.source.value),
        basis=candidate.basis,
        reference=candidate.reference,
        result_size=measured.result_size,
        recovered=measured.positive.intersection_count,
        positives=measured.positive.controls_count,
        admitted=measured.negative.intersection_count,
        negatives=measured.negative.controls_count,
        informs=measured.informs,
    )


def separation_report(result: SeparationResult, *, task_id: UUID) -> SeparationReport:
    """The report of one run: its offer, its measurements, its skips and its cost."""
    skipped = Counter[SkipReason](s.reason for s in result.skipped)
    return SeparationReport(
        task_id=str(task_id),
        site_id=result.site_id,
        mode=result.mode,
        offer=_offer(result, task_id),
        measured=[_measured(m) for m in result.measured],
        skipped_by_reason=dict(sorted(skipped.items())),
        skipped_examples=[
            SkippedCriterion(
                search_name=s.search_name,
                source=_SOURCE.validate_python(s.source.value),
                basis=s.basis,
                reason=s.reason,
                detail=s.detail,
            )
            for s in result.skipped[:SKIPPED_EXAMPLES]
        ],
        unresolved_positive=result.unresolved_positive,
        unresolved_negative=result.unresolved_negative,
        shortfall=result.shortfall,
        charged_requests=result.charged_requests,
        budget=result.budget,
    )


__all__ = ["separation_report"]
