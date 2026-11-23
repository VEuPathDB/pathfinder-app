"""GenesWithAlphafold's organism parameter carries no reference mark, and the site's
organism list names it, so FRAME holds its bind to the organism the request names."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb_mcp.catalog import (
    ParameterInfo,
    format_param_info_typed,
    organism_parameter_of,
    organisms,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._frame_stated import word_problems
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    OrganismValue,
)
from strategist.platform.refusals import refuse_problems
from strategist.tests._support.recorded_searches import suite_search
from strategist.tests._support.site_organisms import recorded_organisms

_ALPHAFOLD = suite_search("search_genes_with_alphafold")
_PARAM = "organismsWithAlphafold"
_PF3D7 = "Plasmodium falciparum 3D7"
_IT = "Plasmodium falciparum IT"


@pytest.fixture(autouse=True)
def _site_organisms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _listed(site_id: str) -> list[str]:
        return recorded_organisms(site_id)

    monkeypatch.setattr(organisms, "list_organisms", _listed)


async def _sheet() -> list[ParameterInfo]:
    declarations = _ALPHAFOLD.parameters or []
    return format_param_info_typed(
        declarations, organism=await organism_parameter_of("plasmodb", declarations)
    )


async def _refusal(named: str, bound: str) -> str | None:
    call = CriterionCall(
        criterion_id="c_alphafold",
        search_name=_ALPHAFOLD.url_segment,
        text="genes with an AlphaFold structure",
        params={},
    ).with_values({_PARAM: MultiPickValue(values=[bound])})
    requirement = Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value=named,
        label="organism",
        value=OrganismValue(organism=named),
    )
    try:
        refuse_problems(
            word_problems(
                _ALPHAFOLD,
                call,
                await _sheet(),
                AgentToolState(stated_requirements=[requirement]),
            )
        )
    except ModelRetry as refused:
        return refused.message
    return None


async def test_the_sheet_names_the_alphafold_organism_parameter() -> None:
    assert [info.name for info in await _sheet() if info.organism_param] == [_PARAM]


async def test_only_a_strain_beside_the_named_one_is_refused() -> None:
    refusals = {bound: await _refusal(_PF3D7, bound) for bound in (_PF3D7, _IT)}

    assert refusals == {
        _PF3D7: None,
        _IT: (
            f"Organism on {_ALPHAFOLD.url_segment} binds ['{_IT}'], and the request "
            f"names '{_PF3D7}', an entry of this vocabulary. Bind the entry the "
            "request names, or ask the researcher which one they mean."
        ),
    }
