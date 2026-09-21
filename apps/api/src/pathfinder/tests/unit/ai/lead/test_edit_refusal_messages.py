"""What an edit says when VEuPathDB refuses the values the edit itself writes."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, flatten_tree
from veupathdb.errors import ValidationError, param_message_rows

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_TEXT = "GenesByText"
_DOMAIN = "GenesByInterproDomain"
_NO_SUCH_STEP = "the tree states a step the strategy does not hold"
_NO_COMMIT = "the commit must not run"
_WDK_SAID = (
    "domain_accession: Cannot be empty.; organism: Cannot be empty.; "
    "domain_typeahead: At least one parameter that 'domain_typeahead' "
    "depends on is invalid or missing"
)


def _on_screen() -> tuple[OperationalSpec, StrategySession]:
    """The strategy the researcher already has: one text search."""
    spec = OperationalSpec(
        goal="odorant binding proteins",
        criteria=[
            Criterion(
                id="obp_text",
                text="odorant binding protein",
                search_name=_TEXT,
                role="seed",
                resolved_params={
                    "text_search_organism": MultiPickValue(values=["Anopheles"])
                },
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="obp_text")
        ),
    )
    tree = build_step_tree(spec)
    session = StrategySession(site_id="vectorbase")
    graph = StrategyGraph(graph_id="g1", name="obp", site_id="vectorbase")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    return renumber_criteria(spec, tree.step_id_by_criterion), session


def _with_the_domain_leaf(before: OperationalSpec) -> OperationalSpec:
    """The edit the Lead asked for: intersect the text search with a domain."""
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(
            id="step_domain",
            text="InterPro odorant binding domain",
            search_name=_DOMAIN,
            resolved_params={
                "organism": MultiPickValue(values=["Anopheles gambiae PEST"]),
                "domain_database": StringValue(value="Pfam"),
                "domain_accession": StringValue(value="N/A"),
                "domain_typeahead": MultiPickValue(values=["PF03392"]),
            },
        )
    )
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(kind="leaf", criterion_id=before.criteria[0].id),
                StructureNode(kind="leaf", criterion_id="step_domain"),
            ],
        )
    )
    return after


class Refused:
    """One edit whose commit was refused, and the message the Lead read."""

    def __init__(self, message: str, stored: OperationalSpec | None) -> None:
        self.message = message
        self.stored = stored


async def _run_the_refused_edit(
    monkeypatch: pytest.MonkeyPatch, commit: Any, ops: Any = None
) -> Refused:
    before, session = _on_screen()
    after = _with_the_domain_leaf(before)
    state = pipeline_state(
        site_id="vectorbase",
        user_prompt="add the InterPro odorant binding domain",
        domain=StrategyDomainState(operational_spec=before.model_copy(deep=True)),
    )
    state.domain.spec_before_turn = before
    deps = lead_deps(state, strategy_session=session)

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = after
        return FrameResult(disposition="spec_ready", summary="reframed")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
    if ops is not None:
        monkeypatch.setattr(edit_dispatch, "operations_for", ops)

    with pytest.raises(ModelRetry) as excinfo:
        await run_edit(deps=deps, parent_tool_call_id="t1", reason="add the domain")
    return Refused(str(excinfo.value), deps.state.domain.operational_spec)


async def _wdk_refuses_the_new_step(**_kwargs: Any) -> CommitResult:
    raise ValidationError(
        title="Invalid parameter value",
        detail=_WDK_SAID,
        errors=param_message_rows(
            {
                "domain_accession": ["Cannot be empty."],
                "organism": ["Cannot be empty."],
            }
        ),
    )


@pytest.fixture
async def refused(monkeypatch: pytest.MonkeyPatch) -> Refused:
    return await _run_the_refused_edit(monkeypatch, _wdk_refuses_the_new_step)


def test_the_refusal_names_the_search_of_the_step_wdk_turned_down(
    refused: Refused,
) -> None:
    """The step the edit adds is the one named, not the strategy as a whole."""
    assert _DOMAIN in refused.message
    assert "step_domain" in refused.message


def test_the_refusal_names_the_parameters_and_quotes_wdk(refused: Refused) -> None:
    assert "organism" in refused.message
    assert "domain_accession" in refused.message
    assert _WDK_SAID in refused.message


def test_the_refusal_says_the_strategy_is_unchanged(refused: Refused) -> None:
    assert "Nothing was applied" in refused.message
    assert refused.stored is not None
    assert [c.search_name for c in refused.stored.criteria] == [_TEXT]


def test_the_refusal_blames_neither_the_existing_steps_nor_the_shape(
    refused: Refused,
) -> None:
    """A parameter WDK turned down is not an edit that maps onto no step."""
    assert "does not map" not in refused.message
    assert "replac" not in refused.message.lower()
    assert "existing steps" not in refused.message.lower()


async def test_a_step_the_push_lost_names_itself_and_spares_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial push reports the refused step without blaming the others."""

    async def _partly_refused(**_kwargs: Any) -> CommitResult:
        return CommitResult(
            description="added the domain step",
            failures=[
                StepPushFailure(
                    step_id="step_domain",
                    search_name=_DOMAIN,
                    error="organism: Cannot be empty.",
                    wdk_status=422,
                )
            ],
        )

    refused = await _run_the_refused_edit(monkeypatch, _partly_refused)

    assert _DOMAIN in refused.message
    assert "every other step" in refused.message
    assert "replac" not in refused.message.lower()


async def test_a_shape_the_strategy_cannot_take_keeps_the_mapping_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An edit that maps onto no step still reads as a shape problem."""

    def _unsupported(*_args: Any, **_kwargs: Any) -> Any:
        raise UnsupportedEditError(_NO_SUCH_STEP)

    async def _never(**_kwargs: Any) -> CommitResult:
        raise AssertionError(_NO_COMMIT)

    refused = await _run_the_refused_edit(monkeypatch, _never, ops=_unsupported)

    assert "does not map onto the strategy's steps" in refused.message
