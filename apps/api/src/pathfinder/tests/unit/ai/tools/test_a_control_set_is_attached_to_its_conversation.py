"""A control set runs a test only in the conversation it is attached to."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import DBSessionFactory
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.lead.verify_dispatch import verification_scope
from pathfinder.ai.tools.standalone import (
    control_sets,
    experiment,
    saved_control_sets,
    scored_comparison,
)
from pathfinder.ai.tools.standalone.control_sets import (
    build_control_set,
    use_control_set,
)
from pathfinder.ai.tools.standalone.optimization import sweep_can_run
from pathfinder.ai.tools.standalone.saved_control_sets import ControlSetSummary
from pathfinder.ai.tools.standalone.scored_comparison import compare_variants_scored
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.services.control_sets import ControlSetResponse, NewControlSet
from pathfinder.services.evidence.control_sets import (
    SavedControls,
    UnknownControlSetError,
)
from pathfinder.services.experiment.control_sourcing import ResolvedControls
from pathfinder.services.experiment.variant_comparison import VariantSpec
from pathfinder.tests._support.durable_dispatch import capture_durable_dispatch
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import (
    agent_run_context,
    detached_lead_context,
)

_KINASES = SavedControls(
    control_set_id="5f1c6a2e-0000-4000-8000-00000000c0de",
    name="Kinase controls",
    positive_ids=["PF3D7_1431500", "PF3D7_0310100"],
    negative_ids=["PF3D7_0102600"],
)
_ELSEWHERE = SavedControls(
    control_set_id="a11b531c-0000-4000-8000-0000000000aa",
    name="Two-gene set",
    positive_ids=["PF3D7_1133400", "PF3D7_0930300"],
    negative_ids=[],
)
_KINASES_NAMED = NamedControlSet(id=_KINASES.control_set_id, name=_KINASES.name)
_STEP = 440968803
_NONE_ATTACHED = (
    "No control set is attached to this conversation; the check states that no "
    "controls were available."
)


def _listed(held: SavedControls) -> ControlSetResponse:
    return ControlSetResponse(
        id=held.control_set_id,
        name=held.name,
        site_id="plasmodb",
        record_type="transcript",
        positive_ids=held.positive_ids,
        negative_ids=held.negative_ids,
        tags=[],
        version=1,
        is_public=False,
        created_at="2026-09-27T00:00:00+00:00",
    )


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, UUID | None]]:
    """Both sets are saved on the site; every read is recorded."""
    asked: list[tuple[str, str, UUID | None]] = []
    held = {s.control_set_id: s for s in (_KINASES, _ELSEWHERE)}

    async def one(
        db_session_factory: DBSessionFactory | None,
        control_set_id: str,
        *,
        site_id: str,
        user_id: UUID | None,
    ) -> SavedControls:
        del db_session_factory
        asked.append((control_set_id, site_id, user_id))
        if control_set_id not in held:
            raise UnknownControlSetError(
                control_set_id, [_listed(s) for s in held.values()]
            )
        return held[control_set_id]

    async def every(
        db_session_factory: DBSessionFactory | None,
        *,
        site_id: str,
        user_id: UUID | None,
    ) -> list[SavedControls]:
        del db_session_factory, site_id, user_id
        return [_ELSEWHERE, _KINASES]

    for reader in (experiment, control_sets):
        monkeypatch.setattr(reader, "saved_control_set", one)
    monkeypatch.setattr(saved_control_sets, "saved_control_sets", every)
    return asked


async def test_a_built_set_is_attached_to_the_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def validate(
        site_id: str, gene_ids: list[str], **_kw: Any
    ) -> ResolvedControls:
        del site_id
        return ResolvedControls(valid_ids=gene_ids)

    async def create(
        _session: AsyncSession,
        spec: NewControlSet,
        *,
        user_id: UUID,
        conversation_id: UUID | None,
    ) -> ControlSetResponse:
        del user_id, conversation_id
        return _listed(
            SavedControls(
                control_set_id="cs_123",
                name=spec.name,
                positive_ids=spec.positive_ids,
                negative_ids=spec.negative_ids,
            )
        )

    monkeypatch.setattr(control_sets, "validate_control_ids", validate)
    monkeypatch.setattr(control_sets, "create_control_set", create)
    ctx = detached_lead_context()

    await build_control_set(ctx, name="my controls", positive_ids=["PF3D7_1431500"])

    assert ctx.deps.state.domain.control_sets == [
        NamedControlSet(id="cs_123", name="my controls")
    ]


async def test_a_saved_set_the_researcher_names_is_attached_once(
    saved: list[tuple[str, str, UUID | None]],
) -> None:
    ctx = lead_run_context()

    first = returned(
        await use_control_set(ctx, _KINASES.control_set_id), ControlSetSummary
    )
    await use_control_set(ctx, _KINASES.control_set_id)

    assert (first.control_set_id, first.positive_count, first.negative_count) == (
        _KINASES.control_set_id,
        2,
        1,
    )
    assert ctx.deps.state.domain.control_sets == [_KINASES_NAMED]
    assert saved == 2 * [
        (_KINASES.control_set_id, "plasmodb", ctx.deps.runtime.user_id)
    ]


async def test_a_set_the_site_does_not_hold_is_not_attached(
    saved: list[tuple[str, str, UUID | None]],
) -> None:
    ctx = lead_run_context()
    missing = str(uuid4())

    with pytest.raises(ModelRetry) as refused:
        await use_control_set(ctx, missing)

    assert str(refused.value) == (
        f"control_set_id {missing!r} names no control set saved on this site. "
        f"The saved control sets: {_KINASES.control_set_id} (Kinase controls); "
        f"{_ELSEWHERE.control_set_id} (Two-gene set). list_control_sets names "
        "every saved set."
    )
    assert ctx.deps.state.domain.control_sets == []
    assert len(saved) == 1


async def test_the_check_lists_only_the_sets_attached_to_the_conversation(
    saved: list[tuple[str, str, UUID | None]],
) -> None:
    ctx = agent_run_context(control_sets=[_KINASES_NAMED])

    listed = returned(
        await saved_control_sets.list_control_sets(ctx), list[ControlSetSummary]
    )

    assert [(s.control_set_id, s.name) for s in listed] == [
        (_KINASES.control_set_id, "Kinase controls")
    ]
    assert saved == []


async def test_a_check_with_no_attached_set_lists_none(
    saved: list[tuple[str, str, UUID | None]],
) -> None:
    listed = returned(
        await saved_control_sets.list_control_sets(agent_run_context()),
        list[ControlSetSummary],
    )

    assert listed == []


async def test_the_step_test_refuses_a_set_of_another_conversation(
    saved: list[tuple[str, str, UUID | None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = capture_durable_dispatch(monkeypatch)
    ctx = agent_run_context(control_sets=[_KINASES_NAMED])
    ctx.deps.conversation_id = uuid4()

    with pytest.raises(ModelRetry) as refused:
        await experiment.run_control_tests_on_step(
            ctx, wdk_step_id=_STEP, control_set_id=_ELSEWHERE.control_set_id
        )

    assert str(refused.value) == (
        f"control_set_id '{_ELSEWHERE.control_set_id}' names no control set "
        f"attached to this conversation. The attached control sets: "
        f"{_KINASES.control_set_id} (Kinase controls). A control test runs only "
        "on a control set attached to this conversation."
    )
    assert (dispatch.created, saved) == ([], [])


async def test_the_step_test_with_no_attached_set_states_no_controls(
    saved: list[tuple[str, str, UUID | None]], monkeypatch: pytest.MonkeyPatch
) -> None:
    dispatch = capture_durable_dispatch(monkeypatch)
    ctx = agent_run_context()
    ctx.deps.conversation_id = uuid4()

    with pytest.raises(ModelRetry) as refused:
        await experiment.run_control_tests_on_step(
            ctx, wdk_step_id=_STEP, control_set_id=_ELSEWHERE.control_set_id
        )

    assert str(refused.value) == _NONE_ATTACHED
    assert (dispatch.created, saved) == ([], [])


async def test_the_search_test_refuses_a_set_that_is_not_attached(
    saved: list[tuple[str, str, UUID | None]],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await experiment.run_control_tests_on_search(
            agent_run_context(),
            "GenesWithSignalPeptide",
            {},
            control_set_id=_ELSEWHERE.control_set_id,
        )

    assert str(refused.value) == _NONE_ATTACHED
    assert saved == []


async def test_a_sweep_on_a_set_that_is_not_attached_is_refused() -> None:
    ctx = lead_run_context()
    ctx.deps.state.domain.attach_control_set(_KINASES_NAMED)

    with pytest.raises(ModelRetry) as refused:
        await sweep_can_run(
            ctx,
            reply="I will sweep the SignalP version against your saved controls.",
            wdk_step_id=_STEP,
            control_set_id=_ELSEWHERE.control_set_id,
        )

    assert str(refused.value) == (
        f"control_set_id '{_ELSEWHERE.control_set_id}' names no control set "
        f"attached to this conversation. The attached control sets: "
        f"{_KINASES.control_set_id} (Kinase controls). Save the researcher's ids "
        "with build_control_set, or attach a saved set the researcher names with "
        "use_control_set. Nothing was started and no card was shown."
    )


async def test_a_sweep_on_an_attached_set_passes_the_check() -> None:
    ctx = lead_run_context()
    ctx.deps.state.domain.attach_control_set(_KINASES_NAMED)

    await sweep_can_run(
        ctx,
        reply="I will sweep the SignalP version against your saved controls.",
        wdk_step_id=_STEP,
        control_set_id=_KINASES.control_set_id,
    )

    assert ctx.deps.state.domain.control_sets == [_KINASES_NAMED]


async def test_a_scored_comparison_on_a_set_that_is_not_attached_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[UUID] = []

    async def get(
        _session: AsyncSession, control_set_id: UUID, _user_id: UUID
    ) -> ControlSetResponse:
        read.append(control_set_id)
        return _listed(_ELSEWHERE)

    monkeypatch.setattr(scored_comparison, "get_control_set", get)

    with pytest.raises(ModelRetry) as refused:
        await compare_variants_scored(
            detached_lead_context(),
            [
                VariantSpec(label="a", search_name="SA", parameters={}),
                VariantSpec(label="b", search_name="SB", parameters={}),
            ],
            control_set_id=_ELSEWHERE.control_set_id,
        )

    assert str(refused.value) == (
        f"control_set_id '{_ELSEWHERE.control_set_id}' names no control set "
        "attached to this conversation. The attached control sets: none. Save "
        "the researcher's ids with build_control_set, or attach a saved set the "
        "researcher names with use_control_set."
    )
    assert read == []


def test_the_check_reads_the_sets_the_conversation_holds() -> None:
    state = pipeline_state()
    state.domain.attach_control_set(_KINASES_NAMED)

    scope = verification_scope(lead_deps(state), check_id="call_verify")

    assert scope.control_sets == [_KINASES_NAMED]
