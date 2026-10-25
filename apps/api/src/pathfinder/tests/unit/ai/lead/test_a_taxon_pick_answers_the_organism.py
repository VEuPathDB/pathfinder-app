"""An organism requirement a step's taxon pick covers stays grounded through the
check, and the card never offers to drop it."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.frame_requirements import requirements_no_search_states
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._frame_sources import stated_by_their_taxa
from pathfinder.domain.caveats import RequirementGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import ConstraintStatus
from pathfinder.domain.strategy.named_taxa import NamedTaxon, phyletic_organism_tree
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._orthomcl_singletons import (
    ORGANISM,
    PLASMODIUM,
    QUESTION,
    SINGLETON,
    UNMET_ROW,
    spec,
    taxon_pick,
    taxonomy,
)
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps

_REVIEW = VerificationReview(
    requirements=[
        RequirementCheck(text=UNMET_ROW, turn=1, how="structure", status="unmet")
    ]
)


def _checked_deps(taxon: NamedTaxon | None) -> LeadDeps:
    deps = reading_deps()
    domain = deps.state.domain
    domain.operational_spec = spec(taxon)
    domain.requirements = [ORGANISM, SINGLETON]
    gaps = check_gaps(
        structure=None,
        words=[],
        review=_REVIEW,
        requirements=derive_ledger(deps.state, None).constraints.grounded,
    )
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.HANDOFF,
            prose="Checked.",
            reason="No step counts the proteins per species.",
            success=False,
            gaps=gaps,
        ),
        revision=strategy_revision(domain.answered_graph),
    )
    return deps


def test_the_taxonomy_names_the_pick_by_its_genus() -> None:
    bound = stated_by_their_taxa(
        {"taxon_type_ahead": taxon_pick(None)},
        {"taxon_type_ahead": phyletic_organism_tree(taxonomy())},
        [QUESTION],
    )

    assert bound["taxon_type_ahead"].taxon == PLASMODIUM


def test_the_unmet_row_names_no_requirement_the_pick_answers() -> None:
    deps = _checked_deps(PLASMODIUM)
    verdict = deps.state.turn_verdict

    assert verdict is not None
    assert verdict.gaps == [RequirementGap(text=UNMET_ROW, status="unmet")]


def test_the_organism_stays_grounded_on_the_pick() -> None:
    grounded = derive_ledger(_checked_deps(PLASMODIUM).state, None).constraints

    organism = next(g for g in grounded.grounded if g.constraint.key == ORGANISM.key)
    assert (organism.status, organism.realized_param, organism.realized_value) == (
        ConstraintStatus.GROUNDED,
        "taxon_type_ahead",
        "Plasmodium",
    )


def test_no_card_offers_to_drop_the_organism() -> None:
    assert requirements_no_search_states(_checked_deps(PLASMODIUM), []) == []
