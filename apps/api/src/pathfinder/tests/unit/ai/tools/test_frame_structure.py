"""``set_structure`` writes the proposed node tree onto the draft spec."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, StructureNode
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state)


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _combine(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _drafted_root(state: AgentToolState) -> StructureNode:
    """The root of the structure the draft holds, which each caller has just set."""
    structure = state.operational_spec_draft.structure
    assert structure is not None
    return structure.root


@pytest.mark.asyncio
async def test_set_structure_wires_a_transform_to_its_input() -> None:
    # A search that maps a prior result is a transform node holding that
    # subtree as its input, never a standalone leaf.
    st = AgentToolState()

    await set_structure(
        _ctx(st),
        root=_combine(
            CombineOp.INTERSECT,
            StructureNode(
                kind="transform", criterion_id="c_ortho", inputs=[_leaf("c_seed")]
            ),
            _leaf("c_pf"),
        ),
    )

    root = _drafted_root(st)
    assert root.kind == "combine"
    assert root.operator == CombineOp.INTERSECT
    assert root.inputs[1].criterion_id == "c_pf"
    transform = root.inputs[0]
    assert transform.kind == "transform"
    assert transform.criterion_id == "c_ortho"
    assert transform.inputs[0].criterion_id == "c_seed"


@pytest.mark.asyncio
async def test_set_structure_keeps_each_nodes_own_operator() -> None:
    st = AgentToolState()

    await set_structure(
        _ctx(st),
        root=_combine(
            CombineOp.UNION,
            _combine(CombineOp.INTERSECT, _leaf("c1"), _leaf("c2")),
            _leaf("c3"),
        ),
    )

    root = _drafted_root(st)
    assert root.operator == CombineOp.UNION
    assert root.inputs[1].criterion_id == "c3"
    assert root.inputs[0].operator == CombineOp.INTERSECT


class TestNestedBranches:
    """A left fold cannot express a UNION branch on the secondary input.

    ``(A UNION B) INTERSECT (E UNION F)`` folds left into
    ``((A UNION B INTERSECT E) UNION F)``, which is a different question. WDK
    step trees carry primary AND secondary inputs, so the shape is
    representable end to end.
    """

    @pytest.mark.asyncio
    async def test_a_union_branch_survives_on_the_secondary_input(self) -> None:
        st = AgentToolState()

        await set_structure(
            _ctx(st),
            root=_combine(
                CombineOp.INTERSECT,
                _leaf("kinases"),
                _combine(CombineOp.UNION, _leaf("massspec"), _leaf("derisi")),
            ),
        )

        root = _drafted_root(st)
        assert root.operator == CombineOp.INTERSECT
        branch = root.inputs[1]
        assert branch.kind == "combine"
        assert branch.operator == CombineOp.UNION
        assert [n.criterion_id for n in branch.inputs] == ["massspec", "derisi"]

    @pytest.mark.asyncio
    async def test_a_transform_can_sit_above_a_union_branch(self) -> None:
        st = AgentToolState()

        await set_structure(
            _ctx(st),
            root=StructureNode(
                kind="transform",
                criterion_id="orthologs",
                inputs=[_combine(CombineOp.UNION, _leaf("ec"), _leaf("interpro"))],
            ),
        )

        root = _drafted_root(st)
        assert root.kind == "transform"
        assert root.criterion_id == "orthologs"
        assert root.inputs[0].operator == CombineOp.UNION

    @pytest.mark.asyncio
    async def test_a_single_leaf_is_still_valid(self) -> None:
        st = AgentToolState()

        result = returned(
            await set_structure(_ctx(st), root=_leaf("only")), SetStructureResult
        )

        root = _drafted_root(st)
        assert root.kind == "leaf"
        assert root.criterion_id == "only"
        assert result.criteria_combined == 1

    @pytest.mark.asyncio
    async def test_it_counts_every_criterion_in_the_tree(self) -> None:
        st = AgentToolState()

        result = returned(
            await set_structure(
                _ctx(st),
                root=_combine(
                    CombineOp.INTERSECT,
                    _leaf("a"),
                    _combine(CombineOp.UNION, _leaf("b"), _leaf("c")),
                ),
            ),
            SetStructureResult,
        )

        assert result.criteria_combined == 3


_COMBINATION = "mass spectrometry evidence OR DeRisi expression"

# The kinase drug-target shape: four kinase evidence sources unioned, then
# intersected with the two lines of evidence the user asked to OR.
_DRUG_TARGET_CRITERIA = [
    Criterion(id="k_go", text="kinases by molecular function", search_name="GenesByGo"),
    Criterion(id="k_ipr", text="kinases by InterPro domain", search_name="GenesByIpr"),
    Criterion(id="k_ec", text="kinases by EC number", search_name="GenesByEc"),
    Criterion(
        id="k_fam", text="kinases by protein family", search_name="GenesByFamily"
    ),
    Criterion(
        id="c_ms",
        text="trophozoite mass spectrometry evidence",
        search_name="GenesByMassSpec",
    ),
    Criterion(
        id="c_derisi",
        text="DeRisi timecourse expression",
        search_name="GenesByRNASeqEvidence",
    ),
]


def _requirement(value: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value=value,
        label="how the evidence combines",
        source=ConstraintSource.USER_EXPLICIT,
    )


def _combination_state() -> AgentToolState:
    state = AgentToolState(combination_requirements=[_requirement(_COMBINATION)])
    for criterion in _DRUG_TARGET_CRITERIA:
        state.frame_set_criterion(criterion)
    return state


def _kinase_union() -> StructureNode:
    return _combine(CombineOp.UNION, *[_leaf(c.id) for c in _DRUG_TARGET_CRITERIA[:4]])


class TestStatedCombinationGate:
    """A stated combination is checked against the PROPOSED tree before it is
    written, so a saved strategy's mirrored operator never reaches it."""

    @pytest.mark.asyncio
    async def test_a_tree_that_intersects_a_stated_or_is_refused(self) -> None:
        st = _combination_state()

        with pytest.raises(ModelRetry) as caught:
            await set_structure(
                _ctx(st),
                root=_combine(
                    CombineOp.INTERSECT,
                    _kinase_union(),
                    _leaf("c_derisi"),
                    _leaf("c_ms"),
                ),
            )

        message = str(caught.value)
        assert _COMBINATION in message
        assert "UNION" in message
        assert "INTERSECT" in message
        assert st.operational_spec_draft.structure is None

    @pytest.mark.asyncio
    async def test_the_same_tree_with_a_union_branch_is_written(self) -> None:
        st = _combination_state()

        result = returned(
            await set_structure(
                _ctx(st),
                root=_combine(
                    CombineOp.INTERSECT,
                    _kinase_union(),
                    _combine(CombineOp.UNION, _leaf("c_ms"), _leaf("c_derisi")),
                ),
            ),
            SetStructureResult,
        )

        assert result.criteria_combined == 6
        assert _drafted_root(st).operator == CombineOp.INTERSECT

    @pytest.mark.asyncio
    async def test_a_requirement_naming_no_criterion_is_written_through(self) -> None:
        st = _combination_state()
        st.combination_requirements = [_requirement("proteomics OR microscopy")]

        await set_structure(
            _ctx(st),
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi")),
        )

        assert _drafted_root(st).operator == CombineOp.INTERSECT

    @pytest.mark.asyncio
    async def test_no_stated_combination_leaves_the_tool_alone(self) -> None:
        st = AgentToolState()

        await set_structure(
            _ctx(st),
            root=_combine(CombineOp.INTERSECT, _leaf("c_ms"), _leaf("c_derisi")),
        )

        assert _drafted_root(st).operator == CombineOp.INTERSECT
