from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from pydantic_ai import RunContext
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PHYLETIC_EXPRESSION_SEARCH,
    ParamValue,
    PhyleticTree,
    StringValue,
)
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKAnswer, WDKRecordInstance

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.evidence_card import CardSources, assemble_evidence_card
from pathfinder.ai.tools.standalone import _expression_check, results
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.expression_fit import (
    SAMPLED_GROUP_LIMIT,
    ExpressionFit,
    bound_expressions,
    live_fits,
)
from pathfinder.domain.site_checks import SiteCheck, expression_fit_checks
from pathfinder.domain.strategy.build_outcome import BuiltCounts
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.ortho_taxonomy import recorded_ortho_taxonomy
from pathfinder.tests._support.orthomcl_step_columns import serve_step_columns
from pathfinder.tests._support.qa_recording import client_recording

from .conftest import agent_run_context

_STEP = 227284080


def failed_fits(fits: list[ExpressionFit]) -> list[SiteCheck]:
    return [c for c in expression_fit_checks(fits) if c.status == "fail"]


_SINGLE_COPY = "APIC=139T AND APIC=139"
_RECORDED_GROUPS = ["OG8_0003303", "OG8_0031041"]


class _TaxonRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    abbrev: str
    count: str


_ROWS = TypeAdapter(list[_TaxonRow])


def _recorded_answer() -> WDKAnswer:
    return WDKAnswer.model_validate(
        client_recording("orthomcl_group_taxon_counts").body
    )


def _with_one_genome_doubled(
    answer: WDKAnswer, group: str, tree: PhyleticTree
) -> WDKAnswer:
    apicomplexan = tree.genomes_under(["APIC"])

    def doubled(record: WDKRecordInstance) -> WDKRecordInstance:
        if record.id[0].value != group:
            return record
        rows = _ROWS.validate_python(record.tables["TaxonCounts"])
        first = next(i for i, row in enumerate(rows) if row.abbrev in apicomplexan)
        rows[first] = rows[first].model_copy(update={"count": "2"})
        table: JsonValue = _ROWS.dump_python(rows, mode="json")
        return record.model_copy(update={"tables": {"TaxonCounts": table}})

    return answer.model_copy(update={"records": [doubled(r) for r in answer.records]})


def _empty_answer() -> WDKAnswer:
    recorded = _recorded_answer()
    meta = recorded.meta.model_copy(
        update={"total_count": 0, "response_count": 0, "view_total_count": 0}
    )
    return WDKAnswer(meta=meta, records=[])


class _Site:
    def __init__(self, answer: WDKAnswer) -> None:
        self.answer = answer
        self.asked: list[tuple[int, list[str] | None, dict[str, int] | None]] = []

    async def get_step_records(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        sorting: object = None,
        *,
        view_filters: object = None,
    ) -> WDKAnswer:
        del attributes, sorting, view_filters
        self.asked.append((step_id, tables, pagination))
        return self.answer


class _Taxonomy:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def __call__(self, site_id: str) -> PhyleticTree:
        self.asked.append(site_id)
        return recorded_ortho_taxonomy()


def _serve(monkeypatch: pytest.MonkeyPatch, site: _Site) -> _Taxonomy:
    taxonomy = _Taxonomy()
    monkeypatch.setattr(_expression_check, "get_strategy_api", lambda site_id: site)
    monkeypatch.setattr(_expression_check, "ortho_taxonomy", taxonomy)
    serve_step_columns(monkeypatch, "group", _STEP, PHYLETIC_EXPRESSION_SEARCH)
    return taxonomy


def _context(search_name: str, params: dict[str, ParamValue]) -> RunContext[AgentDeps]:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph(graph_id="g1", name="Groups", site_id="orthomcl")
    graph.record_type = "group"
    graph.steps = flatten_tree(StrategyStepNode(id="c_one", search_name=search_name))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(wdk_step_ids={"c_one": _STEP})
    criterion = Criterion(
        id="c_one",
        text="groups across the apicomplexans",
        search_name=search_name,
        resolved_params=bind_values(params, "stated", []),
    )
    state = AgentToolState(operational_spec_draft=OperationalSpec(criteria=[criterion]))
    return agent_run_context(
        site_id="orthomcl", strategy_session=session, agent_state=state
    )


