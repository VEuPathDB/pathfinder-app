"""An organism requirement a step's taxon pick covers stays grounded through the
check, and the card never offers to drop it."""

from __future__ import annotations

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.frame_requirements import requirements_no_search_states
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._frame_sources import stated_by_their_taxa
from pathfinder.domain.strategy.constraints import ConstraintStatus
from pathfinder.domain.strategy.named_taxa import NamedTaxon, phyletic_organism_tree
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._orthomcl_singletons import (
    ORGANISM,
    PLASMODIUM,
    QUESTION,
    SINGLETON,
    spec,
    taxon_pick,
    taxonomy,
)
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reading_deps


def _checked_deps(taxon: NamedTaxon | None) -> LeadDeps:
    deps = reading_deps()
    domain = deps.state.domain
    domain.operational_spec = spec(taxon)
    domain.requirements = [ORGANISM, SINGLETON]
    domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="No check of the strategy on the site failed",
            success=True,
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
