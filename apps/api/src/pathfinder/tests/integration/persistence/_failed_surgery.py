from __future__ import annotations

from uuid import UUID

import pytest

from pathfinder.tests.integration.persistence._fake_eda import (
    FakeEda,
    install_fake_eda,
)
from pathfinder.tests.integration.persistence._thread_surgery import (
    FakePush,
    FourTurns,
    add_analysis_state,
    bind_analysis,
    four_turn_thread,
    gametocyte_filter,
    install_fake_push,
    seed_user,
)

REFUSED = "the surgery could not be written"


async def refuse(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError(REFUSED)


async def thread_with_a_study(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[FourTurns, UUID, FakePush, FakeEda]:
    push = install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    subset = [gametocyte_filter("gametocyte")]
    eda.document("a1b2c3d4", subset)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=subset,
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")
    return thread, user_id, push, eda
