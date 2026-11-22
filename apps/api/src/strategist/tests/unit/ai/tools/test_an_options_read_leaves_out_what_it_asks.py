from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, ParamValue, SinglePickValue
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import ParameterInfo, ResolveContext

from strategist.ai.tools.standalone import catalog_discovery
from strategist.ai.tools.standalone._stated_values import typed_values
from strategist.domain.strategy.operational_spec import Criterion
from strategist.tests._support.bound_values import bound
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools.conftest import (
    agent_run_context,
    patch_search_details,
    wdk_param,
)

_PARAM: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
_SEARCH = "GenesByMicroarrayDerisi"
_SAMPLES = "samples_percentile_generic"
_SIBLING = "samples_fold_change"
_PROFILES = "profileset_generic"
_HELD: dict[str, ParamValue] = {
    _PROFILES: SinglePickValue(value="DeRisi 3D7 Smoothed"),
    _SAMPLES: MultiPickValue(values=["Schizont"]),
    _SIBLING: MultiPickValue(values=["Schizont"]),
}
_STALE = (
    'profileset_generic moved from "DeRisi 3D7 Smoothed" to "DeRisi Dd2 Smoothed", '
    'so samples_fold_change, which held ["Schizont"], was read again under it and '
    "refused: "
)
_ASK = (
    "State samples_fold_change again under the new profileset_generic, or leave it "
    "out if a reader can keep it."
)


def _samples(name: str) -> WDKParameter:
    return _PARAM.validate_python(
        {
            "name": name,
            "type": "multi-pick-vocabulary",
            "vocabulary": [["Ring", "Ring", None]],
        }
    )


def _serve(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    client = patch_search_details(
        monkeypatch,
        parameters=[
            wdk_param(_PROFILES, dependent_params=[_SAMPLES, _SIBLING]),
            _samples(_SAMPLES),
            _samples(_SIBLING),
        ],
    )
    return client.contexts


async def test_an_options_read_under_a_new_parent_notes_a_stale_sibling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts = _serve(monkeypatch)
    ctx = agent_run_context()
    ctx.deps.agent_state.frame_set_criterion(
        Criterion(
            id="timecourse",
            text="trophozoite expression",
            search_name=_SEARCH,
            resolved_params=bound(_HELD),
        )
    )

    info = returned(
        await catalog_discovery.get_parameter_options(
            ctx,
            search_name=_SEARCH,
            parameter_id=_SAMPLES,
            context_values={_PROFILES: "DeRisi Dd2 Smoothed"},
        ),
        ParameterInfo,
    )

    assert contexts[-1] == {_PROFILES: "DeRisi Dd2 Smoothed"}
    assert [option.value for option in info.allowed_values or []] == ["Ring"]
    assert info.note is not None
    assert _STALE in info.note
    assert f"so {_SAMPLES}, which held" not in info.note
    assert info.note.endswith(_ASK)


async def test_a_write_under_the_new_parent_refuses_the_stale_sibling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    with pytest.raises(ModelRetry) as refused:
        await typed_values(
            ResolveContext(site_id="plasmodb"),
            _SEARCH,
            {_PROFILES: "DeRisi Dd2 Smoothed", _SAMPLES: ["Ring"]},
            bound=_HELD,
        )

    assert refused.value.message.startswith(f"{_SEARCH}: {_STALE}")
    assert refused.value.message.endswith(f"{_ASK} Nothing was written.")


async def test_an_options_read_refuses_a_context_value_it_states_wrongly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    ctx = agent_run_context()
    ctx.deps.agent_state.frame_set_criterion(
        Criterion(
            id="timecourse",
            text="trophozoite expression",
            search_name=_SEARCH,
            resolved_params=bound(_HELD),
        )
    )

    with pytest.raises(ModelRetry) as refused:
        await catalog_discovery.get_parameter_options(
            ctx,
            search_name=_SEARCH,
            parameter_id=_SAMPLES,
            context_values={
                _PROFILES: "DeRisi Dd2 Smoothed",
                _SIBLING: ["Gametocyte"],
            },
        )

    assert refused.value.message == (
        f"{_SEARCH}: {_SIBLING} has no entry 'Gametocyte'. Candidates: Ring. "
        "Nothing was read."
    )
