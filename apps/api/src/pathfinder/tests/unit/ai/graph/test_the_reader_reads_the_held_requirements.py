from __future__ import annotations

from pathfinder.ai.graph._lead_reading import _reader_input
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)


def test_the_reader_is_given_each_held_requirement_under_its_number() -> None:
    genes = Constraint(
        kind=ConstraintKind.RECORD_TYPE,
        label="record type",
        requested_value="genes",
        source=ConstraintSource.ASSUMED,
    )
    assumed = requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium").model_copy(
        update={"source": ConstraintSource.ASSUMED}
    )
    held = [
        genes,
        assumed,
        requirement(ConstraintKind.FOLD_CHANGE, "fold change", "at least 2-fold"),
        requirement(ConstraintKind.OTHER, "localisation", "signal peptide"),
    ]
    message = "Drop the fold change."
    state = pipeline_state(
        "plasmodb",
        user_prompt=message,
        domain=StrategyDomainState(requirements=held),
    )

    read = _reader_input(state, lead_deps(state), message, {"transcript": "Genes"})

    assert read.record_classes == {"transcript": "Genes"}
    assert read.held == {
        "R1": "fold_change: at least 2-fold",
        "R2": "other: signal peptide",
        "R3": "record_type: genes",
    }
