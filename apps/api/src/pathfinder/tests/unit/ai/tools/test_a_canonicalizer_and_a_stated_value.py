"""A value the catalog rewrites is not a departure the write introduced."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.ai.tools.standalone.strategy_edits import (
    update_leaf_params,
)
from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.revision import strategy_revision

from ._spec_contradiction_case import (
    DEPARTED_GENE,
    MIC2,
    PROFILE,
    PROFILE_JOIN,
    RON2,
    ROOT,
    SIGNAL,
    SIMILARITY_JOIN,
    STATED_GENE,
    TM,
    TM_JOIN,
    lowercases_the_gene,
    measured_deps,
    refuses_a_second_look,
)
from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    pin_validator,
)


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


class TestACanonicalizerAndTheStatedValueGuard:
    async def test_a_canonicalizer_that_shifts_an_untouched_value_does_not_refuse(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The catalog rewrites a value the write never sent; the write stands."""
        pin_validator(monkeypatch, lowercases_the_gene)
        deps = measured_deps(mic2_params=STATED_GENE)

        await update_leaf_params(
            ctx(deps), MIC2, {"ProfileNumToReturn": StringValue(value="100")}
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == {
            "ProfileGeneId": StringValue(value="tgme49_201780"),
            "ProfileNumToReturn": StringValue(value="100"),
        }
        assert stub_api.named("update_step_search_config") != []

    async def test_a_departure_the_write_found_survives_the_canonicalizer(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The gene already departed; a patch on another parameter still lands."""
        pin_validator(monkeypatch, lowercases_the_gene)
        deps = measured_deps(mic2_params=DEPARTED_GENE)

        await update_leaf_params(
            ctx(deps), MIC2, {"ProfileNumToReturn": StringValue(value="100")}
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == {
            "ProfileGeneId": StringValue(value="tgme49_300100"),
            "ProfileNumToReturn": StringValue(value="100"),
        }
        assert stub_api.named("update_step_search_config") != []

    async def test_a_patch_that_repeats_a_departed_value_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        """The write leaves the value where it found it, so it departs nothing."""
        deps = measured_deps(mic2_params=DEPARTED_GENE)

        await update_leaf_params(ctx(deps), MIC2, dict(DEPARTED_GENE))

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == DEPARTED_GENE
        assert stub_api.named("update_step_search_config") == []

    async def test_a_patch_that_touches_no_stated_value_asks_the_catalog_once(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second look at an untouched value could refuse a good patch."""
        seen: list[dict[str, ParamValue]] = []
        pin_validator(monkeypatch, refuses_a_second_look(seen))
        deps = measured_deps(mic2_params=STATED_GENE)

        await update_leaf_params(
            ctx(deps), MIC2, {"ProfileNumToReturn": StringValue(value="100")}
        )

        assert len(seen) == 1
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == {
            **STATED_GENE,
            "ProfileNumToReturn": StringValue(value="100"),
        }
        assert stub_api.named("update_step_search_config") != []


def _measured_tree(mic2_params: dict[str, ParamValue]) -> StrategyStepNode:
    """The five-criterion toxodb tree, with the gene the model writes at MIC2."""
    return combine(
        ROOT,
        combine(TM_JOIN, leaf(TM), leaf(SIGNAL), op=CombineOp.UNION),
        combine(
            PROFILE_JOIN,
            leaf(PROFILE),
            combine(
                SIMILARITY_JOIN,
                leaf(MIC2, mic2_params),
                leaf(RON2),
                CombineOp.UNION,
            ),
        ),
    )


class TestABuildOverADepartedValue:
    """The graph holds the catalog's form of a departed value; the model sends its own."""


class TestABatchOverADepartedValue:
    """Every batch reaches the same seam, so a patch batch reads the same forms."""

    async def test_a_batch_that_repeats_a_departed_value_is_applied(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_validator(monkeypatch, lowercases_the_gene)
        deps = measured_deps(
            mic2_params={"ProfileGeneId": StringValue(value="tgme49_300100")}
        )
        graph = deps.strategy_session.graph
        assert graph is not None

        await apply_operations(
            ctx(deps),
            strategy_revision(graph.to_strategy_ast()),
            [UpdateStepParamsOp(step_id=MIC2, parameters=dict(DEPARTED_GENE))],
        )

        assert graph.steps[MIC2].parameters == {
            "ProfileGeneId": StringValue(value="tgme49_300100")
        }
