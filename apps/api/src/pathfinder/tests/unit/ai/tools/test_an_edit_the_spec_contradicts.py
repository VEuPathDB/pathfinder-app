"""An edit that contradicts the operational spec is refused, not pushed.

The tree and the ids are the ones a live toxodb turn wrote, so each case is a
call the execution agent really made.
"""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy_edits import (
    replace_subtree,
    update_combine_operator,
    update_leaf_params,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)

from ._strategy_edit_stubs import StubAPI, combine, ctx, install_stub_api, leaf, seed

_TM = "step_4f51bc4f"
_SIGNAL = "step_044e4c5c"
_PROFILE = "step_4951705a"
_MIC2 = "step_780fd940"
_RON2 = "step_fb1f017c"
_TM_JOIN = "step_79b8b72b"
_SIMILARITY_JOIN = "step_7eca55ff"
_PROFILE_JOIN = "step_811d87da"
_ROOT = "step_95c8dca2"

_WDK_STEP_IDS = {
    _TM: 101,
    _SIGNAL: 102,
    _PROFILE: 103,
    _MIC2: 104,
    _RON2: 105,
    _TM_JOIN: 201,
    _SIMILARITY_JOIN: 202,
    _PROFILE_JOIN: 203,
    _ROOT: 204,
}
_PATTERN = "%bbes:Y%btau:N%chom:Y%hsap:N%tgme:Y%"


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _joined(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _criteria() -> list[Criterion]:
    return [
        Criterion(id=_TM, text="At least one predicted transmembrane domain"),
        Criterion(id=_SIGNAL, text="Predicted signal peptide"),
        Criterion(
            id=_PROFILE,
            text="Ortholog present in Apicomplexa and absent from Mammalia",
            resolved_params={"profile_pattern": StringValue(value=_PATTERN)},
        ),
        Criterion(
            id=_MIC2,
            text="Cell-cycle expression profile similar to MIC2 (TGME49_201780)",
            resolved_params={"ProfileGeneId": StringValue(value="TGME49_201780")},
        ),
        Criterion(
            id=_RON2,
            text="Cell-cycle expression profile similar to RON2 (TGME49_300100)",
            resolved_params={"ProfileGeneId": StringValue(value="TGME49_300100")},
        ),
    ]


def _measured_deps() -> AgentDeps:
    """The strategy the spec built, and the spec that declares its shape."""
    deps = seed(
        combine(
            _ROOT,
            combine(_TM_JOIN, leaf(_TM), leaf(_SIGNAL), op=CombineOp.UNION),
            combine(
                _PROFILE_JOIN,
                leaf(_PROFILE),
                combine(_SIMILARITY_JOIN, leaf(_MIC2), leaf(_RON2), CombineOp.UNION),
            ),
        ),
        wdk_step_ids=dict(_WDK_STEP_IDS),
    )
    draft = deps.agent_state.operational_spec_draft
    draft.criteria = _criteria()
    draft.structure = SpecStructure(
        root=_joined(
            CombineOp.INTERSECT,
            _joined(CombineOp.UNION, _leaf(_TM), _leaf(_SIGNAL)),
            _joined(
                CombineOp.INTERSECT,
                _leaf(_PROFILE),
                _joined(CombineOp.UNION, _leaf(_MIC2), _leaf(_RON2)),
            ),
        ),
    )
    return deps


def _union_of_the_same_three() -> StrategyStepNode:
    """The subtree the recovery pass wrote, keeping the step ids the spec names."""
    return combine(
        _PROFILE_JOIN,
        leaf(_PROFILE),
        combine(_SIMILARITY_JOIN, leaf(_MIC2), leaf(_RON2), CombineOp.UNION),
        op=CombineOp.UNION,
    )


class TestAnEditTheSpecContradictsIsRefused:
    async def test_an_operator_the_spec_does_not_declare_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await update_combine_operator(ctx(deps), _PROFILE_JOIN, CombineOp.UNION)

        assert "set_structure" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_PROFILE_JOIN].operator == CombineOp.INTERSECT
        assert stub_api.calls == []

    async def test_the_same_flip_written_as_a_subtree_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        """Keeping every step id the spec names does not buy a new operator."""
        deps = _measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(ctx(deps), _PROFILE_JOIN, _union_of_the_same_three())

        assert "set_structure" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_PROFILE_JOIN].operator == CombineOp.INTERSECT
        assert stub_api.calls == []

    async def test_a_value_the_criterion_states_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps), _MIC2, {"ProfileGeneId": StringValue(value="TGME49_300100")}
            )

        assert "set_criterion" in str(excinfo.value)
        assert stub_api.calls == []

    async def test_a_value_frame_derived_is_applied_after_a_push_error(
        self, stub_api: StubAPI
    ) -> None:
        """The one recovery the design keeps: fix the parameter WDK refused."""
        deps = _measured_deps()
        sync_state = deps.strategy_session.sync_state
        assert sync_state is not None
        sync_state.wdk_push_errors[_PROFILE] = "422 profile_pattern: Invalid value"

        await update_leaf_params(
            ctx(deps),
            _PROFILE,
            {"profile_pattern": StringValue(value="%hsap:N%tgme:Y%")},
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_PROFILE].parameters["profile_pattern"] == StringValue(
            value="%hsap:N%tgme:Y%"
        )
        assert stub_api.named("update_step_search_config") != []
