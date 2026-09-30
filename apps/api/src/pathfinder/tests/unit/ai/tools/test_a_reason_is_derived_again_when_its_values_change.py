"""A reason records the values it was derived from. An edit that changes one of
them records the edit's own why, or asks for one; an edit that changes none keeps
the reason."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue, to_wire

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.step_rationale import ComparedSearch, SearchRationale
from pathfinder.tests._support.recorded_counts import no_measurements
from pathfinder.tests._support.recorded_searches import (
    serve_recorded_plasmodb,
    suite_search,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._rationale_catalog import choice
from pathfinder.tests.unit.ai.tools.conftest import serve_no_other_sites
from pathfinder.tests.unit.ai.tools.test_frame_spec import frame_ctx, no_validation

_TEXT = suite_search("search_genes_by_text")
_HELD_REASON = (
    "Search the Apicomplexa lineage for the literal rhoptry annotation in "
    "product-description fields."
)
_HELD_VALUES: dict[str, ParamValue] = {
    "text_expression": StringValue(value="rhoptry"),
    "text_fields": MultiPickValue(values=["product"]),
    "text_search_organism": MultiPickValue(values=["Apicomplexa"]),
}
_HELD = SearchRationale(
    search_name=_TEXT.url_segment,
    basis="parameter",
    term="Text term (use * as wildcard)",
    reason=_HELD_REASON,
    similarity=0.61,
    compared=[
        ComparedSearch(
            name="GenesByRnaSeqEvidence",
            display_name="RNA-Seq Evidence",
            similarity=0.4,
        )
    ],
    answered=12,
    query="rhoptry annotation",
    tool_call_id="call_turn1_read",
    sources=["https://example.org/rhoptry-review"],
    derived_from={name: to_wire(value) for name, value in _HELD_VALUES.items()},
)
_REQUEST = "Only the Plasmodium falciparum 3D7 rhoptry genes, please."


def _state(organism: str = "Apicomplexa") -> AgentToolState:
    held = Criterion(
        id="step_2381d896",
        text="Genes in the Apicomplexa lineage annotated as rhoptry proteins",
        search_name=_TEXT.url_segment,
        resolved_params={
            "text_expression": BoundValue(
                value=StringValue(value="rhoptry"), source="stated"
            ),
            "text_fields": BoundValue(
                value=MultiPickValue(values=["product"]), source="chosen"
            ),
            "text_search_organism": BoundValue(
                value=MultiPickValue(values=[organism]), source="stated"
            ),
        },
        rationale=_HELD,
    )
    state = AgentToolState(operational_spec_draft=OperationalSpec(criteria=[held]))
    state.request_messages = [_REQUEST]
    return state


_EDIT: dict[str, str | list[str] | None] = {
    "text_expression": "rhoptry",
    "text_fields": ["product"],
    "text_search_organism": ["Plasmodium falciparum 3D7"],
}


@pytest.fixture(autouse=True)
def _served(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_recorded_plasmodb(monkeypatch, [_TEXT])
    no_validation(monkeypatch)
    no_measurements(monkeypatch)
    serve_no_other_sites(monkeypatch)


@pytest.mark.asyncio
async def test_a_value_edit_records_its_own_why_when_the_kept_reason_names_the_old_value() -> (
    None
):
    new_reason = (
        "Search Plasmodium falciparum 3D7 for the literal rhoptry annotation in "
        "product-description fields."
    )
    state = _state()

    result = returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="step_2381d896",
            text="Genes in Plasmodium falciparum 3D7 annotated as rhoptry proteins",
            search_name=_TEXT.url_segment,
            params=dict(_EDIT),
            why=choice("parameter", "Text term (use * as wildcard)", new_reason),
        ),
        SetCriterionResult,
    )

    assert result.rationale is not None
    assert (result.rationale.reason, result.rationale.sources) == (new_reason, [])
    assert (result.rationale.tool_call_id, result.rationale.query) == (
        "call_turn1_read",
        "rhoptry annotation",
    )
    [criterion] = state.operational_spec_draft.criteria
    assert criterion.rationale == result.rationale
    assert "Apicomplexa" not in result.rationale.sentence


@pytest.mark.asyncio
async def test_a_value_edit_with_no_why_is_refused_naming_the_values_it_changes() -> (
    None
):
    state = _state()

    with pytest.raises(ModelRetry) as refusal:
        await set_criterion(
            frame_ctx(state),
            criterion_id="step_2381d896",
            text="Genes in Plasmodium falciparum 3D7 annotated as rhoptry proteins",
            search_name=_TEXT.url_segment,
            params=dict(_EDIT),
        )

    assert str(refusal.value) == (
        "step_2381d896: its reason was derived from text_search_organism "
        '["Apicomplexa"], which this edit changes, so the reason no longer holds: '
        f"'{_HELD.sentence}'. Pass a why for the values this call binds. Nothing "
        "was recorded."
    )
    [criterion] = state.operational_spec_draft.criteria
    assert criterion.rationale == _HELD


@pytest.mark.asyncio
async def test_an_edit_s_why_is_recorded_though_the_kept_reason_names_no_value() -> (
    None
):
    """The ME49 rebind quotes the phrase; the reason it held named no value."""
    held = _HELD.model_copy(
        update={"reason": "The text term is the requested phrase in the product field."}
    )
    state = _state()
    state.operational_spec_draft.criteria[0].rationale = held
    new_reason = (
        "The exact phrase in the product field, as the Hammondia search reads it."
    )

    result = returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="step_2381d896",
            text="Genes annotated as rhoptry proteins",
            search_name=_TEXT.url_segment,
            params=_EDIT | {"text_expression": '"rhoptry protein"'},
            why=choice("parameter", "Text term (use * as wildcard)", new_reason),
        ),
        SetCriterionResult,
    )

    assert result.rationale is not None
    assert result.rationale.reason == new_reason


@pytest.mark.asyncio
async def test_a_reason_is_derived_again_whatever_spelling_the_strategy_holds() -> None:
    """The step holds the site's leaf list; the reason was derived from the node."""
    state = _state()
    criterion = state.operational_spec_draft.criteria[0]
    criterion.resolved_params["text_search_organism"] = BoundValue(
        value=MultiPickValue(
            values=["Plasmodium falciparum 3D7", "Toxoplasma gondii ME49"]
        ),
        source="stated",
    )
    new_reason = "Search Plasmodium falciparum 3D7 alone for the rhoptry annotation."

    result = returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="step_2381d896",
            text="Genes in Plasmodium falciparum 3D7 annotated as rhoptry proteins",
            search_name=_TEXT.url_segment,
            params=dict(_EDIT),
            why=choice("parameter", "Text term (use * as wildcard)", new_reason),
        ),
        SetCriterionResult,
    )

    assert result.rationale is not None
    assert result.rationale.reason == new_reason


