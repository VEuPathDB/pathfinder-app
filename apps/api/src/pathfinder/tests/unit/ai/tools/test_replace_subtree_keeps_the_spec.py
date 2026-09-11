"""``replace_subtree`` leaves the strategy holding the criteria the spec states."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import JsonValue, ValidationError
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import walk

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.strategy_edits import delete_step, replace_subtree
from pathfinder.ai.tools.toolsets.execution import build_toolset
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.tool_returns import returned

from ._strategy_edit_stubs import (
    StubAPI,
    combine,
    ctx,
    install_stub_api,
    leaf,
    session_with,
)

_CRITERIA = {
    "step_k1": "kinase domain, PlasmoDB",
    "step_k2": "kinase domain, orthologs",
    "step_k3": "protein kinase InterPro",
    "step_k4": "kinase GO term",
    "step_ms": "mass spectrometry evidence",
    "step_derisi": "DeRisi expression profile",
    "step_ortho": "ortholog map",
    "step_phylo": "phylogenetic profile",
    "step_snp": "SNP filter",
}

_WDK_STEP_IDS = {
    "step_k1": 101,
    "step_k2": 102,
    "step_k3": 103,
    "step_k4": 104,
    "step_ms": 105,
    "step_derisi": 106,
    "step_phylo": 107,
    "step_snp": 108,
    "step_ortho": 109,
    "step_u1": 201,
    "step_u2": 202,
    "step_u3": 203,
    "step_c1": 301,
    "step_c2": 302,
    "step_c3": 303,
    "step_c4": 304,
}


@pytest.fixture
def stub_api(monkeypatch: pytest.MonkeyPatch) -> StubAPI:
    return install_stub_api(monkeypatch)


def _transform(id_: str, source: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        id=id_, search_name="GenesByOrthologs", primary_input=source
    )


def _kinase_strategy() -> StrategyStepNode:
    """Three UNION branches, an ortholog transform, and three filters."""
    u1 = combine("step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION)
    u2 = combine("step_u2", leaf("step_k3"), leaf("step_k4"), op=CombineOp.UNION)
    u3 = combine("step_u3", leaf("step_ms"), leaf("step_derisi"), op=CombineOp.UNION)
    kinases = combine("step_c1", u1, u2)
    evidence = combine("step_c2", kinases, u3)
    orthologs = _transform("step_ortho", evidence)
    profiled = combine("step_c3", orthologs, leaf("step_phylo"))
    return combine("step_c4", profiled, leaf("step_snp"))


def _placeholder(id_: str) -> StrategyStepNode:
    return StrategyStepNode(id=id_, search_name="__input_step__")


def _placeholder_subtree() -> StrategyStepNode:
    """Four placeholder leaves under three intersects."""
    return combine(
        "step_n3",
        combine(
            "step_n2",
            combine("step_n1", _placeholder("step_p1"), _placeholder("step_p2")),
            _placeholder("step_p3"),
        ),
        _placeholder("step_p4"),
    )


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="kinases with expression and ortholog evidence",
        criteria=[
            Criterion(id=step_id, text=text, search_name="GenesByTaxon")
            for step_id, text in _CRITERIA.items()
        ],
    )


def _deps() -> AgentDeps:
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(_kinase_strategy(), _WDK_STEP_IDS),
        conversation_id=uuid4(),
        agent_state=AgentToolState(operational_spec_draft=_spec()),
    )


class TestReplaceSubtreeAgainstTheSpec:
    async def test_a_replacement_that_drops_criteria_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        graph = deps.strategy_session.graph
        assert graph is not None
        assert len(graph.steps) == 16

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(ctx(deps), "step_c1", _placeholder_subtree())

        message = str(excinfo.value)
        for lost in ("step_k1", "step_k2", "step_k3", "step_k4"):
            assert lost in message
            assert _CRITERIA[lost] in message
        assert len(graph.steps) == 16
        assert graph.steps["step_u1"].operator == CombineOp.UNION
        assert stub_api.calls == []

    async def test_a_replacement_that_keeps_every_criterion_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        replacement = combine(
            "step_c1",
            combine("step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION),
            combine(
                "step_u2", leaf("step_k3"), leaf("step_k4"), op=CombineOp.INTERSECT
            ),
        )

        payload = returned(
            await replace_subtree(ctx(deps), "step_c1", replacement),
            dict[str, JsonValue],
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert payload["ok"] is True
        assert len(graph.steps) == 16
        assert graph.steps["step_u2"].operator == CombineOp.INTERSECT
        assert stub_api.named("create_combined_step") != []

    async def test_a_replacement_that_mints_a_stated_criterion_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        """A criterion answers to the step the replacement adds for it."""
        deps = _deps()
        deps.agent_state.operational_spec_draft.criteria.append(
            Criterion(id="step_k5", text="signal peptide", search_name="GenesByTaxon")
        )
        replacement = combine(
            "step_c1",
            combine("step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION),
            combine(
                "step_u2",
                combine(
                    "step_u4", leaf("step_k3"), leaf("step_k5"), op=CombineOp.UNION
                ),
                leaf("step_k4"),
            ),
        )

        payload = returned(
            await replace_subtree(ctx(deps), "step_c1", replacement),
            dict[str, JsonValue],
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert payload["ok"] is True
        assert graph.steps["step_k5"].search_name == "GenesByTaxon"
        assert graph.steps["step_u4"].operator == CombineOp.UNION
        assert stub_api.named("create_step") != []

    @pytest.mark.usefixtures("stub_api")
    async def test_a_placeholder_search_name_never_validates(self) -> None:
        """The arg validator is the boundary the agent's tool call passes."""
        deps = _deps()
        toolset = build_toolset()
        tool = (await toolset.get_tools(ctx(deps)))["replace_subtree"]

        with pytest.raises(ValidationError) as excinfo:
            tool.args_validator.validate_python(
                {
                    "step_id": "step_c1",
                    "new_subtree": {
                        "searchName": "__combine__",
                        "operator": "INTERSECT",
                        "primaryInput": {"searchName": "__input_step__"},
                        "secondaryInput": {"searchName": "GenesByTaxon"},
                    },
                }
            )

        message = str(excinfo.value)
        assert "__input_step__" in message
        assert "__combine__" not in message

    @pytest.mark.usefixtures("stub_api")
    async def test_two_placeholders_are_named_one_after_the_other(self) -> None:
        deps = _deps()
        toolset = build_toolset()
        tool = (await toolset.get_tools(ctx(deps)))["replace_subtree"]

        with pytest.raises(ValidationError) as excinfo:
            tool.args_validator.validate_python(
                {
                    "step_id": "step_c1",
                    "new_subtree": {
                        "searchName": "__combine__",
                        "operator": "INTERSECT",
                        "primaryInput": {"searchName": "__input_step__"},
                        "secondaryInput": {"searchName": "__prior_result__"},
                    },
                }
            )

        message = str(excinfo.value)
        assert "__input_step__, __prior_result__: a placeholder" in message
        assert "['" not in message

    @pytest.mark.usefixtures("stub_api")
    async def test_a_real_search_name_validates(self) -> None:
        deps = _deps()
        toolset = build_toolset()
        tool = (await toolset.get_tools(ctx(deps)))["replace_subtree"]

        args = tool.args_validator.validate_python(
            {
                "step_id": "step_c1",
                "new_subtree": {"searchName": "GenesByTaxon", "id": "step_k1"},
            }
        )

        assert args["new_subtree"].search_name == "GenesByTaxon"


