from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKStepTree

from pathfinder.ai.lead import evidence_card, verify_dispatch
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.domain.evidence import SampledGene
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.evidence import step_answers
from pathfinder.services.gene_sets.step_genes import StepIds
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.site_checks import checked_site
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

pytestmark = pytest.mark.usefixtures("collector")

_STRATEGY = 214670620
_CONSERVED = "Orthology Phylogenetic Profile"
_BERGHEI = "P. berghei experimentally essential genes"
_GONDII = "T. gondii experimentally essential genes"
_APICOPLAST = "Apicoplast targeted genes"
_PBANKA = "PBANKA_1033800"
_TGGT1 = "TGGT1_200010"
_WDK = {
    "c_conserved": 227352470,
    "e_berghei": 227352471,
    "e_gondii": 227352472,
    "x_apicoplast": 227352473,
}
_CONSERVED_COUNT = 218138
_RECORD = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/{}"
_READ = "The record names a conserved protein."
_IN_CONSERVED = f"In the step '{_CONSERVED}' (conserved in the oomycetes)"
_ESSENTIAL = "(experimentally essential)"
_SUBTRACTED = "which the strategy subtracts (not targeted to the apicoplast)"


def _why(*facts: str) -> str:
    return f"{'; '.join(facts)}. {_READ}"


def _leaf(step_id: str, title: str) -> StrategyStepNode:
    return StrategyStepNode(
        id=step_id, search_name=f"Search_{step_id}", display_name=title
    )


def _essential_union() -> StrategyStepNode:
    return StrategyStepNode(
        id="u_essential",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.UNION,
        primary_input=_leaf("e_berghei", _BERGHEI),
        secondary_input=_leaf("e_gondii", _GONDII),
    )


def _conserved_and_essential() -> StrategyStepNode:
    return StrategyStepNode(
        id="root",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=_leaf("c_conserved", _CONSERVED),
        secondary_input=_essential_union(),
    )


def _conserved_minus_apicoplast() -> StrategyStepNode:
    return StrategyStepNode(
        id="root",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.MINUS,
        primary_input=_leaf("c_conserved", _CONSERVED),
        secondary_input=_leaf("x_apicoplast", _APICOPLAST),
    )


_CONSERVED_ASK = requirement(
    ConstraintKind.ORTHOLOG, "ortholog", "conserved in the oomycetes"
)
_ESSENTIAL_ASK = requirement(
    ConstraintKind.PROPERTY, "essentiality", "experimentally essential"
)
_APICOPLAST_ASK = requirement(
    ConstraintKind.PROPERTY, "localization", "not targeted to the apicoplast"
)
_KINASE_ASK = requirement(ConstraintKind.TEXT, "product", "a protein kinase")


def _criterion(step_id: str, *asks: Constraint) -> Criterion:
    return Criterion(
        id=step_id,
        text=step_id,
        search_name=f"Search_{step_id}",
        record_class="transcript",
        answers=[RequirementLink(requirement=ask.id) for ask in asks],
    )


def _deps(
    root: StrategyStepNode,
    criteria: list[Criterion],
    asks: list[Constraint],
    counts: dict[str, int | None],
) -> LeadDeps:
    state = pipeline_state("plasmodb", user_prompt="conserved essential genes")
    state.domain.requirements = asks
    state.domain.operational_spec = OperationalSpec(
        goal="conserved essential genes", criteria=criteria
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=[c.id for c in criteria], wdk_strategy_id=_STRATEGY
    )
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Conserved", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(root)
    graph.recompute_roots()
    session.graph = graph
    held = {step_id: _WDK.get(step_id, 227352480) for step_id in graph.steps}
    session.sync_state = WDKSyncState(
        wdk_step_ids=held,
        step_counts=counts,
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=held["root"]),
    )
    for gene_id in (_PBANKA, _TGGT1):
        state.turn_markers.record_retrieved_source(_RECORD.format(gene_id))
    return lead_deps(state, strategy_session=session)


