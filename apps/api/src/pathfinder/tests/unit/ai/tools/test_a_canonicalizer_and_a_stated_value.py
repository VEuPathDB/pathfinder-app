"""A value the catalog rewrites is not a departure the write introduced."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import ParamValue, StringValue

from pathfinder.ai.tools.standalone.strategy_edits import (
    replace_subtree,
    update_leaf_params,
)

from ._spec_contradiction_case import (
    DEPARTED_GENE,
    MIC2,
    STATED_GENE,
    cascades_from_the_size,
    lowercases_the_gene,
    measured_deps,
    records_the_call,
    refuses_a_second_look,
)
from ._strategy_edit_stubs import StubAPI, ctx, install_stub_api, leaf, pin_validator


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

    async def test_the_same_canonicalizer_still_refuses_a_real_change(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_validator(monkeypatch, lowercases_the_gene)
        deps = measured_deps(mic2_params=STATED_GENE)

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps), MIC2, {"ProfileGeneId": StringValue(value="TGME49_300100")}
            )

        assert "set_criterion" in str(excinfo.value)
        assert "tgme49_201780" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == STATED_GENE
        assert stub_api.calls == []

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

    async def test_a_departed_value_the_write_moves_again_is_refused(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The write names the parameter, so it answers for the value it sends."""
        pin_validator(monkeypatch, lowercases_the_gene)
        deps = measured_deps(mic2_params=DEPARTED_GENE)

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps), MIC2, {"ProfileGeneId": StringValue(value="TGME49_209060")}
            )

        assert "set_criterion" in str(excinfo.value)
        assert "tgme49_201780" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == DEPARTED_GENE
        assert stub_api.calls == []

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

    async def test_a_dependent_value_the_patch_moves_is_refused(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A parameter the patch sends moves a stated value the criterion holds."""
        pin_validator(monkeypatch, cascades_from_the_size)
        deps = measured_deps(mic2_params=STATED_GENE)

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps), MIC2, {"ProfileNumToReturn": StringValue(value="100")}
            )

        assert "set_criterion" in str(excinfo.value)
        assert "TGME49_300100" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == STATED_GENE
        assert stub_api.calls == []

    async def test_a_subtree_that_repeats_a_departed_value_is_applied(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The graph holds the catalog's form of the value; the model sends its own."""
        pin_validator(monkeypatch, lowercases_the_gene)
        deps = measured_deps(
            mic2_params={"ProfileGeneId": StringValue(value="tgme49_300100")}
        )

        await replace_subtree(
            ctx(deps),
            MIC2,
            leaf(
                MIC2,
                {**DEPARTED_GENE, "ProfileNumToReturn": StringValue(value="100")},
            ),
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == {
            "ProfileGeneId": StringValue(value="tgme49_300100"),
            "ProfileNumToReturn": StringValue(value="100"),
        }
        assert len(stub_api.named("update_step_search_config")) == 1

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

    async def test_a_patch_on_a_stated_value_asks_for_its_canonical_form(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Repeating the stated value is allowed, and costs the second look."""
        seen: list[dict[str, ParamValue]] = []
        pin_validator(monkeypatch, records_the_call(seen))
        deps = measured_deps(mic2_params=STATED_GENE)

        await update_leaf_params(ctx(deps), MIC2, dict(STATED_GENE))

        assert len(seen) == 2
        assert stub_api.named("update_step_search_config") == []
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[MIC2].parameters == STATED_GENE