@pytest.mark.asyncio
async def test_a_binding_of_the_same_values_keeps_the_reason() -> None:
    state = _state("Plasmodium falciparum 3D7")
    [criterion] = state.operational_spec_draft.criteria
    held = _HELD.model_copy(
        update={
            "derived_from": {
                name: to_wire(bound.value)
                for name, bound in criterion.resolved_params.items()
            }
        }
    )
    criterion.rationale = held

    result = returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id="step_2381d896",
            text="Genes in Plasmodium falciparum 3D7 annotated as rhoptry proteins",
            search_name=_TEXT.url_segment,
            params=dict(_EDIT),
        ),
        SetCriterionResult,
    )

    assert result.rationale == held


def test_the_glycosome_reason_no_longer_holds_once_the_organism_narrows() -> None:
    """The GO reason names the taxon-wide scope it was derived at."""
    held = _HELD.model_copy(
        update={
            "reason": (
                "The direct GO search supports the requested glycosome annotation "
                "and the Trypanosomatida taxon-wide scope."
            ),
            "derived_from": {
                "organism": '["Trypanosomatida"]',
                "GoTermId": '["GO:0020015"]',
            },
        }
    )

    narrowed = {
        "organism": '["Leishmania donovani BPK282A1"]',
        "GoTermId": '["GO:0020015"]',
    }
    assert held.changed_by(narrowed) == ["organism"]
