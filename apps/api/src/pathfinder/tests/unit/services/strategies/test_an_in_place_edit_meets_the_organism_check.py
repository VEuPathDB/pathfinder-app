"""An edit that keeps the tree's shape is checked for an INTERSECT of two
organisms before any step is pushed, like an edit that re-roots the strategy."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import build_wdk_step_tree
from veupathdb_mcp.catalog import COMPUTE_QUERY, EDA_DATASET_ID_PARAM

from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.commit import apply_and_commit
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support import organism_reads
from pathfinder.tests._support.organism_reads import GT1, ME49, ME49_STUDY
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import (
    StubAPI,
    combine,
    install_stub_api,
    session_with,
)

_DOMAIN = "GenesByInterproDomain"
_ACCESSION = "domain_accession"
_WDK_IDS = {"domain": 441344653, "study": 441344663, "both": 441344683}
_REFUSAL = (
    f"Cannot INTERSECT steps with different organism scopes ({GT1} vs {ME49}). "
    f"Gene IDs from different organisms never match, so this always returns 0 "
    f"results. The {COMPUTE_QUERY} search runs on an experiment of {ME49}, and "
    f"no parameter changes that organism. Map that side to {GT1} with a "
    f"GenesByOrthologs transform."
)


def _domain_params(organism: str, accession: str) -> dict[str, ParamValue]:
    return {
        "organism": MultiPickValue(values=[organism]),
        _ACCESSION: StringValue(value=accession),
    }


def _session() -> StrategySession:
    domain = StrategyStepNode(
        id="domain", search_name=_DOMAIN, parameters=_domain_params(ME49, "PF00069")
    )
    study = StrategyStepNode(
        id="study",
        search_name=COMPUTE_QUERY,
        parameters={EDA_DATASET_ID_PARAM: StringValue(value=ME49_STUDY)},
    )
    root = combine("both", domain, study)
    session = session_with(root, _WDK_IDS)
    ensure_sync_state(session).wdk_step_tree = build_wdk_step_tree(root, _WDK_IDS)
    return session


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    monkeypatch.setitem(organism_reads.MARKS, _DOMAIN, "organism")
    return install_stub_api(monkeypatch)


async def _rebind(session: StrategySession, organism: str, accession: str) -> None:
    await apply_and_commit(
        deps=StrategyMutationContext(site_id="toxodb", strategy_session=session),
        op=UpdateStepParamsOp(
            step_id="domain", parameters=_domain_params(organism, accession)
        ),
    )


def _config_writes(api: StubAPI) -> list[int]:
    """The WDK step each search config write went to."""
    return [
        call.kwargs["step_id"]
        for call in api.calls
        if call.name == "update_step_search_config"
    ]


async def test_another_strain_beside_the_study_is_refused_and_nothing_is_pushed(
    api: StubAPI,
) -> None:
    session = _session()

    with pytest.raises(ApplyError) as excinfo:
        await _rebind(session, GT1, "PF00069")

    graph = session.get_graph(None)
    assert graph is not None
    assert (
        str(excinfo.value),
        api.calls,
        graph.steps["domain"].parameters,
    ) == (_REFUSAL, [], _domain_params(ME49, "PF00069"))


async def test_an_edit_on_the_studys_own_strain_is_pushed(api: StubAPI) -> None:
    session = _session()

    await _rebind(session, ME49, "PF00433")

    graph = session.get_graph(None)
    assert graph is not None
    assert (_config_writes(api), graph.steps["domain"].parameters) == (
        [_WDK_IDS["domain"]],
        _domain_params(ME49, "PF00433"),
    )
