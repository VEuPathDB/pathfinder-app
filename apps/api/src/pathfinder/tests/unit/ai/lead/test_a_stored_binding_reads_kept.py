"""A spec stored before bindings stated the measurement reads kept on a turn that
changes nothing."""

from __future__ import annotations

import json

import pytest

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    DisagreementThread,
    kept,
    session_holding,
)
from pathfinder.tests.unit.domain.strategy._analysis import (
    COMPUTE_SEARCH,
    DATASET,
    E2_DOCUMENT,
    E2_STEP,
    e2_step,
)

_A17_WORDS = (
    "Genes that differ between wildtype and delta-DHC mutant "
    "(DESeq, |effect| >= 1, p <= 0.05)"
)


def _stored() -> OperationalSpec:
    """The E2 spec as the ledger stored it: its binding names no measurement."""
    return OperationalSpec.model_validate_json(
        json.dumps(
            {
                "goal": "compare wild type with the DHC mutant on the sense counts",
                "recordType": "transcript",
                "criteria": [
                    {
                        "id": E2_STEP,
                        "role": "seed",
                        "text": _A17_WORDS,
                        "searchName": COMPUTE_SEARCH,
                        "analysis": {
                            "datasetId": DATASET,
                            "comparison": {
                                "groupA": ["wildtype"],
                                "groupB": ["delta-DHC mutant"],
                            },
                            "method": "DESeq",
                            "effectDirection": "upAndDown",
                            "effectSizeThreshold": 1.0,
                            "significanceThreshold": 0.05,
                            "subset": [],
                            "words": _A17_WORDS,
                            "stepParameters": {
                                "eda_dataset_id": {"type": "string", "value": DATASET},
                                "eda_analysis_spec": {
                                    "type": "string",
                                    "value": E2_DOCUMENT,
                                },
                            },
                        },
                    }
                ],
                "structure": {"root": {"kind": "leaf", "criterionId": E2_STEP}},
            }
        )
    )


async def test_a_turn_that_changes_nothing_keeps_the_stored_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = DisagreementThread(
        monkeypatch, spec=_stored(), session=session_holding(e2_step())
    )
    await thread.next_turn()
    thread.frames(lambda found: found, declared=kept(E2_STEP))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert (delta.operations_applied, thread.committed) == (0, [])
    assert thread.ledger_diff().changes == [
        CriterionChange(criterion_id=E2_STEP, disposition="kept")
    ]
