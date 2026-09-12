"""An edit that contradicts the operational spec is refused, not pushed.

The tree and the ids are the ones a live toxodb turn wrote, so each case is a
call the execution agent really made.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import ParamValue, StringValue, to_wire
from veupathdb.domain.strategy import CombineOp, StrategyStepNode
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy import build_strategy
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
from pathfinder.domain.strategy.revision import strategy_revision

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    pin_validator,
    seed,
)

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
_STATED_GENE: dict[str, ParamValue] = {
    "ProfileGeneId": StringValue(value="TGME49_201780")
}
_SECOND_LOOK = "ProfileGeneId: the catalog turns this value down"


def _records_the_call(
    seen: list[dict[str, ParamValue]],
) -> Callable[..., Awaitable[ValidatedParams]]:
    """A catalog that accepts every value and counts what it was asked."""

    async def _validate(*_args: Any, **kwargs: Any) -> ValidatedParams:
        params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
        seen.append(params)
        return ValidatedParams(params=params, record_class="transcript")

    return _validate


def _refuses_a_second_look(
    seen: list[dict[str, ParamValue]],
) -> Callable[..., Awaitable[ValidatedParams]]:
    """A catalog that answers the write and turns down anything asked after it."""
    accept = _records_the_call(seen)

    async def _validate(*args: Any, **kwargs: Any) -> ValidatedParams:
        if seen:
            raise ValidationError(title="Invalid value", detail=_SECOND_LOOK)
        return await accept(*args, **kwargs)

    return _validate


async def _lowercases_the_gene(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """A catalog that rewrites the gene id, the way a vocabulary match does."""
    params: dict[str, ParamValue] = dict(kwargs.get("parameters") or {})
    gene = params.get("ProfileGeneId")
    if gene is not None:
        params["ProfileGeneId"] = StringValue(value=to_wire(gene).lower())
    return ValidatedParams(params=params, record_class="transcript")


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


def _measured_deps(*, mic2_params: dict[str, ParamValue] | None = None) -> AgentDeps:
    """The strategy the spec built, and the spec that declares its shape."""
    deps = seed(
        combine(
            _ROOT,
            combine(_TM_JOIN, leaf(_TM), leaf(_SIGNAL), op=CombineOp.UNION),
            combine(
                _PROFILE_JOIN,
                leaf(_PROFILE),
                combine(
                    _SIMILARITY_JOIN,
                    leaf(_MIC2, mic2_params),
                    leaf(_RON2),
                    CombineOp.UNION,
                ),
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

    async def test_the_same_value_written_as_a_subtree_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        """A rewritten leaf carries its parameters, and the spec reads them."""
        deps = _measured_deps()

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(
                ctx(deps),
                _MIC2,
                leaf(_MIC2, {"ProfileGeneId": StringValue(value="TGME49_300100")}),
            )

        assert "set_criterion" in str(excinfo.value)
        assert "TGME49_201780" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_MIC2].parameters == {}
        assert stub_api.calls == []

    async def test_a_subtree_that_repeats_the_stated_value_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _measured_deps()

        await replace_subtree(
            ctx(deps),
            _MIC2,
            leaf(_MIC2, {"ProfileGeneId": StringValue(value="TGME49_201780")}),
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_MIC2].parameters == {
            "ProfileGeneId": StringValue(value="TGME49_201780")
        }
        assert stub_api.named("update_step_search_config") != []

    async def test_the_same_value_written_by_a_build_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        """A whole-tree build carries its leaves' values, and the spec reads them."""
        deps = _measured_deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        revision = strategy_revision(graph.to_strategy_ast())

        with pytest.raises(ModelRetry) as excinfo:
            await build_strategy(
                ctx(deps),
                combine(
                    _ROOT,
                    combine(_TM_JOIN, leaf(_TM), leaf(_SIGNAL), op=CombineOp.UNION),
                    combine(
                        _PROFILE_JOIN,
                        leaf(_PROFILE),
                        combine(
                            _SIMILARITY_JOIN,
                            leaf(
                                _MIC2,
                                {"ProfileGeneId": StringValue(value="TGME49_300100")},
                            ),
                            leaf(_RON2),
                            CombineOp.UNION,
                        ),
                    ),
                ),
                base_revision=revision,
            )

        assert "set_criterion" in str(excinfo.value)
        assert "TGME49_201780" in str(excinfo.value)
        assert graph.steps[_MIC2].parameters == {}
        assert stub_api.calls == []

    async def test_a_canonicalizer_that_shifts_an_untouched_value_does_not_refuse(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The catalog rewrites a value the write never sent; the write stands."""
        pin_validator(monkeypatch, _lowercases_the_gene)
        deps = _measured_deps(mic2_params=_STATED_GENE)

        await update_leaf_params(
            ctx(deps), _MIC2, {"ProfileNumToReturn": StringValue(value="100")}
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_MIC2].parameters == {
            "ProfileGeneId": StringValue(value="tgme49_201780"),
            "ProfileNumToReturn": StringValue(value="100"),
        }
        assert stub_api.named("update_step_search_config") != []

    async def test_the_same_canonicalizer_still_refuses_a_real_change(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pin_validator(monkeypatch, _lowercases_the_gene)
        deps = _measured_deps(mic2_params=_STATED_GENE)

        with pytest.raises(ModelRetry) as excinfo:
            await update_leaf_params(
                ctx(deps), _MIC2, {"ProfileGeneId": StringValue(value="TGME49_300100")}
            )

        assert "set_criterion" in str(excinfo.value)
        assert "tgme49_201780" in str(excinfo.value)
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_MIC2].parameters == _STATED_GENE
        assert stub_api.calls == []

    async def test_a_patch_that_touches_no_stated_value_asks_the_catalog_once(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A second look at an untouched value could refuse a good patch."""
        seen: list[dict[str, ParamValue]] = []
        pin_validator(monkeypatch, _refuses_a_second_look(seen))
        deps = _measured_deps(mic2_params=_STATED_GENE)

        await update_leaf_params(
            ctx(deps), _MIC2, {"ProfileNumToReturn": StringValue(value="100")}
        )

        assert len(seen) == 1
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_MIC2].parameters == {
            **_STATED_GENE,
            "ProfileNumToReturn": StringValue(value="100"),
        }
        assert stub_api.named("update_step_search_config") != []

    async def test_a_patch_on_a_stated_value_asks_for_its_canonical_form(
        self, stub_api: StubAPI, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Repeating the stated value is allowed, and costs the second look."""
        seen: list[dict[str, ParamValue]] = []
        pin_validator(monkeypatch, _records_the_call(seen))
        deps = _measured_deps(mic2_params=_STATED_GENE)

        await update_leaf_params(ctx(deps), _MIC2, dict(_STATED_GENE))

        assert len(seen) == 2
        assert stub_api.named("update_step_search_config") == []
        graph = deps.strategy_session.graph
        assert graph is not None
        assert graph.steps[_MIC2].parameters == _STATED_GENE

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
