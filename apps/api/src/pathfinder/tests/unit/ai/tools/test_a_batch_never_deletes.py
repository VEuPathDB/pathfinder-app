"""A batch of edits carries no delete.

``delete_step`` is the one tool that removes a step: it decides how the tree is
re-wired, asks the researcher, and drops the criteria of what it removed.
"""

from __future__ import annotations

import json
import re

import pytest
from pydantic import ValidationError
from pydantic_ai import Tool

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.tools.standalone._validation_helpers import (
    A_REMOVAL_IN_A_BATCH,
    _refuse_a_removal_in_a_batch,
)
from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.domain.strategy.operations import (
    EDITABLE_KINDS,
    KINDS_A_BATCH_REFUSES,
    DeleteResolution,
    DeleteStepOp,
    GraphOperation,
)
from pathfinder.tests._support.instructions import pinned_instructions
from pathfinder.tests._support.operations import refused_models
from pathfinder.tests.unit.ai.tools._apply_operations_stubs import (
    combine,
    context_and_commit,
    graph_with,
    leaf,
    pin_apply,
    revision_of,
)


class TestABatchNeverRemovesAStep:
    """``apply_operations`` changes and wires steps; ``delete_step`` removes them."""

    async def test_a_batch_that_carries_a_delete_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        committed: list[list[GraphOperation]] = []
        _, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        with pytest.raises(ValidationError) as caught:
            Tool(apply_operations).function_schema.validator.validate_python(
                {
                    "base_revision": revision_of(graph),
                    "operations": [
                        {
                            "kind": "updateStepMeta",
                            "stepId": "step_a",
                            "displayName": "Kinases",
                        },
                        {
                            "kind": "deleteStep",
                            "stepId": "step_a",
                            "resolution": "delete-subtree",
                        },
                    ],
                }
            )

        assert "delete_step" in str(caught.value)
        assert committed == []

    async def test_a_batch_that_carries_an_edge_delete_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A collapse takes the combine and the sibling's parent with it."""
        graph = graph_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        committed: list[list[GraphOperation]] = []
        _, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        with pytest.raises(ValidationError) as caught:
            Tool(apply_operations).function_schema.validator.validate_python(
                {
                    "base_revision": revision_of(graph),
                    "operations": [
                        {
                            "kind": "deleteEdge",
                            "sourceId": "step_k2",
                            "targetId": "step_c1",
                            "slot": "secondary",
                            "resolution": "collapse",
                        }
                    ],
                }
            )

        assert "delete_step" in str(caught.value)
        assert committed == []
        assert sorted(graph.steps) == ["step_c1", "step_k1", "step_k2"]

    async def test_a_batch_that_replaces_the_strategy_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A replacement removes every step it does not carry."""
        graph = graph_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        committed: list[list[GraphOperation]] = []
        _, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        with pytest.raises(ValidationError) as caught:
            Tool(apply_operations).function_schema.validator.validate_python(
                {
                    "base_revision": revision_of(graph),
                    "operations": [
                        {
                            "kind": "replaceStrategy",
                            "root": {"id": "step_new", "searchName": "GenesByTaxon"},
                        }
                    ],
                }
            )

        assert "delete_step" in str(caught.value)
        assert "replace_subtree" in str(caught.value)
        assert committed == []
        assert sorted(graph.steps) == ["step_c1", "step_k1", "step_k2"]

    async def test_a_batch_that_replaces_a_subtree_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A replaced subtree drops the steps the new branch does not carry."""
        graph = graph_with(combine("step_c1", leaf("step_k1"), leaf("step_k2")))
        committed: list[list[GraphOperation]] = []
        _, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)

        with pytest.raises(ValidationError) as caught:
            Tool(apply_operations).function_schema.validator.validate_python(
                {
                    "base_revision": revision_of(graph),
                    "operations": [
                        {
                            "kind": "replaceSubtree",
                            "stepId": "step_c1",
                            "subtree": {
                                "id": "step_k1",
                                "searchName": "GenesByTaxon",
                            },
                        }
                    ],
                }
            )

        assert "replace_subtree" in str(caught.value)
        assert committed == []
        assert sorted(graph.steps) == ["step_c1", "step_k1", "step_k2"]

    async def test_the_other_operation_kinds_still_apply(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        graph = graph_with(leaf("step_a"))
        committed: list[list[GraphOperation]] = []
        ctx, commit = context_and_commit(graph, committed)
        pin_apply(monkeypatch, commit)
        args = Tool(apply_operations).function_schema.validator.validate_python(
            {
                "base_revision": revision_of(graph),
                "operations": [
                    {
                        "kind": "updateStepMeta",
                        "stepId": "step_a",
                        "displayName": "Kinases",
                    },
                    {
                        "kind": "duplicateStep",
                        "sourceStepId": "step_a",
                        "duplicateStepId": "step_b",
                        "combineStepId": "step_c",
                    },
                ],
            }
        )

        await apply_operations(ctx, **args)

        assert [op.kind for op in committed[0]] == ["updateStepMeta", "duplicateStep"]


def test_a_removal_the_model_already_parsed_is_refused_by_name() -> None:
    """The tag is read off the operation itself, not off a raw mapping."""
    op = DeleteStepOp(step_id="step_a", resolution=DeleteResolution.DELETE_SUBTREE)

    with pytest.raises(ValueError, match="A batch never removes a step") as caught:
        _refuse_a_removal_in_a_batch(op)

    assert "delete_step" in str(caught.value)


def test_a_payload_with_no_readable_tag_is_left_to_the_union() -> None:
    """A batch entry that is not an operation reads the kinds a batch carries."""
    assert _refuse_a_removal_in_a_batch("nonsense") == "nonsense"


def test_the_schema_offers_no_removal_kind() -> None:
    """The model reads no way to remove a step from a batch, by any of the names."""
    schema = Tool(apply_operations).function_schema.json_schema
    defs = schema.get("$defs", {})
    text = json.dumps(schema)

    assert sorted(KINDS_A_BATCH_REFUSES) == sorted(
        model.model_fields["kind"].default for model in refused_models()
    )
    assert [kind for kind in sorted(KINDS_A_BATCH_REFUSES) if kind in text] == []
    assert [m.__name__ for m in refused_models() if m.__name__ in defs] == []


def test_the_building_pass_is_never_pointed_at_a_batch_to_delete() -> None:
    """The instructions name one tool that removes a step, and a refused
    delete is reported to the Lead rather than retried as a batch."""
    text = "\n".join(pinned_instructions(build_execution_agent()))
    excluded = (
        "``deleteStep``, ``deleteEdge``, ``replaceStrategy`` and "
        "``replaceSubtree`` are not in the list"
    )
    offered = text.split(excluded)[0]

    for tag in KINDS_A_BATCH_REFUSES:
        assert tag not in offered
    assert excluded in text
    assert "``apply_operations`` removes nothing" in text
    assert "report the refusal to the Lead and remove nothing" in text


def test_the_refusal_names_every_kind_a_batch_will_not_carry() -> None:
    """The message and the union are one list, so neither drifts from the other."""
    named = [
        kind for kind in sorted(KINDS_A_BATCH_REFUSES) if kind in A_REMOVAL_IN_A_BATCH
    ]

    assert named == sorted(KINDS_A_BATCH_REFUSES)


def test_the_instruction_names_the_kinds_the_schema_offers() -> None:
    """The prose and the union are one list, so neither drifts from the other."""
    text = "\n".join(pinned_instructions(build_execution_agent()))
    listed = text.split("batch of typed operations (")[1].split(")")[0]

    assert set(re.findall(r"``(\w+)``", listed)) == EDITABLE_KINDS
