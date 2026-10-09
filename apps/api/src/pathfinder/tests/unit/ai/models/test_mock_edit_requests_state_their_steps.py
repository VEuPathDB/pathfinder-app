"""Each step a scripted edit adds is stated by the request that asks for it, so
an edit over a held strategy keeps it."""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import run_frame
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_stream import SubAgentApprovalWait
from pathfinder.ai.models.mock.growths import (
    Growth,
    added_growth,
    orthologs_growth,
    round_trip_growth,
)
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import intersect_spec
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_SITES = ("plasmodb", "vectorbase")
_REQUESTS = {
    "orthologs": "Carry these to their orthologs in the related species.",
    "syntenic": "Carry these to their syntenic orthologs in the related genus.",
    "round-trip": "Keep only those with syntenic orthologs in the related species.",
}
_ADDED = {
    "plasmodb": {
        "add-step": "Also keep only those predicted to be exported to the host cell.",
        "replace-subtree": (
            "Replace the transmembrane-domain search with the exported-protein "
            "prediction."
        ),
    },
    "trichdb": {
        "add-step": "Also keep only Trichomonas vaginalis G3 genes.",
        "replace-subtree": (
            "Replace the transmembrane-domain search with all Trichomonas "
            "vaginalis G3 genes."
        ),
    },
    "vectorbase": {
        "add-step": "Also keep only those with a molecular weight from 0 to 60000.",
        "replace-subtree": (
            "Replace the transmembrane-domain search with a molecular weight search."
        ),
    },
}


def _growth(arc: str, values: SiteValues) -> Growth:
    held = {c.search_name for c in intersect_spec(values).criteria}
    growths = {
        "orthologs": lambda: orthologs_growth(values, syntenic="no"),
        "syntenic": lambda: orthologs_growth(values, syntenic="yes"),
        "round-trip": lambda: round_trip_growth(values),
        "add-step": lambda: added_growth(values, held),
        "replace-subtree": lambda: added_growth(values, held),
    }
    return growths[arc]()


async def _grown(
    monkeypatch: pytest.MonkeyPatch, site_id: str, arc: str
) -> tuple[FrameResult | SubAgentApprovalWait, FrameResult]:
    values = SiteValues.for_site(site_id)
    said = {**_REQUESTS, **_ADDED[site_id]}[arc]
    request = f"{said} [[arc:{arc}]]"
    added = [
        Criterion(id=c.criterion_id, text=c.text, search_name=c.search_name)
        for c in _growth(arc, values).criteria
    ]
    delta = FrameResult(disposition="spec_ready", summary="grew the strategy")

    async def _framed(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft.criteria.extend(added)
        return delta

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _framed)
    deps = lead_deps(
        pipeline_state(site_id, user_prompt=request),
        intent=UserIntent(
            classification=IntentClassification.EDIT_STRATEGY,
            inferred_goal="[mock] edit_strategy",
        ),
        strategy_session=session_with_one_step(site_id),
    )
    deps.state.domain.operational_spec = OperationalSpec(
        goal="secreted membrane genes",
        criteria=[
            Criterion(id=c.criterion_id, text=c.text, search_name=c.search_name)
            for c in intersect_spec(values).criteria
        ],
    )

    result = await run_frame(deps=deps, parent_tool_call_id="t1", work_order="edit")
    return result, delta


@pytest.mark.parametrize("site_id", _SITES)
@pytest.mark.parametrize("arc", [*sorted(_REQUESTS), "add-step", "replace-subtree"])
async def test_the_added_step_is_stated_by_its_request(
    monkeypatch: pytest.MonkeyPatch, site_id: str, arc: str
) -> None:
    result, delta = await _grown(monkeypatch, site_id, arc)

    assert isinstance(result, FrameResult)
    assert (result.disposition, result.summary) == (delta.disposition, delta.summary)


@pytest.mark.parametrize("arc", ["add-step", "replace-subtree"])
async def test_the_organism_a_site_adds_is_stated_by_its_request(
    monkeypatch: pytest.MonkeyPatch, arc: str
) -> None:
    result, delta = await _grown(monkeypatch, "trichdb", arc)

    assert isinstance(result, FrameResult)
    assert (result.disposition, result.summary) == (delta.disposition, delta.summary)
