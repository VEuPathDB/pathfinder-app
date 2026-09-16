"""A criterion that matched no record carries its choices to the Lead.

The path runs from one ``set_criterion`` bind to the frame section the Lead
reads.
"""

from __future__ import annotations

import pytest

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state
from pathfinder.tests.unit.ai.tools.test_frame_spec import bind, serve_search
from pathfinder.tests.unit.ai.tools.test_frame_spec_criterion_count import _serve_count
from pathfinder.tests.unit.ai.tools.test_frame_spec_empty_criterion import (
    _PICK_V3,
    versioned,
    wide_vocabulary,
)


def _frame_section(spec: OperationalSpec) -> str:
    state = pipeline_state(
        domain=StrategyDomainState.model_validate({"operational_spec": spec})
    )
    return derive_ledger(state, None).render_section("frame")


@pytest.mark.asyncio
async def test_a_bind_that_matched_nothing_records_its_choices_on_the_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, 0)
    state = AgentToolState()

    await bind(state, "RecordsByMethod", _PICK_V3)

    choices = state.operational_spec_draft.criteria[0].alternatives
    assert len(choices) == 1
    assert choices[0].param_name == "method_version"
    assert choices[0].bound == ["v3"]
    assert choices[0].option_count == 3
    assert choices[0].other_options == ["v2", "v1"]


@pytest.mark.asyncio
async def test_the_frame_section_names_the_parameter_the_value_and_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, 0)
    state = AgentToolState()

    await bind(state, "RecordsByMethod", _PICK_V3)

    assert (
        "    CHOICES method_version: holds ['v3'], 3 options, others ['v2', 'v1']"
        in _frame_section(state.operational_spec_draft)
    )


@pytest.mark.asyncio
async def test_a_criterion_that_matched_records_renders_no_choices_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, versioned)
    _serve_count(monkeypatch, 12)
    state = AgentToolState()

    await bind(state, "RecordsByMethod", _PICK_V3)

    assert state.operational_spec_draft.criteria[0].alternatives == []
    assert "CHOICES" not in _frame_section(state.operational_spec_draft)


@pytest.mark.asyncio
async def test_a_rebind_that_matches_records_drops_the_choices_it_carried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ledger states what the criterion holds now, not what it held."""
    serve_search(monkeypatch, versioned)
    counts = iter([0, 12])
    state = AgentToolState()

    _serve_count(monkeypatch, next(counts))
    await bind(state, "RecordsByMethod", _PICK_V3)
    assert state.operational_spec_draft.criteria[0].alternatives != []

    _serve_count(monkeypatch, next(counts))
    await bind(state, "RecordsByMethod", {"method_version": "v2"})

    assert len(state.operational_spec_draft.criteria) == 1
    assert state.operational_spec_draft.criteria[0].alternatives == []
    assert "CHOICES" not in _frame_section(state.operational_spec_draft)


@pytest.mark.asyncio
async def test_a_vocabulary_too_large_to_list_renders_its_size_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, wide_vocabulary)
    _serve_count(monkeypatch, 0)
    state = AgentToolState()

    await bind(state, "RecordsByTissue", {"tissue": ["t7"]})

    rendered = _frame_section(state.operational_spec_draft)
    assert "    CHOICES tissue: holds ['t7'], 40 options" in rendered
    assert "others" not in rendered
