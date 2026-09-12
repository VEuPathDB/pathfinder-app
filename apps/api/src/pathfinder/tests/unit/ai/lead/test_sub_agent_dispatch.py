"""``build_strategy``: what it refuses, and what it leaves on the spec."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.ledger_render import render_constraints_full
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations.apply import ApplyError
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
)


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="proteases",
        criteria=[
            Criterion(
                id="step_text",
                text="protease text",
                search_name="GenesByText",
                role="seed",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            ),
            Criterion(id="step_go", text="proteolysis GO", search_name="GenesByGoTerm"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(kind="leaf", criterion_id="step_go"),
                ],
            )
        ),
    )


def _spec_with_an_option() -> OperationalSpec:
    """One search criterion, and a criterion that binds an option on it."""
    return OperationalSpec(
        goal="genes upregulated in gametocytes",
        criteria=[
            Criterion(
                id="gametocyte_expression",
                text="upregulated in gametocytes",
                search_name="GenesByRNASeqEvidence",
                resolved_params={
                    "organism": MultiPickValue(values=["Pf3D7"]),
                    "dataset": StringValue(value="all_rnaseq"),
                },
                defaulted_params=["dataset"],
            ),
            Criterion(
                id="gametocyte_timecourse_option",
                text="use the gametocyte timecourse dataset",
                search_name="GenesByRNASeqEvidence",
                resolved_params={
                    "dataset": StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq")
                },
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="gametocyte_expression")
        ),
    )


def _combined_session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Test", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(id="step_text", search_name="GenesByText"),
            secondary_input=StrategyStepNode(id="step_go", search_name="GenesByGoTerm"),
        ),
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _ctx(
    *, with_strategy: bool, prompt: str = "use P. vivax for the GO criterion"
) -> RunContext[LeadDeps]:
    state = pipeline_state(
        user_prompt=prompt,
        domain=StrategyDomainState(operational_spec=_spec()),
    )
    session = (
        _combined_session() if with_strategy else StrategySession(site_id="plasmodb")
    )
    return run_context_for(lead_deps(state, strategy_session=session))


async def test_build_strategy_dispatch_refuses_a_non_empty_strategy() -> None:
    with pytest.raises(ModelRetry) as excinfo:
        await build_strategy(_ctx(with_strategy=True))

    message = str(excinfo.value)
    assert "edit_strategy" in message
    assert "clear_strategy" in message
    # A camelCase name in a retry sends the model round a loop it cannot exit.
    assert "editStrategy" not in message


async def test_build_strategy_still_materializes_an_empty_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    produced: list[str] = []

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        produced.append(kwargs["root"].id)
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)

    result = await build_strategy(_ctx(with_strategy=False))

    assert result.outcome.pushed_step_ids == produced


_BUILD_REFUSAL = "the criterion 'protease text' states organism = 'Pf3D7'"


async def test_a_build_the_spec_refuses_reaches_the_agent_as_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The spec guard answers the BUILD seam, not an unhandled domain error."""

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        del kwargs
        raise ApplyError(_BUILD_REFUSAL)

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)

    with pytest.raises(ModelRetry) as excinfo:
        await build_strategy(_ctx(with_strategy=False))

    message = str(excinfo.value)
    assert message.startswith("REJECTED: ")
    assert "protease text" in message
    assert "Nothing was built and the strategy is unchanged." in message


