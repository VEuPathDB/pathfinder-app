from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest
from veupathdb.domain.parameters import StringValue

from strategist.domain.eda_parts import EdaAnalysisState
from strategist.services.conversations.responses import (
    ConversationResponse,
    derive_steps_from_strategy_ast,
)
from strategist.services.conversations.shared_context import (
    CONVERSATION_CLEARED,
    CONVERSATION_SHOWN,
    STEP_CLEARED,
    STEP_FILTERED,
    STEP_SHOWN,
    STUDY_CLEARED,
    STUDY_SHOWN,
    WITHHELD_PUSH_ERROR,
    newest_study,
    viewer_strategy,
    viewer_study,
)
from strategist.services.strategies.schemas import StepResponse
from strategist.tests._support.shared_strategy import (
    BUILT_AST,
    PRIVATE_DATASET_ID,
    SHARED_AST,
    STATE,
    UPLOADED_STUDY,
    WDK_STRATEGY_ID,
    state_chunk,
)

NOW = datetime(2026, 11, 23, tzinfo=UTC)

DETAIL = ConversationResponse(
    id=uuid4(),
    name="kinases",
    site_id="plasmodb",
    record_type="transcript",
    steps=derive_steps_from_strategy_ast(SHARED_AST),
    root_step_id="s-both",
    wdk_strategy_id=WDK_STRATEGY_ID,
    wdk_strategy_created_here=True,
    wdk_url=f"https://qa.plasmodb.org/plasmo/app/workspace/strategies/{WDK_STRATEGY_ID}/900119",
    gene_set_id="gs-1",
    total_tokens=5120,
    total_cost_usd=Decimal("0.42"),
    parent_conversation_id=uuid4(),
    parent_message_id=uuid4(),
    dismissed_at=NOW,
    created_at=NOW,
    updated_at=NOW,
)


def test_every_conversation_field_is_shown_or_cleared() -> None:
    assert CONVERSATION_SHOWN | set(CONVERSATION_CLEARED) | {"id"} == set(
        ConversationResponse.model_fields
    )
    assert not CONVERSATION_SHOWN & set(CONVERSATION_CLEARED)


def test_the_viewer_reads_why_the_strategy_could_not_be_read() -> None:
    unreadable = DETAIL.model_copy(
        update={"steps": [], "strategy_unreadable": "root: one step twice"}
    )

    shown, _ = viewer_strategy(unreadable, token="tok-1", include_account_reads=False)

    assert shown.strategy_unreadable == "root: one step twice"


def test_every_step_field_is_shown_cleared_or_filtered() -> None:
    classes = (STEP_SHOWN, frozenset(STEP_CLEARED), STEP_FILTERED)

    assert set[str]().union(*classes) == set(StepResponse.model_fields)
    assert sum(len(c) for c in classes) == len(StepResponse.model_fields)


def test_no_step_field_shown_to_the_viewer_holds_account_data() -> None:
    loaded = next(s for s in DETAIL.steps if s.id == "s-list")

    shown, _ = viewer_strategy(DETAIL, token="tok-1", include_account_reads=False)

    assert loaded.model_fields_set == set(StepResponse.model_fields)
    assert PRIVATE_DATASET_ID in loaded.model_dump_json()
    assert PRIVATE_DATASET_ID not in shown.model_dump_json()


def test_a_step_field_the_viewer_cannot_read_is_flagged() -> None:
    shown, _ = viewer_strategy(DETAIL, token="tok-1", include_account_reads=False)

    step = next(s for s in shown.steps if s.id == "s-list")
    assert step.rationale is None
    assert step.wdk_push_error == WITHHELD_PUSH_ERROR
    assert (
        step.validation is not None,
        step.validation and step.validation.errors,
    ) == (
        True,
        None,
    )
    assert [(f.name, f.value) for f in step.filters or []] == [
        ("gene_list_filter", None)
    ]
    assert [(a.analysis_type, a.parameters) for a in step.analyses or []] == [
        ("go-enrichment", {})
    ]


def test_the_account_reads_box_keeps_the_step_but_not_the_sites_words() -> None:
    shown, _ = viewer_strategy(DETAIL, token="tok-1", include_account_reads=True)

    step = next(s for s in shown.steps if s.id == "s-list")
    assert step.rationale == next(s for s in DETAIL.steps if s.id == "s-list").rationale
    assert [f.value for f in step.filters or []] == [{"ids": PRIVATE_DATASET_ID}]
    assert step.wdk_push_error == WITHHELD_PUSH_ERROR
    assert step.validation is not None
    assert step.validation.errors is None


