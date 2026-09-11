"""The context factory a durable job's body is tested with."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.tests._support.job_context import job_context


def test_it_carries_the_site_the_caller_names() -> None:
    context = job_context(site_id="toxodb")

    assert context.site_id == "toxodb"
    assert context.strategy_session.site_id == "toxodb"


def test_it_carries_the_user_the_caller_names() -> None:
    user_id = uuid4()

    assert job_context(user_id=user_id).user_id == user_id


def test_each_context_gets_its_own_cancel_event() -> None:
    first = job_context()
    second = job_context()

    first.cancel_event.set()

    assert second.cancel_event.is_set() is False