def _conserved_essential_deps(*more: Constraint) -> LeadDeps:
    return _deps(
        _conserved_and_essential(),
        [
            _criterion("c_conserved", _CONSERVED_ASK),
            _criterion("e_berghei", _ESSENTIAL_ASK),
            _criterion("e_gondii", _ESSENTIAL_ASK),
        ],
        [_CONSERVED_ASK, _ESSENTIAL_ASK, *more],
        {
            "c_conserved": _CONSERVED_COUNT,
            "e_berghei": 417,
            "e_gondii": 100,
            "u_essential": 517,
            "root": 319,
        },
    )


class _Site:
    """The step answers the membership reads list, by WDK step id."""

    def __init__(
        self, held: dict[int, list[str]], refused: frozenset[int] = frozenset()
    ) -> None:
        self.held = held
        self.refused = refused
        self.listed: list[tuple[int, int]] = []

    async def first_step_gene_ids(
        self, site_id: str, step_id: int, *, limit: int
    ) -> StepIds:
        assert site_id == "plasmodb"
        self.listed.append((step_id, limit))
        if step_id in self.refused:
            raise ValidationError(title="Step is not in a strategy")
        return StepIds(gene_ids=self.held[step_id], total=len(self.held[step_id]))


class _Dispatch:
    def __init__(self, genes: Sequence[dict[str, str]]) -> None:
        self.outcome = VerificationDelta.model_validate(
            {
                "digest": {
                    "prose": "The sample reads two genes.",
                    "review": {"sampledGenes": list(genes)},
                }
            }
        )
        self.work_order = ""

    async def streamed(self, **kwargs: Any) -> VerificationDelta:
        self.work_order = kwargs["run"].work_order
        return self.outcome


def _gene(gene_id: str, fits: str) -> dict[str, str]:
    return {
        "geneId": gene_id,
        "product": "conserved protein, unknown function",
        "organism": "Plasmodium berghei ANKA",
        "fits": fits,
        "why": _READ,
    }


async def _verified(
    monkeypatch: pytest.MonkeyPatch,
    deps: LeadDeps,
    site: _Site,
    *genes: dict[str, str],
) -> tuple[list[SampledGene], _Dispatch]:
    dispatch = _Dispatch(genes)

    async def counts(site_id: str, wdk_strategy_id: int) -> SiteCounts:
        del site_id, wdk_strategy_id
        return SiteCounts(root_step_id=227352480, counts={})

    checked_site(monkeypatch)
    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", dispatch.streamed)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    monkeypatch.setattr(step_answers, "first_step_gene_ids", site.first_step_gene_ids)
    delta = await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the genes"
    )
    assert isinstance(delta, VerificationDelta)
    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert card.review.sampled_genes == delta.digest.review.sampled_genes
    return delta.digest.review.sampled_genes, dispatch


def _conserved_and_essential_site() -> _Site:
    return _Site(
        {
            _WDK["e_berghei"]: [_PBANKA, "PBANKA_0100600"],
            _WDK["e_gondii"]: [_TGGT1],
        }
    )


async def test_a_gene_both_steps_hold_fits_both_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    genes, _dispatch = await _verified(
        monkeypatch,
        _conserved_essential_deps(),
        _conserved_and_essential_site(),
        _gene(_PBANKA, "unclear"),
    )

    assert [(g.gene_id, g.fits, g.why) for g in genes] == [
        (
            _PBANKA,
            "yes",
            _why(_IN_CONSERVED, f"In the step '{_BERGHEI}' {_ESSENTIAL}"),
        )
    ]


async def test_a_gene_in_one_branch_of_a_union_fits_its_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    genes, _dispatch = await _verified(
        monkeypatch,
        _conserved_essential_deps(),
        _conserved_and_essential_site(),
        _gene(_TGGT1, "unclear"),
    )

    assert [(g.fits, g.why) for g in genes] == [
        (
            "yes",
            _why(_IN_CONSERVED, f"In the step '{_GONDII}' {_ESSENTIAL}"),
        )
    ]


