"""An edit that contradicts the operational spec is refused, not pushed."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy_edits import (
    replace_subtree,
    update_combine_operator,
    update_leaf_params,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.tests._support.bound_values import bound

from ._spec_contradiction_case import (
    MIC2,
    PROFILE,
    PROFILE_JOIN,
    measured_deps,
    union_of_the_same_three,
)
from ._strategy_edit_stubs import StubAPI, ctx, install_stub_api, leaf


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


class TestAnEditTheSpecContradictsIsRefused:
    async def test_an_operator_the_spec_does_not_declare_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await update_combine_operator(ctx(deps), PROFILE_JOIN, CombineOp.UNION)

        assert "set_structure" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[PROFILE_JOIN].operator == CombineOp.INTERSECT
        assert stub_api.calls == []

    async def test_the_same_flip_written_as_a_subtree_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        """Keeping every step id the spec names does not buy a new operator."""
        deps = measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(ctx(deps), PROFILE_JOIN, union_of_the_same_three())

        assert "set_structure" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[PROFILE_JOIN].operator == CombineOp.INTERSECT
        assert stub_api.calls == []

    async def test_a_subtree_that_repeats_the_stated_value_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = measured_deps()

        await replace_subtree(
            ctx(deps),
            MIC2,
            leaf(MIC2, {"ProfileGeneId": StringValue(value="TGME49_201780")}),
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == {
            "ProfileGeneId": StringValue(value="TGME49_201780")
        }
        assert stub_api.named("update_step_search_config") != []

    async def test_a_value_frame_derived_is_applied_after_a_push_error(
        self, stub_api: StubAPI
    ) -> None:
        """The one recovery the design keeps: fix the parameter WDK refused."""
        deps = measured_deps()
        sync_state = deps.strategy_session.sync_state
        assert sync_state is not None
        sync_state.wdk_push_errors[PROFILE] = "422 profile_pattern: Invalid value"

        await update_leaf_params(
            ctx(deps),
            PROFILE,
            {"profile_pattern": StringValue(value="%hsap:N%tgme:Y%")},
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[PROFILE].parameters["profile_pattern"] == StringValue(
            value="%hsap:N%tgme:Y%"
        )
        assert stub_api.named("update_step_search_config") != []


def _grounded_percentile(deps: AgentDeps) -> None:
    draft = deps.agent_state.operational_spec_draft
    draft.criteria = [
        c.model_copy(
            update={
                "search_name": "GenesByRNASeqEvidence",
                "resolved_params": bound(
                    {"min_expression_percentile": NumberValue(value=90)}
                ),
            }
        )
        if c.id == MIC2
        else c
        for c in draft.criteria
    ]
    draft.constraints = [
        Constraint(
            kind=ConstraintKind.PERCENTILE,
            requested_value="top 10%",
            label="expression percentile",
            source=ConstraintSource.USER_EXPLICIT,
        )
    ]


async def test_a_value_a_stated_requirement_grounds_onto_is_refused(
    stub_api: StubAPI,
) -> None:
    deps = measured_deps()
    _grounded_percentile(deps)

    with pytest.raises(ModelRetry) as excinfo:
        await update_leaf_params(
            ctx(deps), MIC2, {"min_expression_percentile": NumberValue(value=80)}
        )

    assert "set_criterion" in str(excinfo.value)
    assert "'90'" in str(excinfo.value)
    assert stub_api.calls == []