def test_every_study_field_is_shown_or_cleared() -> None:
    assert STUDY_SHOWN | set(STUDY_CLEARED) == set(EdaAnalysisState.model_fields)
    assert not STUDY_SHOWN & set(STUDY_CLEARED)


def test_the_viewer_gets_no_wdk_handle_or_spend() -> None:
    shown, _ = viewer_strategy(DETAIL, token="tok-1", include_account_reads=True)

    assert (shown.wdk_url, shown.wdk_strategy_id, shown.gene_set_id) == (
        None,
        None,
        None,
    )
    assert (shown.total_tokens, shown.total_cost_usd) == (0, Decimal(0))
    assert (shown.parent_conversation_id, shown.parent_message_id) == (None, None)
    assert (shown.dismissed_at, shown.wdk_strategy_created_here) == (None, False)
    assert shown.id == uuid5(NAMESPACE_URL, "strategist:shared:tok-1") != DETAIL.id
    assert [s.wdk_step_id for s in shown.steps] == [None, None, None]
    assert "900117" not in shown.model_dump_json()
    assert str(WDK_STRATEGY_ID) not in shown.model_dump_json()


def test_a_private_list_is_named_and_not_carried() -> None:
    built = DETAIL.model_copy(
        update={"steps": derive_steps_from_strategy_ast(BUILT_AST)}
    )

    shown, private = viewer_strategy(built, token="tok-1", include_account_reads=False)

    by_id = {s.id: s for s in shown.steps}
    assert private == {"s-list": ["ds_gene_ids"]}
    assert PRIVATE_DATASET_ID not in shown.model_dump_json()
    assert (by_id["s-list"].estimated_size, by_id["s-list"].parameters) == (41, {})
    assert by_id["s-list"].display_name == "Gene set: 3D7 strain gaps"
    assert by_id["s-text"].parameters == {
        "text_expression": StringValue(value="kinase")
    }
    assert by_id["s-both"].estimated_size == 12


def test_the_account_reads_box_keeps_the_list() -> None:
    shown, private = viewer_strategy(DETAIL, token="tok-1", include_account_reads=True)

    assert private == {}
    assert PRIVATE_DATASET_ID in shown.model_dump_json()


def test_the_study_is_the_newest_state_of_the_bound_analysis() -> None:
    chunks = [
        state_chunk("a-1", revision=2),
        state_chunk("a-0", revision=7),
        state_chunk("a-1", revision=3),
    ]

    found = newest_study(chunks, "a-1")

    assert (None if found is None else found.revision) == 3
    assert newest_study(chunks, "a-9") is None


def test_a_study_no_turn_showed_is_not_shared() -> None:
    chunks = [{"type": "text-delta", "id": "t-1", "delta": "x"}]
    showed = [*chunks, state_chunk("a-1", revision=4)]

    assert [newest_study(chunks, "a-1"), newest_study(showed, "a-1")] == [
        None,
        EdaAnalysisState.model_validate(state_chunk("a-1", revision=4)["data"]),
    ]


def test_the_viewer_study_opens_nothing_on_the_site() -> None:
    state = STATE.model_copy(
        update={
            "analysis_url": "https://qa.plasmodb.org/eda/a-1",
            "can_export_rows": True,
        }
    )

    seen = viewer_study(state, include_account_reads=False)

    assert seen == STATE.model_copy(
        update={"analysis_url": None, "can_export_rows": False}
    )


@pytest.mark.parametrize(
    ("include_account_reads", "shown"), [(False, False), (True, True)]
)
def test_a_study_on_the_owners_upload_is_account_data(
    include_account_reads: bool, shown: bool
) -> None:
    upload = STATE.model_copy(update={"dataset_id": UPLOADED_STUDY})

    seen = viewer_study(upload, include_account_reads=include_account_reads)

    assert (seen is not None) is shown


@pytest.mark.parametrize(
    ("include_account_reads", "kept"), [(False, False), (True, True)]
)
def test_a_reason_quoting_another_steps_private_list_is_cleared(
    include_account_reads: bool, kept: bool
) -> None:
    shown, _ = viewer_strategy(
        DETAIL, token="tok-1", include_account_reads=include_account_reads
    )

    step = next(s for s in shown.steps if s.id == "s-text")
    assert step.parameters == {"text_expression": StringValue(value="kinase")}
    assert (step.rationale is not None) is kept
    assert (PRIVATE_DATASET_ID in shown.model_dump_json()) is kept
