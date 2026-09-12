"""An edit that contradicts the operational spec is refused, not pushed."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.tools.standalone.strategy import build_strategy
from pathfinder.ai.tools.standalone.strategy_edits import (
    replace_subtree,
    update_combine_operator,
    update_leaf_params,
)
from pathfinder.domain.strategy.revision import strategy_revision

from ._spec_contradiction_case import (
    MIC2,
    PROFILE,
    PROFILE_JOIN,
    RON2,
    ROOT,
    SIGNAL,
    SIMILARITY_JOIN,
    TM,
    TM_JOIN,
    measured_deps,
    union_of_the_same_three,
)
from ._strategy_edit_stubs import StubAPI, combine, ctx, install_stub_api, leaf


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

    async def test_a_value_the_criterion_states_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps), MIC2, {"ProfileGeneId": StringValue(value="TGME49_300100")}
            )

        assert "set_criterion" in str(excinfo.value)
        assert stub_api.calls == []

    async def test_the_same_value_written_as_a_subtree_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        """A rewritten leaf carries its parameters, and the spec reads them."""
        deps = measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(
                ctx(deps),
                MIC2,
                leaf(MIC2, {"ProfileGeneId": StringValue(value="TGME49_300100")}),
            )

        assert "set_criterion" in str(excinfo.value)
        assert "TGME49_201780" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == {}
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

    async def test_the_same_value_written_by_a_build_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        """A whole-tree build carries its leaves' values, and the spec reads them."""
        deps = measured_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        revision = strategy_revision(graph.to_strategy_ast())

        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(
                ctx(deps),
                combine(
                    ROOT,
                    combine(TM_JOIN, leaf(TM), leaf(SIGNAL), op=CombineOp.UNION),
                    combine(
                        PROFILE_JOIN,
                        leaf(PROFILE),
                        combine(
                            SIMILARITY_JOIN,
                            leaf(
                                MIC2,
                                {"ProfileGeneId": StringValue(value="TGME49_300100")},
                            ),
                            leaf(RON2),
                            CombineOp.UNION,
                        ),
                    ),
                ),
                base_revision=revision,
            )

        assert "set_criterion" in str(excinfo.value)
        assert "TGME49_201780" in str(excinfo.value)
        assert graph.steps[MIC2].parameters == {}
        assert stub_api.calls == []

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