class TestADeleteKeepsTheGuardArmed:
    async def test_a_destructive_replacement_is_still_refused_after_a_delete(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps()
        await delete_step(ctx(deps), "step_snp")
        graph = deps.strategy_session.graph
        assert graph is not None
        assert len(graph.steps) == 14
        stub_api.calls.clear()

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(ctx(deps), "step_c1", _placeholder_subtree())

        for lost in ("step_k1", "step_k2", "step_k3", "step_k4"):
            assert lost in str(excinfo.value)
        assert len(graph.steps) == 14
        assert stub_api.calls == []

    async def test_the_deleted_criterion_leaves_the_spec(
        self, stub_api: StubAPI
    ) -> None:
        del stub_api
        deps = _deps()

        await delete_step(ctx(deps), "step_snp")

        remaining = {c.id for c in deps.agent_state.operational_spec_draft.criteria}
        assert "step_snp" not in remaining
        assert remaining == set(_CRITERIA) - {"step_snp"}


_EDA_TEXT = "berghei subset"


def _exported_eda_tree() -> StrategyStepNode:
    """``(k1 INTERSECT k2) INTERSECT eda1``, the shape an EDA export leaves."""
    return combine(
        "step_c2",
        combine("step_c1", leaf("step_k1"), leaf("step_k2")),
        StrategyStepNode(
            id="step_eda1",
            search_name="GenesByEdaSubset",
            display_name=_EDA_TEXT,
        ),
    )


def _exported_eda_deps() -> AgentDeps:
    spec = OperationalSpec(
        goal="febrile kinases",
        criteria=[
            Criterion(id="step_k1", text="kinase domain", search_name="GenesByTaxon"),
            Criterion(id="step_k2", text="kinase GO term", search_name="GenesByTaxon"),
            Criterion(id="step_eda1", text=_EDA_TEXT, search_name="GenesByEdaSubset"),
        ],
    )
    wdk_ids = {node.id: 900 + i for i, node in enumerate(walk(_exported_eda_tree()))}
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(_exported_eda_tree(), wdk_ids),
        conversation_id=uuid4(),
        agent_state=AgentToolState(operational_spec_draft=spec),
    )


