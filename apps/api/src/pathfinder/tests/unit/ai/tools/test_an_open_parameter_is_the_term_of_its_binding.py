from __future__ import annotations

import pytest
from veupathdb.domain.parameters import VocabOption
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    EXPORTED,
    ORGANISMS,
    SITE,
    choice,
    choose,
    read,
    refused,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    param_info,
    serve_search,
    serve_site_listing,
)

_SCORE = "Minimum ExportPred Score"
_ORGANISM = ["Plasmodium falciparum 3D7"]


def _sheet(*, score_default: str | None) -> list[ParameterInfo]:
    score = (
        param_info("min_exportpred_score", "number", display_name=_SCORE)
        if score_default is None
        else param_info(
            "min_exportpred_score",
            display_name=_SCORE,
            required=False,
            default_value=score_default,
        )
    )
    return [
        param_info(
            "organism",
            "multi-pick-vocabulary",
            display_name="Organism",
            vocab_leaves=ORGANISMS,
            organism_param=True,
        ),
        score,
        param_info("max_tm_domains", display_name="Maximum TM Domains", required=False),
    ]


async def _read(
    monkeypatch: pytest.MonkeyPatch,
    *,
    score_default: str | None,
    asked: str = "genes with a predicted export signal",
) -> AgentToolState:
    serve_search(monkeypatch, lambda _context: _sheet(score_default=score_default))
    serve_site_listing(monkeypatch, SITE)
    state = AgentToolState()
    state.request_messages = [asked]
    await read(monkeypatch, state, EXPORTED)
    return state


_WHY = choice("parameter", _SCORE, "the score decides which genes are exported")


@pytest.mark.asyncio
async def test_the_open_parameter_a_researcher_decides_is_the_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _read(monkeypatch, score_default=None)

    result = await choose(
        state,
        _WHY,
        params={"organism": _ORGANISM, "min_exportpred_score": None},
    )

    assert result.rationale is not None
    assert (result.rationale.basis, result.rationale.term) == ("parameter", _SCORE)
    assert [s.param_name for s in result.open_slots] == ["min_exportpred_score"]


@pytest.mark.asyncio
async def test_a_null_parameter_left_at_the_default_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _read(monkeypatch, score_default="10")

    refusal = await refused(
        state, _WHY, params={"organism": _ORGANISM, "min_exportpred_score": None}
    )

    assert refusal == (
        f"c_gpi: this call leaves {_SCORE} null, so it decides nothing. Name the "
        "parameter whose value decides the choice."
    )


@pytest.mark.asyncio
async def test_a_null_parameter_beside_a_set_value_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = await _read(monkeypatch, score_default=None)

    refusal = await refused(
        state,
        _WHY,
        params={
            "organism": _ORGANISM,
            "min_exportpred_score": None,
            "max_tm_domains": "2",
        },
    )

    assert refusal.startswith(f"c_gpi: this call leaves {_SCORE} null")


_CASE_8 = (
    "Find orthogroups that have more genes per genome in Toxoplasma than "
    "Plasmodium (expanded gene families)."
)


@pytest.mark.parametrize(
    "messages",
    [
        [_CASE_8],
        ["Find orthogroups like the one of PF3D7_1133400 with more genes per genome."],
        ["Find orthogroups with more genes per genome, as in the 2019 survey."],
        ["Show me the top 10 kinases in 3D7.", _CASE_8],
    ],
)
@pytest.mark.asyncio
async def test_an_open_expression_binds_whatever_numbers_the_messages_hold(
    monkeypatch: pytest.MonkeyPatch, messages: list[str]
) -> None:
    serve_search(
        monkeypatch,
        lambda _context: [
            param_info("phyletic_expression", "string", display_name="Expression")
        ],
    )
    serve_site_listing(monkeypatch, SITE)
    state = AgentToolState()
    state.request_messages = messages
    await read(monkeypatch, state, EXPORTED)

    result = await choose(
        state,
        choice("parameter", "Expression", "the expression compares the copy counts"),
        params={"phyletic_expression": None},
    )

    assert [s.param_name for s in result.open_slots] == ["phyletic_expression"]


def _text_sheet() -> list[ParameterInfo]:
    return [
        param_info(
            "organism",
            "multi-pick-vocabulary",
            display_name="Organism",
            vocab_leaves=ORGANISMS,
            organism_param=True,
        ),
        param_info("text_expression", display_name="Text term"),
    ]


_TERM = choice("parameter", "Text term", "the text term decides which genes match")
_ORGANISM_WHY = choice("parameter", "Organism", "the organism decides which genes")


@pytest.mark.parametrize(
    ("asked", "why", "params"),
    [
        (
            'genes with "kinase" in the product description',
            _TERM,
            {"organism": _ORGANISM, "text_expression": None},
        ),
        ("kinase genes", _TERM, {"organism": _ORGANISM, "text_expression": None}),
        (
            "exported proteins in one organism",
            _ORGANISM_WHY,
            {"organism": None, "text_expression": None},
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_text_term_or_an_organism_left_null_decides_nothing(
    monkeypatch: pytest.MonkeyPatch,
    asked: str,
    why: SearchChoice,
    params: dict[str, str | list[str] | None],
) -> None:
    serve_search(monkeypatch, lambda _context: _text_sheet())
    serve_site_listing(monkeypatch, SITE)
    state = AgentToolState()
    state.request_messages = [asked]
    await read(monkeypatch, state, EXPORTED)

    refusal = await refused(state, why, params=params)

    assert refusal.startswith("c_gpi: this call leaves")


def _two_open_sheet() -> list[ParameterInfo]:
    return [
        param_info(
            "organism",
            "multi-pick-vocabulary",
            display_name="Organism",
            vocab_leaves=ORGANISMS,
            organism_param=True,
        ),
        param_info("min_exportpred_score", "number", display_name=_SCORE),
        param_info(
            "evidence",
            "single-pick-vocabulary",
            display_name="Evidence",
            vocab_leaves=[
                VocabOption(value="Curated", display="Curated"),
                VocabOption(value="Computed", display="Computed"),
            ],
        ),
    ]


@pytest.mark.parametrize(
    ("term", "params"),
    [
        (
            "Evidence",
            {"organism": _ORGANISM, "min_exportpred_score": "5", "evidence": None},
        ),
        (
            _SCORE,
            {"organism": _ORGANISM, "min_exportpred_score": None, "evidence": None},
        ),
    ],
)
@pytest.mark.asyncio
async def test_a_null_value_that_takes_no_reading_decides_nothing(
    monkeypatch: pytest.MonkeyPatch,
    term: str,
    params: dict[str, str | list[str] | None],
) -> None:
    serve_search(monkeypatch, lambda _context: _two_open_sheet())
    serve_site_listing(monkeypatch, SITE)
    state = AgentToolState()
    state.request_messages = ["genes with a predicted export signal"]
    await read(monkeypatch, state, EXPORTED)

    refusal = await refused(
        state, choice("parameter", term, "it decides the choice"), params=params
    )

    assert refusal.startswith(f"c_gpi: this call leaves {term} null")