async def test_the_built_spec_is_re_keyed_on_the_step_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FRAME names a criterion with a label; the spec adopts the minted id."""
    produced: dict[str, str] = {}

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        root = kwargs["root"]
        produced["root"] = root.id
        produced["primary"] = root.primary_input.id
        produced["secondary"] = root.secondary_input.id
        return BuildOutcome(pushed_step_ids=[root.id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    ctx = _ctx(with_strategy=False, prompt="build it")

    await build_strategy(ctx)

    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    assert {c.id for c in spec.criteria} == {produced["primary"], produced["secondary"]}
    assert spec.structure is not None
    assert [node.criterion_id for node in spec.structure.root.inputs] == [
        produced["primary"],
        produced["secondary"],
    ]
    seed = next(c for c in spec.criteria if c.search_name == "GenesByText")
    assert seed.resolved_params == {"organism": MultiPickValue(values=["Plasmodium"])}


async def test_the_build_pushes_the_option_a_criterion_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A criterion the structure leaves out binds a parameter of the step."""
    pushed: dict[str, ParamValue] = {}

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        root = kwargs["root"]
        pushed.update(root.parameters)
        return BuildOutcome(pushed_step_ids=[root.id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    ctx = _ctx(with_strategy=False, prompt="use the gametocyte timecourse")
    ctx.deps.state.domain.operational_spec = _spec_with_an_option()

    await build_strategy(ctx)

    assert pushed == {
        "organism": MultiPickValue(values=["Pf3D7"]),
        "dataset": StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq"),
    }
    spec = ctx.deps.state.domain.operational_spec
    assert spec is not None
    (carrier,) = spec.criteria
    assert carrier.text == "upregulated in gametocytes"
    assert [a.reason for a in carrier.assumptions] == [
        "use the gametocyte timecourse dataset"
    ]


def _unconvertible() -> OperationalSpec:
    # Two inputs and no operator: bound, structured, and not a tree.
    return OperationalSpec(
        goal="drug targets",
        criteria=[
            Criterion(id=n, text=n, role="filter", search_name=f"By{n}")
            for n in ("a", "b")
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                inputs=[
                    StructureNode(kind="leaf", criterion_id="a"),
                    StructureNode(kind="leaf", criterion_id="b"),
                ],
            )
        ),
    )


def _mock_ctx(spec: OperationalSpec) -> Any:
    ctx = MagicMock()
    ctx.deps.state.domain.operational_spec = spec
    ctx.deps.runtime.user_id = uuid4()
    # A build only runs where there is no strategy; an existing one is an edit.
    ctx.deps.runtime.strategy_session.get_graph.return_value = None
    return ctx


class TestTheTurnSurvives:
    async def test_it_raises_model_retry(self) -> None:
        spec = _unconvertible()
        assert spec.ready_to_build

        with pytest.raises(ModelRetry):
            await build_strategy(_mock_ctx(spec))

    async def test_the_message_names_the_problem(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await build_strategy(_mock_ctx(_unconvertible()))

        assert "combine" in str(err.value)

    async def test_the_message_says_the_structure_is_at_fault(self) -> None:
        with pytest.raises(ModelRetry) as err:
            await build_strategy(_mock_ctx(_unconvertible()))

        assert "structure" in str(err.value).lower()


def _option_criterion(search_name: str = "GenesByRNASeqEvidence") -> Criterion:
    return Criterion(
        id="gametocyte_timecourse_option",
        text="use the gametocyte timecourse dataset",
        search_name=search_name,
        resolved_params={
            "dataset": StringValue(value="pfal3D7_Gametocyte_Timecourse_rnaSeq")
        },
    )


def _spec_two_criteria_could_carry() -> OperationalSpec:
    """Two steps run the search, so which one the option qualifies is unknown."""
    spec = _spec_with_an_option()
    spec.criteria.append(
        Criterion(
            id="asexual_expression",
            text="a second read",
            search_name="GenesByRNASeqEvidence",
        )
    )
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(kind="leaf", criterion_id="gametocyte_expression"),
                StructureNode(kind="leaf", criterion_id="asexual_expression"),
            ],
        )
    )
    return spec


def _spec_no_criterion_carries() -> OperationalSpec:
    """The option names a search no criterion in the structure runs."""
    spec = _spec_with_an_option()
    spec.criteria[1] = _option_criterion("GenesByTaxon")
    return spec


def _option_ctx(spec: OperationalSpec) -> RunContext[LeadDeps]:
    ctx = _ctx(with_strategy=False, prompt="use the gametocyte timecourse")
    ctx.deps.state.domain.operational_spec = spec
    return ctx