class TestAnExportedEdaStep:
    async def test_a_replacement_that_keeps_all_three_criteria_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _exported_eda_deps()
        graph = deps.strategy_session.graph
        assert graph is not None

        payload = returned(
            await replace_subtree(
                ctx(deps),
                "step_c1",
                combine(
                    "step_c1",
                    leaf("step_k1"),
                    leaf("step_k2"),
                    op=CombineOp.UNION,
                ),
            ),
            dict[str, JsonValue],
        )

        assert payload["ok"] is True
        assert len(graph.steps) == 5
        assert graph.steps["step_c1"].operator == CombineOp.UNION
        assert graph.steps["step_eda1"].search_name == "GenesByEdaSubset"
        assert stub_api.named("create_combined_step") != []

    async def test_a_replacement_that_drops_the_eda_step_is_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _exported_eda_deps()
        graph = deps.strategy_session.graph
        assert graph is not None

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(
                ctx(deps),
                "step_c2",
                combine("step_c2", leaf("step_k1"), leaf("step_k2")),
            )

        message = str(excinfo.value)
        assert "step_eda1" in message
        assert _EDA_TEXT in message
        assert len(graph.steps) == 5
        assert stub_api.calls == []

    async def test_deleting_the_eda_step_takes_its_criterion_with_it(
        self, stub_api: StubAPI
    ) -> None:
        deps = _exported_eda_deps()

        await delete_step(ctx(deps), "step_eda1")
        graph = deps.strategy_session.graph
        assert graph is not None
        assert set(graph.steps) == {"step_c1", "step_k1", "step_k2"}
        stub_api.calls.clear()

        remaining = {c.id for c in deps.agent_state.operational_spec_draft.criteria}
        assert remaining == {"step_k1", "step_k2"}
        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(
                ctx(deps),
                "step_c1",
                combine("step_c1", leaf("step_k1"), leaf("step_x")),
            )
        assert "step_k2" in str(excinfo.value)
        assert stub_api.calls == []


_OPTION_ID = "gametocyte_timecourse_option"


def _deps_with_an_option_criterion() -> AgentDeps:
    """The kinase spec, plus a criterion that binds an option on a search."""
    spec = _spec()
    spec.criteria.append(
        Criterion(
            id=_OPTION_ID,
            text="use the gametocyte timecourse dataset",
            search_name="GenesByTaxon",
        )
    )
    return AgentDeps(
        site_id="plasmodb",
        strategy_session=session_with(_kinase_strategy(), _WDK_STEP_IDS),
        conversation_id=uuid4(),
        agent_state=AgentToolState(operational_spec_draft=spec),
    )


class TestAnOptionCriterion:
    """A criterion with no step of its own leaves the guard armed."""

    async def test_a_replacement_that_drops_criteria_is_still_refused(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps_with_an_option_criterion()
        graph = deps.strategy_session.graph
        assert graph is not None

        with pytest.raises(ModelRetry) as excinfo:
            await replace_subtree(ctx(deps), "step_c1", _placeholder_subtree())

        message = str(excinfo.value)
        assert "step_k1" in message
        assert _OPTION_ID not in message
        assert len(graph.steps) == 16
        assert stub_api.calls == []

    async def test_a_replacement_that_keeps_every_criterion_is_applied(
        self, stub_api: StubAPI
    ) -> None:
        deps = _deps_with_an_option_criterion()
        replacement = combine(
            "step_c1",
            combine("step_u1", leaf("step_k1"), leaf("step_k2"), op=CombineOp.UNION),
            combine(
                "step_u2", leaf("step_k3"), leaf("step_k4"), op=CombineOp.INTERSECT
            ),
        )

        payload = returned(
            await replace_subtree(ctx(deps), "step_c1", replacement),
            dict[str, JsonValue],
        )

        graph = deps.strategy_session.graph
        assert graph is not None
        assert payload["ok"] is True
        assert graph.steps["step_u2"].operator == CombineOp.INTERSECT
        assert stub_api.named("create_combined_step") != []
