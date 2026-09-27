"""The organism parameter decides a binding only when no other parameter is set
away from its default, and the bound criterion names that parameter."""

from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.tests.unit.ai.tools._rationale_catalog import (
    EXPORTED,
    ORGANISMS,
    SIGNAL,
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

PF = "Plasmodium falciparum 3D7"
SCORE = "Minimum ExportPred Score"


def _marked_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info(
            "organism",
            "multi-pick-vocabulary",
            display_name="Organism",
            vocab_leaves=ORGANISMS,
            organism_param=True,
        ),
        param_info(
            "min_exportpred_score",
            display_name=SCORE,
            required=False,
            default_value="10",
        ),
    ]


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _marked_sheet)
    serve_site_listing(monkeypatch, SITE)


def _organism_parameter() -> SearchChoice:
    return choice("parameter", "Organism", f"sets Organism to {PF}")


def _organism_basis() -> SearchChoice:
    return choice("organism", PF, f"covers {PF}")


@pytest.mark.asyncio
@pytest.mark.parametrize("why", [_organism_parameter(), _organism_basis()])
async def test_the_organism_is_refused_when_another_value_is_set(
    monkeypatch: pytest.MonkeyPatch, why: SearchChoice
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    refusal = await refused(
        state, why, params={"organism": [PF], "min_exportpred_score": "15"}
    )

    assert refusal == (
        f"c_gpi: {why.term} is the organism the search runs on, and this call "
        f"also sets {SCORE}, which is what decides the choice. Pass the term "
        f"'{SCORE}' with basis parameter, and keep the organism in the reason."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [None, "10"])
async def test_the_organism_decides_when_nothing_else_is_set(
    monkeypatch: pytest.MonkeyPatch, score: str | None
) -> None:
    state = AgentToolState()
    await read(monkeypatch, state, EXPORTED, SIGNAL)

    result = await choose(
        state,
        _organism_parameter(),
        params={"organism": [PF], "min_exportpred_score": score},
    )

    assert result.rationale is not None
    assert (result.rationale.basis, result.rationale.term) == ("parameter", "Organism")
    assert [c.organism_param for c in state.operational_spec_draft.criteria] == [
        "organism"
    ]