def _bound(expression: str) -> RunContext[AgentDeps]:
    return _context(
        PHYLETIC_EXPRESSION_SEARCH,
        {PHYLETIC_EXPRESSION_PARAM: StringValue(value=expression)},
    )


async def test_every_sampled_group_meets_the_single_copy_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site(_recorded_answer())
    _serve(monkeypatch, site)
    ctx = _bound(_SINGLE_COPY)

    answer = await results.read_step_columns(ctx.deps, _STEP)

    expected = ExpressionFit(
        wdk_step_id=_STEP, expression=_SINGLE_COPY, sampled=2, held=2
    )
    assert (
        answer.expression_fit,
        answer.fits,
        ctx.deps.turn_markers.expression_fits,
    ) == (
        expected,
        [],
        [expected],
    )
    assert answer.note == ""
    assert site.asked == [
        (_STEP, ["TaxonCounts"], {"offset": 0, "numRecords": SAMPLED_GROUP_LIMIT})
    ]
    assert SAMPLED_GROUP_LIMIT == 5
    assert expected.sentence == (
        f"2 of 2 sampled groups of step {_STEP} meet its phyletic expression on "
        "the site's per-genome counts"
    )


async def test_a_group_with_two_proteins_in_one_genome_fails_single_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = recorded_ortho_taxonomy()
    _serve(
        monkeypatch,
        _Site(_with_one_genome_doubled(_recorded_answer(), "OG8_0031041", tree)),
    )
    ctx = _bound(_SINGLE_COPY)

    answer = await results.read_step_columns(ctx.deps, _STEP)

    fit = answer.expression_fit
    assert fit is not None
    assert (fit.sampled, fit.held, fit.failing) == (2, 1, ["OG8_0031041"])
    assert [c.evidence for c in failed_fits([fit])] == [
        (
            f"1 of 2 sampled groups of step {_STEP} does not meet its phyletic "
            "expression on the site's per-genome counts: OG8_0031041"
        )
    ]


def test_the_evidence_card_holds_the_failing_fit_and_its_gap() -> None:
    failing = ExpressionFit(
        wdk_step_id=_STEP,
        expression=_SINGLE_COPY,
        sampled=2,
        held=1,
        failing=["OG8_0031041"],
    )
    sources = CardSources(
        check_id="call_verify",
        revision="rev-1",
        site_id="orthomcl",
        labels={},
        live_wdk_step_ids=frozenset({_STEP}),
        wdk_strategy_id=None,
        root_wdk_step_id=None,
        node_results=[],
        counts=BuiltCounts(),
        spec=None,
        control_tests=[],
        pending_checks=[],
        review=VerificationReview(),
        expression_fits=[failing],
    )

    card = assemble_evidence_card(
        sources, None, checked_at=datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    )

    assert card.expression_fits == [failing]
    assert [c.status for c in expression_fit_checks(card.expression_fits)] == ["fail"]
    assert failed_fits([failing.model_copy(update={"held": 2, "failing": []})]) == []


@pytest.mark.parametrize(
    ("expression", "unmatched"),
    [
        (
            "APIC>=1T AND MAMM<=0T",
            [
                (
                    "MAMM<=0T matches no group, because the site counts a unit "
                    "only in a group with a protein of its codes; write MAMM=0T "
                    "for absence."
                )
            ],
        ),
        ("APIC>=1T AND MAMM<=0T OR APIC>=1T AND MAMM=0T", []),
        ("APIC>=1T AND (MAMM<=0T OR MAMM=0T)", []),
        ("APIC>=1T AND APIC>5", []),
        (_SINGLE_COPY, []),
    ],
)
async def test_an_empty_step_names_the_units_the_site_matches_no_group_with(
    monkeypatch: pytest.MonkeyPatch, expression: str, unmatched: list[str]
) -> None:
    _serve(monkeypatch, _Site(_empty_answer()))

    answer = await results.read_step_columns(_bound(expression).deps, _STEP)

    fit = answer.expression_fit
    assert fit is not None
    assert (fit.sampled, fit.held, fit.failing, fit.unmatched) == (0, 0, [], unmatched)
    assert (len(failed_fits([fit])), answer.note) == (len(unmatched), "")