async def test_a_subtracted_step_is_absent_by_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(
        _conserved_minus_apicoplast(),
        [
            _criterion("c_conserved", _CONSERVED_ASK),
            _criterion("x_apicoplast", _APICOPLAST_ASK),
        ],
        [_CONSERVED_ASK, _APICOPLAST_ASK],
        {"c_conserved": _CONSERVED_COUNT, "x_apicoplast": 600, "root": 217600},
    )
    site = _Site({})

    genes, _dispatch = await _verified(
        monkeypatch, deps, site, _gene(_PBANKA, "unclear"), _gene(_TGGT1, "no")
    )

    assert site.listed == []
    assert [(g.gene_id, g.fits, g.why) for g in genes] == [
        (
            gene_id,
            "yes",
            _why(_IN_CONSERVED, f"Not in the step '{_APICOPLAST}', {_SUBTRACTED}"),
        )
        for gene_id in (_PBANKA, _TGGT1)
    ]


async def test_only_the_union_branches_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _conserved_and_essential_site()

    await _verified(
        monkeypatch,
        _conserved_essential_deps(),
        site,
        _gene(_PBANKA, "unclear"),
        _gene(_TGGT1, "unclear"),
    )

    assert sorted(site.listed) == [(_WDK["e_berghei"], 5000), (_WDK["e_gondii"], 5000)]


async def test_a_union_branch_over_the_cap_is_left_to_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _conserved_essential_deps()
    sync = deps.runtime.strategy_session.sync_state
    assert sync is not None
    sync.step_counts["e_berghei"] = 9000
    site = _conserved_and_essential_site()

    genes, dispatch = await _verified(
        monkeypatch, deps, site, _gene(_PBANKA, "unclear"), _gene(_TGGT1, "yes")
    )

    assert site.listed == []
    assert [(g.fits, g.why) for g in genes] == [
        (
            fits,
            (
                f"{_IN_CONSERVED}. The step '{_BERGHEI}' holds 9,000 genes, more "
                "than the 5,000 Strategist lists, so the record judges "
                f"experimentally essential. {_READ}"
            ),
        )
        for fits in ("unclear", "yes")
    ]
    assert dispatch.work_order.endswith(f"- conserved in the oomycetes: '{_CONSERVED}'")


async def test_a_requirement_no_step_encodes_is_left_to_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    genes, dispatch = await _verified(
        monkeypatch,
        _conserved_essential_deps(_KINASE_ASK),
        _conserved_and_essential_site(),
        _gene(_PBANKA, "unclear"),
        _gene(_TGGT1, "no"),
    )

    assert [(g.gene_id, g.fits) for g in genes] == [
        (_PBANKA, "unclear"),
        (_TGGT1, "no"),
    ]
    assert dispatch.work_order.endswith(
        "The steps decide these requirements for each sampled gene, by whether "
        "the step holds it:\n"
        f"- conserved in the oomycetes: '{_CONSERVED}'\n"
        f"- experimentally essential: '{_BERGHEI}' or '{_GONDII}'"
    )


async def test_a_gene_the_record_judges_and_the_steps_hold_fits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    genes, _dispatch = await _verified(
        monkeypatch,
        _conserved_essential_deps(_KINASE_ASK),
        _conserved_and_essential_site(),
        _gene(_PBANKA, "yes"),
    )

    assert [g.fits for g in genes] == ["yes"]


async def test_a_branch_the_site_does_not_list_leaves_its_requirement_unclear(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site(
        {_WDK["e_berghei"]: [_PBANKA], _WDK["e_gondii"]: [_TGGT1]},
        refused=frozenset({_WDK["e_berghei"]}),
    )

    genes, _dispatch = await _verified(
        monkeypatch, _conserved_essential_deps(), site, _gene(_PBANKA, "yes")
    )

    assert [(g.fits, g.why) for g in genes] == [
        (
            "unclear",
            _why(
                _IN_CONSERVED,
                f"The site did not say whether the step '{_BERGHEI}' holds it "
                f"{_ESSENTIAL}",
            ),
        )
    ]