class TestAnOptionTwoCriteriaCouldCarry:
    """The build refuses rather than dropping the value the option states."""

    async def test_the_message_names_the_option(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(_option_ctx(_spec_two_criteria_could_carry()))

        assert "gametocyte_timecourse_option" in str(excinfo.value)

    async def test_the_message_names_both_criteria_that_run_the_search(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(_option_ctx(_spec_two_criteria_could_carry()))

        message = str(excinfo.value)
        assert "gametocyte_expression" in message
        assert "asexual_expression" in message


class TestAnOptionNoCriterionCarries:
    async def test_it_refuses_the_build(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(_option_ctx(_spec_no_criterion_carries()))

        assert "gametocyte_timecourse_option" in str(excinfo.value)

    async def test_the_message_names_the_search_nothing_runs(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(_option_ctx(_spec_no_criterion_carries()))

        assert "GenesByTaxon" in str(excinfo.value)


async def test_the_ledger_still_shows_the_option_the_build_folded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The carrier's step name loses the option, and the constraints keep it."""

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    ctx = _option_ctx(_spec_with_an_option())

    await build_strategy(ctx)

    rendered = render_constraints_full(derive_ledger(ctx.deps.state, None).constraints)
    assert "use the gametocyte timecourse dataset" in rendered


_SEXUAL_STAGE = "pfal3D7_Sexual_Stage_rnaSeq"
_TIMECOURSE = "pfal3D7_Gametocyte_Timecourse_rnaSeq"


def _spec_with_two_options(dataset: str) -> OperationalSpec:
    """Both options name the one criterion the structure states."""
    spec = _spec_with_an_option()
    spec.criteria.append(
        Criterion(
            id="sexual_stage_option",
            text="use the sexual stage dataset",
            search_name="GenesByRNASeqEvidence",
            resolved_params={"dataset": StringValue(value=dataset)},
        )
    )
    return spec


class TestTwoOptionsOnOneCarrier:
    """One parameter stated twice: once is idempotent, twice over is refused."""

    async def test_the_same_value_twice_reaches_the_step(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pushed: dict[str, ParamValue] = {}

        async def _fake_build(**kwargs: Any) -> BuildOutcome:
            pushed.update(kwargs["root"].parameters)
            return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

        monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)

        await build_strategy(_option_ctx(_spec_with_two_options(_TIMECOURSE)))

        assert pushed == {
            "organism": MultiPickValue(values=["Pf3D7"]),
            "dataset": StringValue(value=_TIMECOURSE),
        }

    async def test_a_second_value_names_the_parameter(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(_option_ctx(_spec_with_two_options(_SEXUAL_STAGE)))

        message = str(excinfo.value)
        assert "sexual_stage_option" in message
        assert "dataset" in message

    async def test_a_second_value_names_both_values(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(_option_ctx(_spec_with_two_options(_SEXUAL_STAGE)))

        message = str(excinfo.value)
        assert _SEXUAL_STAGE in message
        assert _TIMECOURSE in message


def _spec_with_an_assumed_dataset() -> OperationalSpec:
    """The carrier's dataset is the model's guess, not a value its text states."""
    spec = _spec_with_an_option()
    spec.criteria[0].defaulted_params = []
    spec.criteria[0].assumptions = [
        AssumedValue(
            param_name="dataset",
            value="all_rnaseq",
            reason="the request names no dataset",
        )
    ]
    return spec


class TestAnOptionOverAnAssumedValue:
    """A value FRAME chose is the model's, so the option the user states wins."""

    async def test_the_build_pushes_the_option(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pushed: dict[str, ParamValue] = {}

        async def _fake_build(**kwargs: Any) -> BuildOutcome:
            pushed.update(kwargs["root"].parameters)
            return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

        monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)

        await build_strategy(_option_ctx(_spec_with_an_assumed_dataset()))

        assert pushed == {
            "organism": MultiPickValue(values=["Pf3D7"]),
            "dataset": StringValue(value=_TIMECOURSE),
        }

    async def test_the_ledger_shows_the_option_and_not_the_guess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _fake_build(**kwargs: Any) -> BuildOutcome:
            return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

        monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
        ctx = _option_ctx(_spec_with_an_assumed_dataset())

        await build_strategy(ctx)

        rendered = render_constraints_full(
            derive_ledger(ctx.deps.state, None).constraints
        )
        assert "use the gametocyte timecourse dataset" in rendered
        assert "the request names no dataset" not in rendered
