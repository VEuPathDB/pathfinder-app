from __future__ import annotations

import pytest
from pydantic import JsonValue
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, VocabOption
from veupathdb.errors import joined_refusal
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import (
    ParameterInfo,
    PhyleticListError,
    PhyleticNoSelection,
    ResolvedParams,
    UnreadQuantityError,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import _frame_proposals
from strategist.ai.tools.standalone._frame_answers import AnsweredRequirement
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._frame_sheet import reconcile_dependents
from strategist.ai.tools.standalone._frame_stated import word_problems
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.domain.refusal import RefusalKey
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.orthology_request import OrthologyRequest
from strategist.platform.refusals import ProblemsRefusal
from strategist.tests._support.catalog_reads import listing
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.recorded_searches import client_search
from strategist.tests._support.sheets import declarations
from strategist.tests.unit.ai.tools.test_frame_spec import (
    bind,
    default_why,
    frame_ctx,
    genes_by_text,
    param_info,
    serve_search,
)

_TEXT_CALL: dict[str, JsonValue] = {
    "text_expression": "kinase",
    "text_search_organism": ["Plasmodium"],
    "document_type": None,
    "text_fields": None,
}
_AGGREGATION = [
    VocabOption(value="average1", display="average"),
    VocabOption(value="minimum2", display="minimum"),
]


def _keys(refusal: ProblemsRefusal) -> list[RefusalKey]:
    return [problem.key for problem in refusal.problems.found]


def _children(bound: bool) -> list[ParameterInfo]:
    leaves = _AGGREGATION if bound else _AGGREGATION[:1]
    return [
        param_info(
            "samples_generic",
            "multi-pick-vocabulary",
            vocab_leaves=[VocabOption(value="sampleA", display="sampleA")],
            stated_children=["agg_a", "agg_b"],
            wire_children=["agg_a", "agg_b"],
        ),
        *(
            param_info(
                name,
                "single-pick-vocabulary",
                vocab_leaves=leaves,
                stated_parents=["samples_generic"],
                wire_parents=["samples_generic"],
            )
            for name in ("agg_a", "agg_b")
        ),
    ]


async def test_every_refused_dependent_is_named_and_the_marks_stay() -> None:
    async def fetch_at(context: dict[str, str]) -> list[WDKParameter]:
        del context
        return declarations(_children(bound=True))

    state = AgentToolState()
    for name in ("agg_a", "agg_b"):
        state.mark_redecided("c1", "GenesByRNASeq", name)
    call = CriterionCall(
        criterion_id="c1", search_name="GenesByRNASeq", text="aggregate", params={}
    ).with_values(
        {
            "agg_a": SinglePickValue(value="median9"),
            "agg_b": SinglePickValue(value="mode4"),
        }
    )
    resolved = ResolvedParams(params={})

    with pytest.raises(ProblemsRefusal) as refused:
        await reconcile_dependents(
            "plasmodb", fetch_at, _children(bound=False), resolved, call, state
        )

    assert [key.parameter for key in _keys(refused.value)] == ["agg_a", "agg_b"]
    assert str(refused.value).endswith("Nothing was recorded.")
    assert state.was_redecided("c1", "GenesByRNASeq", "agg_a")


async def test_an_unknown_requirement_joins_the_sheet_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()
    state.record_catalog_read(listing(["GenesByText"]))
    state.request_messages = ["kinases"]
    params = {**_TEXT_CALL, "organsim": None}

    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c1",
            text="kinases",
            search_name="GenesByText",
            params=params,
            answers=[AnsweredRequirement(requirement="R9")],
            why=default_why("GenesByText", params),
        )

    assert {key.check for key in _keys(refused.value)} == {
        "requirements",
        "unknown_names",
    }


async def test_a_call_with_no_why_and_an_unknown_name_is_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()
    state.record_catalog_read(listing(["GenesByText"]))
    state.request_messages = ["kinases"]

    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c1",
            text="kinases",
            search_name="GenesByText",
            params={**_TEXT_CALL, "organsim": None},
            why=None,
        )

    assert {key.check for key in _keys(refused.value)} == {"why", "unknown_names"}


async def test_a_reading_no_question_offered_joins_the_sheet_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()
    state.record_catalog_read(listing(["GenesByText"]))
    state.request_messages = ["kinases"]
    params = {**_TEXT_CALL, "organsim": None}

    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c1",
            text="kinases",
            search_name="GenesByText",
            params=params,
            why=default_why("GenesByText", params),
            reading="broad",
        )

    assert {key.check for key in _keys(refused.value)} == {"reading", "unknown_names"}


async def test_a_lone_unread_quantity_is_refused_and_nothing_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _held_back(**_kw: object) -> ResolvedParams:
        return ResolvedParams(params={}, unread=["min_expression_percentile"])

    serve_search(monkeypatch, genes_by_text)
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _held_back)
    state = AgentToolState()

    with pytest.raises(ProblemsRefusal) as refused:
        await bind(state, "GenesByText", _TEXT_CALL)

    assert _keys(refused.value) == [
        RefusalKey(
            check="resolve",
            criterion="c1",
            search="GenesByText",
            parameter="min_expression_percentile",
        )
    ]
    assert state.operational_spec_draft.criteria == []


async def test_a_phyletic_row_and_an_unread_quantity_are_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refusing(**_kw: object) -> ResolvedParams:
        raise joined_refusal(
            [
                PhyleticListError(PhyleticNoSelection()),
                UnreadQuantityError(["min_expression_percentile"]),
            ]
        )

    serve_search(monkeypatch, genes_by_text)
    monkeypatch.setattr(_frame_proposals, "resolve_params_with_intent", _refusing)
    state = AgentToolState()

    with pytest.raises(ProblemsRefusal) as refused:
        await bind(state, "GenesByText", _TEXT_CALL)

    sentences = {p.key.parameter: p.sentence for p in refused.value.problems.found}
    assert set(sentences) == {"profile_pattern", "min_expression_percentile"}
    assert "lookup_phyletic_codes(query)" in sentences["profile_pattern"]
    assert state.operational_spec_draft.criteria == []


def test_a_transform_names_the_organism_it_carries_to_alone() -> None:
    orthologs = client_search("search_genes_by_orthologs")
    call = CriterionCall(
        criterion_id="c_to",
        search_name=orthologs.url_segment,
        text="their orthologs",
        params={},
    ).with_values(
        {
            "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
            "isSyntenic": SinglePickValue(value="yes"),
        }
    )
    state = AgentToolState(
        orthology_request=OrthologyRequest(
            shape="transform", target="Plasmodium vivax P01"
        ),
        stated_requirements=[
            Constraint(
                kind=ConstraintKind.ORGANISM,
                requested_value="Plasmodium falciparum 3D7",
                label="organism",
                source=ConstraintSource.USER_EXPLICIT,
            )
        ],
    )

    found = word_problems(orthologs, call, sheet_of(orthologs.parameters or []), state)

    assert [p.key for p in found.found] == [
        RefusalKey(check="organism_carried", parameter="organism")
    ]
    assert "Plasmodium vivax P01" in found.found[0].sentence


async def test_an_input_path_names_its_answers_and_its_role_once() -> None:
    state = AgentToolState()

    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c_saved",
            text="my saved genes",
            role="transform",
            gene_set="kinases",
            answers=[AnsweredRequirement(requirement="R9")],
        )

    assert {key.check for key in _keys(refused.value)} == {"requirements", "role"}
    assert state.operational_spec_draft.criteria == []