async def test_an_empty_step_the_site_cannot_match_is_a_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _Site(_empty_answer()))

    answer = await results.read_step_columns(_bound("APIC>140T").deps, _STEP)

    assert answer.expression_fit is not None
    assert answer.expression_fit.sentence == (
        f"step {_STEP} holds no group, and its phyletic expression matches none as "
        "the site reads it: APIC>140T over 139 genomes is true of every group or of "
        "none, so it states no constraint."
    )


async def test_a_group_step_with_no_expression_reads_no_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site(_recorded_answer())
    taxonomy = _serve(monkeypatch, site)
    ctx = _context("GroupsBySingleCopy", {"all_taxon": StringValue(value="50")})

    answer = await results.read_step_columns(ctx.deps, _STEP)

    assert (answer.expression_fit, site.asked, taxonomy.asked) == (None, [], [])


@pytest.mark.parametrize(
    ("expression", "taxonomy_read"),
    [("APIC=", []), ("pfal+HAEM>=1T", ["orthomcl"])],
)
async def test_an_expression_the_site_count_is_unknown_for_reads_no_group(
    monkeypatch: pytest.MonkeyPatch, expression: str, taxonomy_read: list[str]
) -> None:
    site = _Site(_recorded_answer())
    taxonomy = _serve(monkeypatch, site)

    answer = await results.read_step_columns(_bound(expression).deps, _STEP)

    assert (answer.expression_fit, site.asked, taxonomy.asked) == (
        None,
        [],
        taxonomy_read,
    )


def test_a_fit_holds_only_while_its_step_binds_its_expression() -> None:
    criteria = [
        Criterion(
            id="c_one",
            text="groups across the apicomplexans",
            search_name=PHYLETIC_EXPRESSION_SEARCH,
            resolved_params=bind_values(
                {PHYLETIC_EXPRESSION_PARAM: StringValue(value=_SINGLE_COPY)},
                "stated",
                [],
            ),
        ),
        Criterion(id="c_two", text="any group", search_name="GroupsBySingleCopy"),
    ]
    fit = ExpressionFit(wdk_step_id=_STEP, expression=_SINGLE_COPY, sampled=2, held=2)

    bindings = bound_expressions(criteria, {"c_one": _STEP, "c_two": _STEP + 1})

    assert bindings == {_STEP: _SINGLE_COPY}
    assert live_fits(
        [
            fit,
            fit.model_copy(update={"wdk_step_id": _STEP + 1}),
            fit.model_copy(update={"wdk_step_id": _STEP + 2}),
        ],
        bindings,
    ) == [fit]
    assert live_fits([fit], {_STEP: "APIC=139T AND APIC=1"}) == []


def test_a_step_keeps_its_latest_fit() -> None:
    markers = TurnMarkers()
    first = ExpressionFit(wdk_step_id=_STEP, expression=_SINGLE_COPY, sampled=2, held=2)
    other = first.model_copy(update={"wdk_step_id": _STEP + 1})
    latest = first.model_copy(update={"held": 1, "failing": ["OG8_0031041"]})

    for fit in (first, other, latest):
        markers.record_expression_fit(fit)

    assert markers.expression_fits == [latest, other]


def test_a_fit_counts_each_sampled_group_once() -> None:
    with pytest.raises(ValueError, match="held \\+ failing"):
        ExpressionFit(
            wdk_step_id=_STEP,
            expression=_SINGLE_COPY,
            sampled=2,
            held=2,
            failing=["OG8_0031041"],
        )


def test_the_recorded_groups_are_the_two_single_copy_groups() -> None:
    assert [r.id[0].value for r in _recorded_answer().records] == _RECORDED_GROUPS
