from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_requirements import questions_for_the_card
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.operator_reader import read_the_operators
from pathfinder.ai.models.mock.operator_arc import SIGNAL_PEPTIDE, TM_DOMAINS
from pathfinder.ai.models.mock.reading import scripted_intent
from pathfinder.domain.strategy.constraints import ConstraintSource
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests._support.site_organisms import serve_recorded_organisms
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.models._mock_turns import Scene, args_of, names, play

_MESSAGE = f"Find genes with {SIGNAL_PEPTIDE} and {TM_DOMAINS}. [[arc:operator-card]]"
_LISTED = (
    "## Requirements the researcher stated\n"
    f"- R1 (other): {SIGNAL_PEPTIDE}\n"
    f"- R2 (other): {TM_DOMAINS}\n"
)


def test_the_frame_unions_what_the_words_join() -> None:
    calls = play(
        "frame",
        "plasmodb",
        _MESSAGE,
        work_order="Frame work order: mock frame",
        scene=Scene(instructions=_LISTED),
    )

    [structure] = args_of(calls, "set_structure")
    linked = [
        [a["requirement"] for a in call["answers"]]
        for call in args_of(calls, "set_criterion")
        if "answers" in call
    ]
    assert (structure["root"]["operator"], linked) == (
        CombineOp.UNION.value,
        [["R1"], ["R2"]],
    )


async def test_the_words_read_as_an_intersect_and_the_card_asks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_recorded_organisms(monkeypatch)
    state = pipeline_state(
        user_prompt=_MESSAGE,
        user_message_id=uuid4(),
        domain=StrategyDomainState(),
    )
    deps = lead_deps(state)
    await hold_the_intent(deps, scripted_intent(state, _MESSAGE), _MESSAGE)
    first, second = state.domain.requirements
    spec = OperationalSpec(
        criteria=[
            Criterion(
                id=cid,
                text=cid,
                search_name=search,
                record_class="transcript",
                answers=[RequirementLink(requirement=held.id)],
            )
            for cid, search, held in (
                ("signal_peptide", "GenesWithSignalPeptide", first),
                ("tm_domains", "GenesByTransmembraneDomains", second),
            )
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.UNION,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="signal_peptide"),
                    StructureNode(kind="leaf", criterion_id="tm_domains"),
                ],
            )
        ),
    )

    state.domain.operational_spec = await read_the_operators(spec, deps)
    [question] = questions_for_the_card(deps, FrameResult(), [])

    assert (
        [c.source for c in state.domain.requirements],
        [o.label for o in question.options],
    ) == (
        [ConstraintSource.USER_EXPLICIT, ConstraintSource.USER_EXPLICIT],
        [
            f'Keep genes in "{SIGNAL_PEPTIDE}" or "{TM_DOMAINS}"',
            f'Change to genes in both "{SIGNAL_PEPTIDE}" and "{TM_DOMAINS}"',
        ],
    )


def test_the_lead_frames_first() -> None:
    assert names(play("lead", "plasmodb", _MESSAGE))[:1] == ["frame_problem"]
